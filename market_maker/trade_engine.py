import math
import sys
import os
import atexit
import signal
import csv
from typing import List
from time import sleep
from os.path import getmtime
from market_maker.settings import settings
from market_maker.utils import log, constants, errors

from market_maker.market_maker import ExchangeInterface

logger = log.setup_custom_logger('trade_engine')

watched_files_mtimes = [(f, getmtime(f)) for f in settings.WATCHED_FILES]


class Bar:
    def __init__(self, tstamp: int, open: float, high: float, low: float, close: float, volume: float, subbars: list):
        self.tstamp:int = tstamp
        self.open:float = open
        self.high:float = high
        self.low:float = low
        self.close:float = close
        self.volume:float = volume
        self.subbars:list = subbars
        self.bot_data = { "indicators":{} }
        self.did_change:bool = True


class Account:
    def __init__(self):
        self.balance = 0
        self.equity = 0
        self.open_position = 0
        self.open_orders = []
        self.order_history = []


class Order:
    def __init__(self, orderId= None, stop= None, limit= None, amount=0):
        self.id = orderId
        self.stop_price = stop
        self.limit_price = limit
        self.amount = amount
        self.executed_amount = 0
        self.executed_price = None
        self.active = True
        self.stop_triggered = False
        self.tstamp= 0
        self.execution_tstamp= 0


class OrderInterface:
    def send_order(self, order: Order):
        pass

    def update_order(self, order: Order):
        pass

    def cancel_order(self, orderId):
        pass

class Position:
    def __init__(self, id, entry, stop, amount, tstamp):
        self.id= id
        self.signal_tstamp= tstamp
        self.status= "pending"
        self.wanted_entry= entry
        self.initial_stop= stop
        self.amount= amount
        self.filled_entry:float= None
        self.filled_exit:float= None
        self.entry_tstamp=0
        self.exit_tstamp= 0

class TradingBot:
    def __init__(self):
        self.order_interface: OrderInterface= None
        self.last_time= 0
        self.open_positions = {}
        self.known_order_history = 0
        self.position_history= []

    def uid(self)-> str:
        return "GenericBot"

    def on_tick(self, bars: list, account: Account):
        """checks price and levels to manage current orders and set new ones"""
        self.prep_bars(bars)
        self.manage_open_orders(bars, account)
        self.open_orders(bars, account)

    def prep_bars(self,bars:list):
        pass

    ###
    # Order Management
    ###

    def manage_open_orders(self, bars: list, account: Account):
        pass

    def open_orders(self, bars: list, account: Account):
        # new_bar= check_for_new_bar(bars)
        pass

    def check_for_new_bar(self, bars: List[Bar]) -> bool:
        """checks if this tick started a new bar.
        only works on the first call of a bar"""
        if bars[0].tstamp != self.last_time:
            self.last_time= bars[0].tstamp
            return True
        else:
            return False



