import hmac
import json

import time

from kuegi_bot.exchanges.ExchangeWithWS import KuegiWebsocket


class BybitLinearPublicPart(KuegiWebsocket):

    def __init__(self, wsURLs, api_key, api_secret, logger, callback, on_message):
        self.messageCallback= on_message
        super().__init__(wsURLs, api_key, api_secret, logger, callback)

    def on_message(self, message):
        self.messageCallback(message)


class BybitLinearWebsocket(KuegiWebsocket):
    # User can ues MAX_DATA_CAPACITY to control memory usage.
    MAX_DATA_CAPACITY = 200
    PRIVATE_TOPIC = ['position', 'execution', 'order']

    def __init__(self, wsprivateURLs, wspublicURLs, api_key, api_secret, logger, callback,symbol, minutesPerBar):
        self.data = {}
        self.symbol= symbol
        self.minutesPerBar= minutesPerBar
        super().__init__(wsprivateURLs, api_key, api_secret, logger, callback)
        self.publicWS= BybitLinearPublicPart(wspublicURLs,api_key,api_secret,logger,callback,self.on_message)

    def generate_signature(self, expires):
        """Generate a request signature."""
        _val = 'GET/realtime' + expires
        return str(hmac.new(bytes(self.api_secret, "utf-8"), bytes(_val, "utf-8"), digestmod="sha256").hexdigest())

    def do_auth(self):
        expires = str(int(round(time.time()) + 5)) + "000"
        signature = self.generate_signature(expires)
        auth = {"op": "auth", "args": [self.api_key, expires, signature]}
        self.ws.send(json.dumps(auth))

    def subscribeRealtimeData(self):
        retry_times = 5
        while (self.publicWS.ws.sock is None or not self.publicWS.ws.sock.connected) and retry_times > 0:
            time.sleep(1)
            retry_times -= 1
        if retry_times == 0 and (self.publicWS.ws.sock is None or not self.publicWS.ws.sock.connected):
            self.logger.error("Couldn't connect to public WebSocket! Exiting.")
            self.exit()
        self.subscribe_wallet()
        self.subscribe_order()
        self.subscribe_stop_order()
        self.subscribe_execution()
        self.subscribe_position()
        subbarsIntervall = '1' if self.minutesPerBar <= 60 else '60'
        self.subscribe_candle(subbarsIntervall, self.symbol)
        self.subscribe_instrument_info(self.symbol)

    def exit(self):
        super().exit()
        self.publicWS.exit()

    def on_message(self, message):
        """Handler for parsing WS messages."""
        message = json.loads(message)
        if 'success' in message:
            if message["success"]:
                if 'request' in message and message["request"]["op"] == 'auth':
                    self.auth = True
                    self.logger.info("Authentication success.")
                if 'ret_msg' in message and message["ret_msg"] == 'pong':
                    self.data["pong"].append("PING success")
            else:
                self.logger.error("Error in socket: " + str(message))

        if 'topic' in message:
            self.data[message["topic"]].append(message["data"])
            if len(self.data[message["topic"]]) > BybitLinearWebsocket.MAX_DATA_CAPACITY:
                self.data[message["topic"]] = self.data[message["topic"]][BybitLinearWebsocket.MAX_DATA_CAPACITY // 2:]
            if self.callback is not None:
                self.callback(message['topic'])

    def subscribe_candle(self, interval: str, symbol: str):
        args = 'candle.' + interval + '.' + symbol
        param = dict(
            op='subscribe',
            args=[args]
        )
        self.publicWS.ws.send(json.dumps(param))
        if args not in self.data:
            self.data[args] = []

    def subscribe_trade(self):
        self.publicWS.ws.send('{"op":"subscribe","args":["trade"]}')
        if "trade.BTCUSD" not in self.data:
            self.data["trade.BTCUSD"] = []
            self.data["trade.ETHUSD"] = []
            self.data["trade.EOSUSD"] = []
            self.data["trade.XRPUSD"] = []

    def subscribe_insurance(self):
        self.ws.send('{"op":"subscribe","args":["insurance"]}')
        if 'insurance.BTC' not in self.data:
            self.data['insurance.BTC'] = []
            self.data['insurance.XRP'] = []
            self.data['insurance.EOS'] = []
            self.data['insurance.ETH'] = []

    def subscribe_orderBookL2(self, symbol):
        param = {
            'op': 'subscribe',
            'args': ['orderBookL2_25.' + symbol]
        }
        self.ws.send(json.dumps(param))
        if 'orderBookL2_25.' + symbol not in self.data:
            self.data['orderBookL2_25.' + symbol] = []

    def subscribe_instrument_info(self, symbol):
        param = {
            'op': 'subscribe',
            'args': ['instrument_info.100ms.' + symbol]
        }
        self.publicWS.ws.send(json.dumps(param))
        if 'instrument_info.100ms.' + symbol not in self.data:
            self.data['instrument_info.100ms.' + symbol] = []

    def subscribe_position(self):
        self.ws.send('{"op":"subscribe","args":["position"]}')
        if 'position' not in self.data:
            self.data['position'] = []

    def subscribe_wallet(self):
        self.ws.send('{"op":"subscribe","args":["wallet"]}')
        if 'wallet' not in self.data:
            self.data['wallet'] = []

    def subscribe_execution(self):
        self.ws.send('{"op":"subscribe","args":["execution"]}')
        if 'execution' not in self.data:
            self.data['execution'] = []

    def subscribe_order(self):
        self.ws.send('{"op":"subscribe","args":["order"]}')
        if 'order' not in self.data:
            self.data['order'] = []

    def subscribe_stop_order(self):
        self.ws.send('{"op":"subscribe","args":["stop_order"]}')
        if 'stop_order' not in self.data:
            self.data['stop_order'] = []

    def get_data(self, topic):
        if topic not in self.data:
            self.logger.info(" The topic %s is not subscribed." % topic)
            return []
        if topic.split('.')[0] in BybitLinearWebsocket.PRIVATE_TOPIC and not self.auth:
            self.logger.info("Authentication failed. Please check your api_key and api_secret. Topic: %s" % topic)
            return []
        else:
            if len(self.data[topic]) == 0:
                return []
            return self.data[topic].pop()
