import json
import threading
import time
from time import sleep

import websocket
from binance_f.impl.utils import JsonWrapper
from binance_f.model import SubscribeMessageType, AccountUpdate, OrderUpdate, ListenKeyExpired, CandlestickEvent


def get_current_timestamp():
    return int(round(time.time() * 1000))


def parse_json_from_string(value):
    value = value.replace("False", "false")
    value = value.replace("True", "true")
    return JsonWrapper(json.loads(value))


class BinanceWebsocket:

    def __init__(self, wsURL, api_key, api_secret, logger, callback):
        """Initialize"""
        self.logger = logger
        self.logger.debug("Initializing WebSocket.")

        if api_key is not None and api_secret is None:
            raise ValueError('api_secret is required if api_key is provided')
        if api_key is None and api_secret is not None:
            raise ValueError('api_key is required if api_secret is provided')

        self.api_key = api_key
        self.api_secret = api_secret

        self.exited = False
        # We can subscribe right in the connection querystring, so let's build that.
        # Subscribe to all pertinent endpoints
        self.logger.info("Connecting to %s" % wsURL)
        self.__connect(wsURL)
        self.callback = callback

    def __del__(self):
        self.exit()

    def exit(self):
        """Call this to exit - will close websocket."""
        self.exited = True
        self.ws.close()

    def __connect(self, wsURL):
        """Connect to the websocket in a thread."""
        self.logger.debug("Starting thread")

        self.ws = websocket.WebSocketApp(wsURL,
                                         on_message=self.__on_message,
                                         on_close=self.__on_close,
                                         on_open=self.__on_open,
                                         on_error=self.__on_error,
                                         keep_running=True)

        self.wst = threading.Thread(target=lambda: self.ws.run_forever())
        self.wst.daemon = True
        self.wst.start()
        self.logger.debug("Started thread")

        # Wait for connect before continuing
        retry_times = 5
        while not self.ws.sock or not self.ws.sock.connected and retry_times:
            sleep(1)
            retry_times -= 1
        if retry_times == 0 and not self.ws.sock.connected:
            self.logger.error("Couldn't connect to WebSocket! Exiting.")
            self.exit()
            raise websocket.WebSocketTimeoutException('Error！Couldnt not connect to WebSocket!.')

    def __on_message(self, message):
        """Handler for parsing WS messages."""
        wrapper = parse_json_from_string(message)
        # parse wrapper based on type
        responseType = None
        result = None
        if wrapper.contain_key("status") and wrapper.get_string("status") != "ok":
            error_code = wrapper.get_string_or_default("err-code", "Unknown error")
            error_msg = wrapper.get_string_or_default("err-msg", "Unknown error")
            self.__on_error(error_code + ": " + error_msg)
        elif wrapper.contain_key("err-code") and wrapper.get_int("err-code") != 0:
            error_code = wrapper.get_string_or_default("err-code", "Unknown error")
            error_msg = wrapper.get_string_or_default("err-msg", "Unknown error")
            self.__on_error(error_code + ": " + error_msg)
        elif wrapper.contain_key("result") and wrapper.contain_key("id"):
            responseType = SubscribeMessageType.RESPONSE
            result = wrapper.get_int("id")
        else:
            responseType = SubscribeMessageType.PAYLOAD
            if wrapper.get_string("e") == "ACCOUNT_UPDATE":
                result = AccountUpdate.json_parse(wrapper)
            elif wrapper.get_string("e") == "ORDER_TRADE_UPDATE":
                result = OrderUpdate.json_parse(wrapper)
            elif wrapper.get_string("e") == "listenKeyExpired":
                result = ListenKeyExpired.json_parse(wrapper)
            elif wrapper.get_string("e") == "kline":
                result = CandlestickEvent.json_parse(wrapper)

        if self.callback is not None and result is not None:
            self.callback(responseType, result)

    def __on_error(self, error):
        """Called on fatal websocket errors. We exit on these."""
        if not self.exited:
            self.logger.error("Error : %s" % error)
            raise websocket.WebSocketException(error)

    def __on_open(self):
        """
        Called when the WS opens.
        """
        self.logger.debug("Websocket Opened.")

    def __on_close(self):
        """Called on websocket close."""
        self.logger.info('Websocket Closed')
        self.exit()

    def subscribe_candlestick_event(self, symbol: str, interval: str):
        channel = dict()
        channel["params"] = list()
        channel["params"].append(symbol + "@kline_" + interval)
        channel["id"] = get_current_timestamp()
        channel["method"] = "SUBSCRIBE"
        self.ws.send(json.dumps(channel))

    def subscribe_user_data_event(self, listenKey: str):
        channel = dict()
        channel["params"] = list()
        channel["params"].append(listenKey)
        channel["id"] = get_current_timestamp()
        channel["method"] = "SUBSCRIBE"
        self.ws.send(json.dumps(channel))
