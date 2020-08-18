import json
import time

from kuegi_bot.exchanges.ExchangeWithWS import KuegiWebsocket
from kuegi_bot.exchanges.phemex.client import Client


def get_current_timestamp():
    return int(round(time.time() * 1000))


class PhemexWebsocket(KuegiWebsocket):

    def __init__(self, wsURL, api_key, api_secret, logger, callback):
        """Initialize"""
        self.auth_id = 0
        super().__init__(wsURL, api_key, api_secret, logger, callback)

    def send(self, method, params=None):
        channel = dict()
        channel["method"] = method
        channel["params"] = params if params is not None else []
        channel["id"] = get_current_timestamp()
        if method == "user.auth":
            self.auth_id = channel['id']
        self.ws.send(json.dumps(channel))

    def do_auth(self):
        self.logger.info("doing auth")
        self.auth_id = 0
        [signature, expiry] = Client.generate_signature(message=self.api_key, api_secret=self.api_secret)
        self.send("user.auth", ["API", self.api_key, signature, expiry])

    def on_message(self, message):
        """Handler for parsing WS messages."""
        message = json.loads(message)
        if 0 < self.auth_id == message['id']:
            self.auth = True
            self.auth_id = 0
            self.logger.info("authentication success")
            return

        result = None
        responseType = None
        if 'error' in message and message['error'] is not None:
            self.logger.error("error in ws reply: " + message)
            self.on_error(message)
        if "accounts" in message and message['accounts']:
            # account update
            responseType = "account"
            result = message

        if "kline" in message and message['kline'] and "type" in message:
            responseType = "kline"
            result = message

        if self.callback is not None and result is not None:
            try:
                self.callback(responseType, result)
            except Exception as e:
                self.logger.error("Exception in callback: " + str(e) + "\n message: " + str(message))

    def subscribe_candlestick_event(self, symbol: str, intervalMinutes: int):
        self.send("kline.subscribe", [symbol, intervalMinutes * 60])

    def subscribe_account_updates(self):
        self.send("aop.subscribe")
