import logging
import math
#import statistics
import os
import csv

import plotly.graph_objects as go

#import plotly.express as px
from typing import List
from datetime import datetime

from kuegi_bot.bots.trading_bot import TradingBot, PositionDirection
from kuegi_bot.utils.trading_classes import OrderInterface, Bar, Account, Order, Symbol, AccountPosition, \
    PositionStatus, OrderType
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

    def __init__(self, bot: TradingBot, bars: list, funding: dict = None, symbol: Symbol = None,
                 market_slipage_percent=0.15):
        self.bars: List[Bar] = bars
        self.funding = funding
        self.firstFunding = 9999999999
        self.lastFunding = 0
        if funding is not None:
            for key in funding.keys():
                self.firstFunding = min(self.firstFunding, key)
                self.lastFunding = max(self.lastFunding, key)
        self.handles_executions = True
        self.logger = bot.logger
        self.bot = bot
        self.bot.prepare(SilentLogger(), self)

        self.market_slipage_percent = market_slipage_percent
        self.maker_fee = -0.00025
        self.taker_fee = 0.00075

        if symbol is not None:
            self.symbol = symbol
        else:
            self.symbol: Symbol = Symbol(symbol="XBTUSD", isInverse=True, tickSize=0.5, lotSize=1, makerFee=-0.00025,
                                         takerFee=0.00075)

        self.account: Account = None
        self.initialEquity = 100  # BTC

        self.hh = self.initialEquity
        self.maxDD = 0
        self.max_underwater = 0
        self.underwater = 0
        self.maxExposure = 0
        self.lastHHPosition = 0

        self.current_bars: List[Bar] = []
        self.unrealized_equity = 0
        self.total_equity_vec = []
        self.equity_vec = []
        self.unrealized_equity_vec = []
        self.hh_vec = []
        self.ll_vec = []
        self.dd_vec = []
        self.maxDD_vec = []

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
        self.maxExposure = 0
        self.unrealized_equity=0
        self.total_equity_vec = []
        self.equity_vec = []
        self.unrealized_equity_vec = []
        self.hh_vec = []
        self.ll_vec = []
        self.dd_vec = []

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
        [posId, order_type] = TradingBot.position_id_and_type_from_order_id(order.id)
        if order_type == OrderType.ENTRY:
            [unused, direction] = TradingBot.split_pos_Id(posId)
            if direction == PositionDirection.LONG and order.amount < 0:
                self.logger.error("sending long entry with negative amount")
            if direction == PositionDirection.SHORT and order.amount > 0:
                self.logger.error("sending short entry with positive amount")

        self.logger.debug("added order %s" % (order.print_info()))

        order.tstamp = self.current_bars[0].tstamp
        if order not in self.account.open_orders:  # bot might add it himself temporarily.
            self.account.open_orders.append(order)

    def update_order(self, order: Order):
        for existing_order in self.account.open_orders:
            if existing_order.id == order.id:
                self.account.open_orders.remove(existing_order)
                self.account.open_orders.append(order)
                order.tstamp = self.current_bars[0].last_tick_tstamp
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
    def handle_order_execution(self, order: Order, intrabar: Bar, force_taker=False):
        amount = order.amount - order.executed_amount
        order.executed_amount = order.amount
        fee = self.taker_fee
        if order.limit_price and not force_taker:
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
        oldAmount = self.account.open_position.quantity
        if oldAmount != 0:
            oldavgentry = self.account.open_position.avgEntryPrice
            if oldAmount * amount > 0:
                self.account.open_position.avgEntryPrice = (oldavgentry * oldAmount + price * amount) / (
                            oldAmount + amount)
            if oldAmount * amount < 0:
                if abs(oldAmount) < abs(amount):
                    profit = oldAmount * (
                        (price - oldavgentry) if not self.symbol.isInverse else (-1 / price + 1 / oldavgentry))
                    self.account.open_position.walletBalance += profit
                    # close current, open new
                    self.account.open_position.avgEntryPrice = price
                else:
                    # closes the position by "-amount" cause amount is the side and direction of the close
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

        self.bot.on_execution(order_id=order.id, amount=amount, executed_price=price, tstamp=intrabar.tstamp)
        self.account.order_history.append(order)
        self.account.open_orders.remove(order)
        self.logger.debug(
            "executed order %s | %.0f %.2f | %.2f@ %.1f" % (
                order.id, self.account.usd_equity, self.account.open_position.quantity, order.executed_amount,
                order.executed_price))

    def orderKeyForSort(self, order):
        if order.stop_price is None and order.limit_price is None:
            return 0
        # sort buys after sells (higher number) when bar is falling
        long_fac = 1 if self.bars[0].close > self.bars[0].open else 2
        short_fac = 1 if self.bars[0].close < self.bars[0].open else 2
        if order.stop_price is not None:
            if order.amount > 0:
                return order.stop_price
            else:
                return -order.stop_price
        else:  # limit -> bigger numbers to be sorted after the stops
            if order.amount > 0:
                return (self.bars[0].close + self.bars[0].close - order.limit_price) + self.bars[0].close * long_fac
            else:
                return order.limit_price + self.bars[0].close * short_fac

    def check_executions(self, intrabar_to_check: Bar, only_on_close):
        another_round = True
        did_something = False
        allowed_order_ids = None
        if not only_on_close:
            allowed_order_ids = set(map(lambda o: o.id, self.account.open_orders))
        loopbreak = 0
        while another_round:
            if loopbreak > 100:
                print("got loop in backtest execution")
                break
            loopbreak += 1
            another_round = False
            should_execute = False
            for order in sorted(self.account.open_orders, key=self.orderKeyForSort):
                if allowed_order_ids is not None and order.id not in allowed_order_ids:
                    continue
                force_taker = False
                execute_order_only_on_close = only_on_close
                if order.tstamp > intrabar_to_check.tstamp:
                    execute_order_only_on_close = True  # was changed during execution on this bar, might have changed the price. only execute if close triggered it
                if order.limit_price is None and order.stop_price is None:
                    should_execute = True
                elif order.stop_price and not order.stop_triggered:
                    if (order.amount > 0 and order.stop_price < intrabar_to_check.high) or (
                            order.amount < 0 and order.stop_price > intrabar_to_check.low):
                        order.stop_triggered = True
                        something_changed = True
                        if order.limit_price is None:
                            # execute stop market
                            should_execute = True
                            if only_on_close:  # order just came in and executed right away: execution on the worst price cause can't assume anything better
                                order.stop_price = intrabar_to_check.low if order.amount < 0 else intrabar_to_check.high

                        elif ((order.amount > 0 and order.limit_price > intrabar_to_check.close) or (
                                order.amount < 0 and order.limit_price < intrabar_to_check.close)):
                            # close below/above limit: got definitly executed
                            should_execute = True
                            force_taker = True  # need to assume taker.
                else:  # means order.limit_price and (order.stop_price is None or order.stop_triggered):
                    # check for limit execution
                    ref = intrabar_to_check.low if order.amount > 0 else intrabar_to_check.high
                    if execute_order_only_on_close:
                        ref = intrabar_to_check.close
                        force_taker = True  # need to assume taker.
                    if (order.amount > 0 and order.limit_price > ref) or (
                            order.amount < 0 and order.limit_price < ref):
                        should_execute = True

                if should_execute:
                    self.handle_order_execution(order, intrabar_to_check, force_taker=force_taker)
                    self.bot.on_tick(self.current_bars, self.account)
                    another_round = True
                    did_something = True
                    break
        return did_something

    def handle_subbar(self, intrabarToCheck: Bar):
        self.current_bars[0].add_subbar(intrabarToCheck)  # so bot knows about the current intrabar
        # first the ones that are there at the beginning
        something_changed_on_existing_orders = self.check_executions(intrabarToCheck, False)
        something_changed_on_second_pass = self.check_executions(intrabarToCheck, True)
        # then the new ones with updated bar

        if not something_changed_on_existing_orders and not something_changed_on_second_pass:  # no execution happened -> execute on tick now
            self.bot.on_tick(self.current_bars, self.account)

        # update equity = balance + current value of open position
        avgEntry = self.account.open_position.avgEntryPrice
        if avgEntry != 0:
            posValue = self.account.open_position.quantity * (
                (intrabarToCheck.close - avgEntry) if not self.symbol.isInverse else (
                            -1 / intrabarToCheck.close + 1 / avgEntry))
        else:
            posValue = 0
        self.account.equity = self.account.open_position.walletBalance  # + posValue # for backtest: ignore equity for better charts
        self.account.usd_equity = self.account.equity * intrabarToCheck.close
        self.unrealized_equity = posValue

        self.update_stats()

    def update_stats(self):

        if math.fabs( # TODO: why?
                self.account.open_position.quantity) < 1 or self.lastHHPosition * self.account.open_position.quantity < 0:
            self.hh = max(self.hh, self.account.equity)  # only update HH on closed positions, no open equity
            self.lastHHPosition = self.account.open_position.quantity
        dd = self.hh - self.account.equity
        if dd > self.maxDD:
            self.maxDD = dd

        exposure = abs(self.account.open_position.quantity) * (
            1 / self.current_bars[0].close if self.symbol.isInverse else self.current_bars[0].close)
        self.maxExposure = max(self.maxExposure, exposure)
        if self.account.equity < self.hh:
            self.underwater += 1
        else:
            self.underwater = 0
        self.max_underwater = max(self.max_underwater, self.underwater)

    def write_plot_data(self):
        avgEntry = self.account.open_position.avgEntryPrice
        if avgEntry != 0:
            unrealized_equity = self.account.open_position.quantity * (
                (self.current_bars[0].close - avgEntry) if not self.symbol.isInverse else (
                        -1 / self.current_bars[0].close + 1 / avgEntry))
        else:
            unrealized_equity = 0

        self.equity_vec.append(self.account.equity)
        self.unrealized_equity_vec.append(unrealized_equity)
        self.total_equity_vec.append(self.account.equity + unrealized_equity)
        self.hh_vec.append(self.equity_vec[0] if len(self.hh_vec) == 0 else
                           (self.equity_vec[-1] if self.equity_vec[-1] > self.hh_vec[-1] else self.hh_vec[-1]))
        self.ll_vec.append(self.equity_vec[0] if len(self.ll_vec) == 0 else
                           (self.equity_vec[-1] if self.equity_vec[-1] < self.ll_vec[-1] else self.ll_vec[-1]))
        self.dd_vec.append(-(self.hh_vec[-1] - self.equity_vec[-1]))
        self.maxDD_vec.append(self.dd_vec[0] if len(self.maxDD_vec) == 0 else
                              (self.dd_vec[-1] if self.dd_vec[-1] < self.maxDD_vec[-1] else self.maxDD_vec[-1]))

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
        for i in range(0, self.bot.min_bars_needed()):
            self.write_plot_data()
        for i in range(self.bot.min_bars_needed(), len(self.bars)):
            if i == len(self.bars) - 1:# or i < self.bot.min_bars_needed():
                self.write_plot_data()
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
            self.bot.on_tick(self.current_bars, self.account)  # tick on new bar open cause many strats act on that
            self.write_plot_data()
            for subbar in reversed(next_bar.subbars):
                # check open orders & update account
                # ensure correct last tick (must not be the same as tstamp)
                if subbar.last_tick_tstamp < subbar.tstamp + 59:
                    subbar.last_tick_tstamp = subbar.tstamp + 59
                self.handle_subbar(subbar)
                self.current_bars[1].did_change = False

            next_bar.bot_data = forming_bar.bot_data
            for b in self.current_bars:
                if b.did_change:
                    b.did_change = False
                else:
                    break  # no need to go further

        if abs(self.account.open_position.quantity) > self.symbol.lotSize / 10:
            self.send_order(Order(orderId="endOfTest", amount=-self.account.open_position.quantity))
            self.handle_subbar(self.bars[0].subbars[-1])

        if len(self.bot.position_history) > 0:
            daysInPos = 0
            maxDays = 0
            minDays = self.bot.position_history[0].daysInPos() if len(self.bot.position_history) > 0 else 0
            for pos in self.bot.position_history:
                if pos.status != PositionStatus.CLOSED:
                    continue
                if pos.exit_tstamp is None:
                    pos.exit_tstamp = self.bars[0].tstamp
                daysInPos += pos.daysInPos()
                maxDays = max(maxDays, pos.daysInPos())
                minDays = min(minDays, pos.daysInPos())
            daysInPos /= len(self.bot.position_history)

            profit = self.account.equity - self.initialEquity
            uw_updates_per_day = 1440  # every minute
            total_days = (self.bars[0].tstamp - self.bars[-1].tstamp) / (60 * 60 * 24)
            #average_daily_return = profit / total_days
            #rel = profit / (-self.maxDD_vec[-1] if profit > 0 else 0)
            rel = self.hh_vec[-1] / (-self.maxDD_vec[-1] if (-self.maxDD_vec[-1]) != 0 else 1)
            rel_per_year = rel / (total_days / 365) if rel >0 else 0
            nmb = 0
            for position in self.bot.open_positions.values():
                if position.status == PositionStatus.OPEN:
                    nmb += 1
            #std_eq = statistics.stdev(self.equity_vec)

            self.logger.info("trades: " + str(len(self.bot.position_history))
                             + " | open pos: " + str(nmb)
                             + " | profit: " + ("%.1f" % (100 * profit / self.initialEquity)) + "%"
                             + " | unreal.: " + ("%.1f"% (100 * self.unrealized_equity_vec[-1] / self.initialEquity)) + "%"
                             #+ " | HH: " + ("%.1f" % (100 * (self.hh_vec[-1] / self.initialEquity - 1))) + "%"
                             + " | maxDD: " + ("%.1f" % (100 * self.maxDD_vec[-1] / self.initialEquity)) + "%"
                             + " | maxExp: " + ("%.1f" % (self.maxExposure / self.initialEquity)) + "%"
                             + " | rel: " + ("%.2f" % (rel_per_year))
                             + " | UW days: " + ("%.1f" % (self.max_underwater / uw_updates_per_day))
                             #+ " | pos days: " + ("%.1f/%.1f/%.1f" % (minDays, daysInPos, maxDays))
                             )
        else:
            self.logger.info("finished with no trades")

        return self

    def plot_statistics_abs(self):
        self.logger.info("creating statistics plot with absolut number")
        barcenter = (self.bars[0].tstamp - self.bars[1].tstamp) / 2
        time = list(map(lambda b: datetime.fromtimestamp(b.tstamp + barcenter), self.bars))

        #self.unrealized_equity_vec.reverse()
        self.total_equity_vec.reverse()
        #self.hh_vec.reverse()
        #self.ll_vec.reverse()
        self.equity_vec.reverse()
        self.maxDD_vec.reverse()
        self.dd_vec.reverse()

        sub_data ={
            #'unrealized equity':self.unrealized_equity_vec,
            'total equity':self.total_equity_vec,
            #'HH':self.hh_vec,
            #'LL':self.ll_vec,
            'realized equity':self.equity_vec,
            'maxDD':self.maxDD_vec,
            'DD':self.dd_vec,
        }

        colors = {
            # "unrealized equity": 'black',
            "total equity": 'lightblue',
            #"HH": 'lightgreen',
            # "LL": 'magenta',
            "realized equity": 'blue',
            "maxDD": 'red',
            "DD": 'orange'
        }

        data_abs = []
        for key in sub_data.keys():
            data_abs.append(
                go.Scatter(x=time, y=sub_data.get(key), name=(key + ': %.1f' % sub_data.get(key)[0]),
                           line=dict(color=colors[key], width=2))
            )
        fig_abs = go.Figure(data = data_abs)
        fig_abs.show()

    def prepare_plot(self):
        barcenter = (self.bars[0].tstamp - self.bars[1].tstamp) / 2
        self.logger.info("running timelines")
        time = list(map(lambda b: datetime.fromtimestamp(b.tstamp + barcenter), self.bars))
        open = list(map(lambda b: b.open, self.bars))
        high = list(map(lambda b: b.high, self.bars))
        low = list(map(lambda b: b.low, self.bars))
        close = list(map(lambda b: b.close, self.bars))

        self.logger.info("creating plot")
        fig = go.Figure(
            data=[go.Candlestick(x=time, open=open, high=high, low=low, close=close, name=self.symbol.symbol)])

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
                    position.max_filled_amount,
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
                    position.max_filled_amount,
                    position.wanted_entry,
                    position.initial_stop,
                    datetime.fromtimestamp(position.entry_tstamp).isoformat(),
                    position.filled_entry,
                    "",
                    self.bars[0].close,
                    position.exit_equity
                ])
