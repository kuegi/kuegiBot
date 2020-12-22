import gzip
import json

from kuegi_bot.exchanges.ExchangeWithWS import KuegiWebsocket


class HuobiWebsocket(KuegiWebsocket):

    def __init__(self, wsURLs, api_key, api_secret, logger, callback, symbol):
        self.data = {}
        self.symbol = symbol
        self.id= 1
        super().__init__(wsURLs, api_key, api_secret, logger, callback)

    def subscribeTrades(self):
        param = {'sub': "market."+self.symbol+".trade.detail",
                 'id': "id"+str(self.id)
                 }
        self.id += 1
        self.ws.send(json.dumps(param))
        key = "trade"
        if key not in self.data:
            self.data[key] = []

    def subscribeRealtimeData(self):
        self.subscribeTrades()

    def on_message(self, message):
        """Handler for parsing WS messages."""
        try:
            message = gzip.decompress(message)
            message = json.loads(message)
            if "ping" in message:
                self.ws.send(json.dumps({"pong": message['ping']}))
            elif "ch" in message:
                if message['ch'] == "market."+self.symbol+".trade.detail":
                    topic= "trade"
                    for data in message['tick']['data']:
                        self.data[topic].append(data)
                    if self.callback is not None:
                        self.callback(topic)
        except Exception as e:
            self.logger.error("exception in on_message: "+str(e))
            raise e

    def get_data(self, topic):
        if topic not in self.data:
            self.logger.info(" The topic %s is not subscribed." % topic)
            return []
        if len(self.data[topic]) == 0:
            return []
        return self.data[topic].pop()
