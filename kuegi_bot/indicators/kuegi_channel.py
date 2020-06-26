from typing import List

from kuegi_bot.indicators.indicator import Indicator, get_bar_value, highest, lowest, BarSeries, clean_range
from kuegi_bot.trade_engine import Bar
from kuegi_bot.utils import log

logger = log.setup_custom_logger()

class Data:
    def __init__(self, sinceLongReset, sinceShortReset, longTrail, shortTrail, longSwing, shortSwing, buffer, atr):
        self.sinceLongReset = sinceLongReset
        self.sinceShortReset = sinceShortReset
        self.longTrail = longTrail
        self.shortTrail = shortTrail
        self.longSwing = longSwing
        self.shortSwing = shortSwing
        self.buffer = buffer
        self.atr = atr


class KuegiChannel(Indicator):
    ''' calculates trails and swings
    if the price makes a strong move the trail goes to the start of the move.
    there is also a max dist for the trail from the neg.extr of the last X bars

    swings must be confirmed by 2 bars before and 1 bar after the swing.

    a strong move resets the swings. the bar of the move is never considered a swing point

    '''
    def __init__(self, max_look_back: int = 15, threshold_factor: float = 0.9, buffer_factor: float = 0.05,
                 max_dist_factor: float = 2, max_swing_length: int = 3):
        super().__init__(
            'KuegiChannel(' + str(max_look_back) + ',' + str(threshold_factor) + ',' + str(buffer_factor) + ',' + str(
                max_dist_factor) + ')')
        self.max_look_back = max_look_back
        self.threshold_factor = threshold_factor
        self.buffer_factor = buffer_factor
        self.max_dist_factor = max_dist_factor
        self.max_swing_length = max_swing_length

    def on_tick(self, bars: List[Bar]):
        # ignore first 5 bars
        for idx in range(len(bars) - self.max_look_back, -1, -1):
            if bars[idx].did_change:
                self.process_bar(bars[idx:])

    def get_data_for_plot(self, bar: Bar):
        data: Data = self.get_data(bar)
        if data is not None:
            return [data.longTrail, data.shortTrail, data.longSwing, data.shortSwing]
        else:
            return [bar.close, bar.close, bar.close, bar.close]

    def get_plot_offset(self):
        return 1

    def get_number_of_lines(self):
        return 4

    def get_line_styles(self):
        return [{"width": 1, "color": "darkGreen", "dash": "dot"},
                {"width": 1, "color": "darkRed", "dash": "dot"},
                {"width": 1, "color": "green"},
                {"width": 1, "color": "red"}]

    def get_line_names(self):
        return ["longTrail", "shortTrail", "longSwing", "shortSwing"]

    def process_bar(self, bars: List[Bar]):
        atr = clean_range(bars, offset=0, length=self.max_look_back * 2)

        offset = 1
        move_length = 1
        if (bars[offset].high - bars[offset].low) < (bars[offset + 1].high - bars[offset + 1].low):
            move_length = 2

        threshold = atr * self.threshold_factor

        maxDist = atr * self.max_dist_factor
        buffer = atr * self.buffer_factor

        [sinceLongReset, longTrail] = self.calc_trail(bars, offset, 1, move_length, threshold, maxDist)
        [sinceShortReset, shortTrail] = self.calc_trail(bars, offset, -1, move_length, threshold, maxDist)

        sinceReset = min(sinceLongReset, sinceShortReset)

        if sinceReset >= 3:
            last_data: Data = self.get_data(bars[1])
            lastLongSwing = self.calc_swing(bars, 1, last_data.longSwing, sinceReset, buffer)
            lastShortSwing = self.calc_swing(bars, -1, last_data.shortSwing, sinceReset, buffer)
            if last_data.longSwing is not None and last_data.longSwing < bars[0].high:
                lastLongSwing = None
            if last_data.shortSwing is not None and last_data.shortSwing > bars[0].low:
                lastShortSwing = None
        else:
            lastLongSwing = None
            lastShortSwing = None

        self.write_data(bars[0],
                        Data(sinceLongReset=sinceLongReset, sinceShortReset=sinceShortReset, longTrail=longTrail,
                             shortTrail=shortTrail, longSwing=lastLongSwing, shortSwing=lastShortSwing, buffer=buffer,
                             atr=atr))

    def calc_swing(self, bars: List[Bar], direction, default, maxLookBack, minDelta):
        series = BarSeries.HIGH if direction > 0 else BarSeries.LOW
        for length in range(1, min(self.max_swing_length + 1, maxLookBack - 1)):
            cex = lowest(bars, length, 1, series)
            ex = highest(bars, length, 1, series)
            preRange = highest(bars, 2, length + 1, series)
            e = ex
            if direction < 0:
                e = cex
                preRange = lowest(bars, 2, length + 1, series)
            if direction * (e - preRange) > 0 \
                    and direction * (e - get_bar_value(bars[length + 1], series)) > minDelta \
                    and direction * (e - get_bar_value(bars[0], series)) > minDelta:
                return e + direction * minDelta

        return default

    def calc_trail(self, bars: List[Bar], offset, direction, move_length, threshold, maxDist):
        if direction > 0:
            range = highest(bars, 2, offset + move_length, BarSeries.HIGH)
            move = bars[offset].high - range
            last_value = bars[0].low
            offset_value = bars[offset].low
        else:
            range = lowest(bars, 2, offset + move_length, BarSeries.LOW)
            move = range - bars[offset].low
            last_value = bars[0].high
            offset_value = bars[offset].high

        last_data: Data = self.get_data(bars[1])
        if last_data is None:
            # defaults
            last_since_reset = 0
            last_buffer = 0
        else:
            last_buffer = last_data.buffer
            if direction > 0:
                last_since_reset = last_data.sinceLongReset
            else:
                last_since_reset = last_data.sinceShortReset

        if move > threshold and last_since_reset >= move_length and (offset_value - last_value) * direction < 0 and (
                range - last_value) * direction < 0:
            sinceReset = move_length + 1
        else:
            sinceReset = min(last_since_reset + 1, self.max_look_back)

        if direction > 0:
            trail = max(
                lowest(bars, sinceReset - 1, 0, BarSeries.LOW) - maxDist,
                lowest(bars, sinceReset, 0, BarSeries.LOW) - last_buffer)
        else:
            trail = min(
                highest(bars, sinceReset - 1, 0, BarSeries.HIGH) + maxDist,
                highest(bars, sinceReset, 0, BarSeries.HIGH) + last_buffer)

        return [sinceReset, trail]
