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


class StrategyOne(TrendStrategy):
    # Strategy description:
    def __init__(self,
                 # StrategyOne
                 var_1: float = 0, var_2: float = 0,
                 std_fac_sell_off: float = 1, std_fac_reclaim: float = 1,
                 std_fac_sell_off_3: float = 1, std_fac_reclaim_3: float = 1,
                 h_highs_trail_period: int = 1, h_lows_trail_period: int = 1,
                 shortTrailBreakdown: bool = False, longTrailBreakout: bool = False,
                 tradeSwinBreakouts: bool = False, tradeWithLimitOrders: bool = False,short_entry_1: bool = False,
                 long_bband_reclaim: bool = False,
                 max_natr_4_trail_bo: float = 2, max_natr_4_bb_reclaim: float = 2,
                 short_entry_1_std_fac: float = 1,
                 shortsAllowed: bool = False, longsAllowed: bool = False,
                 # TrendStrategy
                 timeframe: int = 240, ema_w_period: int = 2, highs_trail_4h_period: int = 1, lows_trail_4h_period: int = 1,
                 days_buffer_bear: int = 2, days_buffer_ranging: int = 0, atr_4h_period: int = 10, natr_4h_period_slow: int = 10,
                 bbands_4h_period: int = 10, bband_history_size: int =10, rsi_4h_period: int = 10,
                 plotIndicators: bool = False, plot_RSI: bool = False,
                 trend_var_1: float = 0,
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
        self.tradeWithLimitOrders = tradeWithLimitOrders
        self.longTrailBreakout = longTrailBreakout
        self.long_bband_reclaim = long_bband_reclaim
        self.shortTrailBreakdown = shortTrailBreakdown
        self.tradeSwinBreakouts = tradeSwinBreakouts
        self.short_entry_1 = short_entry_1
        self.short_entry_1_std_fac = short_entry_1_std_fac
        self.max_natr_4_trail_bo = max_natr_4_trail_bo
        self.max_natr_4_bb_reclaim = max_natr_4_bb_reclaim
        self.std_fac_sell_off = std_fac_sell_off
        self.std_fac_reclaim = std_fac_reclaim
        self.std_fac_sell_off_3 = std_fac_sell_off_3
        self.std_fac_reclaim_3 = std_fac_reclaim_3
        self.overboughtBB = 0
        self.overboughtBB_entry = 0
        self.sl_atr_fac = sl_atr_fac
        self.shortsAllowed = shortsAllowed
        self.longsAllowed = longsAllowed

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

        longed = False
        shorted = False

        # Entries by Market Orders
        std = self.ta_data_trend_strat.bbands_4h.std
        std_vec = self.ta_data_trend_strat.bbands_4h.std_vec
        atr = self.ta_data_trend_strat.atr_4h
        # middleband = self.ta_data_trend_strat.bbands_4h.middleband
        middleband_vec = self.ta_data_trend_strat.bbands_4h.middleband_vec
        market_bullish = self.ta_data_trend_strat.marketRegime == MarketRegime.BULL
        # market_bearish = self.ta_data_trend_strat.marketRegime == MarketRegime.BEAR
        range_limit = len(middleband_vec)

        # limit order - entries
        if self.tradeWithLimitOrders:
            # Calculate potential trade entries
            longEntry, shortEntry, stopLong, stopShort, longAmount, shortAmount, alreadyLonged, alreadyShorted = self.calc_entry_and_exit(bars)

            if longEntry is not None and shortEntry is not None:
                foundLong, foundShort = self.update_existing_entries(account, open_positions, longEntry, shortEntry,
                                                                     stopLong, stopShort, longAmount, shortAmount)

                # Set entries if no orders are found and the market conditions allow it
                # go LONG
                if not foundLong and self.longsAllowed and directionFilter >= 0 and self.ta_data_trend_strat.natr_4h < 0.8 and\
                    self.ta_trend_strat.taData_trend_strat.rsi_4h_vec[-1] > 35 and\
                        self.ta_trend_strat.taData_trend_strat.rsi_d > 55:
                    self.open_new_position(PositionDirection.LONG, bars, stopLong, open_positions, longEntry,"StopLoss")
                # go SHORT
                if not foundShort and self.shortsAllowed and directionFilter <= 0 and shortEntry is not None:
                    pass

                # Save parameters
                self.data_strat_one.longEntry = longEntry
                self.data_strat_one.shortEntry = shortEntry
                self.data_strat_one.stopLong = stopLong
                self.data_strat_one.stopShort = stopShort

                # Write Data to plot
                plot_data = [self.data_strat_one.longEntry, self.data_strat_one.stopLong,
                             self.data_strat_one.shortEntry, self.data_strat_one.stopShort]
                Indicator.write_data_static(bars[0], plot_data, self.myId())

        # long trail breakout
        if self.longTrailBreakout and not longed and self.longsAllowed:
            condition_1 = bars[1].high > self.ta_data_trend_strat.highs_trail_4h_vec[-2]
            condition_2 = self.ta_data_trend_strat.natr_4h < self.max_natr_4_trail_bo
            close = bars[1].low if bars[1].close > bars[1].open else bars[1].low - 0.3*atr
            if condition_1 and condition_2:
                longed = True
                self.logger.info("Longing trail.")
                if self.telegram is not None:
                    self.telegram.send_log("Longing trail breakout.")
                self.open_new_position(entry=bars[0].close,
                                          stop=close,
                                          open_positions=open_positions,
                                          bars=bars,
                                          direction=PositionDirection.LONG,
                                          ExecutionType = "Market")

        # Long strength when certain BBand levels are reclaimed
        if self.long_bband_reclaim:
            # Option 1
            option_1 = False
            if option_1:
                resetted_bband_entry = False
                std_fac_reset = 3
                support_level_bband_std_fac = 2.5
                #max_natr_1_bb_reclaim = self.var_1
                for i in range(1, range_limit, 1):
                    reset_bband_level = middleband_vec[-i] + std_vec[-i] * std_fac_reset
                    support_level = reset_bband_level - std_vec[-i] * support_level_bband_std_fac
                    if bars[i].close > reset_bband_level:
                        resetted_bband_entry = True
                        break
                    if bars[i].close < support_level and i > 1:
                        resetted_bband_entry = False
                        break

                if resetted_bband_entry:
                    reset_bband_level = middleband_vec[-1] + std_vec[-1] * std_fac_reset
                    support_level = reset_bband_level - std_vec[-1] * support_level_bband_std_fac
                    if bars[1].close < support_level and not longed and self.longsAllowed and market_bullish:
                        longed = True
                        self.logger.info("Longing bband support")
                        if self.telegram is not None:
                            self.telegram.send_log("Longing bband support")
                        self.open_new_position(entry=bars[0].close,
                                               stop=min(bars[0].close - self.sl_atr_fac * atr, bars[2].low, bars[1].low),
                                               open_positions=open_positions,
                                               bars=bars,
                                               direction=PositionDirection.LONG,
                                               ExecutionType="Market")

            option_2 = True
            if option_2:
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
                    natr_still_low = self.ta_data_trend_strat.natr_4h < self.max_natr_4_bb_reclaim
                    if bars[1].close > reclaim_level and natr_still_low and not longed and self.longsAllowed:
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
            option_3 = False
            if option_3:
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
                    if bars[1].close > reclaim_level_3 and natr_still_low and not longed and self.longsAllowed:
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

        # short trail breakdown
        if self.shortTrailBreakdown and not shorted and self.shortsAllowed:
            trail_broke = (bars[1].close < self.ta_strat_one.taData_strat_one.h_body_lows_trail_vec[-35:-2]).all()
            opened_above_trail = (bars[1].open > self.ta_strat_one.taData_strat_one.h_body_lows_trail_vec[-50:-2]).all()
            if trail_broke and opened_above_trail:
                self.logger.info("Shorting trail break.")
                if self.telegram is not None:
                    self.telegram.send_log("Shorting trail break.")
                shorted = True
                self.open_new_position(entry=bars[0].open,
                                       stop=bars[0].close +  atr * 0.5,
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
                if bars[i+2].close < bars[i+1].close < bars[i].close > bars[i-1].close:
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

            if foundSwingHigh and foundSwingLow and not longed and not alreadyLonged and not alreadyShorted and self.longsAllowed:
                condition_1 = 60 < self.ta_trend_strat.taData_trend_strat.rsi_4h_vec[-1] < 80
                if bars[1].close > bars[idxSwingHigh].high and condition_1:
                    self.logger.info("Longing swing breakout.")
                    if self.telegram is not None:
                        self.telegram.send_log("Longing swing breakout.")
                    longed = True
                    self.open_new_position(entry=bars[0].close,
                                              stop=bars[0].close -  atr * 5,
                                              open_positions=open_positions,
                                              bars=bars,
                                              direction=PositionDirection.LONG,
                                              ExecutionType = "Market")

            if foundSwingLow and foundSwingHigh and not shorted and not alreadyShorted and not alreadyLonged and self.shortsAllowed:
                condition_1 = 35 < self.ta_trend_strat.taData_trend_strat.rsi_4h_vec[-1]
                if bars[1].close < bars[idxSwingLow].low and condition_1:
                    self.logger.info("Shorting swing break.")
                    if self.telegram is not None:
                        self.telegram.send_log("Shorting swing break.")
                    shorted = True
                    self.open_new_position(entry=bars[0].close,
                                              stop=max(bars[1].high, bars[2].high),
                                              open_positions=open_positions,
                                              bars=bars,
                                              direction=PositionDirection.SHORT,
                                              ExecutionType = "Market")

        # short entry 1
        if self.short_entry_1 and not market_bullish and not shorted and self.shortsAllowed:
            condition_1 = bars[1].high > middleband_vec[-2] + std_vec[-2] * self.short_entry_1_std_fac
            condition_2 = bars[2].high > middleband_vec[-3] + std_vec[-3] * self.short_entry_1_std_fac
            condition_3 = (bars[1].high > self.ta_strat_one.taData_strat_one.h_highs_trail_vec[-3:-2]).any()
            condition_4 = middleband_vec[-2] + std_vec[-2] * 2.3 > bars[1].close
            if (condition_1 or condition_2) and condition_3 and condition_4:
                self.logger.info("Shorting SFP")
                if self.telegram is not None:
                    self.telegram.send_log("Shorting SFP")
                shorted = True
                self.open_new_position(entry=bars[0].close,
                                       stop=bars[0].close +  atr * 1.5,
                                       open_positions=open_positions,
                                       bars=bars,
                                       direction=PositionDirection.SHORT,
                                       ExecutionType="Market")

        if not self.longsAllowed:
            self.logger.info("Longs not allowed.")
            if self.telegram is not None:
                self.telegram.send_log("Longs not allowed.")
        if not self.shortsAllowed:
            self.logger.info("Shorts not allowed.")
            if self.telegram is not None:
                self.telegram.send_log("Shorts not allowed.")
        if not longed and not shorted:
            self.logger.info("No new entries for now.")
            if self.telegram is not None:
                self.telegram.send_log("No new entries for now.")

    def calc_entry_and_exit(self, bars):
        # find swing highs and lows
        depth = 40
        foundSwingHigh = False
        foundSwingLow = False
        idxSwingHigh = 0
        idxSwingLow = 0
        for i in range(2, depth):
            condition_1 = bars[i + 2].close < bars[i].close
            condition_2 = bars[i + 1].close < bars[i].close
            condition_3 = bars[i].close > bars[i - 1].close
            condition_5 = bars[i + 3].close < bars[i].close
            if condition_1 and condition_2 and condition_3 and condition_5:
                foundSwingHigh = True
                idxSwingHigh = i
                break

        if foundSwingHigh:
            high_values = [bar.close for bar in bars[1:idxSwingHigh]]
            alreadyLonged = any(high > bars[idxSwingHigh].close for high in high_values)
        else:
            alreadyLonged = True

        for i in range(5, depth):
            cond_1 = bars[i + 2].close > bars[i + 1].close
            cond_2 = bars[i + 1].close > bars[i].close
            cond_3 = bars[i].close < bars[i - 1].close
            cond_4 = cond_1 and cond_2 and cond_3
            if cond_4:
                foundSwingLow = True
                idxSwingLow = i
                break
        if foundSwingLow:
            low_values = [bar.close for bar in bars[1:idxSwingLow]]
            alreadyShorted = any(low < bars[idxSwingLow].close for low in low_values)
        else:
            alreadyShorted = True

        if foundSwingHigh and not alreadyLonged and foundSwingLow and not alreadyShorted:
            # Calculate potential trade entries
            longEntry = self.symbol.normalizePrice(bars[idxSwingHigh].high, roundUp=True)
            shortEntry = self.symbol.normalizePrice(bars[idxSwingLow].low, roundUp=False)

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
        else:
            longEntry = None
            shortEntry = None
            stopLong = None
            stopShort = None
            longAmount = None
            shortAmount = None

        return longEntry, shortEntry, stopLong, stopShort, longAmount, shortAmount, alreadyLonged, alreadyShorted

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
        self.h_body_lows_trail_vec = None
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
        self.taData_strat_one.h_body_lows_trail_vec = talib.MIN(self.ta_data_trend_strat.talibbars.close, self.h_lows_trail_period)

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
