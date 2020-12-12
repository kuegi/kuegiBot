import math
from typing import List

from kuegi_bot.indicators.indicator import Indicator, get_bar_value, highest, lowest, BarSeries, clean_range
from kuegi_bot.trade_engine import Bar
from kuegi_bot.utils import log

logger = log.setup_custom_logger()


class Data:
    def __init__(self, inner, hma, inner1, inner2):
        self.inner = inner
        self.inner1= inner1
        self.inner2= inner2
        self.hma = hma


class HMA(Indicator):
    ''' Hull Moving Average
        HMA[i] = MA( (2*MA(input, period/2) – MA(input, period)), SQRT(period))
    '''

    def __init__(self, period: int = 15):
        super().__init__(
            'HMA(' + str(period) + ')')
        self.period = period

    def on_tick(self, bars: List[Bar]):
        first_changed = 0
        for idx in range(len(bars)):
            if bars[idx].did_change:
                first_changed = idx
            else:
                break

        for idx in range(first_changed, -1, -1):
            self.process_bar(bars[idx:])

    def process_bar(self, bars: List[Bar]):
        if len(bars) < self.period:
            self.write_data(bars[0], Data(bars[0].close, bars[0].close,None,None))
            return

        prevData= self.get_data(bars[1])
        sum = 0
        sumhalf = 0
        halfLimit= int(self.period/2)
        if prevData is not None and prevData.inner1 is not None:
            sum= prevData.inner1*self.period
            sumhalf= prevData.inner2*halfLimit
            sum += bars[0].close - bars[self.period].close
            sumhalf += bars[0].close - bars[halfLimit].close
        else:
            for idx, sub in enumerate(bars[:self.period]):
                sum += sub.close
                if idx < halfLimit:
                    sumhalf += sub.close

        sum /= self.period
        sumhalf /= halfLimit

        inner = 2 * sumhalf - sum
        hmasum = inner
        hmalength = int(math.sqrt(self.period))
        cnt = 1
        for sub in bars[1:hmalength]:
            if self.get_data(sub) is not None:
                hmasum += self.get_data(sub).inner
                cnt += 1
        if cnt > 0:
            hmasum /= cnt

        self.write_data(bars[0], Data(inner, hmasum,sum,sumhalf))

    def get_line_names(self):
        return ["hma" + str(self.period)]

    def get_data_for_plot(self, bar: Bar):
        return [self.get_data(bar).hma]
