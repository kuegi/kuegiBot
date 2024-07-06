import math
from typing import List

import plotly.graph_objects as go
import talib

from kuegi_bot.bots.strategies.trend_strategy import TrendStrategy, TAdataTrendStrategy, MarketRegime, BBands
from kuegi_bot.bots.trading_bot import TradingBot, PositionDirection
from kuegi_bot.indicators.indicator import Indicator
from kuegi_bot.indicators.talibbars import TAlibBars
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType, Position


class DataTemplateStrategy:
    def __init__(self):
        self.longEntry = None
        self.stopLong = None
        self.shortEntry = None
        self.stopShort = None
        self.shortsAllowed = False
        self.longsAllowed = False


class TemplateStrategy(TrendStrategy):
    def __init__(self,
                 # TemplateStrategy input variables
                 #variable: bool = True
                 # TrendStrategy input variables

                 # StrategyWithTradeManagement input variables

                 ):
        super().__init__(
            # TrendStrategy input variables

            # StrategyWithTradeManagement input variables

            )
        self.ta_data = TAdataTrendStrategy()
        # TemplateStrategy input variables allocation
        self.data_template_strat = DataTemplateStrategy()
        #self.variable = variable

    def myId(self):
        return "templateStrategy"

    def init(self, bars: List[Bar], account: Account, symbol: Symbol):
        self.logger.info(vars(self))
        super().init(bars, account, symbol)

    def prep_bars(self, is_new_bar: bool, bars: list):
        if is_new_bar:
            super().prep_bars(is_new_bar, bars)
            self.ta_data = self.get_ta_data_trend_strategy()

    def position_got_opened_or_changed(self, position: Position, bars: List[Bar], account: Account, open_positions):
        super().position_got_opened_or_changed(position, bars, account, open_positions)
        # if position got opened, do something here if necessary

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        super().manage_open_order(order, position, bars, to_update, to_cancel, open_positions)

        # Update SLs
        orderType = TradingBot.order_type_from_order_id(order.id)
        if orderType == OrderType.SL: # Manage Stop Losses
            new_trigger_price = order.trigger_price
            if order.amount > 0: # SL for SHORTS
                pass
            elif order.amount < 0: # SL for LONGs
                pass

            if new_trigger_price != order.trigger_price:
                order.trigger_price = new_trigger_price
                to_update.append(order)

        # cancel if the trend has changed
        #ta_data = self.ta.get_ta_data()
        #if (position.amount > 0 and self.ta_data.marketTrend == MarketTrend.BEAR) or \
        #        (position.amount < 0 and self.ta_data.marketTrend == MarketTrend.BULL):
        #    self.logger.info("canceling because the trend changed: " + position.id)
        #    to_cancel.append(order)
        #    del open_positions[position.id]

    def got_data_for_position_sync(self, bars: List[Bar]) -> bool:
        result= super().got_data_for_position_sync(bars)
        return result and (self.ta_trend_strat.get_data(bars[1]) is not None)

    def open_new_trades(self, is_new_bar, directionFilter, bars, account, open_positions, all_open_pos: dict):
        if (not is_new_bar) or not self.entries_allowed(bars) or self.ta_data.atr_4h is None: # TODO revise min number of bars required
            self.logger.info("new entries not allowed by filter")
            return  # only open orders on beginning of bar

        # Calculate potential trade entries
        longEntry, shortEntry, stopLong, stopShort, longAmount, shortAmount = self.calc_entry_and_exit(bars)

        if longEntry is not None and shortEntry is not None and stopLong is not None and stopShort is not None and longAmount is not None and shortAmount is not None:
            # Update existing entries, if available
            foundLong, foundShort = self.update_existing_entries(account, open_positions, longEntry, shortEntry, stopLong,
                                                                 stopShort, longAmount, shortAmount)

            # decide if new entries are allowed
            self.new_entries_allowed(bars)

            # Set mean reversion entries if no orders are found and the market conditions allow it
            # go LONG
            if not foundLong and directionFilter >= 0 and \
                    (self.ta_data.marketRegime != MarketRegime.BEAR) and \
                    self.data_template_strat.longsAllowed and longAmount > 0:
                self.open_new_position(PositionDirection.LONG, bars, stopLong, open_positions, longEntry, longAmount)
            # go SHORT
            if not foundShort and directionFilter <= 0 and \
                    (self.ta_data.marketRegime != MarketRegime.BULL) and \
                    self.data_template_strat.shortsAllowed and shortAmount < 0:
                self.open_new_position(PositionDirection.SHORT, bars, stopShort, open_positions, shortEntry, shortAmount)

            # Save parameters
            self.data_template_strat.longEntry = longEntry
            self.data_template_strat.shortEntry = shortEntry
            self.data_template_strat.stopLong = stopLong
            self.data_template_strat.stopShort = stopShort

            # Write Data to plot
            plot_data = [self.data_template_strat.longEntry, self.data_template_strat.stopLong, self.data_template_strat.shortEntry, self.data_template_strat.stopShort]
            Indicator.write_data_static(bars[0], plot_data, self.myId())

    def calc_entry_and_exit(self, bars):
        temp = True
        if temp: # if entry and SL can be calculated

            # entries
            longEntry = 1
            shortEntry = 1
            longEntry = self.symbol.normalizePrice(longEntry, roundUp=True)
            shortEntry = self.symbol.normalizePrice(shortEntry, roundUp=False)

            # stop losses
            stopLong = 1
            stopShort = 1
            stopLong = self.symbol.normalizePrice(stopLong, roundUp=False)
            stopShort = self.symbol.normalizePrice(stopShort, roundUp=True)

            # amount
            expectedEntrySlippagePer = 0.0015 if self.limit_entry_offset_perc is None else 0
            expectedExitSlippagePer = 0.0015
            longAmount = self.calc_pos_size(risk=self.risk_factor, exitPrice=stopLong * (1 - expectedExitSlippagePer),
                                            entry=longEntry * (1 + expectedEntrySlippagePer), atr = self.ta_data.atr_4h)
            shortAmount = self.calc_pos_size(risk=self.risk_factor, exitPrice=stopShort * (1 + expectedExitSlippagePer),
                                             entry=shortEntry * (1 - expectedEntrySlippagePer), atr = self.ta_data.atr_4h)
        else:
            return None, None, None, None, None, None

        return longEntry, shortEntry, stopLong, stopShort, longAmount, shortAmount

    def new_entries_allowed(self, bars):
        closeA = True
        if closeA:
            self.data_template_strat.shortsAllowed = True
        else:
            self.data_template_strat.shortsAllowed = True

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
        plotStrategyData = True
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


