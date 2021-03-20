import gzip
import json

from kuegi_bot.exchanges.ExchangeWithWS import KuegiWebsocket


class CoinbaseWebsocket(KuegiWebsocket):

    def __init__(self, wsURLs, api_key, api_secret, logger, callback, symbol):
        self.data = {}
        self.symbol = symbol
        self.id= 1
        super().__init__(wsURLs, api_key, api_secret, logger, callback)

    def subscribeTrades(self):
        param = {'type': "subscribe",
                 "product_ids": [self.symbol],
                 'channels': ["ticker"]
                 }
        self.id += 1
        self.ws.send(json.dumps(param))
        key = "trade"
        if key not in self.data:
            self.data[key] = []

    def subscribe_realtime_data(self):
        self.subscribeTrades()

    def on_message(self, message):
        """Handler for parsing WS messages."""
        try:
            topic= None
            message = json.loads(message)
            if message['type'] == "ticker":
                topic = "trade"

                self.data[topic].append(message)
                if self.callback is not None and topic is not None:
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