class BackTest(OrderInterface):

    def __init__(self, bot: TradingBot, bars: list):
        self.bars :List[Bar] = bars
        self.bot = bot
        self.bot.order_interface = self

        self.market_slipage_percent = 0.15
        self.maker_fee = -0.00025
        self.taker_fee = 0.00075

        self.account:Account
        self.initialEquity= 100000

        self.hh = self.initialEquity
        self.maxDD = 0
        self.max_underwater = 0
        self.underwater = 0

        self.reset()

    def reset(self):
        self.account = Account()
        self.account.balance = self.initialEquity
        self.account.open_position = 0
        self.account.equity = self.account.balance
        self.hh= self.account.equity
        self.maxDD= 0
        self.max_underwater= 0
        self.underwater= 0

        self.current_bars = []
        for b in self.bars:
            b.did_change= True
    # implementing OrderInterface

    def send_order(self, order: Order):
        # check if order is val
        if order.amount == 0:
            logger.error("trying to send order without amount")
            return
        logger.debug("added order "+order.id)
        order.tstamp = self.current_bars[0].tstamp
        self.account.open_orders.append(order)

    def update_order(self, order: Order):
        for existing_order in self.account.open_orders:
            if existing_order.id == order.id:
                self.account.open_orders.remove(existing_order)
                self.account.open_orders.append(order)
                logger.debug("updated order "+order.id)
                break


    def cancel_order(self, orderId):
        for order in self.account.open_orders:
            if order.id == orderId:
                order.active = False
                order.final_tstamp = self.current_bars[0].tstamp
                order.final_reason = 'cancel'

                self.account.order_history.append(order)
                self.account.open_orders.remove(order)
                logger.debug("canceled order "+orderId)
                break

    # ----------
    def handle_order_execution(self, order: Order, bar: Bar):
        amount = order.amount - order.executed_amount
        order.executed_amount = order.amount
        fee= self.taker_fee
        if order.limit_price:
            price = order.limit_price
            fee= self.maker_fee
        elif order.stop_price:
            price = order.stop_price *(1 + math.copysign(self.market_slipage_percent, order.amount)/100)
        else:
            price = bar.open *(1 + math.copysign(self.market_slipage_percent, order.amount)/100)
        price = min(bar.high, max(bar.low, price))  # only prices within the bar. might mean less slipage
        order.executed_price= price
        self.account.open_position += amount
        self.account.balance -= amount * price
        self.account.balance -= amount*price*fee

        order.active = False
        order.execution_tstamp = bar.tstamp
        order.final_reason = 'executed'
        self.account.order_history.append(order)
        self.account.open_orders.remove(order)
        logger.debug("executed order " + order.id+" | "+str(self.account.equity)+" "+str(self.account.open_position))

    def handle_open_orders(self, barsSinceLastCheck: List[Bar]):
        for order in self.account.open_orders:
            if order.limit_price is None and order.stop_price is None:
                self.handle_order_execution(order, barsSinceLastCheck[0])
                continue

            for bar in barsSinceLastCheck:
                if order.stop_price and not order.stop_triggered:
                    if (order.amount > 0 and order.stop_price < bar.high) or (
                            order.amount < 0 and order.stop_price > bar.low):
                        order.stop_triggered = True
                        if order.limit_price is None:
                            # execute stop market
                            self.handle_order_execution(order, bar)
                        else:
                            # check if stop limit was filled after stop was triggered
                            reached_trigger = False
                            filled_limit = False
                            for sub in bar.subbars:
                                if reached_trigger:
                                    if ((order.amount > 0 and order.limit_price > sub['low']) or (
                                            order.amount < 0 and order.limit_price < sub['high'])):
                                        filled_limit = True
                                        break
                                else:
                                    if (order.amount > 0 and order.stop_price < sub['high']) or (
                                            order.amount < 0 and order.stop_price > sub['low']):
                                        reached_trigger = True
                            if filled_limit:
                                self.handle_order_execution(order, bar)

                else:  # means order.limit_price and (order.stop_price is None or order.stop_triggered):
                    # check for limit execution
                    if (order.amount > 0 and order.limit_price > bar.low) or (
                            order.amount < 0 and order.limit_price < bar.high):
                        self.handle_order_execution(order, bar)
        # update equity = balance + current value of open position
        self.account.equity = self.account.balance + self.account.open_position*barsSinceLastCheck[-1].close

        if self.account.equity < self.hh:
            self.underwater += 1
        else:
            self.underwater= 0
        self.hh = max(self.hh,self.account.equity)
        dd= self.hh - self.account.equity
        self.maxDD = max(self.maxDD,dd)
        self.max_underwater= max(self.max_underwater,self.underwater)


    def run(self):
        self.reset()
        logger.info("starting backtest with "+str(len(self.bars))+" bars and "+str(self.account.equity)+" equity")
        for i in range(len(self.bars)):
            if i == len(self.bars) - 1:
                continue  # ignore last bar

            # slice bars. TODO: also slice intrabar to simulate tick
            self.current_bars = self.bars[-(i + 1):]
            # add one bar with 1 tick on open to show to bot that the old one is closed
            next_bar = self.bars[-i - 2]
            self.current_bars.insert(0, Bar(tstamp=next_bar.tstamp, open=next_bar.open, high=next_bar.open,
                                            low=next_bar.open, close=next_bar.open,
                                            volume=1, subbars=[]))
            # check open orders & update account
            self.handle_open_orders([self.current_bars[1]])

            self.bot.on_tick(self.current_bars, self.account)
            next_bar.bot_data = self.current_bars[0].bot_data
            for b in self.current_bars:
                b.did_change= False

        if self.account.open_position != 0:
            self.send_order(Order(orderId="endOfTest",amount=-self.account.open_position))
            self.handle_open_orders([self.bars[0]])

        profit= self.account.equity-self.initialEquity
        logger.info("finished with " + str(len(self.bot.position_history)) + " pos "
                    + str(int(profit)) + " profit " + str(
            int(self.maxDD)) + " maxDD relation: " + str(profit / self.maxDD) +" UW: "+str(self.max_underwater))

        self.write_results_to_files()

    def write_results_to_files(self):
        # positions
        base= 'results/'+self.bot.uid()+'/'
        try:
            os.makedirs(base)
        except Exception:
            pass

        uid= str(int(datetime.utcnow().timestamp()))+'_'+str(len(self.bars))
        tradesfilename= base+uid+'_trades.csv'
        logger.info("writing" + str(len(self.bot.position_history))+" trades to file "+tradesfilename)
        with open(tradesfilename,'w',newline='') as csvfile:
            writer = csv.writer(csvfile)
            csv_columns = ['signalTStamp','size', 'wantedEntry','initialStop' ,'openTime', 'openPrice', 'closeTime', 'closePrice']
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

