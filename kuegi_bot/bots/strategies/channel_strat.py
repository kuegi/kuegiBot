from typing import List
import math
import plotly.graph_objects as go

from kuegi_bot.bots.strategies.strat_with_exit_modules import StrategyWithExitModulesAndFilter
from kuegi_bot.bots.trading_bot import TradingBot, PositionDirection
from kuegi_bot.indicators.kuegi_channel import KuegiChannel, Data
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType, Order, PositionStatus, Position


class StrategyWithTradeManagement(StrategyWithExitModulesAndFilter):
    def __init__(self, close_on_opposite: bool = False, bars_till_cancel_triggered: int = 3, delayed_cancel: bool = False,
                 cancel_on_filter:bool = False, tp_fac: float = 0, maxPositions: int = 100, limit_entry_offset_perc: float = -0.1):
        super().__init__()
        self.maxPositions = maxPositions
        self.close_on_opposite = close_on_opposite
        self.bars_till_cancel_triggered = bars_till_cancel_triggered
        self.delayed_cancel = delayed_cancel
        self.cancel_on_filter = cancel_on_filter
        self.tp_fac = tp_fac
        self.limit_entry_offset_perc = limit_entry_offset_perc

    def init(self, bars: List[Bar], account: Account, symbol: Symbol):
        super().init(bars, account, symbol)
        self.logger.info()

    def myId(self):
        return "StrategyWithTradeManagement"

    #def got_data_for_position_sync(self, bars: List[Bar]) -> bool:
    #    result= super().got_data_for_position_sync(bars)
    #    return result and (self.channel.get_data(bars[1]) is not None)

    def get_stop_for_unmatched_amount(self, amount: float, bars: List[Bar]):
        # ignore possible stops from modules for now
        pass

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        # first the modules
        super().manage_open_order(order,position,bars,to_update,to_cancel,open_positions)

        orderType = TradingBot.order_type_from_order_id(order.id)
        if orderType == OrderType.SL:
            for module in self.exitModules:
                module.manage_open_order(order, position, bars, to_update, to_cancel, open_positions)

        # check for triggered but not filled
        if order.stop_triggered:
            # clear other side
            other_id = TradingBot.get_other_direction_id(posId=position.id)
            if other_id in open_positions.keys():
                open_positions[other_id].markForCancel = bars[0].tstamp

            if not hasattr(position, 'waitingToFillSince'):
                position.waitingToFillSince = bars[0].tstamp
            if (bars[0].tstamp - position.waitingToFillSince) > self.bars_till_cancel_triggered * (
                    bars[0].tstamp - bars[1].tstamp):
                # cancel
                position.status = PositionStatus.MISSED
                position.exit_tstamp = bars[0].tstamp
                del open_positions[position.id]
                self.logger.info("canceling not filled position: " + position.id)
                to_cancel.append(order)

        # cancel entries not allowed
        if orderType == OrderType.ENTRY and position.status == PositionStatus.PENDING and \
                (self.cancel_on_filter and not self.entries_allowed(bars)):
            self.logger.info("canceling cause channel got invalid: " + position.id)
            to_cancel.append(order)
            del open_positions[position.id]

    def consolidate_positions(self, is_new_bar, bars, account, open_positions):
        if (not is_new_bar) or len(bars) < 5 or self.maxPositions is None:
            return

        lowestSL = highestSL = secLowestSL = secHighestSL = None
        secHighestSLPosID = highestSLPosID = secLowestSLPosID = lowestSLPosID = None
        amountHighestSL = amountLowestSL = amountSecHighestSL = amountSecLowestSL = None
        nmbShorts = nmbLongs = 0

        # find two lowest and highest SLs
        for order in account.open_orders:
            if order.stop_price is not None:
                orderType = TradingBot.order_type_from_order_id(order.id)
                posId = TradingBot.position_id_from_order_id(order.id)

                if orderType == OrderType.SL and posId in open_positions:
                    if open_positions[posId].status == PositionStatus.OPEN:
                        if order.amount < 0:
                            nmbLongs = nmbLongs + 1
                            if lowestSL is None:
                                lowestSL = order.stop_price
                                secLowestSL = order.stop_price
                                lowestSLPosID = posId
                                amountLowestSL = order.amount
                                amountSecLowestSL = order.amount
                            elif order.stop_price < lowestSL:
                                secLowestSL = lowestSL
                                lowestSL = order.stop_price
                                secLowestSLPosID = lowestSLPosID
                                lowestSLPosID = posId
                                amountSecLowestSL = amountLowestSL
                                amountLowestSL = order.amount
                        else:
                            nmbShorts = nmbShorts + 1
                            if highestSL is None:
                                secHighestSL = order.stop_price
                                highestSL = order.stop_price
                                highestSLPosID = posId
                                amountHighestSL = order.amount
                                amountSecHighestSL = order.amount
                            elif order.stop_price > highestSL:
                                secHighestSL = highestSL
                                highestSL = order.stop_price
                                secHighestSLPosID = highestSLPosID
                                highestSLPosID = posId
                                amountSecHighestSL = amountHighestSL
                                amountHighestSL = order.amount
            else:
                pass

        if nmbShorts > self.maxPositions:
            for order in account.open_orders:
                orderType = TradingBot.order_type_from_order_id(order.id)
                orderID = TradingBot.position_id_from_order_id(order.id)
                self.logger.info("consolidating positions")
                # Cancel two Shorts with the highest SLs
                if orderType == OrderType.SL and orderID == highestSLPosID:
                    order.limit_price = None
                    order.stop_price = None
                    self.logger.info("Closing position with highest SL")
                    self.order_interface.update_order(order)

                elif orderType == OrderType.SL and orderID == secHighestSLPosID:
                    order.limit_price = None
                    order.stop_price = None
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
            self.order_interface.send_order(Order(orderId=orderId, amount=-x, stop=None, limit=None))
            self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(posId, OrderType.SL),
                                                  amount=x, stop=secHighestSL, limit=None))

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
                    order.stop_price = None
                    self.logger.info("Closing positions with lowest SL")
                    self.order_interface.update_order(order)

                elif orderType == OrderType.SL and orderID == secLowestSLPosID:
                    order.limit_price = None
                    order.stop_price = None
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
            self.order_interface.send_order(Order(orderId=orderId, amount=-x, stop=None, limit=None))
            self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(posId, OrderType.SL),
                                                  amount=x, stop=secLowestSL, limit=None))

            pos = Position(id=posId, entry=bars[0].open, amount=-x, stop=y, tstamp=bars[0].last_tick_tstamp)
            pos.status = PositionStatus.OPEN
            open_positions[posId] = pos

    #def add_to_plot(self, fig: go.Figure, bars: List[Bar], time):
        """super().add_to_plot(fig, bars, time)
        lines = self.channel.get_number_of_lines()
        styles = self.channel.get_line_styles()
        names = self.channel.get_line_names()
        offset = 1  # we take it with offset 1
        self.logger.info("adding channel")
        for idx in range(0, lines):
            sub_data = list(map(lambda b: self.channel.get_data_for_plot(b)[idx], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[idx],
                            name=self.channel.id + "_" + names[idx])"""

    def position_got_opened_or_changed(self, position, bars: List[Bar], account: Account, open_positions):
        other_id = TradingBot.get_other_direction_id(position.id)
        if other_id in open_positions.keys():
            open_positions[other_id].markForCancel = bars[0].tstamp

        # add stop
        gotStop = False  # safety check needed to not add multiple SL in case of an error
        gotTp = False
        for order in account.open_orders:
            orderType = TradingBot.order_type_from_order_id(order.id)
            posId = TradingBot.position_id_from_order_id(order.id)
            if orderType == OrderType.SL and posId == position.id:
                gotStop = True
                if abs(order.amount + position.current_open_amount) > self.symbol.lotSize / 2:
                    order.amount = -position.current_open_amount
                    self.order_interface.update_order(order)
            elif self.tp_fac > 0 and orderType == OrderType.TP and posId == position.id:
                gotTp = True
                amount = self.symbol.normalizeSize(-position.current_open_amount + order.executed_amount)
                if abs(order.amount - amount) > self.symbol.lotSize / 2:
                    order.amount = amount
                    self.order_interface.update_order(order)

        if not gotStop:
            order = Order(orderId=TradingBot.generate_order_id(positionId=position.id, type=OrderType.SL),
                          stop=position.initial_stop, amount=-position.amount)
            self.order_interface.send_order(order)

        if self.tp_fac > 0 and not gotTp:
            ref = position.filled_entry - position.initial_stop
            tp = max(0,position.filled_entry + ref * self.tp_fac)
            order = Order(orderId=TradingBot.generate_order_id(positionId=position.id,type=OrderType.TP),
                          limit=tp,amount=-position.amount)
            self.order_interface.send_order(order)

    def manage_open_position(self, p, bars, account, pos_ids_to_cancel):
        # cancel marked positions
        if hasattr(p, "markForCancel") and p.status == PositionStatus.PENDING and (
                not self.delayed_cancel or p.markForCancel < bars[0].tstamp):
            self.logger.info("cancelling position, because marked for cancel: " + p.id)
            p.status = PositionStatus.CANCELLED
            pos_ids_to_cancel.append(p.id)

    def update_existing_entries(self, account, open_positions, longEntry, shortEntry, stopLong, stopShort, atr):
        foundLong = False
        foundShort = False

        expectedEntrySlippagePer = 0.0015 if self.limit_entry_offset_perc is None else 0
        expectedExitSlippagePer = 0.0015
        risk = self.risk_factor

        for position in open_positions.values():
            if position.status == PositionStatus.PENDING:
                if position.amount > 0:
                    foundLong = True
                    entry = longEntry
                    stop = stopLong
                    entryFac = (1 + expectedEntrySlippagePer)
                    exitFac = (1 - expectedExitSlippagePer)
                else:
                    foundShort = True
                    entry = shortEntry
                    stop = stopShort
                    entryFac = (1 - expectedEntrySlippagePer)
                    exitFac = (1 + expectedExitSlippagePer)
                entryBuffer = entry * self.limit_entry_offset_perc * 0.01 if self.limit_entry_offset_perc is not None else None
                for order in account.open_orders:
                    if TradingBot.position_id_from_order_id(order.id) == position.id:
                        newEntry = entry
                        newEntry = self.symbol.normalizePrice(newEntry, roundUp=order.amount > 0)
                        newStop = stop
                        newStop = self.symbol.normalizePrice(newStop, roundUp=order.amount < 0)
                        amount = self.calc_pos_size(risk=risk, exitPrice=newStop * exitFac,
                                                    entry=newEntry * entryFac, atr=atr)
                        if amount * order.amount < 0:
                            self.logger.warn("updating order switching direction")
                        changed = False
                        changed = changed or order.stop_price != newEntry
                        if changed and order.stop_price is not None and newEntry is not None:
                            self.logger.info("old entry: %.1f, new entry: %.1f" % (order.stop_price, newEntry))
                        order.stop_price = newEntry
                        if self.limit_entry_offset_perc is not None:
                            newLimit = newEntry - entryBuffer * math.copysign(1, amount)
                            changed = changed or order.limit_price != newLimit
                            if changed and order.stop_price is not None and newEntry is not None:
                                self.logger.info("old limit: %.1f, new limit: %.1f" % (order.limit_price, newLimit))
                            order.limit_price = newLimit
                        changed = changed or order.amount != amount
                        if changed and order.stop_price is not None and newEntry is not None:
                            self.logger.info("old amount: %.1f, new amount: %.1f" % (order.amount, amount))
                        order.amount = amount
                        if changed:
                            self.logger.info("changing order id: %s, amount: %.1f, stop price: %.1f, limit price: %.f, active: %s" %
                                             (order.id, order.amount, order.stop_price, order.limit_price, order.active))
                            self.order_interface.update_order(order)
                        else:
                            self.logger.info("order didn't change: %s" % order.print_info())

                        position.initial_stop = newStop
                        position.amount = amount
                        position.wanted_entry = newEntry
                        break

        return foundLong, foundShort

    def open_new_position(self, direction, bars, stop, open_positions, entry):
        # define directions
        directionFactor = 1
        oppDirection = PositionDirection.SHORT
        if direction == PositionDirection.SHORT:
            directionFactor = -1
            oppDirection = PositionDirection.LONG
        oppDirectionFactor = directionFactor * -1

        """ "# first close on opposite, if necessary
        if self.close_on_opposite:
            for pos in open_positions.values():
                if pos.status == PositionStatus.OPEN and \
                        TradingBot.split_pos_Id(pos.id)[1] == oppDirection:
                    # execution will trigger close and cancel of other orders
                    self.order_interface.send_order(
                        Order(orderId=TradingBot.generate_order_id(pos.id, OrderType.SL),
                              amount=-pos.amount, stop=None, limit=None))"""

        # Consider slippage
        expectedEntrySplipagePerc = 0.0015
        expectedExitSlipagePerc = 0.0015
        signalId = self.get_signal_id(bars)
        posId = TradingBot.full_pos_id(signalId, direction)
        amount = self.calc_pos_size(risk=self.risk_factor,
                                    exitPrice=stop * (1 + oppDirectionFactor * expectedExitSlipagePerc),
                                    entry=entry * (1 + directionFactor * expectedEntrySplipagePerc))

        # If the trade doesn't make sense, abort
        if (direction == PositionDirection.SHORT and (amount > 0 or entry > stop)) or\
                (direction == PositionDirection.LONG and (amount < 0 or entry < stop)):
            self.logger.warn("entry/stop mismatch or wrong amount")
            return

        # need to add to the bots open pos too, so the execution of the market is not missed
        self.order_interface.send_order(Order(
            orderId=TradingBot.generate_order_id(posId, OrderType.ENTRY), amount=amount, stop=entry, limit=entry))
        pos = Position(id=posId, entry=entry, amount=amount, stop=stop, tstamp=bars[0].tstamp)
        open_positions[posId] = pos


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
                newStop = order.stop_price
                isLong = position.amount > 0
                if self.trail_active:
                    trail = stopLong if isLong else stopShort
                    if (trail - newStop) * position.amount > 0 or \
                            (self.trail_back and position.initial_stop is not None 
                                and (trail - position.initial_stop) * position.amount > 0):
                        newStop = math.floor(trail) if not isLong else math.ceil(trail)

                if newStop != order.stop_price:
                    order.stop_price = newStop
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
                            lowestSL = order.stop_price
                            secLowestSL = order.stop_price
                            lowestSLPosID = posId
                            amountLowestSL = order.amount
                            amountSecLowestSL = order.amount
                        elif order.stop_price < lowestSL:
                            secLowestSL = lowestSL
                            lowestSL = order.stop_price
                            secLowestSLPosID = lowestSLPosID
                            lowestSLPosID = posId
                            amountSecLowestSL = amountLowestSL
                            amountLowestSL = order.amount
                    else:
                        nmbShorts = nmbShorts + 1
                        if highestSL is None:
                            secHighestSL = order.stop_price
                            highestSL = order.stop_price
                            highestSLPosID = posId
                            amountHighestSL = order.amount
                            amountSecHighestSL = order.amount
                        elif order.stop_price > highestSL:
                            secHighestSL = highestSL
                            highestSL = order.stop_price
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
                    order.stop_price = None
                    self.logger.info("Closing position with highest SL")
                    self.order_interface.update_order(order)

                elif orderType == OrderType.SL and orderID == secHighestSLPosID:
                    order.limit_price = None
                    order.stop_price = None
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
            self.order_interface.send_order(Order(orderId=orderId, amount=-x, stop=None, limit=None))
            self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(posId, OrderType.SL),
                                                  amount=x, stop=secHighestSL, limit=None))

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
                    order.stop_price = None
                    self.logger.info("Closing positions with lowest SL")
                    self.order_interface.update_order(order)

                elif orderType == OrderType.SL and orderID == secLowestSLPosID:
                    order.limit_price = None
                    order.stop_price = None
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
            self.order_interface.send_order(Order(orderId=orderId, amount=-x, stop=None, limit=None))
            self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(posId, OrderType.SL),
                                                  amount=x, stop=secLowestSL, limit=None))

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

