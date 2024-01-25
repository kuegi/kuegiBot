from typing import List
import math
import plotly.graph_objects as go

from kuegi_bot.bots.strategies.strat_with_exit_modules import StrategyWithExitModulesAndFilter
from kuegi_bot.bots.trading_bot import TradingBot, PositionDirection
from kuegi_bot.indicators.kuegi_channel import KuegiChannel, Data
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType, Order, PositionStatus, Position


class ChannelStrategy(StrategyWithExitModulesAndFilter):

    def __init__(self):
        super().__init__()
        self.channel: KuegiChannel = None
        self.trail_to_swing = False
        self.delayed_swing_trail = True
        self.trail_back = False
        self.trail_active = False
        self.maxPositions = None

    def myId(self):
        return "ChannelStrategy"

    def withChannel(self, max_look_back, threshold_factor, buffer_factor, max_dist_factor, max_swing_length):
        self.channel = KuegiChannel(max_look_back, threshold_factor, buffer_factor, max_dist_factor, max_swing_length)
        return self

    def withTrail(self, trail_to_swing: bool = False, delayed_swing: bool = True, trail_back: bool = False):
        self.trail_active = False
        self.delayed_swing_trail = delayed_swing
        self.trail_to_swing = trail_to_swing
        self.trail_back = trail_back
        return self

    def init(self, bars: List[Bar], account: Account, symbol: Symbol):
        super().init(bars, account, symbol)
        if self.channel is None:
            self.logger.error("No channel provided on init")
        else:
            self.logger.info("init with %i %.1f %.3f %.1f %i | %.3f %.1f %i %.1f | %s %s %s %s" %
                             (self.channel.max_look_back, self.channel.threshold_factor, self.channel.buffer_factor,
                              self.channel.max_dist_factor, self.channel.max_swing_length,
                              self.risk_factor, self.max_risk_mul, self.risk_type, self.atr_factor_risk,
                              self.trail_active, self.delayed_swing_trail, self.trail_to_swing, self.trail_back))
            self.channel.on_tick(bars)

    def min_bars_needed(self) -> int:
        return self.channel.max_look_back + 1

    def got_data_for_position_sync(self, bars: List[Bar]) -> bool:
        result= super().got_data_for_position_sync(bars)
        return result and (self.channel.get_data(bars[1]) is not None)

    def get_stop_for_unmatched_amount(self, amount: float, bars: List[Bar]):
        # ignore possible stops from modules for now
        data = self.channel.get_data(bars[1])
        stopLong = int(max(data.shortSwing, data.longTrail) if data.shortSwing is not None else data.longTrail)
        stopShort = int(min(data.longSwing, data.shortTrail) if data.longSwing is not None else data.shortTrail)
        stop= stopLong if amount > 0 else stopShort

    def prep_bars(self, is_new_bar: bool, bars: list):
        if is_new_bar:
            self.channel.on_tick(bars)

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        # first the modules
        super().manage_open_order(order,position,bars,to_update,to_cancel,open_positions)
        # now the channel stuff
        last_data: Data = self.channel.get_data(bars[2])
        data: Data = self.channel.get_data(bars[1])
        if data is not None:
            stopLong = data.longTrail
            stopShort = data.shortTrail
            if self.trail_to_swing and \
                    data.longSwing is not None and data.shortSwing is not None and \
                    (not self.delayed_swing_trail or (last_data is not None and
                                                      last_data.longSwing is not None and
                                                      last_data.shortSwing is not None)):
                stopLong = max(data.shortSwing, stopLong)
                stopShort = min(data.longSwing, stopShort)

            orderType = TradingBot.order_type_from_order_id(order.id)
            if position is not None and orderType == OrderType.SL:
                # trail
                newStop = order.trigger_price
                isLong = position.amount > 0
                if self.trail_active:
                    trail = stopLong if isLong else stopShort
                    if (trail - newStop) * position.amount > 0 or \
                            (self.trail_back and position.initial_stop is not None 
                                and (trail - position.initial_stop) * position.amount > 0):
                        newStop = math.floor(trail) if not isLong else math.ceil(trail)

                if newStop != order.trigger_price:
                    order.trigger_price = newStop
                    to_update.append(order)

    def consolidate_positions(self, is_new_bar, bars, account, open_positions):
        if (not is_new_bar) or len(bars) < 5 or self.maxPositions is None:
            return

        lowestSL = highestSL = secLowestSL = secHighestSL = None
        secHighestSLPosID = highestSLPosID = secLowestSLPosID = lowestSLPosID = None
        amountHighestSL = amountLowestSL = amountSecHighestSL = amountSecLowestSL = None
        nmbShorts = nmbLongs = 0

        # find two lowest and highest SLs
        for order in account.open_orders:
            orderType = TradingBot.order_type_from_order_id(order.id)
            posId = TradingBot.position_id_from_order_id(order.id)

            if orderType == OrderType.SL and posId in open_positions:
                if open_positions[posId].status == PositionStatus.OPEN:
                    if order.amount < 0:
                        nmbLongs = nmbLongs + 1
                        if lowestSL is None:
                            lowestSL = order.trigger_price
                            secLowestSL = order.trigger_price
                            lowestSLPosID = posId
                            amountLowestSL = order.amount
                            amountSecLowestSL = order.amount
                        elif order.trigger_price < lowestSL:
                            secLowestSL = lowestSL
                            lowestSL = order.trigger_price
                            secLowestSLPosID = lowestSLPosID
                            lowestSLPosID = posId
                            amountSecLowestSL = amountLowestSL
                            amountLowestSL = order.amount
                    else:
                        nmbShorts = nmbShorts + 1
                        if highestSL is None:
                            secHighestSL = order.trigger_price
                            highestSL = order.trigger_price
                            highestSLPosID = posId
                            amountHighestSL = order.amount
                            amountSecHighestSL = order.amount
                        elif order.trigger_price > highestSL:
                            secHighestSL = highestSL
                            highestSL = order.trigger_price
                            secHighestSLPosID = highestSLPosID
                            highestSLPosID = posId
                            amountSecHighestSL = amountHighestSL
                            amountHighestSL = order.amount

        if nmbShorts > self.maxPositions:
            for order in account.open_orders:
                orderType = TradingBot.order_type_from_order_id(order.id)
                orderID = TradingBot.position_id_from_order_id(order.id)
                self.logger.info("consolidating positions")
                # Cancel two Shorts with the highest SLs
                if orderType == OrderType.SL and orderID == highestSLPosID:
                    order.limit_price = None
                    order.trigger_price = None
                    self.logger.info("Closing position with highest SL")
                    self.order_interface.update_order(order)

                elif orderType == OrderType.SL and orderID == secHighestSLPosID:
                    order.limit_price = None
                    order.trigger_price = None
                    self.logger.info("Closing position with second highest SL")
                    self.order_interface.update_order(order)

            # Open new short as a combination of two previously cancelled shorts
            x = amountHighestSL + amountSecHighestSL
            x1 = amountHighestSL
            y1 = highestSL
            x2 = amountSecHighestSL
            y2 = secHighestSL

            # weighted average (y = new order.stop_price)
            y = (x1 * y1 + x2 * y2) / (x1 + x2)

            # send new short
            signalId = self.get_signal_id(bars)
            posId = TradingBot.full_pos_id(signalId, PositionDirection.SHORT)
            orderId = TradingBot.generate_order_id(posId, OrderType.ENTRY)

            self.logger.info("sending replacement position and SL")
            self.order_interface.send_order(Order(orderId=orderId, amount=-x, trigger=None, limit=None))
            self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(posId, OrderType.SL),
                                                  amount=x, trigger=secHighestSL, limit=None))

            pos = Position(id=posId, entry=bars[0].open, amount=-x, stop=y, tstamp=bars[0].last_tick_tstamp)
            pos.status = PositionStatus.OPEN
            open_positions[posId] = pos

        if nmbLongs > self.maxPositions:
            for order in account.open_orders:
                orderType = TradingBot.order_type_from_order_id(order.id)
                orderID = TradingBot.position_id_from_order_id(order.id)
                self.logger.info("consolidating positions")
                # Cancel two Longs with the lowest SLs
                if orderType == OrderType.SL and orderID == lowestSLPosID:
                    order.limit_price = None
                    order.trigger_price = None
                    self.logger.info("Closing positions with lowest SL")
                    self.order_interface.update_order(order)

                elif orderType == OrderType.SL and orderID == secLowestSLPosID:
                    order.limit_price = None
                    order.trigger_price = None
                    self.logger.info("Closing positions with second lowest SL")
                    self.order_interface.update_order(order)

            # Open new long as a combination of two previously cancelled longs
            x = amountLowestSL + amountSecLowestSL
            x1 = amountLowestSL
            y1 = lowestSL
            x2 = amountSecLowestSL
            y2 = secLowestSL

            # weighted average (y = order.stop_price)
            y = (x1 * y1 + x2 * y2) / (x1 + x2)

            # send new long
            signalId = self.get_signal_id(bars)
            posId = TradingBot.full_pos_id(signalId, PositionDirection.LONG)
            orderId = TradingBot.generate_order_id(posId, OrderType.ENTRY)

            self.logger.info("sending replacement position and SL")
            self.order_interface.send_order(Order(orderId=orderId, amount=-x, trigger=None, limit=None))
            self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(posId, OrderType.SL),
                                                  amount=x, trigger=secLowestSL, limit=None))

            pos = Position(id=posId, entry=bars[0].open, amount=-x, stop=y, tstamp=bars[0].last_tick_tstamp)
            pos.status = PositionStatus.OPEN
            open_positions[posId] = pos

    def add_to_plot(self, fig: go.Figure, bars: List[Bar], time):
        super().add_to_plot(fig, bars, time)
        lines = self.channel.get_number_of_lines()
        styles = self.channel.get_line_styles()
        names = self.channel.get_line_names()
        offset = 1  # we take it with offset 1
        self.logger.info("adding channel")
        for idx in range(0, lines):
            sub_data = list(map(lambda b: self.channel.get_data_for_plot(b)[idx], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[idx],
                            name=self.channel.id + "_" + names[idx])

