import math
from datetime import datetime
from typing import List
import plotly.graph_objects as go

from kuegi_bot.bots.strategies.channel_strat import ChannelStrategy, StrategyWithTradeManagement
from kuegi_bot.bots.trading_bot import TradingBot, PositionDirection
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType, Position, Order, PositionStatus
from kuegi_bot.indicators.indicator import Indicator, SMA, highest, lowest, BarSeries
from kuegi_bot.indicators.talibbars import TAlibBars
import talib


class StrategyData:
    def __init__(self, longEntry, stopLong, shortEntry, stopShort):
        self.longEntry = longEntry
        self.stopLong = stopLong
        self.shortEntry = shortEntry
        self.stopShort = stopShort


class NewStrategy(StrategyWithTradeManagement):
    def __init__(self, slowMAperiod: int = 20, midMAperiod: int = 18, fastMAperiod: int = 16, veryfastMAperiod: int = 14):
        super().__init__(maxPositions = 100, close_on_opposite = True, bars_till_cancel_triggered = 3,
                         limit_entry_offset_perc = -0.1, delayed_cancel = False, cancel_on_filter = True)
        self.ta = TechnicalAnalysis(slowMAperiod, midMAperiod, fastMAperiod, veryfastMAperiod)
        self.strategyData = StrategyData(longEntry=None, stopLong=None, shortEntry=None, stopShort=None)
        self.shortsAllowed = True
        self.longsAllowed = True

    def myId(self):
        return "newStrategy"

    def init(self, bars: List[Bar], account: Account, symbol: Symbol):
        self.logger.info(vars(self))
        super().init(bars, account, symbol)

    def prep_bars(self, is_new_bar: bool, bars: list):
        if is_new_bar:
            self.ta.on_tick(bars)

    def position_got_opened_or_changed(self, position: Position, bars: List[Bar], account: Account, open_positions):
        super().position_got_opened_or_changed(position, bars, account, open_positions)
        if position.amount > 0:
            self.longsAllowed = False
        else:
            self.shortsAllowed = False

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        super().manage_open_order(order, position, bars, to_update, to_cancel, open_positions)

        # Update SLs based BBs
        stopLowerBand = False
        stopMiddleband = True#True
        stopUpperBand = False
        tpMiddleband = False
        orderType = TradingBot.order_type_from_order_id(order.id)
        if orderType == OrderType.SL:
            if position.amount < 0: # SL for SHORTS
                if bars[1].low < self.ta.taData.bbands.middleband < order.stop_price and stopUpperBand:
                    order.stop_price = min(position.wanted_entry, self.ta.taData.bbands.upperband)
                    to_update.append(order)
                if bars[1].low < self.ta.taData.bbands.lowerband < order.stop_price and stopMiddleband:
                    order.stop_price = self.ta.taData.bbands.middleband
                    to_update.append(order)
                if bars[1].low < self.ta.taData.bbands.lowerband < order.stop_price and stopLowerBand:
                    order.stop_price = bars[0].open
                    to_update.append(order)
                if bars[0].open < self.ta.taData.bbands.middleband and tpMiddleband:
                    order.stop_price = self.ta.taData.bbands.middleband
                    to_update.append(order)
            elif position.amount > 0: # SL for LONGs
                if bars[1].high > self.ta.taData.bbands.middleband > order.stop_price and stopLowerBand:
                    order.stop_price = max(position.wanted_entry, self.ta.taData.bbands.lowerband)
                    to_update.append(order)
                if bars[1].high > self.ta.taData.bbands.upperband > order.stop_price and stopMiddleband:
                    order.stop_price = self.ta.taData.bbands.middleband
                    to_update.append(order)
                if bars[1].high > self.ta.taData.bbands.upperband > order.stop_price and stopUpperBand:
                    order.stop_price = bars[0].open
                    to_update.append(order)
                if bars[0].open > self.ta.taData.bbands.middleband and tpMiddleband:
                    order.stop_price = self.ta.taData.bbands.middleband
                    to_update.append(order)




        # cancel if the trend has changed
        #ta_data = self.ta.get_ta_data()
        #if (position.amount > 0 and ta_data.markettrend == -1) or (position.amount < 0 and ta_data.markettrend == 1):
        #    self.logger.info("canceling cause channel got invalid: " + position.id)
        #    to_cancel.append(order)
        #    del open_positions[position.id]

    def manage_open_position(self, p, bars, account, pos_ids_to_cancel):
        super().manage_open_position(p, bars, account, pos_ids_to_cancel)

    def got_data_for_position_sync(self, bars: List[Bar]) -> bool:
        result= super().got_data_for_position_sync(bars)
        return result and (self.ta.get_data(bars[1]) is not None)

    def open_orders(self, is_new_bar, directionFilter, bars, account, open_positions, all_open_pos: dict):
        if (not is_new_bar) or len(bars) < 5 or not self.entries_allowed(bars):
            self.logger.info("new entries not allowed by filter")
            return  # only open orders on beginning of bar

        ta_data = self.ta.get_ta_data()

        # Calculate potential trade entries
        longEntry, shortEntry, stopLong, stopShort, longAmount, shortAmount = self.calc_entry_exit(bars)

        if longEntry and shortEntry and stopLong and stopShort and longAmount and shortAmount is not None:
            # Update existing entries, if available
            foundLong, foundShort = self.update_existing_entries(account, open_positions, longEntry, shortEntry, stopLong, stopShort, self.ta.taData.ATR)

            if bars[1].high > ta_data.bbands.upperband or \
                    (bars[1].high < ta_data.bbands.upperband and (ta_data.bbands.upperband - bars[1].high) < self.ta.taData.ATR):
                self.shortsAllowed = False
            else:
                self.shortsAllowed = True
            if bars[1].low < ta_data.bbands.lowerband or \
                    (bars[1].low > ta_data.bbands.lowerband and (bars[1].low - ta_data.bbands.lowerband) < self.ta.taData.ATR):
                self.longsAllowed = False
            else:
                self.longsAllowed = True

            # Set new entries if no orders are found and the market conditions allow it
            # go LONG
            if not foundLong and directionFilter >= 0 and (ta_data.markettrend == 0 or ta_data.markettrend == 1) and self.longsAllowed:
                self.open_new_position(PositionDirection.LONG, bars, stopLong, open_positions, longEntry)
            # go SHORT
            if not foundShort and directionFilter <= 0 and (ta_data.markettrend == 0 or ta_data.markettrend == -1) and self.shortsAllowed:
                self.open_new_position(PositionDirection.SHORT, bars, stopShort, open_positions, shortEntry)

            # Write Data to plot
            self.strategyData = StrategyData(longEntry= longEntry, stopLong= stopLong, shortEntry= shortEntry, stopShort= stopShort)
            Indicator.write_data_static(bars[0], self.strategyData, self.myId())

    def update_existing_entries(self, account, open_positions, longEntry, shortEntry, stopLong, stopShort, atr):
        foundLong, foundShort = super().update_existing_entries(account, open_positions, longEntry, shortEntry, stopLong, stopShort, atr)
        return foundLong, foundShort

    def calc_entry_exit(self, bars):
        if self.ta.taData.bbands.lowerband is not None and self.ta.taData.bbands.middleband is not None and self.ta.taData.bbands.upperband is not None:
            longEntry = self.symbol.normalizePrice(self.ta.taData.bbands.lowerband, roundUp=True)
            shortEntry = self.symbol.normalizePrice(self.ta.taData.bbands.upperband, roundUp=False)

            std = self.ta.taData.bbands.middleband - self.ta.taData.bbands.lowerband
            sdt_fac = 0.5
            stopLong = self.symbol.normalizePrice(self.ta.taData.bbands.lowerband - sdt_fac * std, roundUp=False)
            stopShort = self.symbol.normalizePrice(self.ta.taData.bbands.upperband + sdt_fac * std, roundUp=True)

            # Calculate amount
            expectedEntrySlippagePer = 0.0015 if self.limit_entry_offset_perc is None else 0
            expectedExitSlippagePer = 0.0015
            longAmount = self.calc_pos_size(risk=self.risk_factor, exitPrice=stopLong * (1 - expectedExitSlippagePer),
                                            entry=longEntry * (1 + expectedEntrySlippagePer), atr=self.ta.taData.ATR)
            shortAmount = self.calc_pos_size(risk=self.risk_factor, exitPrice=stopShort * (1 + expectedExitSlippagePer),
                                             entry=shortEntry * (1 - expectedEntrySlippagePer), atr=self.ta.taData.ATR)
        else:
            return None, None, None, None, None, None

        return longEntry, shortEntry, stopLong, stopShort, longAmount, shortAmount

    def add_to_plot(self, fig: go.Figure, bars: List[Bar], time):
        super().add_to_plot(fig, bars, time)

        # Plot Indicator-generated Data
        styles = self.ta.get_line_styles()
        names = self.ta.get_line_names()
        offset = 0  # we take it with offset 1 TODO: 1 or 0?

        plotMAs = False
        if plotMAs:
            sub_data = list(map(lambda b: self.ta.get_data_for_plot(b)[0], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[0],
                            name=self.ta.id + "_" + names[0])
            sub_data = list(map(lambda b: self.ta.get_data_for_plot(b)[1], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[1],
                            name=self.ta.id + "_" + names[1])
            sub_data = list(map(lambda b: self.ta.get_data_for_plot(b)[2], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[2],
                            name=self.ta.id + "_" + names[2])
            sub_data = list(map(lambda b: self.ta.get_data_for_plot(b)[3], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[3],
                            name=self.ta.id + "_" + names[3])
        sub_data = list(map(lambda b: self.ta.get_data_for_plot(b)[4], bars))
        fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[4],
                        name=self.ta.id + "_" + names[4])
        sub_data = list(map(lambda b: self.ta.get_data_for_plot(b)[5], bars))
        fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[5],
                        name=self.ta.id + "_" + names[5])
        sub_data = list(map(lambda b: self.ta.get_data_for_plot(b)[6], bars))
        fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[6],
                        name=self.ta.id + "_" + names[6])

        # Plot Strategy-generated Data
        plotStrategyData = True
        if plotStrategyData:
            sub_data = list(map(lambda b: self.get_data_for_plot(b)[0], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line={"width": 1, "color": "black"},
                            name=self.myId() + "_" + "Long_Entry")
            sub_data = list(map(lambda b: self.get_data_for_plot(b)[1], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line={"width": 1, "color": "blue"},
                            name=self.myId() + "_" + "Long_Stop")
            sub_data = list(map(lambda b: self.get_data_for_plot(b)[2], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line={"width": 1, "color": "cyan"},
                            name=self.myId() + "_" + "Short_Entry")
            sub_data = list(map(lambda b: self.get_data_for_plot(b)[3], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line={"width": 1, "color": "mediumpurple"},
                            name=self.myId() + "_" + "Short_Stop")

    def get_data_for_plot(self, bar: Bar):
        strategy_data: StrategyData = Indicator.get_data_static(bar,self.myId())
        if strategy_data is not None:
            return [strategy_data.longEntry, strategy_data.stopLong, strategy_data.shortEntry, strategy_data.stopShort]
        else:
            return [bar.close, bar.close, bar.close, bar.close]


class BBands:
    def __init__(self, upperband:float = None, middleband:float = None, lowerband:float = None):
        self.upperband = upperband
        self.middleband = middleband
        self.lowerband = lowerband


class TAData:
    def __init__(self, slowMA, midMA, fastMA, veryfastMA, markettrend, ATR, bbands: BBands()):
        self.talibbars = TAlibBars()
        self.slowMA = slowMA
        self.midMA = midMA
        self.fastMA = fastMA
        self.veryfastMA = veryfastMA
        self.markettrend = markettrend
        self.trend_buffer = 5
        self.ATR = ATR
        self.bbands = BBands(bbands.upperband, bbands.middleband, bbands.lowerband)


class TechnicalAnalysis(Indicator):
    ''' Run technical analysis here '''

    def __init__(self, slowMAperiod: int, midMAperiod: int, fastMAperiod: int, veryfastMAperiod: int, ATRperiod: int = 30,
                 bbands_period: int = 30):
        super().__init__('TA')
        self.taData = TAData(slowMA= None, midMA= None, fastMA= None, veryfastMA= None, markettrend=0, ATR = None, bbands = BBands())
        self.slowMAperiod = slowMAperiod
        self.midMAperiod = midMAperiod
        self.fastMAperiod = fastMAperiod
        self.veryfastMAperiod = veryfastMAperiod
        self.ATRperiod = ATRperiod
        self.bbands_period = bbands_period

    def on_tick(self, bars: List[Bar]):
        self.taData.talibbars.on_tick(bars)
        self.run_ta_analysis()
        self.calculate_custom_data()
        self.write_data_for_plot(bars)

    def get_ta_data(self):
        return self.taData

    def run_ta_analysis(self):
        self.taData.slowMA = talib.SMA(self.taData.talibbars.close, self.slowMAperiod)[-1]
        self.taData.midMA = talib.SMA(self.taData.talibbars.close, self.midMAperiod)[-1]
        self.taData.fastMA = talib.SMA(self.taData.talibbars.close, self.fastMAperiod)[-1]
        self.taData.veryfastMA = talib.SMA(self.taData.talibbars.close, self.veryfastMAperiod)[-1]
        self.taData.ATR = talib.ATR(self.taData.talibbars.high, self.taData.talibbars.low, self.taData.talibbars.close, self.ATRperiod)[-1]
        a, b, c = talib.BBANDS(self.taData.talibbars.close, timeperiod = self.bbands_period)
        self.taData.bbands.upperband = a[-1] if not math.isnan(a[-1]) else None
        self.taData.bbands.middleband = b[-1] if not math.isnan(b[-1]) else None
        self.taData.bbands.lowerband = c[-1] if not math.isnan(c[-1]) else None

    def calculate_custom_data(self):
        trend_buffer_threshold = 0
        buffer = 5

        if self.taData.slowMA is not None and self.taData.midMA is not None and self.taData.fastMA is not None:
            if self.taData.slowMA < self.taData.midMA < self.taData.fastMA < self.taData.veryfastMA:
                self.taData.trend_buffer -= 1
                if self.taData.trend_buffer <= trend_buffer_threshold:
                    self.taData.markettrend = 1                                                         # bull
                else:
                    self.taData.markettrend = 0                                                         # ranging
            elif self.taData.slowMA > self.taData.midMA > self.taData.fastMA > self.taData.veryfastMA:
                self.taData.trend_buffer -= 1
                if self.taData.trend_buffer <= trend_buffer_threshold:
                    self.taData.markettrend = -1                                                        # bear
                else:
                    self.taData.markettrend = 0                                                         # ranging
            else:
                self.taData.markettrend = 0                                                             # ranging
                self.taData.trend_buffer = buffer                          # low pass filter for the ranging condition
        else:
            self.taData.markettrend = 0                                                                 #invalid
            self.taData.trend_buffer = buffer

    def write_data_for_plot(self, bars: List[Bar]):
        ta_data = TAData(self.taData.slowMA, self.taData.midMA, self.taData.fastMA, self.taData.veryfastMA,
                         self.taData.markettrend, self.taData.ATR, self.taData.bbands)
        self.write_data(bars[0], ta_data)

    def get_line_names(self):
        return ["slowMA", "midMA", "fastMA", "veryfastMA",
                "upperband", "middleband", "lowerband"]

    def get_number_of_lines(self):
        return 7

    def get_line_styles(self):
        return [{"width": 1, "color": "red"},
                {"width": 1, "color": "orange"},
                {"width": 1, "color": "yellow"},
                {"width": 1, "color": "white"},
                {"width": 1, "color": "blue"},
                {"width": 1, "color": "brown"},
                {"width": 1, "color": "cyan"}]

    def get_data_for_plot(self, bar: Bar):
        data: TAData = self.get_data(bar)
        if data is not None:
            return [data.slowMA, data.midMA, data.fastMA, data.veryfastMA,
                    data.bbands.upperband , data.bbands.middleband, data.bbands.lowerband]
        else:
            return [bar.close, bar.close, bar.close, bar.close,
                    bar.close, bar.close, bar.close]
