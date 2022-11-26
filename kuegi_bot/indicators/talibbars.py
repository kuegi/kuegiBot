from kuegi_bot.indicators.indicator import Indicator
from kuegi_bot.utils.trading_classes import Bar
from typing import List

import numpy as np


class TAlibBars(Indicator):
    def __init__(self):
        super().__init__("TAlibBars")
        self.close = List[float]
        self.high = List[float]
        self.low = List[float]

    def on_tick(self, bars: List[Bar]):
        size = len(bars)-1
        close = np.ndarray(size)
        high = np.ndarray(size)
        low = np.ndarray(size)
        i = 0
        while i < size:
            close[i] = bars[size-i].close
            high[i] = bars[size - i].high
            low[i] = bars[size - i].low
            i = i + 1
        self.close = close
        self.high = high
        self.low = low