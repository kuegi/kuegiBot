from typing import List
#import math

from kuegi_bot.bots.strategies.strat_w_trade_man import StrategyWithTradeManagement
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType, Order, PositionStatus, Position
from kuegi_bot.bots.trading_bot import TradingBot, PositionDirection
from kuegi_bot.indicators.indicator import Indicator
from kuegi_bot.indicators.talibbars import TAlibBars
import talib
import plotly.graph_objects as go
from enum import Enum
import numpy as np
from datetime import datetime


class MarketRegime(Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    RANGING = "RANGING"
    NONE = "UNDEFINED"


class DataTrendStrategy:
    def __init__(self):
        # non-TA Data of the Trend Strategy
        self.stopLong = None
        self.stopShort = None


class TrendStrategy(StrategyWithTradeManagement):
    def __init__(self,
                 # TrendStrategy
                 timeframe: int = 240, ema_w_period: int = 1, highs_trail_4h_period: int = 1, lows_trail_4h_period: int = 1,
                 days_buffer_bear: int = 2, days_buffer_ranging: int = 0, atr_4h_period: int = 10, natr_4h_period_slow: int = 10,
                 bbands_4h_period: int = 10,
                 plotIndicators: bool = False,
                 trend_var_1: float = 0,
                 # Risk
                 risk_with_trend: float = 1, risk_counter_trend:float = 1, risk_ranging: float = 1,
                 sl_upper_bb_std_fac: float = 1, sl_lower_bb_std_fac: float = 1,
                 # SL input parameters
                 be_by_middleband: bool = True, be_by_opposite: bool = True, stop_at_middleband: bool = True,
                 tp_at_middleband: bool = True, tp_on_opposite: bool = True, stop_at_new_entry: bool = False,
                 trail_sl_with_bband: bool = False, stop_short_at_middleband: bool = True, stop_at_trail: bool = False,
                 stop_at_lowerband: bool = False,
                 atr_buffer_fac: float = 0, moving_sl_atr_fac: float = 5,
                 # StrategyWithTradeManagement
                 maxPositions: int = 100, consolidate: bool = False, close_on_opposite: bool = False, bars_till_cancel_triggered: int = 3,
                 limit_entry_offset_perc: float = -0.1, delayed_cancel: bool = False, cancel_on_filter: bool = True
                 ):
        super().__init__(
            # StrategyWithTradeManagement
            maxPositions = maxPositions, consolidate = consolidate, close_on_opposite = close_on_opposite, bars_till_cancel_triggered = bars_till_cancel_triggered,
            limit_entry_offset_perc = limit_entry_offset_perc, delayed_cancel = delayed_cancel, cancel_on_filter = cancel_on_filter)

        # local variables
        self.data_trend_strat = DataTrendStrategy()
        self.ta_trend_strat = TATrendStrategyIndicator(
            timeframe = timeframe, ema_w_period= ema_w_period, highs_trail_4h_period= highs_trail_4h_period,
            lows_trail_4h_period = lows_trail_4h_period, days_buffer_bear= days_buffer_bear, days_buffer_ranging = days_buffer_ranging,
            atr_4h_period= atr_4h_period, natr_4h_period_slow= natr_4h_period_slow, bbands_4h_period= bbands_4h_period, sl_upper_bb_std_fac = sl_upper_bb_std_fac,
            sl_lower_bb_std_fac = sl_lower_bb_std_fac, trend_var_1= trend_var_1, oversold_limit_w_rsi = 30, reset_level_of_oversold_rsi = 50
        )
        self.plotIndicators = plotIndicators
        # Risk
        self.risk_with_trend = risk_with_trend
        self.risk_counter_trend = risk_counter_trend
        self.risk_ranging = risk_ranging
        # SL entry parameters
        self.be_by_middleband = be_by_middleband
        self.be_by_opposite = be_by_opposite
        self.stop_at_middleband = stop_at_middleband
        self.tp_at_middleband = tp_at_middleband
        self.tp_on_opposite = tp_on_opposite
        self.stop_at_new_entry = stop_at_new_entry
        self.trail_sl_with_bband = trail_sl_with_bband
        self.atr_buffer_fac = atr_buffer_fac
        self.moving_sl_atr_fac = moving_sl_atr_fac
        self.sl_upper_bb_std_fac = sl_upper_bb_std_fac
        self.sl_lower_bb_std_fac = sl_lower_bb_std_fac
        self.stop_short_at_middleband = stop_short_at_middleband
        self.stop_at_trail = stop_at_trail
        self.stop_at_lowerband = stop_at_lowerband

    def init(self, bars: List[Bar], account: Account, symbol: Symbol):
        super().init(bars, account, symbol)
        self.logger.info(vars(self))

    def myId(self):
        return "TrendStrategy"

    def min_bars_needed(self) -> int:
        return self.ta_trend_strat.max_4h_history_candles+1

    def prep_bars(self, is_new_bar: bool, bars: list):
        if is_new_bar:
            self.ta_trend_strat.taData_trend_strat.talibbars.on_tick(bars)
            self.ta_trend_strat.on_tick(bars)

    def get_ta_data_trend_strategy(self):
        return self.ta_trend_strat.taData_trend_strat

    def add_to_plot(self, fig: go.Figure, bars: List[Bar], time):
        super().add_to_plot(fig, bars, time)

        # get ta data settings
        styles = self.ta_trend_strat.get_line_styles()
        names = self.ta_trend_strat.get_line_names()
        offset = 0

        # plot ta data
        plotTrailsAndEMAs = True
        if plotTrailsAndEMAs and self.plotIndicators:
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[0], bars))   # W-EMA
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[0],
                            name=self.ta_trend_strat.id + "_" + names[0])
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[1], bars))   # D-High
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[1],
                            name=self.ta_trend_strat.id + "_" + names[1])
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[2], bars))   # D-Low
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[2],
                            name=self.ta_trend_strat.id + "_" + names[2])
            plotMidTrail = False
            if plotMidTrail:
                sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[4], bars))   # midTrail
                fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[4],
                                name=self.ta_trend_strat.id + "_" + names[4])

        # plot trend indicator
        plotBackgroundColor4Trend = True #TODO: check for offset
        if plotBackgroundColor4Trend and self.plotIndicators:
            trend = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[3], bars))      # Trend
            time_short = []
            trend_short = []
            time_short.append(time[0])
            trend_short.append(trend[0])
            last_trend = trend[0]

            for i, (t, d) in enumerate(zip(time, trend)):
                if d != last_trend:
                    time_short.append(time[i])
                    trend_short.append(d)
                    last_trend = d

            time_short.append(time[-1])
            trend_short.append(trend[-1])

            i = 1
            while i < len(time_short):
                if trend_short[i-1] == 1:
                    color = "lightgreen"
                elif trend_short[i-1] == -1:
                    color = "orangered"
                elif trend_short[i-1] == 0:
                    color = "steelblue"
                elif trend_short[i-1] == 2:
                    color = "black"
                else:
                    color = "blue"
                fig.add_vrect(x0=time_short[i-1], x1=time_short[i], fillcolor=color, opacity=0.3, layer="below", line_width=0)
                i+=1

        # atr_4h
        plotATR = False
        if plotATR and self.plotIndicators:
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[5], bars))   # atr_4h + close
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[5],
                            name=self.ta_trend_strat.id + "_" + names[5])
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[6], bars))   # fast natr_4h
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[6],
                            name=self.ta_trend_strat.id + "_" + names[6])
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[7], bars))  # slow natr_4h
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[7],
                            name=self.ta_trend_strat.id + "_" + names[7])

        # plot Bollinger Bands
        plotBBands = True
        if plotBBands and self.plotIndicators:
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[8], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[8],
                            name=self.ta_trend_strat.id + "_" + names[8])
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[9], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[9],
                            name=self.ta_trend_strat.id + "_" + names[9])
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[10], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[10],
                            name=self.ta_trend_strat.id + "_" + names[10])

        '''plotBBandsTalib = True
        if plotBBandsTalib and self.plotIndicators:
            styles.extend(self.ta_trend_strat.taData_trend_strat.bbands_talib.get_line_styles())
            names.extend(self.ta_trend_strat.taData_trend_strat.bbands_talib.get_line_names())'''

    def calc_pos_size(self, risk, entry, exitPrice, atr: float = 0):
        delta = entry - exitPrice
        risk = self.risk_with_trend

        if (self.ta_trend_strat.taData_trend_strat.marketRegime == MarketRegime.BULL and delta > 0) or \
                (self.ta_trend_strat.taData_trend_strat.marketRegime == MarketRegime.BEAR and delta < 0):
            risk = self.risk_with_trend
        elif (self.ta_trend_strat.taData_trend_strat.marketRegime == MarketRegime.BEAR and delta > 0) or \
                (self.ta_trend_strat.taData_trend_strat.marketRegime == MarketRegime.BULL and delta < 0):
            risk = self.risk_counter_trend
        else:
            risk = self.risk_ranging

        if not self.symbol.isInverse:
            size = risk / delta
        else:
            size = -risk / (1 / entry - 1 / (entry - delta))
        size = self.symbol.normalizeSize(size)
        return size

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        super().manage_open_order(order, position, bars, to_update, to_cancel, open_positions)

        # Update SLs based on BBs
        orderType = TradingBot.order_type_from_order_id(order.id)
        if orderType == OrderType.SL:  # Manage Stop Losses
            new_stop_price = order.trigger_price
            if new_stop_price is not None and \
                    self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband is not None and \
                    self.ta_trend_strat.taData_trend_strat.bbands_4h.std is not None:
                upper_band = self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband + self.ta_trend_strat.taData_trend_strat.bbands_4h.std * self.sl_upper_bb_std_fac
                lower_band = self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband - self.ta_trend_strat.taData_trend_strat.bbands_4h.std * self.sl_lower_bb_std_fac
                if order.amount > 0:  # SL for SHORTS
                    if self.be_by_middleband and \
                            bars[1].low < self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband:
                        new_stop_price = min(position.wanted_entry, new_stop_price)
                    if self.be_by_opposite and \
                            bars[1].low < (lower_band + self.ta_trend_strat.taData_trend_strat.atr_4h * self.atr_buffer_fac):
                        new_stop_price = min(position.wanted_entry, new_stop_price)
                    if self.stop_at_new_entry and \
                            bars[1].low < self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband:
                        new_stop_price = min(upper_band, new_stop_price)
                    if self.stop_short_at_middleband and \
                            bars[1].low < lower_band:
                        new_stop_price = min(self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband - self.ta_trend_strat.taData_trend_strat.atr_4h, new_stop_price)
                    if self.tp_on_opposite and \
                            bars[1].low < lower_band:
                        new_stop_price = min(bars[0].open, new_stop_price)
                    if self.tp_at_middleband and \
                            bars[0].open < self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband:
                        new_stop_price = min(self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband, new_stop_price)
                    if self.trail_sl_with_bband:
                        new_stop_price = min(upper_band, new_stop_price)
                    if self.moving_sl_atr_fac > 0 and \
                        bars[1].low + self.ta_trend_strat.taData_trend_strat.atr_4h * self.moving_sl_atr_fac < new_stop_price:
                        new_stop_price = bars[1].low + self.ta_trend_strat.taData_trend_strat.atr_4h * self.moving_sl_atr_fac

                elif order.amount < 0:  # SL for LONGs
                    if self.stop_at_trail:
                        new_stop_price = max(self.ta_trend_strat.taData_trend_strat.lows_trail_4h - self.ta_trend_strat.taData_trend_strat.atr_4h*2, new_stop_price)
                    if self.stop_at_lowerband:
                        new_stop_price = max(lower_band, new_stop_price)
                    if self.be_by_middleband and \
                            bars[1].high > self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband:
                        new_stop_price = max(position.wanted_entry, new_stop_price)
                    if self.be_by_opposite and \
                            bars[1].high > (upper_band - self.ta_trend_strat.taData_trend_strat.atr_4h * self.atr_buffer_fac):
                        new_stop_price = max(position.wanted_entry, new_stop_price)
                    if self.stop_at_new_entry and \
                            bars[1].high > self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband:
                        new_stop_price = max(lower_band, new_stop_price)
                    if self.stop_at_middleband and \
                            bars[1].high > (upper_band - self.ta_trend_strat.taData_trend_strat.atr_4h * self.atr_buffer_fac):
                        new_stop_price = max(self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband, new_stop_price)
                    if self.tp_on_opposite and \
                            bars[1].high > upper_band:
                        new_stop_price = max(bars[0].open, new_stop_price)
                    if self.tp_at_middleband and \
                            bars[0].open > self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband:
                        new_stop_price = max(self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband, new_stop_price)
                    if self.trail_sl_with_bband:
                        new_stop_price = max(lower_band, new_stop_price)

                if new_stop_price != order.trigger_price:
                    order.trigger_price = new_stop_price
                    to_update.append(order)


