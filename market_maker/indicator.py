from market_maker.utils import log
from market_maker.trade_engine import Bar

from typing import List

logger = log.setup_custom_logger('indicator')


class Indicator:
    def __init__(self,indiId:str):
        self.id= indiId
        pass

    def on_tick(self, bars:List[Bar]):
        pass

    def write_data(self,bar:Bar, data):
        if "indicators" not in bar.bot_data.keys():
            bar.bot_data['indicators']={}

        bar.bot_data["indicators"][self.id] = data

    def get_data(self,bar:Bar):
        return bar.bot_data["indicators"][self.id]

class SMA(Indicator):
    def __init__(self, period: int):
        super().__init__("SMA"+str(period))
        self.period = period

    def on_tick(self, bars:List[Bar]):
        for idx, bar in enumerate(bars):
            if bar.did_change:
                if idx < len(bars)-self.period:
                    sum= 0
                    cnt= 0
                    for sub in bars[idx:idx+self.period]:
                        sum += sub.open
                        cnt += 1

                    sum /= cnt
                    self.write_data(bar,sum)
                else:
                    self.write_data(bar,None)






