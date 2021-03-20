import gzip
import json

from kuegi_bot.exchanges.ExchangeWithWS import KuegiWebsocket


class BitfinexWebsocket(KuegiWebsocket):

    def __init__(self, wsURLs, api_key, api_secret, logger, callback, symbol):
        self.data = {}
        self.symbol = symbol
        self.channelIds = {}
        super().__init__(wsURLs, api_key, api_secret, logger, callback)

    def subscribeTrades(self):
        param = {'event': "subscribe",
                 'channel': "trades",
                 "symbol": self.symbol
                 }
        self.ws.send(json.dumps(param))
        key = "trade"
        if key not in self.data:
            self.data[key] = []
        key = "tradeupdate"
        if key not in self.data:
            self.data[key] = []

    def subscribe_realtime_data(self):
        self.subscribeTrades()

    def on_message(self, message):
        """Handler for parsing WS messages."""
        try:
            message = json.loads(message)
            if "event" in message:
                if message["event"] == "subscribed":
                    self.channelIds[message["chanId"]] = message["channel"];
            if isinstance(message,list) and message[0] in self.channelIds:
                topic= None
                if message[1] == 'hb': #heartbeat
                    return
                if self.channelIds[message[0]] == "trades":
                    topic = "trade"
                    if len(message) == 2: # snapshot
                        for data in message[1]:
                            self.data[topic].append(data)
                    else: #update
                        if message[1] == "tu":
                            topic = "tradeupdate"
                        self.data[topic].append(message[2])

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
