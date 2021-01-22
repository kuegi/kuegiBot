import threading
from functools import reduce
from typing import List

import math
import websocket
from time import sleep, time

from kuegi_bot.utils.trading_classes import Order, Account, Bar, ExchangeInterface, process_low_tf_bars, TickerData


class KuegiWebsocket(object):

    def __init__(self, wsURLs:List[str], api_key, api_secret, logger, callback):
        """Initialize"""
        super().__init__()
        self.logger = logger
        self.logger.debug("Initializing WebSocket.")

        self.api_key = api_key
        self.api_secret = api_secret

        self.exited = False
        self.auth = False
        self.restarting= False
        self.restart_count= 0
        self.last_restart= 0
        # We can subscribe right in the connection querystring, so let's build that.
        # Subscribe to all pertinent endpoints
        self.wsURLs= wsURLs
        self.lastUsedUrlIdx= -1
        self.__connect()
        self.callback = callback

    def __del__(self):
        self.exit()

    def __connect(self):
        """Connect to the websocket in a thread."""
        self.lastUsedUrlIdx +=1
        if self.lastUsedUrlIdx >= len(self.wsURLs):
            self.lastUsedUrlIdx= 0
        usedUrl= self.wsURLs[self.lastUsedUrlIdx]
        self.logger.info("Connecting to %s" % usedUrl)
        self.logger.debug("Starting thread")
        self.exited = False
        self.auth = False

        self.ws = websocket.WebSocketApp(usedUrl,
                                         on_message=self.on_message,
                                         on_close=self.__on_close,
                                         on_open=self.__on_open,
                                         on_error=self.on_error,
                                         keep_running=True)

        self.wst = threading.Thread(target=lambda: self.ws.run_forever(ping_interval=5))
        self.wst.daemon = True
        self.wst.start()
        self.logger.debug("Started thread")

        # Wait for connect before continuing
        retry_times = 5
        while (self.ws.sock is None or not self.ws.sock.connected) and retry_times > 0:
            sleep(1)
            retry_times -= 1
        if retry_times == 0 and (self.ws.sock is None or not self.ws.sock.connected):
            self.logger.error("Couldn't connect to WebSocket! Exiting.")
            self.exit()
            raise websocket.WebSocketTimeoutException('Error！Couldnt not connect to WebSocket!.')

        if self.api_key and self.api_secret:
            self.do_auth()

    def do_auth(self):
        pass

    def subscribeDataAfterAuth(self):
        self.logger.info("subscribing to live updates.")
        retry_times = 5
        while not self.auth and retry_times:
            sleep(1)
            retry_times -= 1
        if self.auth:
            self.subscribeRealtimeData()
            self.logger.info("ready to go")
        else:
            self.logger.error("couldn't auth the socket, exiting")
            self.exit()
            raise Exception('Error！Couldn not auth the WebSocket!.')

    def subscribeRealtimeData(self):
        pass

    def on_message(self, message):
        """Handler for parsing WS messages."""
        pass

    def try_restart(self):
        self.restarting = True
        self.ws.close()
        restartThread = threading.Thread(target=lambda: self.try_restart_())
        restartThread.daemon = True
        restartThread.start()

    def try_restart_(self):
        try:
            self.restarting = True
            sleep(1)

            now= time()
            if self.last_restart < now - 60*15:
                self.restart_count= 0
            if self.restart_count < 5:
                self.logger.info("trying to restart")
                # up to 5 restarts or with delta of 15 minutes allowed
                self.restart_count += 1
                self.last_restart= now
                self.__connect()
                if self.api_key and self.api_secret:
                    self.subscribeDataAfterAuth()
                else:
                    self.subscribeRealtimeData()
                self.restarting= False
            else:
                self.exited= True
                self.restarting= False
                self.on_error("too many restarts")
        except Exception as e:
            self.restarting= False
            self.on_error("error during restart: "+str(e))


    def on_error(self, error):
        """Called on fatal websocket errors. We exit on these."""
        if not self.exited and not self.restarting:
            self.logger.error("Error : %s" % error)
            self.logger.error("last ping: " + str(self.ws.last_ping_tm) + " last pong: " + str(self.ws.last_pong_tm) +
                               " delta: "+str(self.ws.last_pong_tm-self.ws.last_ping_tm))
            self.try_restart()


    def __on_open(self):
        """
        Called when the WS opens.
        """
        self.logger.debug("Websocket Opened.")

    def __on_close(self):
        """Called on websocket close."""
        self.logger.info('Websocket Closed '+str(self.exited)+" "+str(self.restarting))
        if not self.exited and not self.restarting:
            self.exit()

    def exit(self):
        """Call this to exit - will close websocket."""
        self.exited = True
        self.ws.close()


