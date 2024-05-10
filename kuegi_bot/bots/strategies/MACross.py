import math
from typing import List
import plotly.graph_objects as go

from kuegi_bot.bots.strategies.strat_with_exit_modules import StrategyWithExitModulesAndFilter
from kuegi_bot.bots.trading_bot import TradingBot, PositionDirection
from kuegi_bot.indicators.indicator import SMA, BarSeries, highest, lowest
from kuegi_bot.indicators.swings import Swings, Data
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType, Position, Order, PositionStatus


class MACross(StrategyWithExitModulesAndFilter):

    def __init__(self, fastMA: int = 8, slowMA: int = 34, swingBefore: int = 3, swingAfter: int = 2):
        super().__init__()
        self.fastMA = SMA(fastMA)
        self.slowMA = SMA(slowMA)
        self.swings = Swings(swingBefore, swingAfter)

    def myId(self):
        return "MACross(%d,%d,%d,%d)" % (self.fastMA.period, self.slowMA.period, self.swings.before, self.swings.after)

    def init(self, bars: List[Bar], account: Account, symbol: Symbol):
        super().init(bars, account, symbol)
        self.logger.info("init with %d,%d,%d,%d" %
                         (self.fastMA.period, self.slowMA.period, self.swings.before, self.swings.after))
        self.fastMA.on_tick(bars)
        self.slowMA.on_tick(bars)
        self.swings.on_tick(bars)

    def min_bars_needed(self) -> int:
        return max(self.fastMA.period, self.slowMA.period, self.swings.before + self.swings.after) + 1

    def got_data_for_position_sync(self, bars: List[Bar]) -> bool:
        result = super().got_data_for_position_sync(bars)
        return result and (self.swings.get_data(bars[1]) is not None)

    def prep_bars(self, is_new_bar: bool, bars: list):
        if is_new_bar:
            self.fastMA.on_tick(bars)
            self.slowMA.on_tick(bars)
            self.swings.on_tick(bars)

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        # first the modules
        super().manage_open_order(order, position, bars, to_update, to_cancel, open_positions)
        # now the swing trail
        data: Data = self.swings.get_data(bars[1])
        if data is not None:
            stopLong = data.swingLow
            stopShort = data.swingHigh

            orderType = TradingBot.order_type_from_order_id(order.id)
            if position is not None and orderType == OrderType.SL:
                # trail
                newStop = order.trigger_price
                isLong = position.amount > 0
                trail = stopLong if isLong else stopShort
                if trail is not None and (trail - newStop) * position.amount > 0:
                    newStop = math.floor(trail) if not isLong else math.ceil(trail)

                if newStop != order.trigger_price:
                    order.trigger_price = newStop
                    to_update.append(order)

    def owns_signal_id(self, signalId: str):
        return signalId.startswith("MACross+")  # old style pure tstamp

    def open_new_trades(self, is_new_bar, directionFilter, bars, account, open_positions, all_open_pos: dict):
        if (not is_new_bar) or len(bars) < self.min_bars_needed():
            return  # only open orders on beginning of bar

        if not self.entries_allowed(bars):
            self.logger.info("no entries allowed")
            return

        # check for signal. we are at the open of the new bar. so bars[0] contains of only 1 tick.
        # we look at data bars[1] and bars[2]
        prevFast = self.fastMA.get_data(bars[2])
        currentFast = self.fastMA.get_data(bars[1])
        prevSlow = self.slowMA.get_data(bars[2])
        currentSlow = self.slowMA.get_data(bars[1])
        swingData: Data = self.swings.get_data(bars[1])  # for stops

        # include the expected slipage in the risk calculation
        expectedEntrySplipagePerc = 0.0015
        expectedExitSlipagePerc = 0.0015
        signalId = "MACross+" + str(bars[0].tstamp)

        if prevFast <= prevSlow and currentFast > currentSlow:
            # cross up -> long entry
            entry = bars[0].open  # current price
            stop = swingData.swingLow
            if stop is None:
                stop= lowest(bars,self.swings.before+self.swings.after,1,BarSeries.LOW)
            amount = self.calc_pos_size(risk=self.risk_factor, exitPrice=stop * (1 - expectedExitSlipagePerc),
                                        entry=entry * (1 + expectedEntrySplipagePerc))

            # open the position and save it
            posId = TradingBot.full_pos_id(signalId, PositionDirection.LONG)
            pos = Position(id=posId, entry=entry, amount=amount, stop=stop, tstamp=bars[0].tstamp)
            open_positions[posId] = pos
            # send entry as market, immediatly send SL too
            self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(posId, OrderType.ENTRY),
                                                  amount=amount, trigger=None, limit=None))
            self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(posId, OrderType.SL),
                                                  amount=-amount, trigger=stop, limit=None))
            pos.status = PositionStatus.OPEN

        elif prevFast >= prevSlow and currentFast < currentSlow:
            # cross down -> short entry
            entry = bars[0].open  # current price
            stop = swingData.swingHigh
            if stop is None:
                stop= highest(bars,self.swings.before+self.swings.after,1,BarSeries.HIGH)
            amount = self.calc_pos_size(risk=self.risk_factor, exitPrice=stop * (1 + expectedExitSlipagePerc),
                                        entry=entry * (1 - expectedEntrySplipagePerc))

            # open the position and save it
            posId = TradingBot.full_pos_id(signalId, PositionDirection.SHORT)
            pos = Position(id=posId, entry=entry, amount=amount, stop=stop, tstamp=bars[0].tstamp)
            open_positions[posId] = pos
            # send entry as market, immediatly send SL too
            self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(posId, OrderType.ENTRY),
                                                  amount=amount, trigger=None, limit=None))
            self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(posId, OrderType.SL),
                                                  amount=-amount, trigger=stop, limit=None))
            pos.status = PositionStatus.OPEN

    def add_to_price_data_plot(self, fig: go.Figure, bars: List[Bar], time):
        super().add_to_price_data_plot(fig, bars, time)
        styles = self.swings.get_line_styles()
        styles.extend(self.slowMA.get_line_styles())
        styles.extend(self.fastMA.get_line_styles())

        names = self.swings.get_line_names()
        names.extend(self.slowMA.get_line_names())
        names.extend(self.fastMA.get_line_names())
        offset = 0  # we take it with offset 1

        sub_data = list(map(lambda b: self.swings.get_data_for_plot(b)[0], bars))
        fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[0],
                        name=self.swings.id + "_" + names[0])
        sub_data = list(map(lambda b: self.swings.get_data_for_plot(b)[1], bars))
        fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[1],
                        name=self.swings.id + "_" + names[1])

        sub_data = list(map(lambda b: self.fastMA.get_data_for_plot(b)[0], bars))
        fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=self.fastMA.get_line_styles()[0],
                        name=self.fastMA.get_line_names()[0])
        sub_data = list(map(lambda b: self.slowMA.get_data_for_plot(b)[0], bars))
        fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=self.slowMA.get_line_styles()[0],
                        name=self.slowMA.get_line_names()[0])

    def get_stop_for_unmatched_amount(self, amount: float, bars: List[Bar]):
        # TODO: implement, not needed for sample strat
        pass
