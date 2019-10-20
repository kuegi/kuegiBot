import math
import sys
import os
import atexit
import signal
from time import sleep
from os.path import getmtime
from market_maker.settings import settings
from market_maker.utils import log, constants, errors

from market_maker.market_maker import ExchangeInterface

logger = log.setup_custom_logger('root')

watched_files_mtimes = [(f, getmtime(f)) for f in settings.WATCHED_FILES]


class Account:
    def __init__(self):
        self.equity = 0
        self.open_position = 0
        self.open_orders = []
        self.order_history = []


class Order:
    def __init__(self, id, stop, limit, amount, direction):
        self.id = id
        self.stop_price = stop
        self.limit_price = limit
        self.amount = amount
        self.executed_amount = 0
        self.active = True
        self.stop_triggered = False


class OrderInterface:
    def send_order(self, order: Order):
        pass

    def cancel_order(self, orderId):
        pass


class TradingBot:
    def __init__(self):
        self.order_interface: OrderInterface

    def on_tick(self, bars: list, account: Account):
        """checks price and levels to manage current orders and set new ones"""
        self.manage_open_orders(bars, account)
        self.open_orders(bars, account)

    ###
    # Order Management
    ###

    def manage_open_orders(self, bars: list, account: Account):
        pass

    def open_orders(self, bars: list, account: Account):
        # new_bar= check_for_new_bar(bars)
        pass

    def check_for_new_bar(self, bars: list) -> bool:
        """checks if this tick started a new bar.

        only works on the first call of a bar"""
        # TODO: implement
        pass


class BackTest(OrderInterface):

    def __init__(self, bot: TradingBot, bars: list):
        self.bars = bars
        self.bot = bot
        self.bot.order_interface = self

        self.account = Account()
        self.account.equity = 100000
        self.account.open_position = 0

        self.current_bars = []

        self.market_slipage = 5

    # implementing OrderInterface

    def send_order(self, order: Order):
        # check if order is val
        order.tstamp= self.current_bars[0]['tstamp']
        self.account.open_orders.append(order)

    def cancel_order(self, orderId):
        for order in self.account.open_orders:
            if order.id == orderId:
                order.active = False
                order.final_tstamp= self.current_bars[0]['tstamp']
                order.final_reason= 'cancel'

                self.account.order_history.append(order)
                self.account.open_orders.remove(order)
                break

    # ----------

    def handle_open_orders(self,barsSinceLastCheck:list):
        for order in self.account.open_orders:
            for bar in barsSinceLastCheck:
                if ( order.amount > 0 and order.stop_price < bar['high'] ) or (order.amount < 0 and order.stop_price > bar['low'] ):
                    order.stop_triggered = True
                    if order.limit_price == None :
                        #execute stop market
                        amount= order.amount - order.executed_amount
                        price = order.stop_price + math.copysign(self.market_slipage,order.amount)
                        price = min(bar['high'],max(bar['low'] , price)) # only prices within the bar. might mean less slipage

    def run(self):
        for i in range(len(self.bars)):
            if i == len(self.bars)-1:
                continue  # ignore last bar

            # slice bars. TODO: also slice intrabar to simulate tick
            self.current_bars = self.bars[-(i+1):]
            # add one bar with 1 tick on open to show to bot that the old one is closed
            next_bar = self.bars[-i-2]
            self.current_bars.insert(0, dict(tstamp=next_bar['tstamp'], open=next_bar['open'], high=next_bar['open'],
                                             low=next_bar['open'], close=next_bar['open'],
                                             volume=1, subbars=[]))
            # check open orders & update account
            self.handle_open_orders([self.current_bars[1]])
            self.bot.on_tick(self.current_bars, self.account)


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