class BBands:
    def __init__(self, middleband:float = None, std:float = None):
        self.middleband = middleband
        self.std = std


'''class Talib_BBANDS(Indicator):
    def __init__(self, period: int = None, middleband:float = None, std:float = None):
        super().__init__("BBands" + str(period))
        self.period = period
        self.middleband = middleband
        self.std = std

    def on_tick(self, bars: List[Bar]):
        pass

    def on_tick_talib(self, close: np.array, period: int):
        # Update Bollinger Bands arrays
        a, b, c = talib.BBANDS(close[-period - 1:], timeperiod=period, nbdevup=1,
                               nbdevdn=1)
        upperband = a[-1]
        self.middleband = b[-1]
        if not np.isnan(upperband) and not np.isnan(self.middleband):
            self.std = upperband - self.middleband
        else:
            self.std = np.nan

    def get_line_names(self):
        return ["bbands_talib" + str(self.period)]

    def get_line_styles(self):
        return [{"width": 1, "color": "purple"}]'''


class TAdataTrendStrategy:
    def __init__(self):
        ''' TA-data of the Trend Strategy '''
        self.talibbars = TAlibBars()
        self.marketRegime = MarketRegime.NONE
        # 4h arrays
        self.bbands_4h = BBands(None, None)
        #self.bbands_talib = Talib_BBANDS(None, None, None)
        #self.atr_4h_vec = None
        self.atr_4h = None
        #self.natr_4h_vec = None
        self.natr_4h = None
        #self.natr_slow_4h_vec = None
        self.natr_slow_4h = None
        self.highs_trail_4h_vec = None
        self.highs_trail_4h = None
        self.lows_trail_4h_vec = None
        self.lows_trail_4h = None
        self.mid_trail_4h = None
        #self.rsi_4h_vec = None
        # daily arrays
        #self.rsi_d_vec = None
        self.rsi_d = None
        # weekly arrays
        #self.ema_w_vec = None
        self.ema_w = None
        #self.rsi_w_vec = None
        self.rsi_w = None
        # index of last bar
        self.last_4h_index = -1
        self.last_d_index = -1
        self.last_w_index = -1
        self.is_initialized = False


