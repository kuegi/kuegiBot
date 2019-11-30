import math
import os
import csv

import plotly.graph_objects as go

from typing import List
from datetime import datetime

from market_maker.utils.trading_classes import OrderInterface, Bar, TradingBot, Account, Order,Symbol
from market_maker.utils import log

logger = log.setup_custom_logger('backtest_engine')


class BackTest(OrderInterface):

    def __init__(self, bot: TradingBot, bars: list):
        self.bars: List[Bar] = bars
        self.bot = bot
        self.bot.order_interface = self

        self.market_slipage_percent = 0.15
        self.maker_fee = -0.00025
        self.taker_fee = 0.00075

        self.symbol :Symbol= Symbol(symbol="XBTUSD",isInverse=True, tickSize=0.5,lotSize=1,makerFee=-0.00025,takerFee=0.00075)

        self.account: Account = None
        self.initialEquity = 100000

        self.hh = self.initialEquity
        self.maxDD = 0
        self.max_underwater = 0
        self.underwater = 0

        self.current_bars = []

        self.reset()

    def reset(self):
        self.account = Account()
        self.account.balance = self.initialEquity/self.bars[-1].open
        self.account.open_position = 0
        self.account.equity = self.account.balance
        self.account.usd_equity= self.initialEquity
        self.hh = self.account.equity
        self.maxDD = 0
        self.max_underwater = 0
        self.underwater = 0
        self.bot.reset()

        self.current_bars = []
        for b in self.bars:
            b.did_change = True
        self.bot.init(self.bars[-1:],self.account,self.symbol)

    # implementing OrderInterface

    def send_order(self, order: Order):
        # check if order is val
        if order.amount == 0:
            logger.error("trying to send order without amount")
            return
        logger.debug("added order " + order.id)
        order.tstamp = self.current_bars[0].tstamp
        self.account.open_orders.append(order)

    def update_order(self, order: Order):
        for existing_order in self.account.open_orders:
            if existing_order.id == order.id:
                self.account.open_orders.remove(existing_order)
                self.account.open_orders.append(order)
                logger.debug("updated order " + order.id)
                break

    def cancel_order(self, orderId):
        for order in self.account.open_orders:
            if order.id == orderId:
                order.active = False
                order.final_tstamp = self.current_bars[0].tstamp
                order.final_reason = 'cancel'

                self.account.order_history.append(order)
                self.account.open_orders.remove(order)
                logger.debug("canceled order " + orderId)
                break

    # ----------
    def handle_order_execution(self, order: Order, intrabar):
        amount = order.amount - order.executed_amount
        order.executed_amount = order.amount
        fee = self.taker_fee
        if order.limit_price:
            price = order.limit_price
            fee = self.maker_fee
        elif order.stop_price:
            price = order.stop_price * (1 + math.copysign(self.market_slipage_percent, order.amount) / 100)
        else:
            price = intrabar["open"] * (1 + math.copysign(self.market_slipage_percent, order.amount) / 100)
        price = min(intrabar["high"],
                    max(intrabar["low"], price))  # only prices within the bar. might mean less slipage
        order.executed_price = price
        self.account.open_position += amount
        delta= amount* (price if not self.symbol.isInverse else -1/price)
        self.account.balance -= delta
        self.account.balance -= math.fabs(delta) * fee

        order.active = False
        order.execution_tstamp = intrabar["tstamp"]
        order.final_reason = 'executed'
        self.account.order_history.append(order)
        self.account.open_orders.remove(order)
        logger.debug(
            "executed order " + order.id + " | " + str(self.account.usd_equity) + " " + str(self.account.open_position))

    def handle_open_orders(self, intrabarToCheck) -> bool:
        something_changed = False
        to_execute = []
        for order in self.account.open_orders:
            if order.limit_price is None and order.stop_price is None:
                to_execute.append(order)
                something_changed = True
                continue

            if order.stop_price and not order.stop_triggered:
                if (order.amount > 0 and order.stop_price < intrabarToCheck["high"]) or (
                        order.amount < 0 and order.stop_price > intrabarToCheck["low"]):
                    order.stop_triggered = True
                    something_changed = True
                    if order.limit_price is None:
                        # execute stop market
                        to_execute.append(order)
                    elif ((order.amount > 0 and order.limit_price > intrabarToCheck['close']) or (
                            order.amount < 0 and order.limit_price < intrabarToCheck['close'])):
                        # close below/above limit: got definitly executed
                        to_execute.append(order)

            else:  # means order.limit_price and (order.stop_price is None or order.stop_triggered):
                # check for limit execution
                if (order.amount > 0 and order.limit_price > intrabarToCheck["low"]) or (
                        order.amount < 0 and order.limit_price < intrabarToCheck["high"]):
                    to_execute.append(order)

        for order in to_execute:
            something_changed = True
            self.handle_order_execution(order, intrabarToCheck)
        # update equity = balance + current value of open position
        posValue= self.account.open_position*(intrabarToCheck["close"] if not self.symbol.isInverse else -1/intrabarToCheck["close"])
        self.account.equity = self.account.balance + posValue
        self.account.usd_equity= self.account.equity * (1 if not self.symbol.isInverse else intrabarToCheck["close"])

        self.hh = max(self.hh, self.account.usd_equity)
        dd = self.hh - self.account.usd_equity
        if dd > self.maxDD:
            self.maxDD = max(self.maxDD, dd)

        if self.account.equity < self.hh:
            self.underwater += 1
        else:
            self.underwater = 0
        self.max_underwater = max(self.max_underwater, self.underwater)
        return something_changed

    def run(self):
        self.reset()
        logger.info(
            "starting backtest with " + str(len(self.bars)) + " bars and " + str(self.account.usd_equity) + " equity")
        for i in range(len(self.bars)):
            if i == len(self.bars) - 1:
                continue  # ignore last bar

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
            # self.bot.on_tick(self.current_bars, self.account)
            should_execute = True
            for subbar in reversed(next_bar.subbars):
                # check open orders & update account
                should_execute = self.handle_open_orders(subbar) or should_execute
                forming_bar.add_subbar(subbar)
                if should_execute:
                    self.bot.on_tick(self.current_bars, self.account)
                self.current_bars[1].did_change = False
                should_execute = False

            next_bar.bot_data = forming_bar.bot_data
            for b in self.current_bars:
                b.did_change = False

        if self.account.open_position != 0:
            self.send_order(Order(orderId="endOfTest", amount=-self.account.open_position))
            self.handle_open_orders(self.bars[0].subbars[-1])

        profit = self.account.usd_equity - self.initialEquity
        logger.info("finished | pos: " + str(len(self.bot.position_history)) + " | profit: "
                    + str(int(profit)) + " | maxDD: " + str(
            int(self.maxDD)) + " | rel: " + ("%.2f" % (profit / self.maxDD)) + " | UW days: " + (
                                "%.1f" % (self.max_underwater / 1440)))

        self.write_results_to_files()
        return self

    def prepare_plot(self):

        logger.info("running timelines")
        time = list(map(lambda b: datetime.fromtimestamp(b.tstamp), self.bars))
        open = list(map(lambda b: b.open, self.bars))
        high = list(map(lambda b: b.high, self.bars))
        low = list(map(lambda b: b.low, self.bars))
        close = list(map(lambda b: b.close, self.bars))

        logger.info("creating plot")
        fig = go.Figure(data=[go.Candlestick(x=time, open=open, high=high, low=low, close=close, name="XBTUSD")])

        logger.info("adding bot data")
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

        uid = str(int(datetime.utcnow().timestamp())) + '_' + str(len(self.bars))
        tradesfilename = base + uid + '_trades.csv'
        logger.info("writing" + str(len(self.bot.position_history)) + " trades to file " + tradesfilename)
        with open(tradesfilename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            csv_columns = ['signalTStamp', 'size', 'wantedEntry', 'initialStop', 'openTime', 'openPrice', 'closeTime',
                           'closePrice']
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
                    position.filled_exit
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
                    self.bars[0].close
                ])
