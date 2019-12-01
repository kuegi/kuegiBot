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
from market_maker.ws.ws_thread import OnTickHook
from market_maker.utils.trading_classes import TradingBot,OrderInterface, Order, Account, Bar,Symbol

logger = log.setup_custom_logger('trade_engine')

watched_files_mtimes = [(f, getmtime(f)) for f in settings.WATCHED_FILES]


class LiveTrading(OrderInterface,OnTickHook):

    def __init__(self, trading_bot:TradingBot):
        self.tick_waiting = False
        self.exchange = ExchangeInterface(settings.DRY_RUN,self)
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
        self.symbolInfo:Symbol= Symbol(symbol= self.instrument['symbol'],
                                       isInverse=self.instrument['isInverse'],
                                       lotSize= self.instrument['lotSize'],
                                       tickSize=self.instrument['tickSize'],
                                       makerFee= self.instrument['makerFee'],
                                       takerFee= self.instrument['takerFee']
                                       )
        self.bot: TradingBot = trading_bot
        self.bot.order_interface = self
        # init market data dict to be filled later
        self.bars : List[Bar] = []
        self.update_bars()
        self.account : Account = Account()
        self.update_account()
        self.bot.reset()
        self.bot.init(self.bars,self.account,self.symbolInfo)

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
        self.exchange.update_account(self.account)
        orders= self.exchange.get_orders()
        prevOpenIds= []
        for o in self.account.open_orders:
            prevOpenIds.append(o.id)

        self.account.open_orders= []
        for o in orders:
            if o.active:
                self.account.open_orders.append(o)
            elif o.id in prevOpenIds:
                self.account.order_history.append(o)

    def update_bars(self):
        """get data from exchange"""
        if len(self.bars) < 10 :
            self.bars= self.exchange.get_bars(240,0)
        else:
            new_bars = self.exchange.recent_bars(240,0)
            for b in reversed(new_bars):
                if b.tstamp < self.bars[0].tstamp:
                    continue
                elif b.tstamp == self.bars[0].tstamp:
                    # merge?
                    if b.subbars[-1].tstamp == self.bars[0].subbars[-1].tstamp:
                        self.bars[0]= b
                    else:
                        #merge!
                        first= self.bars[0].subbars[0]
                        newBar= Bar(tstamp=b.tstamp, open=first['open'], high=first['high'], low=first['low'], close=first['close'],
                              volume=first['volume'], subbars=[first])
                        for sub in reversed(self.bars[0].subbars[1:]):
                            if sub.tstamp < b.subbars[-1].tstamp:
                                newBar.add_subbar(sub)
                            else:
                                break
                        for sub in reversed(b.subbars):
                            if sub.tstamp > newBar.subbars[0].tstamp:
                                newBar.add_subbar(sub)
                            else:
                                continue
                else: #b.tstamp > self.bars[0].tstamp
                    self.bars.insert(0,b)

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

    def handle_tick(self):
        self.tick_waiting = False
        self.update_bars()
        self.update_account()
        self.bot.on_tick(self.bars,self.account)


    def run_loop(self):
        sys.stdout.write("-----\n")
        sys.stdout.flush()
        while(True):
            self.check_file_change()
            if not self.tick_waiting:
                sleep(settings.LOOP_INTERVAL)

            # This will restart on very short downtime, but if it's longer,
            # the MM will crash entirely as it is unable to connect to the WS on boot.
            if not self.check_connection():
                logger.error("Realtime data connection unexpectedly closed, restarting.")
                self.restart()
            self.handle_tick()


    def tick_happened(self):
        self.tick_waiting= True

    def restart(self):
        logger.info("Restarting the market maker...")
        os.execv(sys.executable, [sys.executable] + sys.argv)



