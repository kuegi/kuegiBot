from kuegi_bot.indicators.indicator import Indicator
from kuegi_bot.utils.trading_classes import Bar
from typing import List
import datetime
import numpy as np


class TAlibBars(Indicator):
    def __init__(self, close: List[float] = None, high: List[float] = None, low: List[float] = None, open: List[float] = None):
        super().__init__("TAlibBars")
        self.close = np.array(close) if close is not None else None
        self.high = np.array(high) if high is not None else None
        self.low = np.array(low) if low is not None else None
        self.open = np.array(open) if open is not None else None
        self.timestamps = None

        # Initialize daily candles
        self.close_daily = None
        self.high_daily = None
        self.low_daily = None
        self.open_daily = None

        # Initialize weekly candles
        self.close_weekly = None
        self.high_weekly = None
        self.low_weekly = None
        self.open_weekly = None

    def set_timestamps(self, bars: List[Bar]):
        self.timestamps = np.array([bar.tstamp for bar in reversed(bars[1:])])

    def on_tick(self, bars: List[Bar]):
        if self.close is None or self.open is None or self.high is None or self.low is None:
            self.reset_candles(bars)
        else:
            self.close = np.append(self.close, bars[1].close)
            self.high = np.append(self.high, bars[1].high)
            self.low = np.append(self.low, bars[1].low)
            self.open = np.append(self.open, bars[1].open)

            self._update_daily_candles(bars[1].tstamp)
            self._update_weekly_candles(bars[1].tstamp)

        if not self.is_synchronized(bars):
            # Resynchronize the data
            self.reset_candles(bars)

    def is_synchronized(self, bars: List[Bar]):
        return len(bars) - 1 == len(self.close)

    def reset_candles(self, bars: List[Bar]):
        # 4H
        close = np.array([bar.close for bar in reversed(bars[1:])])
        high = np.array([bar.high for bar in reversed(bars[1:])])
        low = np.array([bar.low for bar in reversed(bars[1:])])
        open = np.array([bar.open for bar in reversed(bars[1:])])
        self.close = close
        self.high = high
        self.low = low
        self.open = open
        self.set_timestamps(bars)

        # daily & weekly
        self._reset_daily_candles()
        self._reset_weekly_candles()
        self._repopulate_daily_candles()
        self._repopulate_weekly_candles()

    def _update_daily_candles(self, last_tstamp):
        last_date = datetime.datetime.utcfromtimestamp(last_tstamp)
        if last_date.hour == 20 and len(self.close) >= 7:
            close_daily = self.close[-1]
            high_daily = max(self.high[-6:])
            low_daily = min(self.low[-6:])
            open_daily = self.open[-6]

            if self.close_daily is None:
                self.close_daily = np.array([close_daily])
                self.high_daily = np.array([high_daily])
                self.low_daily = np.array([low_daily])
                self.open_daily = np.array([open_daily])
            else:
                self.close_daily = np.append(self.close_daily, close_daily)
                self.high_daily = np.append(self.high_daily, high_daily)
                self.low_daily = np.append(self.low_daily, low_daily)
                self.open_daily = np.append(self.open_daily, open_daily)

    def _update_weekly_candles(self, last_tstamp):
        last_date = datetime.datetime.utcfromtimestamp(last_tstamp)
        if last_date.weekday() == 0 and last_date.hour == 0 and len(self.close) > (4 * 6 *7):  # Sunday TODO: make adaptable to timeframe
            close_weekly = self.close_daily[-1]
            high_weekly = max(self.high_daily[-7:])
            low_weekly = min(self.low_daily[-7:])
            open_weekly = self.open_daily[-7]

            if self.close_weekly is None:
                self.close_weekly = np.array([close_weekly])
                self.high_weekly = np.array([high_weekly])
                self.low_weekly = np.array([low_weekly])
                self.open_weekly = np.array([open_weekly])
            else:
                self.close_weekly = np.append(self.close_weekly, close_weekly)
                self.high_weekly = np.append(self.high_weekly, high_weekly)
                self.low_weekly = np.append(self.low_weekly, low_weekly)
                self.open_weekly = np.append(self.open_weekly, open_weekly)

    def _repopulate_daily_candles(self):
        if self.close is None or len(self.close) < 6:
            return

        daily_candle_start_index = self._find_daily_candle_start_index()
        if daily_candle_start_index is None or len(self.close) < daily_candle_start_index+6:
            return

        open_indices = range(daily_candle_start_index, len(self.open), 6)
        close_indices = range(daily_candle_start_index+5, len(self.close), 6)
        self.open_daily = self.open[open_indices]
        self.close_daily = self.close[close_indices]
        self.high_daily = np.array([max(self.high[i:i + 6]) for i in open_indices])
        self.low_daily = np.array([min(self.low[i:i + 6]) for i in open_indices])

    def _find_daily_candle_start_index(self):
        if self.timestamps is None or len(self.timestamps) == 0:
            return None

        desired_start_hour = 0  # Change this to the desired starting hour of the daily candle, e.g., 4 for 4 AM
        for i, tstamp in enumerate(self.timestamps):
            dt = datetime.datetime.utcfromtimestamp(tstamp)
            if dt.hour == desired_start_hour:
                return i

        return None

    def _find_weekly_candle_start_index(self):
        if self.timestamps is None or len(self.timestamps) == 0 or self.close_daily is None:
            return None

        daily_candle_start_index = self._find_daily_candle_start_index()
        if daily_candle_start_index is None:
            return None

        daily_timestamps = self.timestamps[daily_candle_start_index::6]  # Convert 4H timestamps to daily timestamps
        for i, tstamp in enumerate(daily_timestamps):
            dt = datetime.datetime.utcfromtimestamp(tstamp)
            if dt.weekday() == 0:  # Start of the week (Monday)
                return i

        return None

    def _repopulate_weekly_candles(self):
        weekly_candle_start_index = self._find_weekly_candle_start_index()
        if weekly_candle_start_index is None or self.close_daily is None or len(self.close_daily) < (weekly_candle_start_index + 7):
            return

        open_indices = range(weekly_candle_start_index,len(self.open_daily), 7)
        close_indices = range(weekly_candle_start_index + 6, len(self.close_daily), 7)
        self.open_weekly = self.open_daily[open_indices]
        self.close_weekly = self.close_daily[close_indices]
        self.high_weekly = np.array([max(self.high_daily[i:i + 7]) for i in open_indices])
        self.low_weekly = np.array([min(self.low_daily[i:i + 7]) for i in open_indices])

    def _reset_daily_candles(self):
        self.close_daily = None
        self.high_daily = None
        self.low_daily = None
        self.open_daily = None

    def _reset_weekly_candles(self):
        self.close_weekly = None
        self.high_weekly = None
        self.low_weekly = None
        self.open_weekly = None