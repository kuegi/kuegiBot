from market_maker.utils import log
from market_maker.trade_engine import Bar

from typing import List

from enum import Enum


class BarSeries(Enum):
    OPEN = "open"
    HIGH = "high"
    LOW = "low"
    CLOSE = "close"
    VOLUME = "volume"

logger = log.setup_custom_logger('indicator')


def get_bar_value(bar:Bar,series:BarSeries):
    return getattr(bar,series.value)


def highest(bars: List[Bar], length: int, offset: int, series: BarSeries):
    result: float = get_bar_value(bars[offset], series)
    for idx in range(offset, offset + length):
        if result < get_bar_value(bars[idx], series):
            result = get_bar_value(bars[idx], series)
    return result


def lowest(bars: List[Bar], length: int, offset: int, series: BarSeries):
    result: float = get_bar_value(bars[offset], series)
    for idx in range(offset, offset + length):
        if result > get_bar_value(bars[idx], series):
            result = get_bar_value(bars[idx], series)
    return result


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
        if 'indicators' in bar.bot_data.keys() and self.id in bar.bot_data['indicators'].keys():
            return bar.bot_data["indicators"][self.id]
        else:
            return None

    def get_data_for_plot(self,bar:Bar):
        return self.get_data(bar) #default

    def get_plot_offset(self):
        return 0

    def get_number_of_lines(self):
        return 1

    def get_line_styles(self):
        return [{"width":1,"color":"blue"}]

    def get_line_names(self):
        return ["1"]


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






