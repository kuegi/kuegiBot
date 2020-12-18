import json

from kuegi_bot.exchanges.ExchangeWithWS import KuegiWebsocket


class BitstampWebsocket(KuegiWebsocket):

    def __init__(self, wsURLs, api_key, api_secret, logger, callback, symbol):
        self.data = {}
        self.symbol = symbol
        super().__init__(wsURLs, api_key, api_secret, logger, callback)

    def subscribeTrades(self):
        param = {'event': 'bts:subscribe',
                 'data': {"channel": "live_trades_"+self.symbol}
                 }
        self.ws.send(json.dumps(param))
        key = "trade"
        if key not in self.data:
            self.data[key] = []

    def subscribeRealtimeData(self):
        self.subscribeTrades()

    def on_message(self, message):
        """Handler for parsing WS messages."""
        message = json.loads(message)

        if message['event'] == 'trade':
            self.data[message['event']].append(message["data"])
            if self.callback is not None:
                self.callback(message['event'])

    def get_data(self, topic):
        if topic not in self.data:
            self.logger.info(" The topic %s is not subscribed." % topic)
            return []
        if len(self.data[topic]) == 0:
            return []
        return self.data[topic].pop()
