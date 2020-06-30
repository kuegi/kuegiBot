from typing import List

from kuegi_bot.indicators.indicator import Indicator, BarSeries, lowest, highest
from kuegi_bot.utils.trading_classes import Bar


class Data:
    def __init__(self, swingHigh, swingLow):
        self.swingHigh = swingHigh
        self.swingLow = swingLow


class Swings(Indicator):

    def __init__(self, before: int = 2, after: int = 2):
        super().__init__("Swings(" + str(before) + "," + str(after) + ")")
        self.before = before
        self.after = after

    def on_tick(self, bars: List[Bar]):
        # ignore first bars
        for idx in range(len(bars) - self.before - self.after-2, -1, -1):
            if bars[idx].did_change:
                self.process_bar(bars[idx:])

    def process_bar(self, bars: List[Bar]):
        prevData: Data = self.get_data(bars[1])

        swingHigh = prevData.swingHigh if prevData is not None else None
        highestAfter = highest(bars, self.after, 1, BarSeries.HIGH)
        candidate = bars[self.after + 1].high
        highestBefore = highest(bars, self.before, self.after + 2, BarSeries.HIGH)
        if highestAfter <= candidate and highestBefore <= candidate:
            swingHigh = candidate
        if swingHigh is not None and bars[0].high > swingHigh:
            swingHigh= None

        swingLow = prevData.swingLow if prevData is not None else None
        lowestAfter = lowest(bars, self.after, 1, BarSeries.LOW)
        candidate = bars[self.after + 1].low
        lowestBefore = lowest(bars, self.before, self.after + 2, BarSeries.LOW)
        if lowestAfter >= candidate and lowestBefore >= candidate:
            swingLow = candidate
        if swingLow is not None and bars[0].low < swingLow:
            swingLow= None

        self.write_data(bars[0], Data(swingHigh=swingHigh, swingLow=swingLow))

    def get_data_for_plot(self, bar: Bar):
        data: Data = self.get_data(bar)
        if data is not None:
            return [data.swingHigh, data.swingLow]
        else:
            return [bar.close, bar.close]

    def get_plot_offset(self):
        return 1

    def get_number_of_lines(self):
        return 2

    def get_line_styles(self):
        return [{"width": 1, "color": "green"}, {"width": 1, "color": "red"}]

    def get_line_names(self):
        return ["swingHigh", "swingLow"]
