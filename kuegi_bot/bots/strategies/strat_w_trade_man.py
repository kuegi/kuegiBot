from typing import List
import math

from kuegi_bot.bots.strategies.strat_with_exit_modules import StrategyWithExitModulesAndFilter
from kuegi_bot.bots.trading_bot import TradingBot, PositionDirection
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType, Order, PositionStatus, Position


class StrategyWithTradeManagement(StrategyWithExitModulesAndFilter):
    def __init__(self, close_on_opposite: bool = False, bars_till_cancel_triggered: int = 3, delayed_cancel: bool = False,
                 cancel_on_filter:bool = False, tp_fac: float = 0, maxPositions: int = 100, consolidate: bool = False,
                 limit_entry_offset_perc: float = -0.1):
        super().__init__()
        self.maxPositions = maxPositions
        self.consolidate = consolidate
        self.close_on_opposite = close_on_opposite
        self.bars_till_cancel_triggered = bars_till_cancel_triggered
        self.delayed_cancel = delayed_cancel
        self.cancel_on_filter = cancel_on_filter
        self.tp_fac = tp_fac
        self.limit_entry_offset_perc = limit_entry_offset_perc

    def init(self, bars: List[Bar], account: Account, symbol: Symbol):
        super().init(bars, account, symbol)
        self.logger.info(vars(self))

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

        # cancel entries not allowed
        if orderType == OrderType.ENTRY and position.status == PositionStatus.PENDING:
            if not hasattr(position, 'waitingToFillSince'):
                position.waitingToFillSince = bars[0].tstamp
            if ((bars[0].tstamp - position.waitingToFillSince) > self.bars_till_cancel_triggered * (
                    bars[0].tstamp - bars[1].tstamp)) or (len(open_positions) >= self.maxPositions):
                # cancel
                position.status = PositionStatus.MISSED
                position.exit_tstamp = bars[0].tstamp
                #del open_positions[position.id]
                self.logger.info("canceling not filled position: " + position.id)
                to_cancel.append(order)

    def consolidate_positions(self, is_new_bar, bars, account, open_positions):
        if (not is_new_bar) or self.maxPositions is None or self.consolidate is False:
            return

        lowestSL = highestSL = secLowestSL = secHighestSL = None
        secHighestSLPosID = highestSLPosID = secLowestSLPosID = lowestSLPosID = None
        amountHighestSL = amountLowestSL = amountSecHighestSL = amountSecLowestSL = None
        nmbShorts = nmbLongs = 0

        # find two lowest and highest SLs
        for order in account.open_orders:
            if order.trigger_price is not None:
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
                          trigger=position.initial_stop, amount=-position.amount)
            self.order_interface.send_order(order)

        if self.tp_fac > 0 and not gotTp:
            ref = position.filled_entry - position.initial_stop
            tp = max(0.0,position.filled_entry + ref * self.tp_fac)
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

    def update_existing_entries(self, account, open_positions, longEntry, shortEntry, stopLong, stopShort, longAmount, shortAmount):
        foundLong = False
        foundShort = False

        for position in open_positions.values():
            if position.status == PositionStatus.PENDING:
                if position.amount > 0:
                    foundLong = True
                    entry = longEntry
                    stop = stopLong
                    amount = longAmount
                else:
                    foundShort = True
                    entry = shortEntry
                    stop = stopShort
                    amount = shortAmount
                for order in account.open_orders:
                    if TradingBot.position_id_from_order_id(order.id) == position.id:
                        if order.trigger_price != stop or order.amount != amount or order.limit_price != entry:
                            entryBuffer = entry * self.limit_entry_offset_perc * 0.01
                            if amount > 0:
                                entryBuffer = -entryBuffer
                            order.limit_price = entry - entryBuffer
                            order.trigger_price = entry
                            order.amount = amount
                            self.logger.info("changing order id: %s, amount: %.1f, stop price: %.1f, limit price: %.f, active: %s" %
                                             (order.id, order.amount, order.trigger_price, order.limit_price, order.active))
                            self.order_interface.update_order(order)
                            position.wanted_entry = entry
                            position.initial_stop = stop
                            position.amount = amount
                        else:
                            self.logger.info("order didn't change: %s" % order.print_info())
                        break

        return foundLong, foundShort

    def open_new_position(self, direction, bars, stop, open_positions, entry, ExecutionType):
        # cancel if type of entry order not specified
        if ExecutionType not in ["Limit", "StopLimit", "StopLoss", "Market"]:
            self.logger.warn("Order type not specified. No order placed.")
            if self.telegram is not None:
                self.telegram.send_log("Execution type not specified. No order placed.")
            return

        # define directions
        oppDirection = PositionDirection.SHORT
        if direction == PositionDirection.SHORT:
            oppDirection = PositionDirection.LONG

        # first, close on opposite, if necessary
        if self.close_on_opposite:
            for pos in open_positions.values():
                if pos.status == PositionStatus.OPEN and \
                        TradingBot.split_pos_Id(pos.id)[1] == oppDirection:
                    # execution will trigger close and cancel of other orders
                    self.order_interface.send_order(
                        Order(orderId=TradingBot.generate_order_id(pos.id, OrderType.SL),
                              amount=-pos.amount, trigger=None, limit=None))

        # account position amount for slippage during stop loss execution
        expectedExitSlippagePer = 0.0015
        if direction == PositionDirection.LONG:
            entry = self.symbol.normalizePrice(entry, roundUp=True)
            stop = self.symbol.normalizePrice(stop, roundUp=False)
            exitPrice = stop * (1 - expectedExitSlippagePer)
        else:
            entry = self.symbol.normalizePrice(entry, roundUp=False)
            stop = self.symbol.normalizePrice(stop, roundUp=True)
            exitPrice = stop * (1 + expectedExitSlippagePer)
        amount = self.calc_pos_size(risk=self.risk_factor, entry=entry, exitPrice=exitPrice, atr=0)

        # If the trade doesn't make sense, abort
        if (direction == PositionDirection.SHORT and (amount >= 0 or entry > stop)) or\
                (direction == PositionDirection.LONG and (amount <= 0 or entry < stop)):
            self.logger.warn("entry/stop mismatch or wrong amount")
            return

        # Decide on entry order type
        if ExecutionType == "Limit":
            trigger_price = None
            limit_price = entry
        elif ExecutionType == "StopLimit":
            entryBuffer = entry * self.limit_entry_offset_perc * 0.01
            if amount > 0:
                entryBuffer = -entryBuffer
            trigger_price = entry
            limit_price = entry - entryBuffer
            limit_price = self.symbol.normalizePrice(limit_price, roundUp=amount < 0)
        elif ExecutionType == "StopLoss":
            trigger_price = entry
            limit_price = None
        else:                   # MarketOrder
            trigger_price = None
            limit_price = None

        # need to add to the bots open pos too, so the execution of the market is not missed
        signalId = self.get_signal_id(bars)
        posId = TradingBot.full_pos_id(signalId, direction)
        pos = Position(id=posId, entry=entry, amount=amount, stop=stop, tstamp=bars[0].tstamp)
        open_positions[posId] = pos
        self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(posId, OrderType.ENTRY),
                                              amount=amount, trigger=trigger_price, limit=limit_price))



