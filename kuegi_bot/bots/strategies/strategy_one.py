import math
from typing import List

import plotly.graph_objects as go
import numpy as np
import talib

from kuegi_bot.bots.strategies.trend_strategy import TrendStrategy, TAdataTrendStrategy, MarketRegime, BBands
from kuegi_bot.bots.trading_bot import TradingBot, PositionDirection
from kuegi_bot.indicators.indicator import Indicator
from kuegi_bot.indicators.talibbars import TAlibBars
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType, Position
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType, Order, PositionStatus, Position


class DataStrategyOne:
    def __init__(self):
        self.longEntry = None
        self.stopLong = None
        self.shortEntry = None
        self.stopShort = None
        self.shortsAllowed = False
        self.longsAllowed = False
        self.longs_from_middleband_alowed = False


class StrategyOne(TrendStrategy):
    # Strategy description:
    def __init__(self,
                 # StrategyOne
                 var_1: float = 1, var_2: float = 2,
                 std_fac_sell_off: float = 1, std_fac_reclaim: float = 1,
                 std_fac_sell_off_3: float = 1, std_fac_reclaim_3: float = 1, std_fac_sell_off_4: float = 1, std_fac_reclaim_4: float = 1,
                 h_highs_trail_period: int = 1, h_lows_trail_period: int = 1, nmb_bars_entry: int = 1, const_trail_period: int = 4,
                 shortTrailBreakdown: bool = False,
                 longReclaimBBand: bool = False, longTrailReversal: bool = False, longTrailBreakout: bool = False, short_entry_2: bool = False,
                 tradeSwinBreakouts: bool = False, tradeWithLimitOrders: bool = False,
                 longEMAbreakout: bool = False, short_entry_1: bool = False, entry_lower_bb_std_fac: float = 2.0,
                 max_natr_4_trail_bo: float = 2, max_natr_4_bb_reclaim: float = 2, min_natr_bb_bd: float = 2,
                 max_rsi_trail_rev: float = 50, min_rsi_bd: float = 50, overbought_std_fac: float = 5,
                 overbought_std_fac_entr: float = 2, max_natr_5_bb_reclaim: float = 1, short_entry_2_std_fac: float = 1,
                 short_entry_2_std_fac_entry: float = 1, short_entry_1_max_natr: float = 1, short_entry_1_std_fac: float = 1,
                 short_entry_1_max_day_rsi: float = 50, short_entry_1_max_4h_rsi: float = 50,
                 short_entry_2_max_natr: float = 1, short_entry_2_min_natr: float = 1,
                 short_entry_3_max_natr: float = 1,
                 # TrendStrategy
                 timeframe: int = 240, ema_w_period: int = 2, highs_trail_4h_period: int = 1, lows_trail_4h_period: int = 1,
                 days_buffer_bear: int = 2, days_buffer_ranging: int = 0, atr_4h_period: int = 10, natr_4h_period_slow: int = 10,
                 bbands_4h_period: int = 10, bband_history_size: int =10, rsi_4h_period: int = 10,
                 plotIndicators: bool = False, plot_RSI: bool = False,
                 trend_var_1: float = 1,
                 # Risk
                 risk_with_trend: float = 1, risk_counter_trend: float = 1, risk_ranging: float = 1,
                 # SL
                 sl_atr_fac: float = 2, be_by_middleband: bool = True, be_by_opposite: bool = True, stop_at_middleband: bool = True,
                 tp_at_middleband: bool = True, atr_buffer_fac: float = 0, tp_on_opposite: bool = True, stop_at_new_entry: bool = False,
                 trail_sl_with_bband: bool = False, stop_short_at_middleband: bool = False, stop_at_trail: bool = False,
                 stop_at_lowerband: bool = False,
                 moving_sl_atr_fac: float = 5, sl_upper_bb_std_fac: float = 1, sl_lower_bb_std_fac: float = 1,
                 # StrategyWithTradeManagement
                 maxPositions: int = 100, consolidate: bool = False, close_on_opposite: bool = False, bars_till_cancel_triggered: int = 3,
                 limit_entry_offset_perc: float = -0.1, delayed_cancel: bool = False, cancel_on_filter: bool = True
                 ):
        super().__init__(
            # TrendStrategy
            timeframe = timeframe, ema_w_period= ema_w_period, highs_trail_4h_period= highs_trail_4h_period,
            lows_trail_4h_period= lows_trail_4h_period, days_buffer_bear= days_buffer_bear, days_buffer_ranging= days_buffer_ranging,
            atr_4h_period= atr_4h_period, natr_4h_period_slow= natr_4h_period_slow,
            bbands_4h_period= bbands_4h_period, bband_history_size = bband_history_size, rsi_4h_period = rsi_4h_period,
            plotIndicators = plotIndicators, plot_RSI = plot_RSI,
            trend_var_1 = trend_var_1,
            # Risk
            risk_with_trend = risk_with_trend, risk_counter_trend = risk_counter_trend, risk_ranging = risk_ranging,
            # SL
            be_by_middleband = be_by_middleband, be_by_opposite = be_by_opposite,
            stop_at_middleband = stop_at_middleband, tp_at_middleband = tp_at_middleband,
            tp_on_opposite = tp_on_opposite, stop_at_new_entry = stop_at_new_entry, trail_sl_with_bband = trail_sl_with_bband,
            atr_buffer_fac = atr_buffer_fac, moving_sl_atr_fac = moving_sl_atr_fac,
            sl_upper_bb_std_fac = sl_upper_bb_std_fac, sl_lower_bb_std_fac = sl_lower_bb_std_fac,
            stop_short_at_middleband = stop_short_at_middleband, stop_at_trail = stop_at_trail, stop_at_lowerband = stop_at_lowerband,
            # StrategyWithTradeManagement
            maxPositions = maxPositions, consolidate = consolidate, close_on_opposite = close_on_opposite, bars_till_cancel_triggered = bars_till_cancel_triggered,
            limit_entry_offset_perc = limit_entry_offset_perc, delayed_cancel = delayed_cancel, cancel_on_filter = cancel_on_filter
            )
        self.ta_data_trend_strat = TAdataTrendStrategy()
        self.data_strat_one = DataStrategyOne()
        self.ta_strat_one = TAStrategyOne(timeframe = timeframe, h_highs_trail_period= h_highs_trail_period,
                                          h_lows_trail_period = h_lows_trail_period, ta_data_trend_strat = self.ta_data_trend_strat)
        # Entry variables
        self.var_1 = var_1 # for backtesting
        self.var_2 = var_2 # for backtesting
        self.nmb_bars_entry = nmb_bars_entry
        self.const_trail_period = const_trail_period
        self.tradeWithLimitOrders = tradeWithLimitOrders
        self.longReclaimBBand = longReclaimBBand
        self.longTrailReversal = longTrailReversal
        self.longTrailBreakout = longTrailBreakout
        self.short_entry_2 = short_entry_2
        self.shortTrailBreakdown = shortTrailBreakdown
        self.tradeSwinBreakouts = tradeSwinBreakouts
        self.longEMAbreakout = longEMAbreakout
        self.short_entry_1 = short_entry_1
        self.short_entry_1_max_natr = short_entry_1_max_natr
        self.short_entry_1_std_fac = short_entry_1_std_fac
        self.short_entry_1_max_4h_rsi = short_entry_1_max_4h_rsi
        self.short_entry_1_max_day_rsi = short_entry_1_max_day_rsi
        self.entry_lower_bb_std_fac = entry_lower_bb_std_fac
        self.max_natr_4_trail_bo = max_natr_4_trail_bo
        self.max_natr_4_bb_reclaim = max_natr_4_bb_reclaim
        self.max_natr_5_bb_reclaim = max_natr_5_bb_reclaim
        self.min_natr_bb_bd = min_natr_bb_bd
        self.max_rsi_trail_rev = max_rsi_trail_rev
        self.overbought_std_fac = overbought_std_fac
        self.overbought_std_fac_entr = overbought_std_fac_entr
        self.min_rsi_bd = min_rsi_bd
        self.std_fac_sell_off = std_fac_sell_off
        self.std_fac_reclaim = std_fac_reclaim
        self.std_fac_sell_off_3 = std_fac_sell_off_3
        self.std_fac_sell_off_4 = std_fac_sell_off_4
        self.std_fac_reclaim_3 = std_fac_reclaim_3
        self.std_fac_reclaim_4 = std_fac_reclaim_4
        self.short_entry_2_std_fac = short_entry_2_std_fac
        self.short_entry_2_std_fac_entry = short_entry_2_std_fac_entry
        self.short_entry_2_max_natr = short_entry_2_max_natr
        self.short_entry_2_min_natr = short_entry_2_min_natr
        self.short_entry_3_max_natr = short_entry_3_max_natr
        self.overboughtBB = 0
        self.overboughtBB_entry = 0
        self.sl_atr_fac = sl_atr_fac

    def myId(self):
        return "strategyOne"

    def init(self, bars: List[Bar], account: Account, symbol: Symbol):
        self.logger.info(vars(self))
        super().init(bars, account, symbol)

    def min_bars_needed(self) -> int:
        min_bars = super().min_bars_needed()
        return min_bars

    def prep_bars(self, is_new_bar: bool, bars: list):
        if is_new_bar:
            #print("processing new bar")
            super().prep_bars(is_new_bar, bars)
            self.ta_data_trend_strat = self.get_ta_data_trend_strategy()
            self.ta_strat_one.set_ta_data_trend_strat(self.ta_data_trend_strat)
            self.ta_strat_one.on_tick(bars)

    def position_got_opened_or_changed(self, position: Position, bars: List[Bar], account: Account, open_positions):
        super().position_got_opened_or_changed(position, bars, account, open_positions)

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        super().manage_open_order(order, position, bars, to_update, to_cancel, open_positions)

    def got_data_for_position_sync(self, bars: List[Bar]) -> bool:
        result= super().got_data_for_position_sync(bars)
        return result

    def open_new_trades(self, is_new_bar, directionFilter, bars, account, open_positions, all_open_pos: dict):
        if not is_new_bar:
            return

        if not self.entries_allowed(bars):
            self.logger.info("New entries not allowed")
            if self.telegram is not None:
                self.telegram.send_log("New entries not allowed")
            return

        if self.ta_data_trend_strat.atr_4h is None:
            self.logger.info("atr not available")
            return

        if self.ta_data_trend_strat.marketRegime == MarketRegime.NONE:
            self.logger.info("Market regime unknown")
            return

        if len(all_open_pos) >= self.maxPositions and self.consolidate is False:
            self.logger.info("Reached max Positions: " + str(len(all_open_pos)))
            if self.telegram is not None:
                self.telegram.send_log("Reached max Positions")
            return

        self.logger.info("New bar. Checking for new entry options")
        self.logger.info("Market Regime: "+str(self.ta_data_trend_strat.marketRegime))
        if self.telegram is not None:
            self.telegram.send_log("Market Regime: "+str(self.ta_data_trend_strat.marketRegime))
            self.telegram.send_log("NATR: %.2f" % self.ta_data_trend_strat.natr_4h)


        # Bad: Limit Orders
        if self.tradeWithLimitOrders:
            # Calculate potential trade entries
            longEntry, shortEntry, stopLong, stopShort, longAmount, shortAmount = self.calc_entry_and_exit(bars)
            longAmount=longAmount/2
            shortAmount=shortAmount/2

            if longEntry is not None and shortEntry is not None and stopLong is not None and stopShort is not None and \
                    longAmount is not None and shortAmount is not None:
                # Update existing entries, if available
                foundLong, foundShort = self.update_existing_entries(account, open_positions, longEntry, shortEntry,
                                                                     stopLong, stopShort, longAmount, shortAmount)

                # decide if new entries are allowed
                #self.new_entries_allowed(bars)

                # Set entries if no orders are found and the market conditions allow it
                # go LONG
                if not foundLong and directionFilter >= 0 and \
                        self.data_strat_one.longsAllowed and longAmount > 0 and \
                    self.ta_data_trend_strat.natr_4h < 0.5:
                    pass#self.open_new_position(PositionDirection.LONG, bars, stopLong, open_positions, longEntry, longAmount,"Limit")
                # go SHORT
                if not foundShort and directionFilter <= 0 and \
                        self.data_strat_one.shortsAllowed and shortAmount < 0and \
                    self.ta_data_trend_strat.natr_4h < 0.5:#(self.ta_data_trend_strat.marketTrend != MarketRegime.BULL) and \
                    pass#self.open_new_position(PositionDirection.SHORT, bars, stopShort, open_positions, shortEntry, shortAmount,"Limit")

                # Save parameters
                self.data_strat_one.longEntry = longEntry
                self.data_strat_one.shortEntry = shortEntry
                self.data_strat_one.stopLong = stopLong
                self.data_strat_one.stopShort = stopShort

                # Write Data to plot
                plot_data = [self.data_strat_one.longEntry, self.data_strat_one.stopLong,
                             self.data_strat_one.shortEntry, self.data_strat_one.stopShort]
                Indicator.write_data_static(bars[0], plot_data, self.myId())

        # Entries by Market Orders
        std = self.ta_data_trend_strat.bbands_4h.std
        std_vec = self.ta_data_trend_strat.bbands_4h.std_vec
        atr = self.ta_data_trend_strat.atr_4h
        #middleband = self.ta_data_trend_strat.bbands_4h.middleband
        middleband_vec = self.ta_data_trend_strat.bbands_4h.middleband_vec
        market_bullish = self.ta_data_trend_strat.marketRegime == MarketRegime.BULL
        #market_bearish = self.ta_data_trend_strat.marketRegime == MarketRegime.BEAR
        range_limit = len(middleband_vec)

        longed = False
        # Long trail breakout
        if self.longTrailBreakout and not longed:
            condition_1 = bars[1].high > self.ta_data_trend_strat.highs_trail_4h_vec[-2]
            condition_2 = self.ta_data_trend_strat.natr_4h < self.max_natr_4_trail_bo
            close = bars[1].low if bars[1].close > bars[1].open else bars[1].low - 0.3*atr
            if condition_1 and condition_2:
                longed = True
                self.logger.info("Longing trail.")
                if self.telegram is not None:
                    self.telegram.send_log("Longing trail breakout.")
                self.open_new_position(entry=bars[0].close,
                                          stop=close,#bars[0].close - self.sl_atr_fac * atr,#
                                          open_positions=open_positions,
                                          bars=bars,
                                          direction=PositionDirection.LONG,
                                          ExecutionType = "Market")

        # Long EMA bullish reclaim/breakout
        if self.longEMAbreakout and not longed:
            condition_1 = bars[1].close > self.ta_trend_strat.taData_trend_strat.ema_w > bars[1].open
            condition_2 = self.ta_data_trend_strat.natr_4h < self.max_natr_4_trail_bo
            if condition_1 and condition_2:
                longed = True
                self.logger.info("Longing ema breakout.")
                if self.telegram is not None:
                    self.telegram.send_log("Longing ema breakout.")
                self.open_new_position(entry=bars[0].close,
                                          stop=bars[0].low - self.sl_atr_fac * atr,
                                          open_positions=open_positions,
                                          bars=bars,
                                          direction=PositionDirection.LONG,
                                          ExecutionType = "Market")

        # Long strength when certain BBand levels are reclaimed
        if self.longReclaimBBand:
            # Option 1
            sold_off_bband_4 = False
            for i in range(1, range_limit, 1):
                sell_off_level_4 = middleband_vec[-i] + std_vec[-i] * self.std_fac_sell_off_4
                reclaim_level_4 = sell_off_level_4 + std_vec[-i] * self.std_fac_reclaim_4
                if bars[i].close > reclaim_level_4 and i > 1:
                    sold_off_bband_4 = False
                    break
                if bars[i].low <= sell_off_level_4:
                    sold_off_bband_4 = True
                    break

            if sold_off_bband_4:
                sell_off_level_4 = middleband_vec[-1] + std_vec[-1] * self.std_fac_sell_off_4
                reclaim_level_4 = sell_off_level_4 + std_vec[-1] * self.std_fac_reclaim_4
                natr_still_low = self.ta_data_trend_strat.natr_4h < self.max_natr_5_bb_reclaim
                if bars[1].close > reclaim_level_4 and not longed and natr_still_low:
                    longed = True
                    self.logger.info("Longing bollinger bands reclaim 4.")
                    if self.telegram is not None:
                        self.telegram.send_log("Longing bollinger bands reclaim 4.")
                    self.open_new_position(entry=bars[0].close,
                                           stop=min(bars[0].close - self.sl_atr_fac * atr, bars[2].low,
                                                    bars[1].low),
                                           open_positions=open_positions,
                                           bars=bars,
                                           direction=PositionDirection.LONG,
                                           ExecutionType="Market")

            # Option 2
            sold_off_bband = False
            # Find the index when sell_off_level was reached
            for i in range(1,range_limit,1):
                sell_off_level = middleband_vec[-i] - std_vec[-i] * self.std_fac_sell_off
                reclaim_level = sell_off_level + std_vec[-i] * self.std_fac_reclaim
                if bars[i].close > reclaim_level and i > 1:
                    sold_off_bband = False
                    break
                if bars[i].close <= sell_off_level:
                    sold_off_bband = True
                    break

            if sold_off_bband:
                sell_off_level = middleband_vec[-1] - std_vec[-1] * self.std_fac_sell_off
                reclaim_level = sell_off_level + std_vec[-1] * self.std_fac_reclaim
                natr_still_low = self.ta_data_trend_strat.natr_4h < 0.8
                if bars[1].close > reclaim_level and natr_still_low and not longed:
                    longed = True
                    self.logger.info("Longing bollinger bands reclaim 1.")
                    if self.telegram is not None:
                        self.telegram.send_log("Longing bollinger bands reclaim 1.")
                    self.open_new_position(entry=bars[0].close,
                                           stop=bars[0].close - self.sl_atr_fac * atr,
                                           open_positions=open_positions,
                                           bars=bars,
                                           direction=PositionDirection.LONG,
                                           ExecutionType="Market")

            # Option 3
            sold_off_bband_3 = False
            # Find the index when sell_off_level was reached
            for i in range(1, range_limit, 1):
                sell_off_level_3 = middleband_vec[-i] - std_vec[-i] * self.std_fac_sell_off_3
                reclaim_level_3 = sell_off_level_3 + std_vec[-i] * self.std_fac_reclaim_3
                if bars[i].close > reclaim_level_3 and i > 1:
                    sold_off_bband_3 = False
                    break
                if bars[i].low <= sell_off_level_3:
                    sold_off_bband_3 = True
                    break

            if sold_off_bband_3 and market_bullish:
                natr_still_low = self.ta_data_trend_strat.natr_4h < self.max_natr_4_bb_reclaim
                reclaim_level_3 = middleband_vec[-1] - std * abs(self.std_fac_sell_off_3 - self.std_fac_reclaim_3)
                if bars[1].close > reclaim_level_3 and natr_still_low and not longed:
                    longed = True
                    self.logger.info("Longing bollinger bands reclaim 3.")
                    if self.telegram is not None:
                        self.telegram.send_log("Longing bollinger bands reclaim 3.")
                    self.open_new_position(entry=bars[0].close,
                                           stop=min(bars[0].close - self.sl_atr_fac * atr, bars[2].low, bars[1].low),
                                           open_positions=open_positions,
                                           bars=bars,
                                           direction=PositionDirection.LONG,
                                           ExecutionType="Market")

        # Bad: long reversal at lower traill
        if self.longTrailReversal and not longed and \
                bars[1].low < self.ta_strat_one.taData_strat_one.h_lows_trail_vec[-2] < bars[1].close and \
                self.ta_data_trend_strat.rsi_d < self.max_rsi_trail_rev:
            longed = True
            self.logger.info("Longing fakedown.")
            if self.telegram is not None:
                self.telegram.send_log("Longing fakedown.")
            self.open_new_position(entry=bars[0].open,
                                      stop=bars[0].open - self.sl_atr_fac * atr,
                                      open_positions=open_positions,
                                      bars=bars,
                                      direction=PositionDirection.LONG,
                                      ExecutionType = "Market")

        shorted = False
        # Short entry 1: short highest BBand and Trail levels
        if self.short_entry_1:
            condition_1 = bars[1].high > middleband_vec[-2] + std_vec[-2] * self.short_entry_1_std_fac > bars[1].close
            condition_2 = (bars[1].high > self.ta_strat_one.taData_strat_one.h_highs_trail_vec[-5:-2]).any()
            condition_3 = self.ta_data_trend_strat.natr_4h > self.short_entry_1_max_natr
            condition_4 = self.ta_trend_strat.taData_trend_strat.rsi_4h_vec[-1] < self.short_entry_1_max_4h_rsi
            condition_5 = self.ta_trend_strat.taData_trend_strat.rsi_d < self.short_entry_1_max_day_rsi
            condition_6 = abs(bars[1].close-bars[1].open) > atr * 0.2
            if condition_1 and condition_2 and condition_3 and condition_4 and condition_5 and condition_6 and not shorted:
                shorted = True
                self.logger.info("Shorting because above BBand and high-trail")
                if self.telegram is not None:
                    self.telegram.send_log("Shorting because above BBand and high-trail")
                self.open_new_position(entry=bars[0].close,
                                       stop=bars[0].close + self.sl_atr_fac * atr,#
                                       open_positions=open_positions,
                                       bars=bars,
                                       direction=PositionDirection.SHORT,
                                       ExecutionType="Market")

        # Short entry 2: Short lost BBand
        if self.short_entry_2:
            overbought_bband_level = False
            for i in range(1, range_limit, 1):
                overbought_level = middleband_vec[-i] + std_vec[-i] * self.short_entry_2_std_fac
                entry_level = overbought_level - std_vec[-i] * self.short_entry_2_std_fac_entry
                if bars[i].close < entry_level and i > 1:
                    overbought_bband_level = False
                    break
                if bars[i].high >= overbought_level:
                    overbought_bband_level = True
                    break

            if overbought_bband_level and not market_bullish:
                natr_in_range = self.short_entry_2_max_natr > self.ta_data_trend_strat.natr_4h > self.short_entry_2_min_natr
                shot_over = bars[1].high > bars[2].high
                if bars[1].close < entry_level and not shorted and natr_in_range and shot_over:
                    shorted = True
                    self.logger.info("Shorting lost bband level")
                    if self.telegram is not None:
                        self.telegram.send_log("Shorting lost bband level")
                    self.open_new_position(entry= bars[0].close,
                                           stop= bars[0].close + self.sl_atr_fac * atr * 0.4,
                                           open_positions=open_positions,
                                           bars=bars,
                                           direction=PositionDirection.SHORT,
                                           ExecutionType="Market")

        # short entry 3: break down from lower trail
        if self.shortTrailBreakdown and not shorted:
            trail_broke = (bars[1].close < self.ta_strat_one.taData_strat_one.h_lows_trail_vec[-3:-2]).all()
            opened_above_trail = (bars[1].open > self.ta_strat_one.taData_strat_one.h_lows_trail_vec[-5:-2]).all()
            natr_low = self.ta_data_trend_strat.natr_4h < self.short_entry_3_max_natr
            if trail_broke and opened_above_trail and natr_low and not market_bullish:
                self.logger.info("Shorting trail break.")
                if self.telegram is not None:
                    self.telegram.send_log("Shorting trail break.")
                self.open_new_position(entry=bars[0].open,
                                       stop=bars[0].open + self.sl_atr_fac * atr,
                                       open_positions=open_positions,
                                       bars=bars,
                                       direction=PositionDirection.SHORT,
                                       ExecutionType="Market")

        # trade swing breakouts by market orders
        if self.tradeSwinBreakouts:
            depth = 40
            foundSwingHigh = False
            foundSwingLow = False
            idxSwingHigh = 0
            idxSwingLow = 0
            for i in range(3, depth):
                if bars[i+2].high < bars[i+1].high < bars[i].high > bars[i-1].high:
                    foundSwingHigh = True
                    idxSwingHigh = i
                    break

            if foundSwingHigh:
                close_values = [bar.close for bar in bars[2:idxSwingHigh]]
                alreadyLonged = any(close > bars[idxSwingHigh].high for close in close_values)
            else:
                alreadyLonged = True

            for i in range(3, depth):
                if bars[i+3].low > bars[i+2].low > bars[i+1].low > bars[i].low < bars[i-1].low < bars[i-2].low:
                    foundSwingLow = True
                    idxSwingLow = i
                    break
            if foundSwingLow:
                close_values = [bar.close for bar in bars[2:idxSwingLow]]
                alreadyShorted = any(close < bars[idxSwingLow].low for close in close_values)
            else:
                alreadyShorted = True

            if foundSwingHigh and foundSwingLow and not longed and not alreadyLonged and not alreadyShorted:
                condition_1 = 60 < self.ta_trend_strat.taData_trend_strat.rsi_4h_vec[-1] < 80
                if bars[1].close > bars[idxSwingHigh].high and condition_1:
                    self.logger.info("Longing swing breakout.")
                    if self.telegram is not None:
                        self.telegram.send_log("Longing swing breakout.")
                    self.open_new_position(entry=bars[0].close,
                                              stop=bars[0].close - self.sl_atr_fac * atr,
                                              open_positions=open_positions,
                                              bars=bars,
                                              direction=PositionDirection.LONG,
                                              ExecutionType = "Market")

            if foundSwingLow and foundSwingHigh and not shorted and not alreadyShorted and not alreadyLonged:
                condition_1 = 35 < self.ta_trend_strat.taData_trend_strat.rsi_4h_vec[-1]
                if bars[1].close < bars[idxSwingLow].low and condition_1:
                    self.logger.info("Shorting swing break.")
                    if self.telegram is not None:
                        self.telegram.send_log("Shorting swing break.")
                    self.open_new_position(entry=bars[0].close,
                                              stop=bars[1].high,
                                              open_positions=open_positions,
                                              bars=bars,
                                              direction=PositionDirection.SHORT,
                                              ExecutionType = "Market")

        if not longed and not shorted:
            self.logger.info("No new entries for now.")
            if self.telegram is not None:
                self.telegram.send_log("No new entries for now.")

    def calc_entry_and_exit(self, bars):
        # Calculate potential trade entries
        longEntry = self.symbol.normalizePrice(self.ta_strat_one.taData_strat_one.h_highs_trail_vec[-1], roundUp=True)
        shortEntry = self.symbol.normalizePrice(self.ta_strat_one.taData_strat_one.h_lows_trail_vec[-1], roundUp=False)

        # Calculate stops
        stopLong = longEntry - self.ta_data_trend_strat.atr_4h * self.sl_atr_fac
        stopShort = shortEntry + self.ta_data_trend_strat.atr_4h * self.sl_atr_fac

        stopLong = self.symbol.normalizePrice(stopLong, roundUp=False)
        stopShort = self.symbol.normalizePrice(stopShort, roundUp=True)

        # amount
        expectedEntrySlippagePer = 0.0015 if self.limit_entry_offset_perc is None else 0
        expectedExitSlippagePer = 0.0015
        longAmount = self.calc_pos_size(risk=self.risk_factor, exitPrice=stopLong * (1 - expectedExitSlippagePer),
                                        entry=longEntry * (1 + expectedEntrySlippagePer), atr=0)
        shortAmount = self.calc_pos_size(risk=self.risk_factor, exitPrice=stopShort * (1 + expectedExitSlippagePer),
                                         entry=shortEntry * (1 - expectedEntrySlippagePer), atr=0)

        return longEntry, shortEntry, stopLong, stopShort, longAmount, shortAmount

    def constant_trail(self, periodStart, periodEnd, trail):
        is_constant = True
        for i in range(periodStart, periodEnd):
            if trail[-i] != trail[-(i + 1)]:
                is_constant = False
        return is_constant

    def higher_equal_h_trail(self, periodStart, periodEnd, trail):
        higher_equal = True
        for i in range(periodStart, periodEnd):
            if trail[-i] > trail[-(i + 1)]:
                higher_equal = False
        return higher_equal

    def lower_equal_h_trail(self, periodStart, periodEnd, trail):
        lower_equal = True
        for i in range(periodStart, periodEnd):
            if trail[-i] < trail[-(i + 1)]:
                lower_equal = False
        return lower_equal

    '''def new_entries_allowed(self, bars):
        self.data_strat_one.shortsAllowed = True
        self.data_strat_one.longsAllowed = True
        for i in range(1, self.nmb_bars_entry):
            if self.ta_data_trend_strat.lows_trail_4h_vec[-i] != \
                    self.ta_data_trend_strat.lows_trail_4h_vec[-(i + 1)]:
                self.data_strat_one.shortsAllowed = False

            if self.ta_data_trend_strat.highs_trail_4h_vec[-i] != \
                    self.ta_data_trend_strat.highs_trail_4h_vec[-(i + 1)]:
                self.data_strat_one.longsAllowed = False'''

    def manage_open_position(self, p, bars, account, pos_ids_to_cancel):
        super().manage_open_position(p, bars, account, pos_ids_to_cancel)
        # now local position management, if necessary

    def update_existing_entries(self, account, open_positions, longEntry, shortEntry, stopLong, stopShort, longAmount, shortAmount):
        foundLong, foundShort = super().update_existing_entries(account, open_positions, longEntry, shortEntry, stopLong, stopShort, longAmount, shortAmount)
        # now local updates, if necessary
        return foundLong, foundShort

    def get_data_for_plot(self, bar: Bar):
        plot_data = Indicator.get_data_static(bar, self.myId())
        if plot_data is not None:
            return plot_data
        else:
            return [bar.close, bar.close, bar.close, bar.close]

    def add_to_price_data_plot(self, fig: go.Figure, bars: List[Bar], time):
        super().add_to_price_data_plot(fig, bars, time)

        # Plot TA-generated data
        offset = 0

        # Plot Strategy-generated Data
        plotStrategyData = False
        if plotStrategyData:
            sub_data = list(map(lambda b: self.get_data_for_plot(b)[0], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line={"width": 1, "color": "cyan"},
                            name=self.myId() + "_" + "Long_Entry")
            sub_data = list(map(lambda b: self.get_data_for_plot(b)[1], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line={"width": 1, "color": "mediumpurple"},
                            name=self.myId() + "_" + "Long_Stop")
            sub_data = list(map(lambda b: self.get_data_for_plot(b)[2], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line={"width": 1, "color": "cyan"},
                            name=self.myId() + "_" + "Short_Entry")
            sub_data = list(map(lambda b: self.get_data_for_plot(b)[3], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line={"width": 1, "color": "mediumpurple"},
                            name=self.myId() + "_" + "Short_Stop")

        # plot ta data
        # get ta data settings
        styles = self.ta_strat_one.get_line_styles()
        names = self.ta_strat_one.get_line_names()
        offset = 0

        plotTrails = True
        if plotTrails and self.plotIndicators:
            sub_data = list(map(lambda b: self.ta_strat_one.get_data_for_plot(b)[0], bars))  # 4H-High
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[0],
                            name=self.ta_strat_one.id + "_" + names[0])
            sub_data = list(map(lambda b: self.ta_strat_one.get_data_for_plot(b)[1], bars))  # 4H-Low
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[1],
                            name=self.ta_strat_one.id + "_" + names[1])

    def add_to_normalized_plot(self, fig: go.Figure, bars: List[Bar], time):
        super().add_to_normalized_plot(fig, bars, time)


class DataTAStrategyOne:
    def __init__(self):
        self.h_highs_trail_vec = None
        self.h_lows_trail_vec = None
        self.h_highs_trail = None
        self.h_lows_trail = None


class TAStrategyOne(Indicator):
    ''' Run technical analysis here and store data in TAdataTrendStrategy '''

    def __init__(self,
                 timeframe: int = 240,
                 h_highs_trail_period: int = 10,
                 h_lows_trail_period: int = 10,
                 ta_data_trend_strat: TAdataTrendStrategy() = None
                 ):
        super().__init__('TAStrategyOne')
        # parant data
        self.ta_data_trend_strat = ta_data_trend_strat
        # local data
        self.taData_strat_one = DataTAStrategyOne()
        self.ranging_buffer = 0
        # Input parameters
        self.bars_per_week = int(60*24*7 / timeframe)
        self.bars_per_day = int(60*24 / timeframe)
        self.h_highs_trail_period = h_highs_trail_period
        self.h_lows_trail_period = h_lows_trail_period

    def on_tick(self, bars: List[Bar]):
        #print("TA analysis StrategyOne")
        self.run_ta_analysis()
        self.write_data_for_plot(bars)

    def set_ta_data_trend_strat(self, ta_data_trend_strat = None):
        self.ta_data_trend_strat = ta_data_trend_strat

    def get_ta_data(self):
        return self.taData_strat_one

    def run_ta_analysis(self):
        # Trails
        self.taData_strat_one.h_highs_trail_vec = talib.MAX(self.ta_data_trend_strat.talibbars.high, self.h_highs_trail_period)
        self.taData_strat_one.h_lows_trail_vec = talib.MIN(self.ta_data_trend_strat.talibbars.low, self.h_lows_trail_period)

        self.taData_strat_one.h_highs_trail = self.taData_strat_one.h_highs_trail_vec[-1] if not np.isnan(self.taData_strat_one.h_highs_trail_vec[-1]) else None
        self.taData_strat_one.h_lows_trail = self.taData_strat_one.h_lows_trail_vec[-1] if not np.isnan(self.taData_strat_one.h_lows_trail_vec[-1]) else None

    def write_data_for_plot(self, bars: List[Bar]):
        plot_data = [self.taData_strat_one.h_highs_trail,
                     self.taData_strat_one.h_lows_trail
                    ]
        self.write_data(bars[0], plot_data)  # [0] because we only know about it after the candle is closed and processed

    def get_line_names(self):
        return ["%1.fx4H-High" % self.h_highs_trail_period,         # 4H-High
                "%1.fx4H-Low" % self.h_lows_trail_period            # 4H-Low
                ]

    def get_number_of_lines(self):
        return 2

    def get_line_styles(self):
        return [
            {"width": 1, "color": "green", "dash": "dot"},          # 4H-High
            {"width": 1, "color": "red", "dash": "dot"},            # 4H-Low
               ]

    def get_data_for_plot(self, bar: Bar):
        plot_data = self.get_data(bar)
        if plot_data is not None:
            return plot_data
        else:
            return [bar.close, bar.close                            # 4H-Trails
             ]
