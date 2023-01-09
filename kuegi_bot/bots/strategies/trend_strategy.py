from typing import List
import math

from kuegi_bot.bots.strategies.strat_w_trade_man import StrategyWithTradeManagement
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType, Order, PositionStatus, Position
from kuegi_bot.bots.trading_bot import TradingBot, PositionDirection
from kuegi_bot.indicators.indicator import Indicator
from kuegi_bot.indicators.talibbars import TAlibBars
import talib
import plotly.graph_objects as go
from enum import Enum
import numpy as np


class MarketTrend(Enum):
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
                 timeframe: int = 240, w_ema_period: int = 1, d_highs_trail_period: int = 1,
                 d_lows_trail_period: int = 1, trend_d_period: int = 2, trend_w_period: int = 0,
                 atr_period: int = 10, natr_period_slow: int = 10, bbands_period: int = 10, bb_nbdevup: float = 2.0,
                 bb_nbdevdn: float = 2.0,
                 plotIndicators: bool = False,
                 # StrategyWithTradeManagement
                 maxPositions: int = 100, close_on_opposite: bool = False, bars_till_cancel_triggered: int = 3,
                 limit_entry_offset_perc: float = -0.1, delayed_cancel: bool = False, cancel_on_filter: bool = True
                 ):
        super().__init__(
            # StrategyWithTradeManagement
            maxPositions = maxPositions, close_on_opposite = close_on_opposite, bars_till_cancel_triggered = bars_till_cancel_triggered,
            limit_entry_offset_perc = limit_entry_offset_perc, delayed_cancel = delayed_cancel, cancel_on_filter = cancel_on_filter)

        # local variables
        self.data_trend_strat = DataTrendStrategy()
        self.ta_trend_strat = TATrendStrategyIndicator(
            timeframe = timeframe, w_ema_period= w_ema_period, d_highs_trail_period = d_highs_trail_period,
            d_lows_trail_period = d_lows_trail_period, trend_d_period = trend_d_period, trend_w_period = trend_w_period,
            atr_period = atr_period, natr_period_slow= natr_period_slow, bbands_period = bbands_period, bb_nbdevup = bb_nbdevup,
            bb_nbdevdn = bb_nbdevdn
        )
        self.plotIndicators = plotIndicators

    def init(self, bars: List[Bar], account: Account, symbol: Symbol):
        super().init(bars, account, symbol)
        self.logger.info()

    def myId(self):
        return "TrendStrategy"

    def prep_bars(self, is_new_bar: bool, bars: list):
        if is_new_bar:
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

        # ATR
        plotATR = False
        if plotATR and self.plotIndicators:
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[5], bars))   # ATR + close
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[5],
                            name=self.ta_trend_strat.id + "_" + names[5])
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[6], bars))   # fast NATR
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[6],
                            name=self.ta_trend_strat.id + "_" + names[6])
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[7], bars))  # slow NATR
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
        # Plot strategy-generated data

    def calc_pos_size(self, risk, entry, exitPrice, atr: float = 0):
        delta = entry - exitPrice
        if self.risk_type <= 2:
            if self.risk_type == 1:
                # use atr as delta reference, but max X the actual delta. so risk is never more than X times the
                # wanted risk
                delta = math.copysign(max(abs(delta) / self.max_risk_mul, atr * self.atr_factor_risk), delta)

            if not self.symbol.isInverse:
                size = risk / delta
            else:
                size = -risk / (1 / entry - 1 / (entry - delta))
            size = self.symbol.normalizeSize(size)
            return size
        elif self.risk_type == 3:
            if (self.ta_trend_strat.taData_trend_strat.marketTrend == MarketTrend.BULL and delta > 0) or \
                    (self.ta_trend_strat.taData_trend_strat.marketTrend == MarketTrend.BEAR and delta < 0):
                pass
            elif self.ta_trend_strat.taData_trend_strat.marketTrend == MarketTrend.RANGING or \
                    (self.ta_trend_strat.taData_trend_strat.marketTrend == MarketTrend.BULL and delta < 0) or \
                    (self.ta_trend_strat.taData_trend_strat.marketTrend == MarketTrend.BEAR and delta > 0):
                risk = risk / 3
            else:
                risk = 0
                pass

            if not self.symbol.isInverse:
                size = risk / delta
            else:
                size = -risk / (1 / entry - 1 / (entry - delta))
            size = self.symbol.normalizeSize(size)
            return size

    #def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
    #    super().manage_open_order(order, position, bars, to_update, to_cancel, open_positions)


