import math
from typing import List

import plotly.graph_objects as go
import numpy as np
import talib

from kuegi_bot.bots.strategies.trend_strategy import TrendStrategy, TAdataTrendStrategy, MarketRegime, MarketDynamic, BBands
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
                 var_1: float = 0, var_2: float = 0, risk_ref: float = 1, reduceRisk: bool = False, max_r: float = 20,
                 entry_4_std_fac: float = 1, entry_4_std_fac_reclaim: float = 1,
                 h_highs_trail_period: int = 1, h_lows_trail_period: int = 1,
                 entry_5: bool = False, entry_3: bool = False,
                 entry_6: bool = False, entry_2: bool = False, entry_7: bool = False,
                 entry_1:bool = False, entry_1_atr_fac: float = 1, entry_1_vol_fac: float = 2.0,
                 entry_4: bool = False,
                 entry_3_max_natr: float = 2, entry_3_vol_fac: float = 2.0, entry_3_rsi_4h: int = 50,
                 entry_7_std_fac: float = 1, entry_7_4h_rsi: float = 2.5, entry_7_vol_fac: float = 2,
                 shortsAllowed: bool = False, longsAllowed: bool = False,
                 entry_2_max_natr: float = 1, entry_2_min_rsi_4h: int = 50, entry_2_min_rsi_d:int = 80,
                 entry_2_min_natr: float = 1, entry_2_min_rsi_4h_short:int=50,entry_2_min_rsi_d_short:int=50,
                 entry_3_atr_fac: float = 1, entry_5_natr: float = 2, entry_5_rsi_d: int = 40, entry_5_rsi_4h: int = 80,
                 entry_5_atr_fac: float = 0.8, entry_5_trail_1_period: int = 10, entry_5_trail_2_period: int = 10,
                 entry_5_vol_fac: float = 2.0,
                 entry_6_rsi_4h_max: int = 90, entry_6_max_natr: float = 2,
                 entry_6_atr_fac: float = 5, entry_8: bool = False, entry_9:bool = False, entry_10: bool = False,
                 entry_8_vol_fac: float = 2.0,
                 entry_9_std: float = 1, entry_9_4h_rsi: int = 50, entry_9_atr: float = 2,
                 entry_10_natr: float = 2, entry_10_natr_ath: float = 2, entry_10_rsi_4h: int = 50,
                 tp_fac_strat_one: float = 0,
                 plotStrategyOneData: bool = False, plotTrailsStatOne: bool = False,
                 # TrendStrategy
                 timeframe: int = 240, ema_w_period: int = 2, highs_trail_4h_period: int = 1, lows_trail_4h_period: int = 1,
                 days_buffer_bear: int = 2, days_buffer_bull: int = 0, atr_4h_period: int = 10, natr_4h_period_slow: int = 10,
                 bbands_4h_period: int = 10, rsi_4h_period: int = 10, volume_sma_4h_period: int = 100,
                 plotIndicators: bool = False, plot_RSI: bool = False, use_shapes: bool = False, plotBackgroundColor4Trend: bool = False,
                 plotTrailsAndEMAs: bool = False, plotBBands:bool=False, plotATR:bool=False, trend_atr_fac: float = 0.5,
                 trend_var_1: float = 0,
                 # Risk
                 risk_with_trend: float = 1, risk_counter_trend: float = 1, risk_ranging: float = 1,
                 # SL
                 sl_atr_fac: float = 2, be_by_middleband: bool = True, be_by_opposite: bool = True, stop_at_middleband: bool = True,
                 tp_at_middleband: bool = True, atr_buffer_fac: float = 0, tp_on_opposite: bool = True, stop_at_new_entry: bool = False,
                 trail_sl_with_bband: bool = False, stop_short_at_middleband: bool = False, stop_at_trail: bool = False,
                 stop_at_lowerband: bool = False,
                 moving_sl_atr_fac: float = 5, sl_upper_bb_std_fac: float = 1, sl_lower_bb_std_fac: float = 1,
                 ema_multiple_4_tp: float = 10,
                 # StrategyWithTradeManagement
                 maxPositions: int = 100, consolidate: bool = False, close_on_opposite: bool = False, bars_till_cancel_triggered: int = 3,
                 limit_entry_offset_perc: float = -0.1, delayed_cancel: bool = False, cancel_on_filter: bool = True, tp_fac:float = 0
                 ):
        super().__init__(
            # TrendStrategy
            timeframe = timeframe, ema_w_period= ema_w_period, highs_trail_4h_period= highs_trail_4h_period,
            lows_trail_4h_period= lows_trail_4h_period, days_buffer_bear= days_buffer_bear, days_buffer_bull= days_buffer_bull,
            atr_4h_period= atr_4h_period, natr_4h_period_slow= natr_4h_period_slow, trend_atr_fac = trend_atr_fac,
            bbands_4h_period= bbands_4h_period, rsi_4h_period = rsi_4h_period,
            volume_sma_4h_period =volume_sma_4h_period,
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
            ema_multiple_4_tp = ema_multiple_4_tp,
            # Plots
            use_shapes = use_shapes, plotBackgroundColor4Trend = plotBackgroundColor4Trend, plotTrailsAndEMAs=plotTrailsAndEMAs,
            plotBBands = plotBBands, plotATR=plotATR,
            # StrategyWithTradeManagement
            maxPositions = maxPositions, consolidate = consolidate, close_on_opposite = close_on_opposite, bars_till_cancel_triggered = bars_till_cancel_triggered,
            limit_entry_offset_perc = limit_entry_offset_perc, delayed_cancel = delayed_cancel, cancel_on_filter = cancel_on_filter, tp_fac = tp_fac
            )
        self.ta_data_trend_strat = TAdataTrendStrategy()
        self.data_strat_one = DataStrategyOne()
        self.ta_strat_one = TAStrategyOne(timeframe = timeframe, h_highs_trail_period= h_highs_trail_period,
                                          h_lows_trail_period = h_lows_trail_period, ta_data_trend_strat = self.ta_data_trend_strat)
        # Entry variables
        self.var_1 = var_1 # for backtesting
        self.var_2 = var_2 # for backtesting
        self.max_r = max_r
        self.entry_1 = entry_1
        self.entry_2 = entry_2
        self.entry_3 = entry_3
        self.entry_4 = entry_4
        self.entry_5 = entry_5
        self.entry_6 = entry_6
        self.entry_8 = entry_8
        self.entry_7 = entry_7
        self.entry_9 = entry_9
        self.entry_10 = entry_10
        self.risk_ref = risk_ref
        self.reduceRisk = reduceRisk
        self.entry_1_atr_fac = entry_1_atr_fac
        self.entry_1_vol_fac = entry_1_vol_fac
        self.entry_2_max_natr = entry_2_max_natr
        self.entry_2_min_natr = entry_2_min_natr
        self.entry_2_min_rsi_4h = entry_2_min_rsi_4h
        self.entry_2_min_rsi_4h_short = entry_2_min_rsi_4h_short
        self.entry_2_min_rsi_d = entry_2_min_rsi_d
        self.entry_2_min_rsi_d_short = entry_2_min_rsi_d_short
        self.entry_3_atr_fac = entry_3_atr_fac
        self.entry_3_vol_fac = entry_3_vol_fac
        self.entry_3_max_natr = entry_3_max_natr
        self.entry_3_rsi_4h = entry_3_rsi_4h
        self.entry_4_std_fac = entry_4_std_fac
        self.entry_4_std_fac_reclaim = entry_4_std_fac_reclaim
        self.entry_5_natr = entry_5_natr
        self.entry_5_rsi_d = entry_5_rsi_d
        self.entry_5_rsi_4h = entry_5_rsi_4h
        self.entry_5_atr_fac = entry_5_atr_fac
        self.entry_5_trail_1_period = entry_5_trail_1_period
        self.entry_5_trail_2_period = entry_5_trail_2_period
        self.entry_5_vol_fac = entry_5_vol_fac
        self.entry_6_max_natr = entry_6_max_natr
        self.entry_6_rsi_4h_max = entry_6_rsi_4h_max
        self.entry_6_atr_fac = entry_6_atr_fac
        self.entry_7_4h_rsi = entry_7_4h_rsi
        self.entry_7_std_fac = entry_7_std_fac
        self.entry_7_vol_fac = entry_7_vol_fac
        self.entry_8_vol_fac = entry_8_vol_fac
        self.entry_9_4h_rsi = entry_9_4h_rsi
        self.entry_9_std = entry_9_std
        self.entry_9_atr = entry_9_atr
        self.entry_10_natr = entry_10_natr
        self.entry_10_natr_ath = entry_10_natr_ath
        self.entry_10_rsi_4h = entry_10_rsi_4h
        self.sl_atr_fac = sl_atr_fac
        self.shortsAllowed = shortsAllowed
        self.longsAllowed = longsAllowed
        self.tp_fac_strat_one = tp_fac_strat_one
        self.plotStrategyOneData = plotStrategyOneData
        self.plotTrailsStatOne = plotTrailsStatOne

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
            self.logger.info('Current ta indicator values of strat one:')
            self.logger.info(vars(self.ta_strat_one.taData_strat_one))

    def position_got_opened_or_changed(self, position: Position, bars: List[Bar], account: Account, open_positions):
        super().position_got_opened_or_changed(position, bars, account, open_positions)

        gotTp = False
        for order in account.open_orders:
            orderType = TradingBot.order_type_from_order_id(order.id)
            posId = TradingBot.position_id_from_order_id(order.id)
            if self.tp_fac_strat_one > 0 and orderType == OrderType.TP and posId == position.id:
                gotTp = True
                amount = self.symbol.normalizeSize(-position.current_open_amount + order.executed_amount)
                if abs(order.amount - amount) > self.symbol.lotSize / 2:
                    order.amount = amount
                    self.order_interface.update_order(order)

        if self.tp_fac_strat_one > 0 and not gotTp and self.ta_trend_strat.taData_trend_strat.talibbars.open is not None:
            condition_1 = position.amount < 0
            condition_2 = (self.ta_trend_strat.taData_trend_strat.talibbars.open[-1] <
                           self.ta_data_trend_strat.bbands_4h.middleband - self.ta_data_trend_strat.bbands_4h.std * 2)
            condition_3 = self.ta_data_trend_strat.rsi_d < 40
            if condition_1 and (condition_3 or condition_2):
                ref = position.filled_entry - position.initial_stop
                tp = max(0.0,position.filled_entry + ref * self.tp_fac_strat_one)
                order = Order(orderId=TradingBot.generate_order_id(positionId=position.id,type=OrderType.TP),
                              limit=tp,amount=-position.amount)
                self.order_interface.send_order(order)

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

        if self.reduceRisk:
            totalPos = 0
            totalWorstCase = 0
            for pos in open_positions.values():
                filled_entry=pos.filled_entry
                amount = pos.amount
                if filled_entry is not None:
                    for o in pos.connectedOrders:
                        orderType = TradingBot.order_type_from_order_id(o.id)
                        if orderType == OrderType.SL:
                            initial_stop = pos.initial_stop
                            wanted_entry = pos.wanted_entry
                            sl = o.trigger_price
                            if self.symbol.isInverse:
                                worstCase = (1 / sl - 1 / filled_entry) / (1 / wanted_entry - 1 / initial_stop)
                                initialRisk = amount / initial_stop - amount / wanted_entry
                            else:
                                worstCase = (sl - filled_entry) / (wanted_entry - initial_stop)
                                initialRisk = amount * (wanted_entry - initial_stop)

                            totalPos += pos.amount
                            totalWorstCase += (worstCase*initialRisk)

            totalWorstCase = totalWorstCase / self.risk_ref
            if totalWorstCase < - self.max_r:
                self.logger.info("Too much active risk. No new entries.")
                if self.telegram is not None:
                    self.telegram.send_log("Too much active risk. No new entries.")
                    self.telegram.send_log("totalWorstCase:" + str(totalWorstCase))
                return

        self.logger.info("New bar. Checking for new entry options")
        self.logger.info("Market Regime: "+str(self.ta_data_trend_strat.marketRegime))
        if self.telegram is not None and not self.symbol.baseCoin == 'USDT':
            self.telegram.send_log("Market Regime: "+str(self.ta_data_trend_strat.marketRegime))
            self.telegram.send_log("NATR: %.2f" % self.ta_data_trend_strat.natr_4h)

        longed = False
        shorted = False

        # Entries by Market Orders
        std = self.ta_data_trend_strat.bbands_4h.std
        std_vec = self.ta_data_trend_strat.bbands_4h.std_vec
        atr = self.ta_data_trend_strat.atr_4h
        atr_trail_mix = self.ta_data_trend_strat.atr_trail_mix
        natr_4h = self.ta_data_trend_strat.natr_4h
        middleband = self.ta_data_trend_strat.bbands_4h.middleband
        middleband_vec = self.ta_data_trend_strat.bbands_4h.middleband_vec
        market_bullish = self.ta_data_trend_strat.marketRegime == MarketRegime.BULL
        market_bearish = self.ta_data_trend_strat.marketRegime == MarketRegime.BEAR
        market_ranging = self.ta_data_trend_strat.marketRegime == MarketRegime.RANGING
        range_limit = len(middleband_vec)

        # short daily sfp
        if self.entry_1 and not shorted and self.shortsAllowed:
            talibbars = self.ta_trend_strat.taData_trend_strat.talibbars
            condition_1 = talibbars.close_daily[-1] < talibbars.open_daily[-1]
            condition_2 = (
                talibbars.high_daily[-1] > self.ta_data_trend_strat.highs_trail_4h_vec[-6] or
                talibbars.high_daily[-1] > self.ta_data_trend_strat.highs_trail_4h_vec[-7]
            )
            condition_3 = market_bearish
            condition_4 = self.ta_data_trend_strat.volume_sma_4h_vec[-1] * self.entry_1_vol_fac < self.ta_data_trend_strat.volume_4h
            if condition_1 and condition_2 and condition_3 and condition_4:
                self.logger.info("Shorting daily sfp")
                if self.telegram is not None:
                    self.telegram.send_log("Shorting daily sfp")
                self.open_new_position(entry=bars[0].close,
                                       stop=bars[0].close + atr_trail_mix * self.entry_1_atr_fac,
                                       open_positions=open_positions,
                                       bars=bars,
                                       direction=PositionDirection.SHORT,
                                       ExecutionType="Market")

        # long confirmed trail breakout
        if self.entry_10 and not longed and self.longsAllowed:
            ath = (self.ta_trend_strat.taData_trend_strat.talibbars.close[-1] == max(self.ta_trend_strat.taData_trend_strat.talibbars.close)).all()
            condition_1 = bars[1].close > self.ta_strat_one.taData_strat_one.h_highs_trail_vec[-2]
            condition_2 = natr_4h < self.entry_10_natr
            condition_2b = natr_4h < self.entry_10_natr_ath
            condition_3 = self.ta_data_trend_strat.rsi_4h_vec[-1] < self.entry_10_rsi_4h
            condition_4 = not market_bearish
            conditions_set_1 = condition_1 and condition_2 and condition_3 and condition_4
            conditions_set_2 = condition_1 and condition_2b and ath and condition_3 and condition_4
            if conditions_set_1 or conditions_set_2:
                longed = True
                self.logger.info("Longing confirmed trail breakout.")
                if self.telegram is not None:
                    self.telegram.send_log("Longing confirmed trail breakout.")
                self.open_new_position(entry=bars[0].close,
                                       stop=bars[1].low-atr*0.2,
                                       open_positions=open_positions,
                                       bars=bars,
                                       direction=PositionDirection.LONG,
                                       ExecutionType="Market")
                self.logger.info("Sending additional long.")
                if self.telegram is not None:
                    self.telegram.send_log("Sending additional long.")
                entry = bars[1].close - 0.5 * atr
                self.open_new_position(entry=entry,
                                       stop=entry - atr,
                                       open_positions=open_positions,
                                       bars=bars,
                                       direction=PositionDirection.LONG,
                                       ExecutionType="StopLimit")

        # limit order - entries
        if self.entry_2:
            # Calculate potential trade entries
            longEntry, shortEntry, stopLong, stopShort, longAmount, shortAmount, alreadyLonged, alreadyShorted = self.calc_entry_and_exit(bars)

            if longEntry is not None and shortEntry is not None:
                condition_1 = natr_4h < self.entry_2_max_natr
                condition_2 = self.ta_trend_strat.taData_trend_strat.rsi_4h_vec[-1] > self.entry_2_min_rsi_4h
                condition_3 = self.ta_trend_strat.taData_trend_strat.rsi_d > self.entry_2_min_rsi_d
                condition_8 = market_bullish
                bullish_conditions = condition_1 and condition_2 and condition_3 and condition_8

                condition_4 = natr_4h > self.entry_2_min_natr
                condition_5 = self.ta_trend_strat.taData_trend_strat.rsi_4h_vec[-1] > self.entry_2_min_rsi_4h_short
                condition_6 = self.ta_trend_strat.taData_trend_strat.rsi_d > self.entry_2_min_rsi_d_short
                condition_7 = market_bearish
                bearish_conditions = condition_4 and condition_5 and condition_6 and condition_7

                foundLong = False
                foundShort = False
                if bullish_conditions or bearish_conditions:
                    foundLong, foundShort = self.update_existing_entries(account, open_positions, longEntry, shortEntry,
                                                                     stopLong, stopShort, longAmount, shortAmount)
                # Set entries if no orders are found and the market conditions allow it
                # go LONG
                if not foundLong and self.longsAllowed and directionFilter >= 0 and bullish_conditions:
                    self.open_new_position(PositionDirection.LONG, bars, stopLong, open_positions, longEntry,"StopLimit")

                # go SHORT
                if not foundShort and self.shortsAllowed and directionFilter <= 0 and shortEntry is not None and bearish_conditions:
                    self.open_new_position(PositionDirection.SHORT, bars, stopShort, open_positions, shortEntry,"StopLimit")

                # Save parameters
                '''self.data_strat_one.longEntry = longEntry
                self.data_strat_one.shortEntry = shortEntry
                self.data_strat_one.stopLong = stopLong
                self.data_strat_one.stopShort = stopShort

                # Write Data to plot
                plot_data = [self.data_strat_one.longEntry, self.data_strat_one.stopLong,
                             self.data_strat_one.shortEntry, self.data_strat_one.stopShort]
                Indicator.write_data_static(bars[0], plot_data, self.myId())'''

        # long trail breakout
        if self.entry_3 and not longed and self.longsAllowed:
            condition_1 = bars[1].high > self.ta_data_trend_strat.highs_trail_4h_vec[-2]
            condition_2 = natr_4h < self.entry_3_max_natr
            condition_3 = self.ta_data_trend_strat.rsi_4h_vec[-1] < self.entry_3_rsi_4h
            condition_4 = self.ta_data_trend_strat.volume_sma_4h_vec[-1] * self.entry_3_vol_fac > self.ta_data_trend_strat.volume_4h
            if condition_1 and condition_2 and condition_3 and condition_4:# and condition_5:
                longed = True
                self.logger.info("Longing trail breakout by StopLimit.")
                if self.telegram is not None:
                    self.telegram.send_log("Longing trail breakout by StopLimit.")
                delta = -0.2 * atr
                self.open_new_position(entry=bars[0].close + delta,
                                       stop=bars[1].low + delta,
                                       open_positions=open_positions,
                                       bars=bars,
                                       direction=PositionDirection.LONG,
                                       ExecutionType="StopLimit")

        # Long strength when certain BBand levels are reclaimed
        if self.entry_4:
            sold_off_bband = False
            # Find the index when sell_off_level was reached
            for i in range(1,range_limit,1):
                sell_off_level = middleband_vec[-i] - std_vec[-i] * self.entry_4_std_fac
                reclaim_level = sell_off_level + std_vec[-i] * self.entry_4_std_fac_reclaim
                if bars[i].close > reclaim_level and i > 1:
                    sold_off_bband = False
                    break
                if bars[i].close <= sell_off_level:
                    sold_off_bband = True
                    break

            if sold_off_bband:
                sell_off_level = middleband_vec[-1] - std_vec[-1] * self.entry_4_std_fac
                reclaim_level = sell_off_level + std_vec[-1] * self.entry_4_std_fac_reclaim
                condition_1 = bars[1].close > reclaim_level
                if condition_1 and not longed and self.longsAllowed:
                    longed = True
                    self.logger.info("Longing bollinger bands reclaim 1.")
                    if self.telegram is not None:
                        self.telegram.send_log("Longing bollinger bands reclaim 1.")
                    self.open_new_position(entry=bars[0].close,
                                           stop=bars[0].close - self.sl_atr_fac * atr_trail_mix,
                                           open_positions=open_positions,
                                           bars=bars,
                                           direction=PositionDirection.LONG,
                                           ExecutionType="Market")

        # short trail breakdown
        if self.entry_5 and not shorted and self.shortsAllowed:
            trail_broke = (bars[1].close < self.ta_strat_one.taData_strat_one.h_body_lows_trail_vec[-self.entry_5_trail_1_period:-2]).all()
            opened_above_trail = (bars[1].open > self.ta_strat_one.taData_strat_one.h_body_lows_trail_vec[-self.entry_5_trail_2_period:-2]).all()
            condition_1 = natr_4h < self.entry_5_natr
            condition_2 = self.ta_trend_strat.taData_trend_strat.rsi_d < self.entry_5_rsi_d
            condition_3 = self.ta_trend_strat.taData_trend_strat.rsi_4h_vec[-1] < self.entry_5_rsi_4h
            condition_4 = self.ta_data_trend_strat.volume_sma_4h_vec[-1] * self.entry_5_vol_fac < self.ta_data_trend_strat.volume_4h
            condition_5 = not market_bullish#market_bearish
            if trail_broke and opened_above_trail and condition_2 and condition_1 and condition_3 and condition_4:# and condition_5:
                self.logger.info("Shorting trail break.")
                if self.telegram is not None:
                    self.telegram.send_log("Shorting trail break.")
                shorted = True
                self.open_new_position(entry=bars[0].close,
                                       stop=min(bars[1].high,bars[0].close + atr_trail_mix * self.entry_5_atr_fac),
                                       open_positions=open_positions,
                                       bars=bars,
                                       direction=PositionDirection.SHORT,
                                       ExecutionType="Market")

        # trade swing breakouts by market orders
        if self.entry_6:
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
                condition_1 = self.ta_trend_strat.taData_trend_strat.rsi_4h_vec[-1] > self.entry_6_rsi_4h_max
                condition_2 = natr_4h < self.entry_6_max_natr
                condition_3 = market_bullish
                if bars[1].close > bars[idxSwingHigh].high and condition_2 and condition_1 and condition_3:
                    self.logger.info("Longing swing breakout.")
                    if self.telegram is not None:
                        self.telegram.send_log("Longing swing breakout.")
                    longed = True
                    sl = bars[1].low if bars[1].close > bars[1].open else bars[1].low - self.entry_6_atr_fac * atr_trail_mix
                    self.open_new_position(entry=bars[0].close,
                                           stop=sl,
                                           open_positions=open_positions,
                                           bars=bars,
                                           direction=PositionDirection.LONG,
                                           ExecutionType = "Market")

            if foundSwingLow and foundSwingHigh and not shorted and not alreadyShorted and not alreadyLonged and self.shortsAllowed:
                condition_2 = bars[1].open > self.ta_data_trend_strat.ema_w
                condition_3 = not market_bullish#not needed
                if bars[1].close < bars[idxSwingLow].low and condition_2:# and condition_3:
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

        # short entry 7
        if self.entry_7 and not shorted and self.shortsAllowed:
            condition_1 = bars[2].high > bars[1].high
            condition_2 = bars[2].high > self.ta_strat_one.taData_strat_one.h_highs_trail_vec[-3]
            condition_4 = bars[2].close < bars[2].open
            condition_7 = self.ta_data_trend_strat.volume_sma_4h_vec[-3] < self.ta_data_trend_strat.volume_4h * self.entry_7_vol_fac
            condition_8 = bars[1].open > middleband + std * self.entry_7_std_fac
            condition_9 = self.ta_trend_strat.taData_trend_strat.rsi_4h_vec[-1] < self.entry_7_4h_rsi
            if condition_1 and condition_2 and condition_4 and condition_7 and condition_8 and condition_9:
                self.logger.info("Shorting 4H SFP")
                if self.telegram is not None:
                    self.telegram.send_log("Shorting 4H SFP")
                shorted = True
                self.open_new_position(entry=bars[0].close,
                                       stop=max(bars[2].high, bars[1].high, bars[3].high),
                                       open_positions=open_positions,
                                       bars=bars,
                                       direction=PositionDirection.SHORT,
                                       ExecutionType="Market")

        # short entry 8
        if self.entry_8 and not shorted and self.shortsAllowed:
            condition_1 = (bars[1].high > bars[2].high and
                           bars[1].high > bars[3].high and
                           bars[1].high > bars[4].high and
                           bars[1].high > bars[5].close and
                           bars[1].high > bars[6].close and
                           bars[1].open > bars[7].close and
                           bars[1].open > bars[8].close)
            condition_2 = (bars[2].close > bars[1].close and
                           bars[3].close > bars[1].close and
                           bars[4].close > bars[1].close and
                           bars[5].close > bars[1].close and
                           bars[6].close > bars[1].close and
                           bars[7].close > bars[1].close and
                           bars[8].close > bars[1].close)
            condition_4 = self.ta_data_trend_strat.volume_sma_4h_vec[-1] * self.entry_8_vol_fac > self.ta_data_trend_strat.volume_4h
            condition_5 = not market_bullish#market_bearish
            condition_6 = self.ta_trend_strat.taData_trend_strat.marketDynamic == MarketDynamic.RANGING
            if condition_1 and condition_2 and condition_4 and condition_6:# and condition_5:
                self.logger.info("Shorting rapid sell-off")
                if self.telegram is not None:
                    self.telegram.send_log("Shorting rapid sell-off")
                shorted = True
                self.open_new_position(entry=bars[0].close,
                                       stop=bars[1].high,
                                       open_positions=open_positions,
                                       bars=bars,
                                       direction=PositionDirection.SHORT,
                                       ExecutionType="Market")

        # short entry 9
        if self.entry_9 and not shorted and self.shortsAllowed:
            condition_1 = bars[1].low < self.ta_data_trend_strat.lows_trail_4h_vec[-2] < bars[1].close < bars[1].open
            condition_2 = bars[1].open < bars[2].open
            condition_3 = bars[1].close > middleband_vec[-2] - std_vec[-2] * self.entry_9_std
            condition_5 = self.ta_trend_strat.taData_trend_strat.rsi_4h_vec[-1] < self.entry_9_4h_rsi
            condition_6 = not market_bullish#market_bearish
            condition_7 = self.ta_trend_strat.taData_trend_strat.marketDynamic == MarketDynamic.RANGING
            if condition_1 and condition_2 and condition_3 and condition_5 and condition_7:# and condition_6:
                self.logger.info("Shorting short trail tap")
                if self.telegram is not None:
                    self.telegram.send_log("Shorting short trail tap")
                shorted = True
                self.open_new_position(entry=bars[0].close,
                                       stop=bars[1].high + self.entry_9_atr * atr,
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
        if not longed and not shorted and not self.symbol.baseCoin == 'USDT':
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
        for i in range(3, depth):
            condition_1 = bars[i + 2].close < bars[i].close
            condition_2 = bars[i + 1].close < bars[i].close
            condition_3 = bars[i-2].close < bars[i].close > bars[i - 1].close
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
            cond_3 = bars[i - 2].close > bars[i].close < bars[i - 1].close
            if cond_1 and cond_2 and cond_3:
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
            longEntry = self.symbol.normalizePrice(bars[idxSwingHigh].high+self.ta_data_trend_strat.atr_4h*0.05, roundUp=True)
            shortEntry = self.symbol.normalizePrice(bars[idxSwingLow].low-self.ta_data_trend_strat.atr_4h*0.05, roundUp=False)

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
        if self.plotStrategyOneData and self.plotIndicators:
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

        if self.plotTrailsStatOne and self.plotIndicators:
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
