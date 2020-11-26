import time
from datetime import datetime, timedelta
from dateutil import tz
import json
import os
from typing import List

from kuegi_bot.exchanges.bitstamp.bitstmap_interface import BitstampInterface
from kuegi_bot.utils.dotdict import dotdict
from kuegi_bot.utils.trading_classes import Bar


class VolubaData:
    def __init__(self,tstamp):
        self.tstamp : int = tstamp
        self.barsByExchange = {}


class VolubaAggregator:

    def __init__(self,settings,logger):
        self.exchanges= {}
        self.logger= logger
        self.m1Data = {}
        # read last data
        # init exchanges from settings
        for exset in settings.exchanges:
            exset= dotdict(exset)
            if exset.id == "bitstamp":
                ex= BitstampInterface(settings=exset,logger=logger)
                self.exchanges[exset.id]= ex

    def aggregate_data(self):
        for exId,exchange in self.exchanges.items():
            m1bars= exchange.get_bars(1,0)
            for bar in m1bars:
                if bar.tstamp not in self.m1Data:
                    self.m1Data[bar.tstamp]= VolubaData(bar.tstamp)
                self.m1Data[bar.tstamp].barsByExchange[exId]= bar

    def serialize_current_data(self):
        base = 'voluba/'
        try:
            os.makedirs(base)
        except Exception:
            pass

        try:
            data:List[VolubaData]= sorted(self.m1Data.values(), key=lambda d: d.tstamp)

            today = datetime.today()
            startOfToday = datetime(today.year, today.month, today.day, tzinfo=tz.tzutc()).timestamp()
            yesterday= today - timedelta(days=1)
            now = time.time()

            last60Min= []
            todayData= []
            yesterdayData= []

            for d in data:
                dic= dict(d.__dict__)
                for ex,bar in d.barsByExchange.items():
                    bard= dict(bar.__dict__)
                    if "did_change" in bard:
                        del bard['did_change']
                    if "bot_data" in bard:
                        del bard['bot_data']
                    if "subbars" in bard:
                        del bard['subbars']
                    dic['barsByExchange'][ex]=bard
                if d.tstamp >= now - 60*60:
                    last60Min.append(dic)
                if d.tstamp >= startOfToday:
                    todayData.append(dic)
                if startOfToday - 1440 <= d.tstamp < startOfToday:
                    yesterdayData.append(dic)

            string = json.dumps(last60Min, sort_keys=False, indent=4)
            with open(base + "last60Min.json", 'w') as file:
                file.write(string)

            string = json.dumps(todayData, sort_keys=False, indent=4)
            with open(base + today.strftime("%Y%m%d.json"), 'w') as file:
                file.write(string)

            string = json.dumps(yesterdayData, sort_keys=False, indent=4)
            with open(base + yesterday.strftime("%Y%m%d.json"), 'w') as file:
                file.write(string)

            #also write last two days
        except Exception as e:
            self.logger.error("Error saving data " + str(e))
            raise e