import sys
import os
import atexit
import signal
from time import sleep
from os.path import getmtime
from typing import List

from market_maker.settings import settings
from market_maker.utils import log, errors
from market_maker.market_maker import ExchangeInterface
from market_maker.utils.trading_classes import TradingBot,OrderInterface, Order, Account, Bar

logger = log.setup_custom_logger('trade_engine')

watched_files_mtimes = [(f, getmtime(f)) for f in settings.WATCHED_FILES]

class LiveTrading(OrderInterface):

    def __init__(self, trading_bot:TradingBot):
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
        self.bot.order_interface = self
        # init market data dict to be filled later
        self.bars : List[Bar] = []
        self.update_bars()
        self.account :Account = Account()
        self.update_account()
        self.bot.reset()

    def print_status(self):
        """Print the current status."""
        logger.info("Current Contract Position: %d" % self.exchange.get_position())
        """TODO: open orders"""

    ###
    # Order handling
    ###

    def send_order(self, order: Order):
        self.exchange.send_order(order)

    def update_order(self, order: Order):
        self.exchange.update_order(order)

    def cancel_order(self, orderId):
        self.exchange.cancel_order(orderId)

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

    def update_account(self):
        self.account.open_position= self.exchange.get_position(self.exchange.symbol)
        orders= self.exchange.get_orders()
        self.account.open_orders= []
        for o in orders:
            self.account.open_orders.append(Order(orderId=o["clOrderId"],stop=o["stopPx"],limit=o["price"],amount=o["quantity"]))
        pass

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



