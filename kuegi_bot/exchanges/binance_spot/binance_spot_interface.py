import math
from datetime import datetime
from typing import List

from kuegi_bot.utils.trading_classes import Bar
from .binance_spot_websocket import BinanceSpotWebsocket
from ..ExchangeWithWS import ExchangeWithWS


class BinanceSpotInterface(ExchangeWithWS):

    def __init__(self, settings, logger, on_tick_callback=None, on_api_error=None):
        self.on_api_error = on_api_error
        self.m1_bars: List[Bar] = []
        hosts = ["wss://stream.binance.com:9443/stream"]  # no testnet on binance spot
        super().__init__(settings, logger,
                         ws=BinanceSpotWebsocket(wsURLs=hosts,
                                                 api_key=settings.API_KEY,
                                                 api_secret=settings.API_SECRET,
                                                 logger=logger,
                                                 callback=self.socket_callback,
                                                 symbol=settings.SYMBOL),
                         on_tick_callback=on_tick_callback)

    def init(self):
        self.ws.subscribeRealtimeData()
        self.logger.info("subscribed to data")

    def get_instrument(self, symbol=None):
        return None

    def initOrders(self):
        pass

    def initPositions(self):
        pass

    def get_ticker(self, symbol=None):
        pass

    def get_bars(self, timeframe_minutes, start_offset_minutes) -> List[Bar]:
        if timeframe_minutes == 1:
            return self.m1_bars
        else:
            raise NotImplementedError

    def socket_callback(self, topic):
        try:
            data = self.ws.get_data(topic)
            gotTick = False
            while len(data) > 0:
                if topic == 'aggTrade':
                    tstamp = int(data['T']/1000)
                    bar_time = math.floor(tstamp / 60) * 60
                    price = float(data['p'])
                    volume = float(data['q'])
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
                    if not data['m']:
                        last_bar.buyVolume += volume
                    else:
                        last_bar.sellVolume += volume

                data = self.ws.get_data(topic)

            # new bars is handling directly in the messagecause we get a new one on each tick
            if gotTick and self.on_tick_callback is not None:
                self.on_tick_callback(fromAccountAction=False)
        except Exception as e:
            self.logger.error("error in socket data(%s): %s " % (topic, str(e)))
