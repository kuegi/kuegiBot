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
        return [self.get_data(bar)]  # default

    def get_plot_offset(self):
        return 0

    def get_number_of_lines(self):
        return 1

    def get_line_styles(self):
        return [{"width": 1, "color": "blue"}]

    def get_line_names(self):
        return ["1"]


class MarketTrend(Indicator):
    ''' Market trend based on SMAs
    '''

    def __init__(self, slowMA: int, midMA: int, fastMA: int, veryfastMA: int):
        super().__init__('MarketTrend(' + str(slowMA) + ',' + str(midMA) + ',' + str(fastMA) + ',' + str(
            veryfastMA) + ')')
        self.slowMA = SMA(slowMA)
        self.midMA = SMA(midMA)
        self.fastMA = SMA(fastMA)
        self.veryfastMA = SMA(veryfastMA)
        self.markettrend = 0
        self.trend_buffer = 5

    def on_tick(self, bars: List[Bar]):
        self.slowMA.on_tick(bars)
        self.midMA.on_tick(bars)
        self.fastMA.on_tick(bars)
        self.veryfastMA.on_tick(bars)
        self.markettrend = self.calc_market_trend(bars)

    def get_market_trend(self):
        return self.markettrend

    def calc_market_trend(self, bars: List[Bar]):
        slowMA = self.slowMA.get_data(bars[1])
        midMA = self.midMA.get_data(bars[1])
        fastMA = self.fastMA.get_data(bars[1])
        veryfastMA = self.veryfastMA.get_data(bars[1])
        bar = bars[1]
        trend_buffer_threshold = 0
        buffer = 5

        if slowMA is not None and midMA is not None and fastMA is not None:
            if slowMA > midMA > fastMA > veryfastMA:
                self.trend_buffer -= 1
                if self.trend_buffer <= trend_buffer_threshold:
                    trend = -1 # bear
                else:
                    trend = 0  # ranging

                data = TrendData(trend*1000, slowMA, midMA, fastMA, veryfastMA)
                self.write_data(bars[1], data)
                return trend
            elif slowMA < midMA < fastMA < veryfastMA:
                self.trend_buffer -= 1
                if self.trend_buffer <= trend_buffer_threshold:
                    trend = 1  # bull
                else:
                    trend = 0  # ranging

                data = TrendData(trend * 1000, slowMA, midMA, fastMA, veryfastMA)
                self.write_data(bars[1], data)
                return trend
            else:
                trend = 0 # ranging
                self.trend_buffer = buffer # low pass filter for the ranging condition
                data = TrendData(trend * 1000, slowMA, midMA, fastMA, veryfastMA)
                self.write_data(bars[1],data)
                return trend
        else:
            trend = 0 #invalid
            self.trend_buffer = buffer
            data = TrendData(trend * 1000, bar.close, bar.close, bar.close, bar.close)
            self.write_data(bars[1], data)
            return trend

    def get_line_names(self):
        return ["MarketTrend",  "slowMA", "midMA", "fastMA", "verfastMA"]

    def get_number_of_lines(self):
        return 5

    def get_line_styles(self):
        return [{"width": 1, "color": "blue"},
                {"width": 1, "color": "red"},
                {"width": 1, "color": "orange"},
                {"width": 1, "color": "yellow"},
                {"width": 1, "color": "cyan"}]

    def get_data_for_plot(self, bar: Bar):
        data: TrendData = self.get_data(bar)
        if data is not None:
            return [data.trend, data.slowMA, data.midMA, data.fastMA, data.verfastMA]
        else:
            return [0, bar.close, bar.close, bar.close, bar.close]


class TrendData:
    def __init__(self,  trend, slowMA, midMA, fastMA, verfastMA):
        self.trend = trend
        self.slowMA = slowMA
        self.midMA = midMA
        self.fastMA = fastMA
        self.verfastMA = verfastMA


class SMA(Indicator):
    def __init__(self, period: int):
        super().__init__("SMA" + str(period))
        self.period = period

    def on_tick(self, bars: List[Bar]):
        first_changed = 0
        for idx in range(len(bars)):
            if bars[idx].did_change:
                first_changed = idx
            else:
                break

        for idx in range(first_changed, -1, -1):
            bar= bars[idx]
            if idx < len(bars) - self.period:
                sum = 0
                cnt = 0
                for sub in bars[idx:idx + self.period]:
                    sum += sub.close
                    cnt += 1

                sum /= cnt
                self.write_data(bar, sum)
            else:
                self.write_data(bar, None)

    def get_line_names(self):
        return ["sma" + str(self.period)]


class EMA(Indicator):
    def __init__(self, period: int):
        super().__init__("EMA" + str(period))
        self.period = period
        self.alpha = 2 / (1 + period)

    def on_tick(self, bars: List[Bar]):
        first_changed = 0
        for idx in range(len(bars)):
            if bars[idx].did_change:
                first_changed = idx
            else:
                break

        for idx in range(first_changed, -1, -1):
            bar = bars[idx]
            ema = bar.close
            last = self.get_data(bars[idx + 1]) if idx < len(bars) - 1 else None
            if last is not None:
                ema = bar.close * self.alpha + last * (1 - self.alpha)
            self.write_data(bar, ema)

    def get_line_names(self):
        return ["ema" + str(self.period)]


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