class LiveTrading:

    def __init__(self, trading_bot):
        self.exchange = ExchangeInterface(settings.DRY_RUN)
        # Once exchange is created, register exit handler that will always cancel orders
        # on any error.
        atexit.register(self.exit)
        signal.signal(signal.SIGTERM, self.exit)

        logger.info("Using symbol %s." % self.exchange.symbol)

        if settings.DRY_RUN:
            logger.info("Initializing dry run. Orders printed below represent what would be posted to BitMEX.")
        else:
            logger.info("Order Manager initializing, connecting to BitMEX. Live run: executing real trades.")

        self.instrument = self.exchange.get_instrument()
        self.bot = trading_bot
        # init market data dict to be filled later
        self.bars = []
        self.update_bars()
        self.bot.init(self.bars)

    def print_status(self):
        """Print the current status."""
        logger.info("Current Contract Position: %d" % self.exchange.get_position())
        """TODO: open orders"""

    ###
    # Sanity
    ##

    def sanity_check(self):
        """Perform checks before placing orders."""

        # Check if OB is empty - if so, can't quote.
        self.exchange.check_if_orderbook_empty()

        # Ensure market is still open.
        self.exchange.check_market_open()

        # Get ticker, which sets price offsets and prints some debugging info.

    ###
    # Running
    ###

    def update_bars(self):
        """get data from exchange"""
        new_bars = self.exchange.bitmex.get_bars(timeframe=settings.TIMEFRAME, start_time=self.bars[-1]["timestamp"])
        # append to current bars

    def check_file_change(self):
        """Restart if any files we're watching have changed."""
        for f, mtime in watched_files_mtimes:
            if getmtime(f) > mtime:
                self.restart()

    def check_connection(self):
        """Ensure the WS connections are still open."""
        return self.exchange.is_open()

    def exit(self):
        logger.info("Shutting down. open orders are not touched! Close manually!")
        try:
            self.exchange.bitmex.exit()
        except errors.AuthenticationError as e:
            logger.info("Was not authenticated; could not cancel orders.")
        except Exception as e:
            logger.info("Unable to cancel orders: %s" % e)

        sys.exit()

    def run_loop(self):
        while True:
            sys.stdout.write("-----\n")
            sys.stdout.flush()

            self.check_file_change()
            sleep(settings.LOOP_INTERVAL)

            # This will restart on very short downtime, but if it's longer,
            # the MM will crash entirely as it is unable to connect to the WS on boot.
            if not self.check_connection():
                logger.error("Realtime data connection unexpectedly closed, restarting.")
                self.restart()
            self.update_bars()
            self.bot.on_tick(self.bars)

    def restart(self):
        logger.info("Restarting the market maker...")
        os.execv(sys.executable, [sys.executable] + sys.argv)


import json
from market_maker.exchange_interface import process_low_tf_bars


def load_bars(days_in_history,wanted_tf):
    end= 42
    start= end - int(days_in_history*1440/50000)
    m1_bars = []
    logger.info("loading " + str(end - start) + " history files")
    for i in range(start, end + 1):
        with open('history/M1_' + str(i) + '.json') as f:
            m1_bars += json.load(f)
    logger.info("done loading files, now preparing them")
    return process_low_tf_bars(m1_bars, wanted_tf)


import plotly.graph_objects as go
from datetime import datetime
from typing import List
from market_maker.indicator import Indicator


def prepare_plot(bars, indis:List[Indicator]):
    logger.info("calculating "+str(len(indis))+" indicators on "+str(len(bars))+" bars")
    for indi in indis:
        indi.on_tick(bars)

    logger.info("running timelines")
    time = list(map(lambda b: datetime.fromtimestamp(b.tstamp), bars))
    open = list(map(lambda b: b.open, bars))
    high = list(map(lambda b: b.high, bars))
    low = list(map(lambda b: b.low, bars))
    close = list(map(lambda b: b.close, bars))

    logger.info("creating plot")
    fig = go.Figure(data=[go.Candlestick(x=time, open=open, high=high, low=low, close=close, name="XBTUSD")])

    logger.info("adding indicators")
    for indi in indis:
        lines=indi.get_number_of_lines()
        offset= indi.get_plot_offset()
        for idx in range(0,lines):
            sub_data= list(map(lambda b:indi.get_data_for_plot(b)[idx],bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line_width=1, name=indi.id+"_"+str(idx))

    fig.update_layout(xaxis_rangeslider_visible=False)
    return fig

