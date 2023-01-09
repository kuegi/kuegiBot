from kuegi_bot.indicators.indicator import Indicator
from kuegi_bot.utils.trading_classes import Bar
from typing import List

import numpy as np


class TAlibBars(Indicator):
    def __init__(self, close: List[float] = None, high: List[float] = None, low: List[float] = None, open: List[float] = None):
        super().__init__("TAlibBars")
        self.close = close
        self.high = high
        self.low = low
        self.open = open

    def on_tick(self, bars: List[Bar]):
        if self.close is None or self.open is None or self.high is None or self.low is None:
            self.update_candles(bars)
        else:
            length = len(self.close)
            size = len(bars)
            idx = 1
            while idx < size-length:
                self.close = np.append(self.close, bars[idx].close)
                self.high = np.append(self.high, bars[idx].high)
                self.low = np.append(self.low, bars[idx].low)
                self.open = np.append(self.open, bars[idx].open)
                idx += 1
        if len(bars) != len(self.close) != len(self.open) != len(self.high) != len(self.low):
            self.update_candles(bars)

    def update_candles(self, bars: List[Bar]):
        size = len(bars)-1
        close = np.ndarray(size)
        high = np.ndarray(size)
        low = np.ndarray(size)
        open = np.ndarray(size)
        i = 0
        while i < size:
            close[i] = bars[size - i].close
            high[i] = bars[size - i].high
            low[i] = bars[size - i].low
            open[i] = bars[size - i].open
            i += 1
        self.close = close
        self.high = high
        self.low = low
        self.open = open