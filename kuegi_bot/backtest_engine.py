import logging
import math
import os
import csv

import plotly.graph_objects as go

from typing import List
from datetime import datetime

from kuegi_bot.bots.trading_bot import TradingBot
from kuegi_bot.utils.trading_classes import OrderInterface, Bar, Account, Order, Symbol, AccountPosition, PositionStatus
from kuegi_bot.utils import log

class SilentLogger(object):

    def info(self, *args, **kwargs):
        pass

    def warn(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

    def debug(self, *args, **kwargs):
        pass


class BackTest(OrderInterface):

    def __init__(self, bot: TradingBot, bars: list, funding:dict= None,symbol:Symbol=None,market_slipage_percent= 0.15):
        self.bars: List[Bar] = bars
        self.funding= funding
        self.firstFunding= 9999999999
        self.lastFunding= 0
        if funding is not None:
            for key in funding.keys():
                self.firstFunding = min(self.firstFunding,key)
                self.lastFunding= max(self.lastFunding,key)

        self.logger= bot.logger
        self.bot = bot
        self.bot.prepare(SilentLogger(),self)

        self.market_slipage_percent = market_slipage_percent
        self.maker_fee = -0.00025
        self.taker_fee = 0.00075

        if symbol is not None:
            self.symbol= symbol
        else:
            self.symbol: Symbol = Symbol(symbol="XBTUSD", isInverse=True, tickSize=0.5, lotSize=1, makerFee=-0.00025,
                                         takerFee=0.00075)

        self.account: Account = None
        self.initialEquity = 100  # BTC

        self.hh = self.initialEquity
        self.maxDD = 0
        self.max_underwater = 0
        self.underwater = 0
        self.maxExposure= 0
        self.lastHHPosition = 0

        self.current_bars: List[Bar] = []

        self.reset()

    def reset(self):
        self.account = Account()
        self.account.open_position.walletBalance = self.initialEquity
        self.account.open_position.quantity = 0
        self.account.equity = self.account.open_position.walletBalance
        self.account.usd_equity = self.initialEquity * self.bars[-1].open
        self.hh = self.initialEquity
        self.maxDD = 0
        self.max_underwater = 0
        self.lastHHPosition = 0
        self.underwater = 0
        self.maxExposure= 0
        self.bot.reset()

        self.current_bars = []
        for b in self.bars:
            b.did_change = True
        self.bot.init(self.bars[-self.bot.min_bars_needed():], self.account, self.symbol, None)

    # implementing OrderInterface

    def send_order(self, order: Order):
        # check if order is val
        if order.amount == 0:
            self.logger.error("trying to send order without amount")
            return
        self.logger.debug("added order %s" % (order.print_info()))

        order.tstamp = self.current_bars[0].tstamp
        if order not in self.account.open_orders:  # bot might add it himself temporarily.
            self.account.open_orders.append(order)

    def update_order(self, order: Order):
        for existing_order in self.account.open_orders:
            if existing_order.id == order.id:
                self.account.open_orders.remove(existing_order)
                self.account.open_orders.append(order)
                self.logger.debug("updated order %s" % (order.print_info()))
                break

    def cancel_order(self, order_to_cancel):
        for order in self.account.open_orders:
            if order.id == order_to_cancel.id:
                order.active = False
                order.final_tstamp = self.current_bars[0].tstamp
                order.final_reason = 'cancel'

                self.account.order_history.append(order)
                self.account.open_orders.remove(order)
                self.logger.debug("canceled order " + order_to_cancel.id)
                break

    # ----------
    def handle_order_execution(self, order: Order, intrabar: Bar):
        amount = order.amount - order.executed_amount
        order.executed_amount = order.amount
        fee = self.taker_fee
        if order.limit_price:
            price = order.limit_price
            fee = self.maker_fee
        elif order.stop_price:
            price = int(order.stop_price * (1 + math.copysign(self.market_slipage_percent,
                                                              order.amount) / 100) / self.symbol.tickSize) * self.symbol.tickSize
        else:
            price = intrabar.open * (1 + math.copysign(self.market_slipage_percent, order.amount) / 100)
        price = min(intrabar.high,
                    max(intrabar.low, price))  # only prices within the bar. might mean less slipage
        order.executed_price = price
        oldAmount= self.account.open_position.quantity
        if oldAmount != 0:
            oldavgentry= self.account.open_position.avgEntryPrice
            if oldAmount * amount > 0 :
                self.account.open_position.avgEntryPrice = (oldavgentry*oldAmount + price*amount)/(oldAmount+amount)
            if oldAmount*amount < 0:
                if abs(oldAmount) < abs(amount):
                    profit= oldAmount * ((price-oldavgentry) if not self.symbol.isInverse else (-1 / price + 1/oldavgentry))
                    self.account.open_position.walletBalance += profit
                    #close current, open new
                    self.account.open_position.avgEntryPrice= price
                else:
                    #closes the position by "-amount" cause amount is the side and direction of the close
                    profit = -amount * (
                        (price - oldavgentry) if not self.symbol.isInverse else (-1 / price + 1 / oldavgentry))
                    self.account.open_position.walletBalance += profit
        else:
            self.account.open_position.avgEntryPrice = price
        self.account.open_position.quantity += amount
        volume = amount * (price if not self.symbol.isInverse else -1 / price)
        self.account.open_position.walletBalance -= math.fabs(volume) * fee

        order.active = False
        order.execution_tstamp = intrabar.tstamp
        order.final_reason = 'executed'
        self.account.order_history.append(order)
        self.account.open_orders.remove(order)
        self.logger.debug(
            "executed order %s | %.0f %.2f | %.2f@ %.1f" % (
            order.id, self.account.usd_equity, self.account.open_position.quantity, order.executed_amount,
            order.executed_price))

    def orderKeyForSort(self,order):
        if order.stop_price is None and order.limit_price is None:
            return 0
        if order.stop_price is not None:
            return abs(self.current_bars[0].close - order.stop_price)
        else: # limit -> bigger numbers to be sorted after the stops
            return abs(self.current_bars[0].close - order.limit_price)+self.current_bars[0].close

    def handle_open_orders(self, intrabarToCheck: Bar) -> bool:
        something_changed = False
        another_round= True
        while another_round:
            another_round= False
            should_execute= False
            for order in sorted(self.account.open_orders, key=self.orderKeyForSort):
                if order.limit_price is None and order.stop_price is None:
                    should_execute= True
                elif order.stop_price and not order.stop_triggered:
                    if (order.amount > 0 and order.stop_price < intrabarToCheck.high) or (
                            order.amount < 0 and order.stop_price > intrabarToCheck.low):
                        order.stop_triggered = True
                        something_changed = True
                        if order.limit_price is None:
                            # execute stop market
                            should_execute= True
                        elif ((order.amount > 0 and order.limit_price > intrabarToCheck.close) or (
                                order.amount < 0 and order.limit_price < intrabarToCheck.close)):
                            # close below/above limit: got definitly executed
                            should_execute= True
                else:  # means order.limit_price and (order.stop_price is None or order.stop_triggered):
                    # check for limit execution
                    if (order.amount > 0 and order.limit_price > intrabarToCheck.low) or (
                            order.amount < 0 and order.limit_price < intrabarToCheck.high):
                        should_execute= True

                if should_execute:
                    self.handle_order_execution(order, intrabarToCheck)
                    self.bot.on_tick(self.current_bars, self.account)
                    another_round= True
                    something_changed= True
                    break


        # update equity = balance + current value of open position
        avgEntry= self.account.open_position.avgEntryPrice
        if avgEntry != 0:
            posValue = self.account.open_position.quantity * (
                (intrabarToCheck.close-avgEntry) if not self.symbol.isInverse else (-1 / intrabarToCheck.close + 1/avgEntry))
        else:
            posValue= 0
        self.account.equity = self.account.open_position.walletBalance # + posValue # for backtest: ignore equity for better charts
        self.account.usd_equity = self.account.equity * intrabarToCheck.close

        self.update_stats()
        return something_changed

    def update_stats(self):

        if math.fabs(self.account.open_position.quantity) < 1 or self.lastHHPosition * self.account.open_position.quantity < 0:
            self.hh = max(self.hh, self.account.equity)  # only update HH on closed positions, no open equity
            self.lastHHPosition = self.account.open_position.quantity
        dd = self.hh - self.account.equity
        if dd > self.maxDD:
            self.maxDD = max(self.maxDD, dd)

        exposure= abs(self.account.open_position.quantity)* (1/self.current_bars[0].close if self.symbol.isInverse else self.current_bars[0].close)
        self.maxExposure= max(self.maxExposure,exposure)
        if self.account.equity < self.hh:
            self.underwater += 1
        else:
            self.underwater = 0
        self.max_underwater = max(self.max_underwater, self.underwater)

    def do_funding(self):
        funding = 0
        bar = self.current_bars[0]
        if self.funding is not None and self.firstFunding <= bar.tstamp <= self.lastFunding:
            if bar.tstamp in self.funding:
                funding = self.funding[bar.tstamp]
        else:
            dt = datetime.fromtimestamp(bar.tstamp)
            if dt.hour == 0 or dt.hour == 8 or dt.hour == 16:
                funding = 0.0001

        if funding != 0 and self.account.open_position.quantity != 0:
            self.account.open_position.walletBalance -= funding * self.account.open_position.quantity / bar.open


    def run(self):
        self.reset()
        self.logger.info(
            "starting backtest with " + str(len(self.bars)) + " bars and " + str(self.account.equity) + " equity")
        for i in range(self.bot.min_bars_needed(),len(self.bars)):
            if i == len(self.bars) - 1 or i < self.bot.min_bars_needed():
                continue  # ignore last bar and first x

            # slice bars. TODO: also slice intrabar to simulate tick
            self.current_bars = self.bars[-(i + 1):]
            # add one bar with 1 tick on open to show to bot that the old one is closed
            next_bar = self.bars[-i - 2]
            forming_bar = Bar(tstamp=next_bar.tstamp, open=next_bar.open, high=next_bar.open,
                              low=next_bar.open, close=next_bar.open,
                              volume=0, subbars=[])
            self.current_bars.insert(0, forming_bar)
            self.current_bars[0].did_change = True
            self.current_bars[1].did_change = True

            self.do_funding()
            # self.bot.on_tick(self.current_bars, self.account)
            for subbar in reversed(next_bar.subbars):
                # check open orders & update account
                self.handle_open_orders(subbar)
                open= len(self.account.open_orders)
                forming_bar.add_subbar(subbar)
                self.bot.on_tick(self.current_bars, self.account)
                if open != len(self.account.open_orders):
                    self.handle_open_orders(subbar) # got new ones
                self.current_bars[1].did_change = False

            next_bar.bot_data = forming_bar.bot_data
            for b in self.current_bars:
                if b.did_change:
                    b.did_change = False
                else:
                    break # no need to go further

        if abs(self.account.open_position.quantity) > self.symbol.lotSize/10:
            self.send_order(Order(orderId="endOfTest", amount=-self.account.open_position.quantity))
            self.handle_open_orders(self.bars[0].subbars[-1])

        if len(self.bot.position_history) > 0:
            daysInPos = 0
            maxDays= 0
            minDays= self.bot.position_history[0].daysInPos() if len(self.bot.position_history) > 0 else 0
            for pos in self.bot.position_history:
                if pos.status != PositionStatus.CLOSED:
                    continue
                if pos.exit_tstamp is None:
                    pos.exit_tstamp = self.bars[0].tstamp
                daysInPos += pos.daysInPos()
                maxDays= max(maxDays,pos.daysInPos())
                minDays= min(minDays,pos.daysInPos())
            daysInPos /= len(self.bot.position_history)

            profit = self.account.equity - self.initialEquity
            uw_updates_per_day = 1440  # every minute
            total_days= (self.bars[0].tstamp - self.bars[-1].tstamp)/(60*60*24)
            rel= profit / (self.maxDD if self.maxDD > 0 else 1)
            rel_per_year = rel / (total_days/365)
            self.logger.info("finished | closed pos: " + str(len(self.bot.position_history))
                        + " | open pos: " + str(len(self.bot.open_positions))
                        + " | profit: " + ("%.2f" % (100 * profit / self.initialEquity))
                        + " | HH: " + ("%.2f" % (100 * (self.hh / self.initialEquity - 1)))
                        + " | maxDD: " + ("%.2f" % (100 * self.maxDD / self.initialEquity))
                        + " | maxExp: " + ("%.2f" % (self.maxExposure / self.initialEquity))
                        + " | rel: " + ("%.2f" % (rel_per_year))
                        + " | UW days: " + ("%.1f" % (self.max_underwater / uw_updates_per_day))
                        + " | pos days: " + ("%.1f/%.1f/%.1f" % (minDays,daysInPos,maxDays))
                        )
        else:
            self.logger.info("finished with no trades")

        #self.write_results_to_files()
        return self

    def prepare_plot(self):
        barcenter= (self.bars[0].tstamp - self.bars[1].tstamp)/2
        self.logger.info("running timelines")
        time = list(map(lambda b: datetime.fromtimestamp(b.tstamp+barcenter), self.bars))
        open = list(map(lambda b: b.open, self.bars))
        high = list(map(lambda b: b.high, self.bars))
        low = list(map(lambda b: b.low, self.bars))
        close = list(map(lambda b: b.close, self.bars))

        self.logger.info("creating plot")
        fig = go.Figure(data=[go.Candlestick(x=time, open=open, high=high, low=low, close=close, name=self.symbol.symbol)])

        self.logger.info("adding bot data")
        self.bot.add_to_plot(fig, self.bars, time)

        fig.update_layout(xaxis_rangeslider_visible=False)
        return fig

    def write_results_to_files(self):
        # positions
        base = 'results/' + self.bot.uid() + '/'
        try:
            os.makedirs(base)
        except Exception:
            pass

        uid = str(int(datetime.utcnow().timestamp())) + '_' + str(len(self.bot.position_history))
        tradesfilename = base + uid + '_trades.csv'
        self.logger.info("writing" + str(len(self.bot.position_history)) + " trades to file " + tradesfilename)
        with open(tradesfilename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            csv_columns = ['signalTStamp', 'size', 'wantedEntry', 'initialStop', 'openTime', 'openPrice', 'closeTime',
                           'closePrice', 'equityOnExit']
            writer.writerow(csv_columns)
            for position in self.bot.position_history:
                writer.writerow([
                    datetime.fromtimestamp(position.signal_tstamp).isoformat(),
                    position.amount,
                    position.wanted_entry,
                    position.initial_stop,
                    datetime.fromtimestamp(position.entry_tstamp).isoformat(),
                    position.filled_entry,
                    datetime.fromtimestamp(position.exit_tstamp).isoformat(),
                    position.filled_exit,
                    position.exit_equity
                ])
            for position in self.bot.open_positions.values():
                writer.writerow([
                    datetime.fromtimestamp(position.signal_tstamp).isoformat(),
                    position.amount,
                    position.wanted_entry,
                    position.initial_stop,
                    datetime.fromtimestamp(position.entry_tstamp).isoformat(),
                    position.filled_entry,
                    "",
                    self.bars[0].close,
                    position.exit_equity
                ])