class ExchangeWithWS(ExchangeInterface):

    def __init__(self, settings, logger, ws: KuegiWebsocket, on_tick_callback=None):
        super().__init__(settings, logger, on_tick_callback)
        self.symbol = settings.SYMBOL
        self.baseCurrency = settings.BASE
        self.ws = ws
        self.last_order_sync= 0

        self.orders = {}
        self.positions = {}
        self.bars: List[Bar] = []
        self.last = 0
        self.symbol_info = self.get_instrument()
        self.init()

    def hasAuth(self):
        return self.settings.API_KEY is not None and self.settings.API_SECRET is not None

    def init(self):
        self.logger.info("loading market data. this may take a moment")
        self.initOrders()
        self.last_order_sync= time()
        self.initPositions()
        self.last= self.get_ticker(self.symbol).last
        # TODO: init bars

        if self.hasAuth():
            self.logger.info(
                "starting with %.2f in wallet, %i orders, pos %.2f @ %.2f" % (self.positions[self.symbol].walletBalance,
                                                                               len(self.orders),
                                                                               self.positions[self.symbol].quantity,
                                                                               self.positions[self.symbol].avgEntryPrice))
            self.ws.subscribeDataAfterAuth()
        else:
            self.ws.subscribeRealtimeData()

    def initOrders(self):
        raise NotImplementedError

    def resyncOrders(self):
        self.resync_internal(1)

    def resync_internal(self, retrycount):
        prev: dict = self.orders
        # resync doesn't get the executed orders, but maybe we don't know about the execution yet -> keep recent executions
        executed = [o for o in prev.values() if not o.active]
        self.orders = {}
        rem_exec = 0
        try:
            self.initOrders()
            # readd executed orders
            for o in executed:
                if o.execution_tstamp > time() - 30 * 60:
                    self.orders[o.id] = o
                else:
                    rem_exec += 1

        except Exception as e:
            self.logger.warn("error syncing orders, back to previous ones. " + str(e))
            self.orders = prev

        if len(prev) - rem_exec != len(self.orders):
            self.logger.warn("different order count after resync %i-%i vs %i" % (len(prev), rem_exec, len(self.orders)))
            prev_str = reduce(lambda x, y: x + " " + y.id, prev.values(), "")
            new_str = reduce(lambda x, y: x + " " + y.id, self.orders.values(), "")
            self.logger.warn("prevs: [" + prev_str + "], new: [" + new_str + "]")

            if retrycount <= 0:
                self.orders = prev
            else:
                self.logger.warn("waiting 5 sec for resync in case its a glitch")
                sleep(5)
                self.resync_internal(retrycount-1)

        self.last_order_sync= time()

    def initPositions(self):
        raise NotImplementedError

    def get_instrument(self, symbol=None):
        raise NotImplementedError

    def get_ticker(self, symbol=None) -> TickerData:
        raise NotImplementedError

    def get_bars(self, timeframe_minutes, start_offset_minutes) -> List[Bar]:
        raise NotImplementedError

    def internal_cancel_order(self, order: Order):
        pass

    def internal_send_order(self, order: Order):
        pass

    def internal_update_order(self, order: Order):
        pass

    def exit(self):
        self.ws.exit()

    def reset_order_sync_timer(self):
        self.last_order_sync= time()

    def get_orders(self) -> List[Order]:
        if self.last_order_sync < time() - 10*60: # resync every 10 minutes
            self.resyncOrders()
        return list(self.orders.values())

    def recent_bars(self, timeframe_minutes, start_offset_minutes) -> List[Bar]:
        return self._aggregate_bars(self.bars, timeframe_minutes, start_offset_minutes)

    def _aggregate_bars(self, bars: List[Bar], timeframe_minutes, start_offset_minutes) -> List[Bar]:
        """ bars need to be ordered newest bar = index 0 """
        return process_low_tf_bars(bars, timeframe_minutes, start_offset_minutes)

    def get_position(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        return self.positions[symbol] if symbol in self.positions.keys() else None

    def is_open(self):
        return not self.ws.exited

    def check_market_open(self):
        return self.is_open()

    def update_account(self, account: Account):
        pos = self.positions[self.symbol]
        account.open_position = pos
        account.equity = pos.walletBalance
        account.usd_equity = account.equity * self.last
