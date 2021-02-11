import math
from typing import List

from kuegi_bot.indicators.indicator import Indicator, get_bar_value, highest, lowest, BarSeries, clean_range
from kuegi_bot.trade_engine import Bar
from kuegi_bot.utils import log

logger = log.setup_custom_logger()


class Data:
    def __init__(self,  hma, hmasum, inner, inner1, inner2):
        self.inner = inner
        self.inner1= inner1
        self.inner2= inner2
        self.hmasum= hmasum
        self.hma = hma


class HMA(Indicator):
    ''' Hull Moving Average
        HMA[i] = MA( (2*MA(input, period/2) – MA(input, period)), SQRT(period))
    '''

    def __init__(self, period: int = 15, maType: int= 0):
        super().__init__(
            'HMA(' + str(period) + ','+str(maType)+')')
        self.period = period
        self.halfperiod= int(self.period/2)
        self.hmalength = int(math.sqrt(self.period))
        self.maType= maType

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
            self.write_data(bars[0], Data(hma=bars[0].close, hmasum=None,
                                          inner=bars[0].close, inner1=None,inner2=None))
            return

        prevData= self.get_data(bars[1])
        inner1 = 0
        inner2 = 0
        inner= 0
        if self.maType == 0:
            if prevData is not None and prevData.inner1 is not None:
                inner1= prevData.inner1
                inner2= prevData.inner2
                inner1 += bars[0].close - bars[self.period].close
                inner2 += bars[0].close - bars[self.halfperiod].close
            else:
                for idx, sub in enumerate(bars[:self.period]):
                    inner1 += sub.close
                    if idx < self.halfperiod:
                        inner2 += sub.close

            inner = (2 * inner2 / self.halfperiod) - inner1 / self.period
        elif self.maType == 1:
            for idx, sub in enumerate(bars[:self.period]):
                inner1 += sub.close*(self.period-idx)/self.period
                if idx < self.halfperiod:
                    inner2 += sub.close*(self.halfperiod-idx)/self.halfperiod

            inner = (2 * inner2*2/(self.halfperiod+1)) - inner1*2/(self.period+1)


        hmasum= 0
        hma = 0
        if self.maType == 0:
            cnt=1
            firstInner = self.get_data(bars[self.hmalength])
            if firstInner is not None and firstInner.inner is not None and prevData.hmasum is not None:
                hmasum = prevData.hmasum
                hmasum += inner - firstInner.inner
                cnt = self.hmalength
            else:
                hmasum = inner
                cnt = 1
                for sub in bars[1:self.hmalength]:
                    if self.get_data(sub) is not None:
                        hmasum += self.get_data(sub).inner
                        cnt += 1
            hma= hmasum/cnt
        elif self.maType == 1:
            hmasum = inner #*(self.hmalength)/(self.hmalength)
            for idx, sub in enumerate(bars[1:self.hmalength]):
                if self.get_data(sub) is not None:
                    hmasum += self.get_data(sub).inner*(self.hmalength-(idx+1))/(self.hmalength)
                else:
                    hmasum += sub.close*(self.hmalength-(idx+1))/(self.hmalength)

            hma= hmasum*2/(self.hmalength+1)

        self.write_data(bars[0], Data(hma=hma, hmasum=hmasum,
                                      inner=inner, inner1=inner1, inner2=inner2))

    def get_line_names(self):
        return ["hma" + str(self.period)]

    def get_data_for_plot(self, bar: Bar):
        return [self.get_data(bar).hma]