class TATrendStrategyIndicator(Indicator):
    ''' Run technical analysis calculations here and store data in TAdataTrendStrategy '''

    def __init__(self,
                 timeframe: int = 240,
                 # 4h periods
                 bbands_4h_period: int = 10,
                 atr_4h_period: int = 10,
                 natr_4h_period_slow: int = 10,
                 highs_trail_4h_period: int = 10,
                 lows_trail_4h_period: int = 10,
                 rsi_4h_period: int = 14,
                 # daily periods
                 days_buffer_bear: int = 2,
                 days_buffer_ranging: int = 0,
                 rsi_d_period: int = 14,
                 # weekly periods
                 ema_w_period: int = 10,
                 rsi_w_period: int = 14,
                 oversold_limit_w_rsi: int = 10,
                 reset_level_of_oversold_rsi: int = 90,
                 # stop loss bband factors
                 sl_upper_bb_std_fac: float = 2.0,
                 sl_lower_bb_std_fac: float = 2.0,
                 # debug variables
                 trend_var_1: float = 0):
        super().__init__('TAtrend')
        # local input data
        self.taData_trend_strat = TAdataTrendStrategy()
        # debug variables
        self.trend_var_1 = trend_var_1
        # Trend identification parameters
        self.bull_buffer = 0
        self.bull_rsi_locked = False
        self.ranging_buffer = 0
        self.bear_buffer = 0
        self.bullish_reversal = False
        self.oversold_limit_w_rsi = oversold_limit_w_rsi
        self.reset_level_of_oversold_rsi = reset_level_of_oversold_rsi
        # Constant enabler parametersbb
        self.bars_per_week = int(60 * 24 * 7 / timeframe)
        self.bars_per_day = int(60 * 24 / timeframe)
        # 4H periods
        self.bbands_4h_period = bbands_4h_period
        self.atr_4h_period = atr_4h_period
        self.natr_4h_period_slow = natr_4h_period_slow
        self.rsi_4h_period = rsi_4h_period
        self.sl_upper_bb_4h_std_fac = sl_upper_bb_std_fac
        self.sl_lower_bb_4h_std_fac = sl_lower_bb_std_fac
        self.highs_trail_4h_period = highs_trail_4h_period
        self.lows_trail_4h_period = lows_trail_4h_period
        # Daily periods
        self.days_buffer_bear = days_buffer_bear
        self.rsi_d_period = rsi_d_period
        # Weekly periods
        self.days_buffer_ranging = days_buffer_ranging
        self.ema_w_period = ema_w_period
        self.rsi_w_period = rsi_w_period
        # Max period variables
        self.max_4h_period = max(self.bbands_4h_period, self.atr_4h_period, self.natr_4h_period_slow, self.rsi_4h_period, self.highs_trail_4h_period, self.lows_trail_4h_period)
        self.max_d_period = max(self.days_buffer_ranging, self.days_buffer_bear, self.rsi_d_period)
        self.max_w_period = max(self.ema_w_period, self.rsi_w_period)
        self.max_4h_history_candles = max(self.max_4h_period, self.max_d_period * 6, self.max_w_period * 7 * 6)
        #self.initialize_arrays()

    def on_tick(self, bars: List[Bar]):
        # Update the index of the last bar of the current timeframe
        first_bar_dt = datetime.fromtimestamp(bars[0].tstamp)
        daily_candle_start_index = (first_bar_dt.hour * 60 + first_bar_dt.minute) // (4 * 60) % 6
        weekly_candle_start_index = first_bar_dt.weekday() * 6 + daily_candle_start_index

        # Update the index of the last bar of the current timeframe
        self.taData_trend_strat.last_4h_index = (len(bars) - 1) % self.max_4h_period
        self.taData_trend_strat.last_d_index = ((len(bars) - 1 - daily_candle_start_index) // 6) % self.max_d_period
        self.taData_trend_strat.last_w_index = ((len(bars) - 1 - weekly_candle_start_index) // 42) % self.max_w_period

        # Run TA calculations
        #print("TA analysis TrendStrategy")
        self.run_ta_analysis(self.taData_trend_strat.last_4h_index)
        self.identify_trend()
        self.write_data_for_plot(bars)

    def get_ta_data(self):
        return self.taData_trend_strat

    def run_ta_analysis(self, last_index=None):
        if not self.taData_trend_strat.is_initialized:
            # Initialize arrays only if not initialized yet
            self.initialize_arrays(last_index)
            #self.taData_trend_strat.is_initialized = True

        # Update TA-idnicators
        self.update_4h_values(last_index)
        self.update_daily_values(self.taData_trend_strat.last_d_index)
        self.update_weekly_values(self.taData_trend_strat.last_w_index)

    def initialize_arrays(self, last_index: int = 0):
        # Initialize arrays with the provided lengths
        # 4H arrays
        self.taData_trend_strat.highs_trail_4h_vec = np.full(self.max_4h_period, np.nan)
        self.taData_trend_strat.lows_trail_4h_vec = np.full(self.max_4h_period, np.nan)
        #self.taData_trend_strat.atr_4h_vec = np.full(self.max_4h_period, np.nan)
        #self.taData_trend_strat.natr_4h_vec = np.full(self.max_4h_period, np.nan)
        #self.taData_trend_strat.natr_slow_4h_vec = np.full(self.max_4h_period, np.nan)
        #self.taData_trend_strat.rsi_4h_vec = np.full(self.max_4h_period, np.nan)

        # Daily arrays
        #self.taData_trend_strat.rsi_d_vec = np.full(self.max_d_period, np.nan)
        # Weekly arrays
        #self.taData_trend_strat.ema_w_vec = np.full(self.max_w_period, np.nan)
        #self.taData_trend_strat.rsi_w_vec = np.full(self.max_w_period, np.nan)

        talibbars = self.taData_trend_strat.talibbars

        # 4h arrays
        if last_index != 0:
            self.taData_trend_strat.highs_trail_4h_vec[:last_index] = talib.MAX(talibbars.high, self.highs_trail_4h_period)[-last_index:]
            self.taData_trend_strat.lows_trail_4h_vec[:last_index] = talib.MIN(talibbars.low, self.lows_trail_4h_period)[-last_index:]
        else:
            self.taData_trend_strat.highs_trail_4h_vec = talib.MAX(talibbars.high,self.highs_trail_4h_period)[-self.max_4h_period:]
            self.taData_trend_strat.lows_trail_4h_vec = talib.MIN(talibbars.low,self.lows_trail_4h_period)[-self.max_4h_period:]

        # weekly:
        len_weekly = len(talibbars.close_weekly)
        ema_w_vec = talib.EMA(talibbars.close_weekly[-len_weekly:], timeperiod=self.ema_w_period)
        # self.taData_trend_strat.ema_w_vec[last_index] = ema_w
        self.taData_trend_strat.ema_w = ema_w_vec[-1]

        # Set the initialized flag to True
        self.taData_trend_strat.is_initialized = True

    def update_4h_values(self, last_index):
        talibbars = self.taData_trend_strat.talibbars
        close = talibbars.close
        high = talibbars.high
        low = talibbars.low

        if close is None or len(close) < self.max_4h_period+1:
            return

        # Trails
        highs_trail = talib.MAX(high[-self.highs_trail_4h_period:], self.highs_trail_4h_period)[-1]
        lows_trail = talib.MIN(low[-self.lows_trail_4h_period:], self.lows_trail_4h_period)[-1]
        self.taData_trend_strat.highs_trail_4h_vec[last_index] = highs_trail
        self.taData_trend_strat.lows_trail_4h_vec[last_index] = lows_trail
        self.taData_trend_strat.highs_trail_4h = highs_trail
        self.taData_trend_strat.lows_trail_4h = lows_trail
        if self.taData_trend_strat.highs_trail_4h is not None and self.taData_trend_strat.lows_trail_4h is not None and \
                self.taData_trend_strat.lows_trail_4h != 0:
            self.taData_trend_strat.mid_trail_4h = 0.5*(self.taData_trend_strat.highs_trail_4h - self.taData_trend_strat.lows_trail_4h) + self.taData_trend_strat.lows_trail_4h

        # Update Bollinger Bands arrays
        a, b, c = talib.BBANDS(close[-self.bbands_4h_period-1:], timeperiod=self.bbands_4h_period, nbdevup=1, nbdevdn=1)
        upperband = a[-1]
        self.taData_trend_strat.bbands_4h.middleband = b[-1]
        if not np.isnan(upperband) and not np.isnan(self.taData_trend_strat.bbands_4h.middleband):
            self.taData_trend_strat.bbands_4h.std = upperband - self.taData_trend_strat.bbands_4h.middleband
        else:
            self.taData_trend_strat.bbands_4h.std = np.nan

        # Update atr_4h & natr_4h arrays
        atr_4h = talib.ATR(high[- self.atr_4h_period-1:],low[-self.atr_4h_period-1:], close[- self.atr_4h_period-1:], self.atr_4h_period)[-1]
        natr_4h = talib.NATR(high[-self.atr_4h_period-1:],low[-self.atr_4h_period-1:], close[-self.atr_4h_period-1:], self.atr_4h_period)[-1]
        natr_slow_4h = talib.NATR(high[- self.natr_4h_period_slow-1:],low[- self.natr_4h_period_slow-1:], close[- self.natr_4h_period_slow-1:], self.natr_4h_period_slow)[-1]
        #self.taData_trend_strat.atr_4h_vec[last_index] = atr_4h
        self.taData_trend_strat.atr_4h = atr_4h
        #self.taData_trend_strat.natr_4h_vec[last_index] = natr_4h
        self.taData_trend_strat.natr_4h = natr_4h
        #self.taData_trend_strat.natr_slow_4h_vec[last_index] = natr_slow_4h
        self.taData_trend_strat.natr_slow_4h = natr_slow_4h

        # Update RSI for 4H timeframe
        #rsi_4h = talib.RSI(close[-self.rsi_4h_period-1:], self.rsi_4h_period)[-1]
        #self.taData_trend_strat.rsi_4h_vec[last_index] = rsi_4h

    def update_daily_values(self, last_index):
        talibbars = self.taData_trend_strat.talibbars
        close = talibbars.close_daily

        if close is None or len(close) < self.max_d_period+1:
            return

        # Update RSI for daily timeframe
        rsi_daily = talib.RSI(close[-self.rsi_d_period-1:], self.rsi_d_period)[-1]
        #self.taData_trend_strat.rsi_d_vec[last_index] = rsi_daily
        self.taData_trend_strat.rsi_d = rsi_daily

    def update_weekly_values(self, last_index):
        talibbars = self.taData_trend_strat.talibbars
        close = talibbars.close_weekly

        # Update EMA for weekly timeframe
        if close is None or len(close) < self.max_w_period+1:
            return
        ema_w = talib.EMA(close[-self.ema_w_period:], timeperiod=self.ema_w_period)[-1]
        #self.taData_trend_strat.ema_w_vec[last_index] = ema_w
        self.taData_trend_strat.ema_w = ema_w

        # Update RSI for weekly timeframe
        rsi_w = talib.RSI(close[-self.rsi_w_period-1:], timeperiod=self.rsi_w_period)[-1]
        #self.taData_trend_strat.rsi_w_vec[last_index] = rsi_w
        self.taData_trend_strat.rsi_w = rsi_w

    def identify_trend(self):
        # Trend based on W-EMA and trails
        if self.taData_trend_strat.rsi_w is not None and self.taData_trend_strat.ema_w is not None:
            #if self.taData_trend_strat.talibbars.close_daily[-1] < self.taData_trend_strat.lows_trail_4h_vec[self.taData_trend_strat.last_4h_index-2] or \
            if self.taData_trend_strat.talibbars.close_weekly[-1] < self.taData_trend_strat.ema_w:
                self.taData_trend_strat.marketRegime = MarketRegime.BEAR
                self.bear_buffer = self.days_buffer_bear * self.bars_per_day
                self.ranging_buffer = self.days_buffer_ranging * self.bars_per_day
            elif self.taData_trend_strat.talibbars.close[-1] > self.taData_trend_strat.highs_trail_4h_vec[self.taData_trend_strat.last_4h_index-2] or \
                    self.taData_trend_strat.talibbars.close[-1] > self.taData_trend_strat.ema_w:
                self.bear_buffer -= 1
                if self.bear_buffer <= 0:
                    self.ranging_buffer -= 1
                    if self.ranging_buffer <= 0:
                        self.taData_trend_strat.marketRegime = MarketRegime.BULL
                    else:
                        self.taData_trend_strat.marketRegime = MarketRegime.RANGING
                else:
                    self.taData_trend_strat.marketRegime = MarketRegime.BEAR
            else:
                self.ranging_buffer -= 1
                if self.ranging_buffer <= 0:
                    self.taData_trend_strat.marketRegime = MarketRegime.RANGING
                else:
                    self.taData_trend_strat.marketRegime = MarketRegime.BEAR
        else:
            self.taData_trend_strat.marketRegime = MarketRegime.NONE

    def write_data_for_plot(self, bars: List[Bar]):
        if self.taData_trend_strat.marketRegime == MarketRegime.BULL:
            trend = 1
        elif self.taData_trend_strat.marketRegime == MarketRegime.BEAR:
            trend = -1
        elif self.taData_trend_strat.marketRegime == MarketRegime.RANGING:
            trend = 0
        elif self.taData_trend_strat.marketRegime == MarketRegime.NONE:
            trend = 2
        else:
            trend = 10

        atr_close = self.taData_trend_strat.talibbars.close[-1] + self.taData_trend_strat.atr_4h if self.taData_trend_strat.atr_4h is not None else self.taData_trend_strat.talibbars.close[-1]
        if self.taData_trend_strat.bbands_4h.middleband is not None:
            upper_band = self.taData_trend_strat.bbands_4h.middleband + self.taData_trend_strat.bbands_4h.std * self.sl_upper_bb_4h_std_fac
            lower_band = self.taData_trend_strat.bbands_4h.middleband - self.taData_trend_strat.bbands_4h.std * self.sl_lower_bb_4h_std_fac
        else:
            upper_band = None
            lower_band = None

        plot_data = [self.taData_trend_strat.ema_w,
                     self.taData_trend_strat.highs_trail_4h,
                     self.taData_trend_strat.lows_trail_4h,
                     trend,
                     self.taData_trend_strat.mid_trail_4h,
                     atr_close,
                     self.taData_trend_strat.natr_4h,
                     self.taData_trend_strat.natr_slow_4h,
                     upper_band,
                     self.taData_trend_strat.bbands_4h.middleband,
                     lower_band
                    ]
        self.write_data(bars[0], plot_data)  # [0] because we only know about it after the candle is closed and processed

    def get_line_names(self):
        return ["%1.fW-EMA" % self.ema_w_period,
                "%1.fD-High" % self.highs_trail_4h_period,
                "%1.fD-Low" % self.lows_trail_4h_period,
                "Market Trend",
                "MidTrail",
                "1ATR+Close",
                "1NATR",
                "1slowNATR",
                "%.1fSTD_upperband" % self.sl_upper_bb_4h_std_fac,  # Bollinger Bands SL
                "middleband",  # Bollinger Bands
                "%.1fSTD_lowerband" % self.sl_lower_bb_4h_std_fac  # Bollinger Bands SL
                ]

    def get_number_of_lines(self):
        return 11

    def get_line_styles(self):
        return [
            {"width": 1, "color": "black"},                         # W-EMA
            {"width": 1, "color": "green"},                         # D-High
            {"width": 1, "color": "red"},                           # D-Low
            {"width": 1, "color": "black"},                         # Trend
            {"width": 1, "color": "blue", "dash": "dot"},           # Mid-Trail
            {"width": 1, "color": "purple", "dash": "dot"},         # atr_4h+Close
            {"width": 1, "color": "black"},                         # natr_4h
            {"width": 1, "color": "blue"},                          # slowNATR
            {"width": 1, "color": "dodgerblue"},                    # BBands SL
            {"width": 1, "color": "dodgerblue", "dash": "dot"},     # BBands
            {"width": 1, "color": "dodgerblue"}                     # BBands SL
               ]

    def get_data_for_plot(self, bar: Bar):
        plot_data = self.get_data(bar)
        if plot_data is not None:
            return plot_data
        else:
            return [bar.close, bar.close, bar.close, bar.close, bar.close, bar.close, bar.close, bar.close,
                    bar.close, bar.close, bar.close                 # Bollinger Bands
             ]
