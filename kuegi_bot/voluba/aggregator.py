import time
from datetime import datetime, timedelta
from dateutil import tz
import json
import os
from typing import List

from kuegi_bot.exchanges.binance_spot.binance_spot_interface import BinanceSpotInterface
from kuegi_bot.exchanges.bitfinex.bitfinex_interface import BitfinexInterface
from kuegi_bot.exchanges.bitstamp.bitstmap_interface import BitstampInterface
from kuegi_bot.exchanges.coinbase.coinbase_interface import CoinbaseInterface
from kuegi_bot.exchanges.huobi.huobi_interface import HuobiInterface
from kuegi_bot.exchanges.kraken.kraken_interface import KrakenInterface
from kuegi_bot.utils.dotdict import dotdict
from kuegi_bot.utils.trading_classes import Bar


class VolubaData:
    def __init__(self, tstamp):
        self.tstamp: int = tstamp
        self.barsByExchange = {}


class VolubaAggregator:

    def __init__(self, settings, logger):
        self.settings = settings
        self.exchanges = {}
        self.logger = logger
        self.m1Data = {}

        base = self.settings.dataPath
        try:
            os.makedirs(base)
        except Exception:
            pass

        # read last data
        # init exchanges from settings
        self.read_data()
        for exset in settings.exchanges:
            exset = dotdict(exset)
            ex= None
            if exset.id == "bitstamp":
                ex = BitstampInterface(settings=exset, logger=logger)
            if exset.id == "binance":
                ex = BinanceSpotInterface(settings=exset, logger=logger)
            if exset.id == "huobi":
                ex = HuobiInterface(settings=exset, logger=logger)
            if exset.id == "coinbase":
                ex = CoinbaseInterface(settings=exset, logger=logger)
            if exset.id == "kraken":
                ex = KrakenInterface(settings=exset, logger=logger)
            if exset.id == "bitfinex":
                ex = BitfinexInterface(settings=exset, logger=logger)
            if ex is not None:
                self.exchanges[exset.id] = ex

    def aggregate_data(self):
        for exId, exchange in self.exchanges.items():
            m1bars = exchange.get_bars(1, 0)
            for bar in m1bars:
                if bar.tstamp not in self.m1Data:
                    self.m1Data[bar.tstamp] = VolubaData(bar.tstamp)
                self.m1Data[bar.tstamp].barsByExchange[exId] = bar

    def read_data_file(self, filename):
        try:
            with open(filename, 'r') as file:
                data = json.load(file)
                for entry in data:
                    d = VolubaData(entry['tstamp'])
                    for exchange, bar in entry['barsByExchange'].items():
                        bar = dotdict(bar)
                        b = Bar(tstamp=bar.tstamp,
                                open=bar.open,
                                high=bar.high,
                                low=bar.low,
                                close=bar.close,
                                volume=bar.volume)
                        b.buyVolume = bar.buyVolume
                        b.sellVolume = bar.sellVolume
                        d.barsByExchange[exchange] = b
                    self.m1Data[entry['tstamp']] = d

        except Exception as e:
            self.logger.error("Error reading data " + str(e))

    def read_data(self):
        base = self.settings.dataPath
        today = datetime.today()
        for delta in range(0, 4):
            date = today - timedelta(days=delta)
            self.read_data_file(base + date.strftime("%Y-%m-%d.json"))

    def serialize_current_data(self):
        base = self.settings.dataPath
        try:
            data: List[VolubaData] = sorted(self.m1Data.values(), key=lambda d: d.tstamp)

            today = datetime.today()
            startOfToday = datetime(today.year, today.month, today.day, tzinfo=tz.tzutc()).timestamp()
            yesterday = today - timedelta(days=1)
            now = time.time()

            latest = []
            todayData = []
            yesterdayData = []

            for d in data:
                dic = {'tstamp': d.tstamp,
                       'barsByExchange': {}
                       }
                for ex, bar in d.barsByExchange.items():
                    bard = dict(bar.__dict__)
                    if "did_change" in bard:
                        del bard['did_change']
                    if "bot_data" in bard:
                        del bard['bot_data']
                    if "subbars" in bard:
                        del bard['subbars']
                    dic['barsByExchange'][ex] = bard
                if d.tstamp >= now - 3 * 60:
                    latest.append(dic)
                if d.tstamp >= startOfToday:
                    todayData.append(dic)
                if startOfToday - 1440 * 60 <= d.tstamp < startOfToday:
                    yesterdayData.append(dic)

                # clear old data (2 days for extra buffer)
                if d.tstamp < startOfToday - 1440 * 60 * 2:
                    del self.m1Data[d.tstamp]

            string = json.dumps(latest, sort_keys=False, indent=4)
            with open(base + "latest.json", 'w') as file:
                file.write(string)

            string = json.dumps(todayData, sort_keys=False, indent=4)
            with open(base + today.strftime("%Y-%m-%d.json"), 'w') as file:
                file.write(string)

            string = json.dumps(yesterdayData, sort_keys=False, indent=4)
            with open(base + yesterday.strftime("%Y-%m-%d.json"), 'w') as file:
                file.write(string)

            # also write last two days
        except Exception as e:
            self.logger.error("Error saving data " + str(e))
