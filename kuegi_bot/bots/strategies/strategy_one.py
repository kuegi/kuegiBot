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
                 std_fac_sell_off: float = 1, std_fac_reclaim: float = 1, std_fac_sell_off_2: float = 1, std_fac_reclaim_2: float = 1,
                 std_fac_sell_off_3: float = 1, std_fac_reclaim_3: float = 1,
                 h_highs_trail_period: int = 1, h_lows_trail_period: int = 1, nmb_bars_entry: int = 1, const_trail_period: int = 4,
                 longReversals: bool = False, shortReversals: bool = False, longBreakouts: bool = False, shortBreakdown: bool = False,
                 longReclaimBBand: bool = False, shortLostBBand: bool = False,
                 entry_upper_bb_std_fac: float = 2.0, entry_lower_bb_std_fac: float = 2.0,
                 rsi_limit_breakout_long: int = 100,
                 # TrendStrategy
                 timeframe: int = 240, ema_w_period: int = 2, highs_trail_4h_period: int = 1, lows_trail_4h_period: int = 1,
                 trend_d_period: int = 2, trend_w_period: int = 0, atr_4h_period: int = 10, natr_4h_period_slow: int = 10,
                 bbands_4h_period: int = 10,
                 plotIndicators: bool = False,
                 trend_var_1: float = 1,
                 # Risk
                 risk_with_trend: float = 1, risk_counter_trend: float = 1, risk_ranging: float = 1,
                 # SL
                 sl_atr_fac: float = 2, be_by_middleband: bool = True, be_by_opposite: bool = True, stop_at_middleband: bool = True,
                 tp_at_middleband: bool = True, atr_buffer_fac: float = 0, tp_on_opposite: bool = True, stop_at_new_entry: bool = False,
                 trail_sl_with_bband: bool = False, stop_short_at_middleband: bool = False, moving_sl_atr_fac: float = 5,
                 sl_upper_bb_std_fac: float = 1, sl_lower_bb_std_fac: float = 1,
                 # StrategyWithTradeManagement
                 maxPositions: int = 100, close_on_opposite: bool = False, bars_till_cancel_triggered: int = 3,
                 limit_entry_offset_perc: float = -0.1, delayed_cancel: bool = False, cancel_on_filter: bool = True
                 ):
        super().__init__(
            # TrendStrategy
            timeframe = timeframe, ema_w_period= ema_w_period, highs_trail_4h_period= highs_trail_4h_period,
            lows_trail_4h_period= lows_trail_4h_period, trend_d_period = trend_d_period, trend_w_period = trend_w_period,
            atr_4h_period= atr_4h_period, natr_4h_period_slow= natr_4h_period_slow,
            bbands_4h_period= bbands_4h_period,
            plotIndicators = plotIndicators,
            trend_var_1 = trend_var_1,
            # Risk
            risk_with_trend = risk_with_trend, risk_counter_trend = risk_counter_trend, risk_ranging = risk_ranging,
            # SL
            sl_atr_fac = sl_atr_fac, be_by_middleband = be_by_middleband, be_by_opposite = be_by_opposite,
            stop_at_middleband = stop_at_middleband, tp_at_middleband = tp_at_middleband,
            tp_on_opposite = tp_on_opposite, stop_at_new_entry = stop_at_new_entry, trail_sl_with_bband = trail_sl_with_bband,
            atr_buffer_fac = atr_buffer_fac, moving_sl_atr_fac = moving_sl_atr_fac,
            sl_upper_bb_std_fac = sl_upper_bb_std_fac, sl_lower_bb_std_fac = sl_lower_bb_std_fac,
            stop_short_at_middleband = stop_short_at_middleband,
            # StrategyWithTradeManagement
            maxPositions = maxPositions, close_on_opposite = close_on_opposite, bars_till_cancel_triggered = bars_till_cancel_triggered,
            limit_entry_offset_perc = limit_entry_offset_perc, delayed_cancel = delayed_cancel, cancel_on_filter = cancel_on_filter
            )
        self.ta_data_trend_strat = TAdataTrendStrategy()
        self.data_strat_one = DataStrategyOne()
        self.ta_strat_one = TAStrategyOne(timeframe = timeframe, h_highs_trail_period= h_highs_trail_period,
                                          h_lows_trail_period = h_lows_trail_period, ta_data_trend_strat = self.ta_data_trend_strat)
        # Entry variables
        self.var_1 = var_1 # for backetsting
        self.var_2 = var_2 # for backetsting,
        self.nmb_bars_entry = nmb_bars_entry
        self.const_trail_period = const_trail_period
        self.longReversals = longReversals
        self.shortReversals = shortReversals
        self.longBreakouts = longBreakouts
        self.shortBreakdown = shortBreakdown
        self.longReclaimBBand = longReclaimBBand
        self.shortLostBBand = shortLostBBand
        self.entry_upper_bb_std_fac = entry_upper_bb_std_fac
        self.entry_lower_bb_std_fac = entry_lower_bb_std_fac
        self.sold_off_bband = False
        self.reclaimed_bband = False
        self.sold_off_bband_2 = False
        self.reclaimed_bband_2 = False
        self.sold_off_bband_3 = False
        self.reclaimed_bband_3 = False
        self.std_fac_sell_off = std_fac_sell_off
        self.std_fac_reclaim = std_fac_reclaim
        self.std_fac_sell_off_2 = std_fac_sell_off_2
        self.std_fac_reclaim_2 = std_fac_reclaim_2
        self.std_fac_sell_off_3 = std_fac_sell_off_3
        self.std_fac_reclaim_3 = std_fac_reclaim_3
        self.overboughtBB = 0
        self.overboughtBB_entry = 0
        self.rsi_limit_breakout_long = rsi_limit_breakout_long

    def myId(self):
        return "strategyOne"

    def init(self, bars: List[Bar], account: Account, symbol: Symbol):
        self.logger.info(vars(self))
        super().init(bars, account, symbol)

    #def got_data_for_position_sync(self, bars: List[Bar]) -> bool:
    #    result = super().got_data_for_position_sync(bars)
    #    return result and (self.swings.get_data(bars[1]) is not None)

    def prep_bars(self, is_new_bar: bool, bars: list):
        if is_new_bar:
            super().prep_bars(is_new_bar, bars)
            self.ta_data_trend_strat = self.get_ta_data_trend_strategy()
            self.ta_strat_one.set_ta_data_trend_strat(self.ta_data_trend_strat)
            self.ta_strat_one.on_tick(bars)

    def position_got_opened_or_changed(self, position: Position, bars: List[Bar], account: Account, open_positions):
        super().position_got_opened_or_changed(position, bars, account, open_positions)

        # calculate current exposure
        unrealized_loss = 0
        """if account.equity != 0:
            for i in open_positions:
                for k in open_positions[i].connectedOrders:
                    orderType = TradingBot.order_type_from_order_id(k.id)
                    if orderType == OrderType.SL:
                        current_price = (1 / bars[0].close) if self.symbol.isInverse else bars[0].close
                        stop_price = (1 / k.stop_price) if self.symbol.isInverse else k.stop_price
                        trade_loss = abs(current_price - stop_price) * abs(k.amount)
                        unrealized_loss += trade_loss
                        break
            unrealized_loss = unrealized_loss / account.equity

        if unrealized_loss > 0.1:
            return"""

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        super().manage_open_order(order, position, bars, to_update, to_cancel, open_positions)

        orderType = TradingBot.order_type_from_order_id(order.id)
        # cancel entries not allowed
        if orderType == OrderType.ENTRY and position.status == PositionStatus.PENDING and \
                ((position.amount>0 and not self.data_strat_one.longsAllowed) or
                 (position.amount<0 and not self.data_strat_one.shortsAllowed)):
            self.logger.info("canceling cause channel got invalid: " + position.id)
            to_cancel.append(order)
            del open_positions[position.id]

    def got_data_for_position_sync(self, bars: List[Bar]) -> bool:
        result= super().got_data_for_position_sync(bars)
        return result and (self.ta_trend_strat.get_data(bars[1]) is not None)

    def open_new_trades(self, is_new_bar, directionFilter, bars, account, open_positions, all_open_pos: dict):
        if (not is_new_bar) or not self.entries_allowed(bars) or \
                self.ta_data_trend_strat.atr_4h is None or \
                self.ta_data_trend_strat.marketRegime == MarketRegime.NONE or \
                len(all_open_pos) >= self.maxPositions: # TODO revise min number of bars required
            self.logger.info("new entries not allowed by filter")
            return  # only open orders on beginning of bar

        # Limit Orders
        tradeWithLimitOrders = False
        if tradeWithLimitOrders:
            # Calculate potential trade entries
            longEntry, shortEntry, stopLong, stopShort, longAmount, shortAmount = self.calc_entry_and_exit(bars)

            if longEntry is not None and shortEntry is not None and stopLong is not None and stopShort is not None and \
                    longAmount is not None and shortAmount is not None:
                # Update existing entries, if available
                foundLong, foundShort = self.update_existing_entries(account, open_positions, longEntry, shortEntry,
                                                                     stopLong, stopShort, longAmount, shortAmount)

                # decide if new entries are allowed
                self.new_entries_allowed(bars)

                # Set entries if no orders are found and the market conditions allow it
                # go LONG
                if not foundLong and directionFilter >= 0 and \
                        self.data_strat_one.longsAllowed and longAmount > 0:#(self.ta_data_trend_strat.marketTrend != MarketRegime.BEAR) and \
                    self.open_new_position(PositionDirection.LONG, bars, stopLong, open_positions, longEntry, longAmount)
                # go SHORT
                if not foundShort and directionFilter <= 0 and \
                        self.data_strat_one.shortsAllowed and shortAmount < 0:#(self.ta_data_trend_strat.marketTrend != MarketRegime.BULL) and \
                    self.open_new_position(PositionDirection.SHORT, bars, stopShort, open_positions, shortEntry, shortAmount)

                # Save parameters
                self.data_strat_one.longEntry = longEntry
                self.data_strat_one.shortEntry = shortEntry
                self.data_strat_one.stopLong = stopLong
                self.data_strat_one.stopShort = stopShort

                # Write Data to plot
                plot_data = [self.data_strat_one.longEntry, self.data_strat_one.stopLong,
                             self.data_strat_one.shortEntry, self.data_strat_one.stopShort]
                Indicator.write_data_static(bars[0], plot_data, self.myId())

        # Market Orders
        std = self.ta_data_trend_strat.bbands_4h.std
        atr = self.ta_data_trend_strat.atr_4h
        middleband = self.ta_data_trend_strat.bbands_4h.middleband

        # Market orders after breakouts by close above the bollinger band
        if self.ta_data_trend_strat.rsi_w_vec is not None:
            if self.longBreakouts and \
                    bars[1].close > (middleband + std * self.entry_upper_bb_std_fac) and \
                    bars[1].close > bars[2].close and \
                    self.ta_data_trend_strat.rsi_w_vec[-1] < self.rsi_limit_breakout_long and \
                    self.ta_data_trend_strat.marketRegime == MarketRegime.BULL:
                self.entry_by_market_order(entry=bars[0].open,
                                           stop=min(bars[0].open - self.sl_atr_fac * atr, bars[2].low, bars[1].low),
                                           open_positions=open_positions,
                                           bars=bars,
                                           direction=PositionDirection.LONG)

        # Long reclaimed BBands 1
        if self.longReclaimBBand and \
                self.ta_data_trend_strat.marketRegime == MarketRegime.BULL:
            sell_off_level = middleband - std * self.std_fac_sell_off
            reclaim_level = sell_off_level + std * self.std_fac_reclaim
            if bars[1].low < sell_off_level:
                self.sold_off_bband = True
                self.reclaimed_bband = False
            if bars[1].close > reclaim_level and self.sold_off_bband and not self.reclaimed_bband:
                self.sold_off_bband = False
                self.reclaimed_bband = True
                # TODO: log to Telegram which trade is executed
                self.entry_by_market_order(entry=bars[0].open,
                                           stop=min(bars[0].open - self.sl_atr_fac * atr, bars[2].low, bars[1].low),
                                           open_positions=open_positions,
                                           bars=bars,
                                           direction=PositionDirection.LONG)

        # Long reclaimed BBands 2
        if self.longReclaimBBand and \
                self.ta_data_trend_strat.marketRegime == MarketRegime.BULL:
            sell_off_level = middleband - std * self.std_fac_sell_off_2
            reclaim_level = sell_off_level + std * self.std_fac_reclaim_2
            if bars[1].low < sell_off_level:
                self.sold_off_bband_2 = True
                self.reclaimed_bband_2 = False
            if bars[1].close > reclaim_level and self.sold_off_bband_2 and not self.reclaimed_bband_2:
                self.sold_off_bband_2 = False
                self.reclaimed_bband_2 = True
                # TODO: log to Telegram which trade is executed
                self.entry_by_market_order(entry=bars[0].open,
                                           stop=min(bars[0].open - self.sl_atr_fac * atr, bars[2].low, bars[1].low),
                                           open_positions=open_positions,
                                           bars=bars,
                                           direction=PositionDirection.LONG)

        # Long reclaimed BBands 3
        if self.longReclaimBBand and \
                self.ta_data_trend_strat.marketRegime == MarketRegime.BULL:
            sell_off_level = middleband - std * self.std_fac_sell_off_3
            reclaim_level = sell_off_level + std * self.std_fac_reclaim_3
            if bars[1].low < sell_off_level:
                self.sold_off_bband_3 = True
                self.reclaimed_bband_3 = False
            if bars[1].close > reclaim_level and self.sold_off_bband_3 and not self.reclaimed_bband_3:
                self.sold_off_bband_3 = False
                self.reclaimed_bband_3 = True
                # TODO: log to Telegram which trade is executed
                self.entry_by_market_order(entry=bars[0].open,
                                           stop=min(bars[0].open - self.sl_atr_fac * atr, bars[2].low, bars[1].low),
                                           open_positions=open_positions,
                                           bars=bars,
                                           direction=PositionDirection.LONG)

        # short break down
        if self.ta_data_trend_strat.rsi_4h_vec is not None:
            if self.shortBreakdown and \
                    self.ta_data_trend_strat.marketRegime == MarketRegime.BEAR and \
                    bars[1].close < (middleband - std * self.entry_lower_bb_std_fac) and \
                    bars[1].close < bars[2].close < bars[3].open and \
                    15 < self.ta_data_trend_strat.rsi_4h_vec[-1] < 20:
                self.entry_by_market_order(entry = bars[0].open,
                                           stop= max(bars[0].open + self.sl_atr_fac * atr, bars[2].high, bars[1].high),
                                           open_positions = open_positions,
                                           bars = bars,
                                           direction = PositionDirection.SHORT)

        # Short lost BBands
        if self.shortLostBBand:
            self.overboughtBB = middleband + std * 4
            self.overboughtBB_entry = middleband - std * 1
            if bars[1].high > self.overboughtBB:
                self.sold_off_bband_3 = True
                self.reclaimed_bband_3 = False
            if bars[1].close < self.overboughtBB_entry and self.sold_off_bband_3 and not self.reclaimed_bband_3:
                self.sold_off_bband_3 = False
                self.reclaimed_bband_3 = True
                # TODO: log to Telegram which trade is executed
                self.entry_by_market_order(entry=bars[0].open,
                                           stop=max(bars[0].open + self.sl_atr_fac * atr, bars[2].high, bars[1].high),
                                           open_positions=open_positions,
                                           bars=bars,
                                           direction=PositionDirection.SHORT)
        # long reversal
        """if self.longReversals and \
                bars[1].low < self.ta_strat_one.taData_strat_one.h_lows_trail_vec[-2] < bars[1].close and \
                ((self.ta_data_trend_strat.marketRegime == MarketRegime.BULL and
                 (self.constant_trail(2, self.const_trail_period, self.ta_strat_one.taData_strat_one.h_lows_trail_vec) or
                  self.constant_trail(3, self.const_trail_period + 1, self.ta_strat_one.taData_strat_one.h_lows_trail_vec) or
                  self.constant_trail(4, self.const_trail_period + 2, self.ta_strat_one.taData_strat_one.h_lows_trail_vec))) or
                 (False and self.ta_data_trend_strat.marketRegime == MarketRegime.BEAR and
                  (abs(self.ta_strat_one.taData_strat_one.h_lows_trail_vec[-2] - (middleband - std * self.entry_lower_bb_std_fac)) < std * self.var_1))):
            self.entry_by_market_order(entry=bars[0].open,
                                       stop=(bars[1].low - self.sl_atr_fac * self.ta_data_trend_strat.atr_4h),
                                       open_positions=open_positions,
                                       bars=bars,
                                       direction=PositionDirection.LONG)"""

        # short revesal
        if self.shortReversals and \
                (bars[1].high > self.ta_data_trend_strat.highs_trail_4h_vec[-2] > bars[1].close and
                 self.ta_data_trend_strat.highs_trail_4h < (middleband + std * self.entry_upper_bb_std_fac)):
            self.entry_by_market_order(entry=bars[0].open,
                                       stop=max(bars[0].open + self.sl_atr_fac * atr, bars[2].high, bars[1].high),
                                       open_positions=open_positions,
                                       bars=bars,
                                       direction=PositionDirection.SHORT)

    def entry_by_market_order(self, entry, stop, open_positions, bars, direction):
        expectedEntrySlippagePer = 0.0015 if self.limit_entry_offset_perc is None else 0
        expectedExitSlippagePer = 0.0015
        if direction == PositionDirection.LONG:
            entry = self.symbol.normalizePrice(entry, roundUp=True)
            stop = self.symbol.normalizePrice(stop, roundUp=False)
            exitPrice = stop * (1 - expectedExitSlippagePer)
            entry = entry * (1 + expectedEntrySlippagePer)
        else:
            entry = self.symbol.normalizePrice(entry, roundUp=False)
            stop = self.symbol.normalizePrice(stop, roundUp=True)
            exitPrice = stop * (1 + expectedExitSlippagePer)
            entry = entry * (1 - expectedEntrySlippagePer)

        amount = self.calc_pos_size(risk=self.risk_factor, entry=entry, exitPrice = exitPrice, atr=0)
        self.open_new_position(direction, bars, stop, open_positions, entry, amount)

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

    def new_entries_allowed(self, bars):
        self.data_strat_one.shortsAllowed = True
        self.data_strat_one.longsAllowed = True
        for i in range(1, self.nmb_bars_entry):
            if self.ta_data_trend_strat.lows_trail_4h_vec[-i] != \
                    self.ta_data_trend_strat.lows_trail_4h_vec[-(i + 1)]:
                self.data_strat_one.shortsAllowed = False

            if self.ta_data_trend_strat.highs_trail_4h_vec[-i] != \
                    self.ta_data_trend_strat.highs_trail_4h_vec[-(i + 1)]:
                self.data_strat_one.longsAllowed = False

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

    def add_to_plot(self, fig: go.Figure, bars: List[Bar], time):
        super().add_to_plot(fig, bars, time)

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
