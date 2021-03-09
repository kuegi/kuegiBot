import math
from typing import List

from kuegi_bot.utils.trading_classes import Bar
from .bitfinex_websocket import BitfinexWebsocket
from ..ExchangeWithWS import ExchangeWithWS


class BitfinexInterface(ExchangeWithWS):

    def __init__(self, settings, logger, on_tick_callback=None, on_api_error=None):
        self.on_api_error = on_api_error
        self.m1_bars: List[Bar] = []
        hosts = ["wss://api-pub.bitfinex.com/ws/2"]  # no testnet on spot
        super().__init__(settings, logger,
                         ws=BitfinexWebsocket(wsURLs=hosts,
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
            if len(self.m1_bars) > 0:
                self.recalcBar(self.m1_bars[-1])
            return self.m1_bars
        else:
            raise NotImplementedError

    @staticmethod
    def recalcBar(bar:Bar):
        if "trades" not in bar.bot_data or len(bar.bot_data['trades']) == 0:
            return
        lastTstamp= 0
        firstTstamp= bar.last_tick_tstamp
        bar.volume= 0
        bar.buyVolume= 0
        bar.sellVolume= 0
        bar.high= bar.low= list(bar.bot_data['trades'].values())[0][3]
        for data in bar.bot_data['trades'].values():
            tstamp = int(data[1])/1000
            price = data[3]
            volume = abs(data[2])
            isBuy= data[2] > 0

            if tstamp > lastTstamp:
                bar.close = price
                lastTstamp= tstamp
            if tstamp<= firstTstamp:
                bar.open= price
                firstTstamp= tstamp
            bar.low = min(bar.low, price)
            bar.high = max(bar.high, price)
            bar.volume += volume
            bar.last_tick_tstamp = tstamp
            if isBuy:
                bar.buyVolume += volume
            else:
                bar.sellVolume += volume

    def socket_callback(self, topic):
        try:
            data = self.ws.get_data(topic)
            gotTick = False
            while len(data) > 0:
                if topic == 'trade':
                    tstamp = int(data[1])/1000
                    bar_time = math.floor(tstamp / 60) * 60
                    price = data[3]
                    volume = abs(data[2])
                    isBuy= data[2] > 0

                    if len(self.m1_bars) > 0 and self.m1_bars[-1].tstamp == bar_time:
                        last_bar = self.m1_bars[-1]
                    else:
                        if len(self.m1_bars) > 0:
                            self.recalcBar(self.m1_bars[-1])
                        for bar in self.m1_bars[-5:-2]:
                            if "trades" in bar.bot_data:
                                del bar.bot_data['trades']
                        last_bar = Bar(tstamp=bar_time, open=price, high=price, low=price, close=price, volume=0)
                        last_bar.bot_data['trades']= {}
                        self.m1_bars.append(last_bar)
                        gotTick = True
                    last_bar.close = price
                    last_bar.low = min(last_bar.low, price)
                    last_bar.high = max(last_bar.high, price)
                    last_bar.volume += volume
                    last_bar.last_tick_tstamp = tstamp
                    last_bar.bot_data['trades'][data[0]]= data
                    if isBuy:
                        last_bar.buyVolume += volume
                    else:
                        last_bar.sellVolume += volume

                if topic == 'tradeupdate':
                    tstamp = int(data[1])/1000
                    bar_time = math.floor(tstamp / 60) * 60
                    found= False
                    for i in range(len(self.m1_bars)):
                        bar = self.m1_bars[-i-1]
                        if bar_time == bar.tstamp:
                            found= True
                            if "trades" in bar.bot_data:
                                if data[0] not in bar.bot_data['trades']:
                                    self.logger.warn("got trade update before trade entry")
                                bar.bot_data['trades'][data[0]]=data
                            else:
                                self.logger.error("wanted to update trade but no trades in bar at index -"+str(i+1))
                            if i > 0:
                                # need to recalc, cause wasn't last bar that changed
                                self.recalcBar(bar)
                            break

                    if not found:
                        self.logger.error("didn't find bar for trade to update! "+str(data))

                data = self.ws.get_data(topic)

            # new bars is handling directly in the messagecause we get a new one on each tick
            if gotTick and self.on_tick_callback is not None:
                self.on_tick_callback(fromAccountAction=False)
        except Exception as e:
            self.logger.error("error in socket data(%s): %s " % (topic, str(e)))
