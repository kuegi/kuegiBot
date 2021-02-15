import math
from typing import List

from kuegi_bot.indicators.indicator import Indicator, get_bar_value, highest, lowest, BarSeries, clean_range
from kuegi_bot.trade_engine import Bar
from kuegi_bot.utils import log

logger = log.setup_custom_logger()


class Data:
    def __init__(self,  mean, std, sum):
        self.mean = mean
        self.std= std
        self.sum= sum


class MeanStd(Indicator):
    ''' Mean and Standard deviation
    '''

    def __init__(self, period: int):
        super().__init__("MeanStd" + str(period))
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
                data = self.get_data(bar)
                sum = 0
                sqsum= 0
                if data is not None:
                    sum = data.sum + bar.close - bars[idx+self.period].close
                else:
                    for sub in bars[idx:idx + self.period]:
                        sum += sub.close
                mean = sum/self.period

                for sub in bars[idx:idx + self.period]:
                    sqsum += (sub.close-mean)*(sub.close-mean)/self.period
                self.write_data(bar, Data(mean=mean,std= math.sqrt(sqsum),sum=sum))
            else:
                self.write_data(bar, None)

    def get_number_of_lines(self):
        return 3

    def get_line_styles(self):
        return [{"width": 1, "color": "blue"},
                {"width": 1, "color": "orange"},
                {"width": 1, "color": "orange"}
                ]

    def get_line_names(self):
        return ["mean" + str(self.period),
                "mean+std" + str(self.period),
                "mean-std" + str(self.period)
        ]

    def get_data_for_plot(self, bar: Bar):
        data= self.get_data(bar)
        if data is not None:
            return [data.mean, data.mean+data.std, data.mean-data.std]
        else:
            return [None, None, None]
