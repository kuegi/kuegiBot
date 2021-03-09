import math
from typing import List

from kuegi_bot.utils.trading_classes import Bar
from .bitstamp_websocket import BitstampWebsocket
from ..ExchangeWithWS import ExchangeWithWS


class BitstampInterface(ExchangeWithWS):

    def __init__(self, settings, logger, on_tick_callback=None, on_api_error=None):
        self.on_api_error = on_api_error
        self.m1_bars: List[Bar] = []
        hosts = ["wss://ws.bitstamp.net/"]  # no testnet on bitstamp
        super().__init__(settings, logger,
                         ws=BitstampWebsocket(wsURLs=hosts,
                                              api_key=settings.API_KEY,
                                              api_secret=settings.API_SECRET,
                                              logger=logger,
                                              callback=self.socket_callback,
                                              symbol=settings.SYMBOL),
                         on_tick_callback=on_tick_callback)

    def init(self):
        self.ws.subscribe_realtime_data()
        self.logger.info("subscribed to data")

    def get_instrument(self, symbol=None):
        return None

    def initOrders(self):
        pass

    def initPositions(self):
        pass

    def get_ticker(self, symbol=None):
        pass

    def get_bars(self, timeframe_minutes, start_offset_minutes, min_bars_needed) -> List[Bar]:
        if timeframe_minutes == 1:
            return self.m1_bars
        else:
            raise NotImplementedError

    def socket_callback(self, topic):
        try:
            data = self.ws.get_data(topic)
            gotTick = False
            while len(data) > 0:
                if topic == 'trade':
                    tstamp = int(data['timestamp'])
                    bar_time = math.floor(tstamp / 60) * 60
                    price = data['price']
                    volume = data['amount']
                    if len(self.m1_bars) > 0 and self.m1_bars[-1].tstamp == bar_time:
                        last_bar = self.m1_bars[-1]
                    else:
                        last_bar = Bar(tstamp=bar_time, open=price, high=price, low=price, close=price, volume=0)
                        self.m1_bars.append(last_bar)
                        gotTick = True
                    last_bar.close = price
                    last_bar.low = min(last_bar.low, price)
                    last_bar.high = max(last_bar.high, price)
                    last_bar.volume += volume
                    last_bar.last_tick_tstamp = tstamp
                    if data['type'] == 0:
                        last_bar.buyVolume += volume
                    else:
                        last_bar.sellVolume += volume

                data = self.ws.get_data(topic)

            # new bars is handling directly in the messagecause we get a new one on each tick
            if gotTick and self.on_tick_callback is not None:
                self.on_tick_callback(fromAccountAction=False)
        except Exception as e:
            self.logger.error("error in socket data(%s): %s " % (topic, str(e)))
