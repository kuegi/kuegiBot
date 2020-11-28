import json

from kuegi_bot.exchanges.ExchangeWithWS import KuegiWebsocket


class BinanceSpotWebsocket(KuegiWebsocket):

    def __init__(self, wsURLs, api_key, api_secret, logger, callback, symbol):
        self.data = {}
        self.symbol = symbol
        self.id= 1
        super().__init__(wsURLs, api_key, api_secret, logger, callback)

    def subscribeTrades(self):
        param = {'method': 'SUBSCRIBE',
                 'params': [self.symbol+"@aggTrade"],
                 "id":self.id
                 }
        self.ws.send(json.dumps(param))
        self.id += 1
        key = "aggTrade"
        if key not in self.data:
            self.data[key] = []

    def subscribeRealtimeData(self):
        self.subscribeTrades()

    def on_message(self, message):
        """Handler for parsing WS messages."""
        message = json.loads(message)
        data= message['data']

        if data['e'] == 'aggTrade':
            self.data[data['e']].append(data)
            if self.callback is not None:
                self.callback(data['e'])

    def get_data(self, topic):
        if topic not in self.data:
            self.logger.info(" The topic %s is not subscribed." % topic)
            return []
        if len(self.data[topic]) == 0:
            return []
        return self.data[topic].pop()
