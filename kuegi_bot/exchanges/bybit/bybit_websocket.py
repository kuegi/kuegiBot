import websocket
import threading
from time import sleep
import json
import time
import hmac

class BybitWebsocket:

    #User can ues MAX_DATA_CAPACITY to control memory usage.
    MAX_DATA_CAPACITY = 200
    PRIVATE_TOPIC = ['position', 'execution', 'order']
    def __init__(self, wsURL, api_key, api_secret,logger):
        '''Initialize'''
        self.logger = logger
        self.logger.debug("Initializing WebSocket.")

        if api_key is not None and api_secret is None:
            raise ValueError('api_secret is required if api_key is provided')
        if api_key is None and api_secret is not None:
            raise ValueError('api_key is required if api_secret is provided')

        self.api_key = api_key
        self.api_secret = api_secret

        self.data = {}
        self.exited = False
        self.auth = False
        # We can subscribe right in the connection querystring, so let's build that.
        # Subscribe to all pertinent endpoints
        self.logger.info("Connecting to %s" % wsURL)
        self.__connect(wsURL)
        self.callback= None

    def __del__(self):
        self.exit()

    def exit(self):
        '''Call this to exit - will close websocket.'''
        self.exited = True
        self.ws.close()

    def __connect(self, wsURL):
        '''Connect to the websocket in a thread.'''
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
            raise websocket.WebSocketTimeoutException('Error！Couldn not connect to WebSocket!.')

        if self.api_key and self.api_secret:
            self.__do_auth()

    def generate_signature(self, expires):
        """Generate a request signature."""
        _val = 'GET/realtime' + expires
        return str(hmac.new(bytes(self.api_secret, "utf-8"), bytes(_val, "utf-8"), digestmod="sha256").hexdigest())

    def __do_auth(self):

        expires = str(int(round(time.time())+1))+"000"
        signature = self.generate_signature(expires)

        auth = {}
        auth["op"] = "auth"
        auth["args"] = [self.api_key, expires, signature]

        args = json.dumps(auth)

        self.ws.send(args)

    def __on_message(self, message):
        '''Handler for parsing WS messages.'''
        message = json.loads(message)
        if 'success' in message and message["success"]:
            if 'request' in message and message["request"]["op"] == 'auth':
                self.auth = True
                self.logger.info("Authentication success.")
            if 'ret_msg' in message and message["ret_msg"] == 'pong':
                self.data["pong"].append("PING success")

        if 'topic' in message:
            self.data[message["topic"]].append(message["data"])
            if len(self.data[message["topic"]]) > BybitWebsocket.MAX_DATA_CAPACITY:
                self.data[message["topic"]] = self.data[message["topic"]][BybitWebsocket.MAX_DATA_CAPACITY//2:]
            if self.callback is not None :
                self.callback(message['topic'])


    def __on_error(self, error):
        '''Called on fatal websocket errors. We exit on these.'''
        if not self.exited:
            self.logger.error("Error : %s" % error)
            raise websocket.WebSocketException(error)

    def __on_open(self):
        '''Called when the WS opens.'''
        self.logger.debug("Websocket Opened.")

    def __on_close(self):
        '''Called on websocket close.'''
        self.logger.info('Websocket Closed')
        self.exit()

    def ping(self):
        self.ws.send('{"op":"ping"}')
        if 'pong' not in self.data:
            self.data['pong'] = []

    def subscribe_kline(self, symbol:str, interval:str):
        param = {}
        param['op'] = 'subscribe'
        param['args'] = ['kline.' + symbol + '.' + interval]
        self.ws.send(json.dumps(param))
        if 'kline.' + symbol + '.' + interval not in self.data:
            self.data['kline.' + symbol + '.' + interval] = []

    def subscribe_klineV2(self, interval: str, symbol: str):
        param = {}
        param['op'] = 'subscribe'
        args = 'klineV2.' + interval + '.' + symbol
        param['args'] = [args]
        self.ws.send(json.dumps(param))
        if args not in self.data:
            self.data[args] = []

    def subscribe_trade(self):
        self.ws.send('{"op":"subscribe","args":["trade"]}')
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
        param = {}
        param['op'] = 'subscribe'
        param['args'] = ['orderBookL2_25.' + symbol]
        self.ws.send(json.dumps(param))
        if 'orderBookL2_25.' + symbol not in self.data:
            self.data['orderBookL2_25.' + symbol] = []

    def subscribe_instrument_info(self, symbol):
        param = {}
        param['op'] = 'subscribe'
        param['args'] = ['instrument_info.100ms.' + symbol]
        self.ws.send(json.dumps(param))
        if 'instrument_info.100ms.' + symbol not in self.data:
            self.data['instrument_info.100ms.' + symbol] = []

    def subscribe_position(self):
        self.ws.send('{"op":"subscribe","args":["position"]}')
        if 'position' not in self.data:
            self.data['position'] = []

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
        if topic.split('.')[0] in BybitWebsocket.PRIVATE_TOPIC and not self.auth:
            self.logger.info("Authentication failed. Please check your api_key and api_secret. Topic: %s" % topic)
            return []
        else:
            if len(self.data[topic]) == 0:
                # self.logger.info(" The topic %s is empty." % topic)
                return []
            # while len(self.data[topic]) == 0 :
            #     sleep(0.1)
            return self.data[topic].pop()