class BBands:
    def __init__(self, upperband:float = None, middleband:float = None, lowerband:float = None):
        self.upperband = upperband
        self.middleband = middleband
        self.lowerband = lowerband


class TAdataTrendStrategy:
    def __init__(self):
        ''' TA- / Indicator-data of the Trend Strategy '''
        self.talibbars = talibbars = TAlibBars()
        self.w_ema = None
        self.w_ema_vec = None
        self.d_highs_trail_vec = None
        self.d_lows_trail_vec = None
        self.d_highs_trail = None
        self.d_mid_trail = None
        self.d_lows_trail = None
        self.marketTrend = MarketTrend.NONE
        self.ATR_vec = None
        self.ATR = None
        self.NATR_vec = None
        self.NATR = None
        self.NATR_slow_vec = None
        self.NATR_slow = None
        self.bbands = BBands(None, None, None)


class TATrendStrategyIndicator(Indicator):
    ''' Run technical analysis here and store data in TAdataTrendStrategy '''

    def __init__(self,
                 timeframe: int = 240,
                 w_ema_period: int = 10,
                 d_highs_trail_period: int = 10,
                 d_lows_trail_period: int = 10,
                 trend_d_period: int = 2,
                 trend_w_period: int = 0,
                 atr_period: int = 10,
                 natr_period_slow: int = 10,
                 bbands_period: int = 10,
                 bb_nbdevup: float = 2.0,
                 bb_nbdevdn: float = 2.0):
        super().__init__('TAtrend')
        # local data
        self.taData_trend_strat = TAdataTrendStrategy()
        self.ranging_buffer = 0
        # Input parameters
        self.bars_per_week = int(60*24*7 / timeframe)
        self.bars_per_day = int(60*24 / timeframe)
        self.trend_d_period = trend_d_period
        self.trend_w_period = trend_w_period
        self.w_ema_period = w_ema_period
        self.highs_trail_period = d_highs_trail_period
        self.lows_trail_period = d_lows_trail_period
        self.atr_period = atr_period
        self.natr_period_slow = natr_period_slow
        self.bbands_period = bbands_period
        self.bb_nbdevup = bb_nbdevup
        self.bb_nbdevdn = bb_nbdevdn

    def on_tick(self, bars: List[Bar]):
        self.taData_trend_strat.talibbars.on_tick(bars)
        self.run_ta_analysis()
        self.identify_trend()
        self.write_data_for_plot(bars)

    def get_ta_data(self):
        return self.taData_trend_strat

    def run_ta_analysis(self):
        # W-EMA
        temp_w_ema = talib.EMA(self.taData_trend_strat.talibbars.close, self.w_ema_period * self.bars_per_week)
        w_ema_vec = []
        for value in temp_w_ema:
            if not np.isnan(value):
                w_ema_vec.append(value)
        self.taData_trend_strat.w_ema_vec = w_ema_vec
        if self.taData_trend_strat.w_ema_vec is not None and len(self.taData_trend_strat.w_ema_vec)>0:
            if self.taData_trend_strat.w_ema_vec[-1] is not None:
                self.taData_trend_strat.w_ema = self.taData_trend_strat.w_ema_vec[-1]
            else:
                self.taData_trend_strat.w_ema = None

        # Trails
        temp_d_highs = talib.MAX(self.taData_trend_strat.talibbars.high, self.highs_trail_period * self.bars_per_day)
        temp_d_lows = talib.MIN(self.taData_trend_strat.talibbars.low, self.lows_trail_period * self.bars_per_day)
        d_highs_vec = []
        d_lows_vec = []
        for value_high, value_low in zip(temp_d_highs, temp_d_lows):
            if not np.isnan(value_high):
                d_highs_vec.append(value_high)
            if not np.isnan(value_low):
                d_lows_vec.append(value_low)
        self.taData_trend_strat.d_highs_trail_vec = d_highs_vec
        self.taData_trend_strat.d_lows_trail_vec = d_lows_vec

        if self.taData_trend_strat.d_highs_trail_vec is not None and len(self.taData_trend_strat.d_highs_trail_vec)>0:
            if self.taData_trend_strat.d_highs_trail_vec[-1] is not None:
                self.taData_trend_strat.d_highs_trail = self.taData_trend_strat.d_highs_trail_vec[-1]
            else:
                self.taData_trend_strat.d_highs_trail = None

        if self.taData_trend_strat.d_lows_trail_vec is not None and len(self.taData_trend_strat.d_lows_trail_vec)>0:
            if self.taData_trend_strat.d_lows_trail_vec[-1] is not None:
                self.taData_trend_strat.d_lows_trail = self.taData_trend_strat.d_lows_trail_vec[-1]
            else:
                self.taData_trend_strat.d_lows_trail = None

        if self.taData_trend_strat.d_lows_trail is not None and self.taData_trend_strat.d_highs_trail is not None:
            self.taData_trend_strat.d_mid_trail = (self.taData_trend_strat.d_highs_trail + self.taData_trend_strat.d_lows_trail) / 2
        else:
            self.taData_trend_strat.d_mid_trail = None

        # ATR & NATR
        self.taData_trend_strat.ATR_vec = talib.ATR(self.taData_trend_strat.talibbars.high, self.taData_trend_strat.talibbars.low,
                                                    self.taData_trend_strat.talibbars.close, self.atr_period)
        self.taData_trend_strat.ATR = self.taData_trend_strat.ATR_vec[-1] if not np.isnan(self.taData_trend_strat.ATR_vec[-1]) else None
        self.taData_trend_strat.NATR_vec = talib.NATR(self.taData_trend_strat.talibbars.high, self.taData_trend_strat.talibbars.low,
                                                      self.taData_trend_strat.talibbars.close, self.atr_period)
        self.taData_trend_strat.NATR = self.taData_trend_strat.NATR_vec[-1] if not np.isnan(self.taData_trend_strat.NATR_vec[-1]) else None
        self.taData_trend_strat.NATR_slow_vec = talib.NATR(self.taData_trend_strat.talibbars.high, self.taData_trend_strat.talibbars.low,
                                                           self.taData_trend_strat.talibbars.close, self.natr_period_slow)
        self.taData_trend_strat.NATR_slow = self.taData_trend_strat.NATR_slow_vec[-1] if not np.isnan(self.taData_trend_strat.NATR_slow_vec[-1]) else None

        # Bollinger Bands
        a, b, c = talib.BBANDS(self.taData_trend_strat.talibbars.close, timeperiod=self.bbands_period, nbdevup = self.bb_nbdevup, nbdevdn = self.bb_nbdevdn)
        self.taData_trend_strat.bbands.upperband = a[-1] if not math.isnan(a[-1]) else None
        self.taData_trend_strat.bbands.middleband = b[-1] if not math.isnan(b[-1]) else None
        self.taData_trend_strat.bbands.lowerband = c[-1] if not math.isnan(c[-1]) else None

    def identify_trend(self):
        # Trend based on W-EMA and trails
        if self.taData_trend_strat.w_ema is not None:
            if self.taData_trend_strat.talibbars.low[-1] < self.taData_trend_strat.d_lows_trail_vec[-2] or \
                    self.taData_trend_strat.talibbars.low[-1] < self.taData_trend_strat.w_ema:
                self.taData_trend_strat.marketTrend = MarketTrend.BEAR

                nmb_required_candles_w = self.trend_w_period * self.bars_per_week
                nmb_required_candles_d = self.trend_d_period * self.bars_per_day
                self.ranging_buffer = max(nmb_required_candles_w, nmb_required_candles_d)
            elif self.taData_trend_strat.talibbars.close[-1] > self.taData_trend_strat.w_ema or \
                    self.taData_trend_strat.talibbars.close[-1] > self.taData_trend_strat.d_highs_trail_vec[-2]:
                self.ranging_buffer -= 1
                if self.ranging_buffer <= 0:
                    self.taData_trend_strat.marketTrend = MarketTrend.BULL
                else:
                    self.taData_trend_strat.marketTrend = MarketTrend.RANGING

            else:
                self.ranging_buffer -= 1
                if self.ranging_buffer <= 0:
                    self.taData_trend_strat.marketTrend = MarketTrend.RANGING
                else:
                    self.taData_trend_strat.marketTrend = MarketTrend.BEAR

    def write_data_for_plot(self, bars: List[Bar]):
        if self.taData_trend_strat.marketTrend == MarketTrend.BULL:
            trend = 1
        elif self.taData_trend_strat.marketTrend == MarketTrend.BEAR:
            trend = -1
        elif self.taData_trend_strat.marketTrend == MarketTrend.RANGING:
            trend = 0
        elif self.taData_trend_strat.marketTrend == MarketTrend.NONE:
            trend = 2
        else:
            trend = 10

        atr_close = self.taData_trend_strat.talibbars.close[-1] + self.taData_trend_strat.ATR if self.taData_trend_strat.ATR is not None else self.taData_trend_strat.talibbars.close[-1]

        plot_data = [self.taData_trend_strat.w_ema,
                     self.taData_trend_strat.d_highs_trail,
                     self.taData_trend_strat.d_lows_trail,
                     trend,
                     self.taData_trend_strat.d_mid_trail,
                     atr_close,
                     self.taData_trend_strat.NATR,
                     self.taData_trend_strat.NATR_slow,
                     self.taData_trend_strat.bbands.upperband, self.taData_trend_strat.bbands.middleband, self.taData_trend_strat.bbands.lowerband
                    ]
        self.write_data(bars[0], plot_data)  # [0] because we only know about it after the candle is closed and processed

    def get_line_names(self):
        return ["%1.fW-EMA" % self.w_ema_period,
                "%1.fD-High" % self.highs_trail_period,
                "%1.fD-Low" % self.lows_trail_period,
                "Market Trend",
                "MidTrail",
                "1ATR+Close",
                "1NATR",
                "1slowNATR",
                "%.1fSTD_upperband" % self.bb_nbdevup,          # Bollinger Bands
                "middleband",                                   # Bollinger Bands
                "%.1fSTD_lowerband" % self.bb_nbdevdn           # Bollinger Bands
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
            {"width": 1, "color": "purple", "dash": "dot"},         # ATR+Close
            {"width": 1, "color": "black"},                         # NATR
            {"width": 1, "color": "blue"},                          # slowNATR
            {"width": 1, "color": "dodgerblue"},                    # BBands
            {"width": 1, "color": "dodgerblue", "dash": "dot"},     # BBands
            {"width": 1, "color": "dodgerblue"}                     # BBands
               ]

    def get_data_for_plot(self, bar: Bar):
        plot_data = self.get_data(bar)
        if plot_data is not None:
            return plot_data
        else:
            return [bar.close, bar.close, bar.close, bar.close, bar.close, bar.close, bar.close, bar.close,
                    bar.close, bar.close, bar.close                 # Bollinger Bands
             ]
