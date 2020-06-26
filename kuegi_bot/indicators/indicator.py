from kuegi_bot.utils import log

from typing import List

from enum import Enum

from kuegi_bot.utils.trading_classes import Bar


class BarSeries(Enum):
    OPEN = "open"
    HIGH = "high"
    LOW = "low"
    CLOSE = "close"
    VOLUME = "volume"


logger = log.setup_custom_logger()


def get_bar_value(bar: Bar, series: BarSeries):
    return getattr(bar, series.value)


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
    def __init__(self, indiId: str):
        self.id = indiId
        pass

    def on_tick(self, bars: List[Bar]):
        pass

    def write_data(self, bar: Bar, data):
        self.write_data_static(bar, data, self.id)

    @staticmethod
    def write_data_static(bar: Bar, data, indiId: str):
        if "indicators" not in bar.bot_data.keys():
            bar.bot_data['indicators'] = {}

        bar.bot_data["indicators"][indiId] = data

    def get_data(self,bar:Bar):
        return self.get_data_static(bar, self.id)

    @staticmethod
    def get_data_static(bar: Bar, indiId:str):
        if 'indicators' in bar.bot_data.keys() and indiId in bar.bot_data['indicators'].keys():
            return bar.bot_data["indicators"][indiId]
        else:
            return None

    def get_data_for_plot(self, bar: Bar):
        return self.get_data(bar)  # default

    def get_plot_offset(self):
        return 0

    def get_number_of_lines(self):
        return 1

    def get_line_styles(self):
        return [{"width": 1, "color": "blue"}]

    def get_line_names(self):
        return ["1"]


class SMA(Indicator):
    def __init__(self, period: int):
        super().__init__("SMA" + str(period))
        self.period = period

    def on_tick(self, bars: List[Bar]):
        for idx, bar in enumerate(bars):
            if bar.did_change:
                if idx < len(bars) - self.period:
                    sum = 0
                    cnt = 0
                    for sub in bars[idx:idx + self.period]:
                        sum += sub.open
                        cnt += 1

                    sum /= cnt
                    self.write_data(bar, sum)
                else:
                    self.write_data(bar, None)


from functools import reduce


def clean_range(bars: List[Bar], offset: int, length: int):
    ranges = []
    for idx in range(offset, offset + length):
        if idx < len(bars):
            ranges.append(bars[idx].high - bars[idx].low)

    ranges.sort(reverse=True)

    # ignore the biggest 10% of ranges
    ignored_count = int(length / 5)
    sum = reduce(lambda x1, x2: x1 + x2, ranges[ignored_count:])
    return sum / (len(ranges) - ignored_count)
