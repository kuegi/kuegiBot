from kuegi_bot.bots.bot_with_channel import BotWithChannel
from kuegi_bot.bots.trading_bot import PositionDirection
from kuegi_bot.utils.trading_classes import Position, Order, Account, Bar, Symbol, OrderType, PositionStatus
from kuegi_bot.indicators.kuegi_channel import Data, clean_range
import math
from typing import List
from datetime import datetime


class KuegiBot(BotWithChannel):

    def __init__(self, logger=None, directionFilter=0,
                 max_channel_size_factor: float = 6, min_channel_size_factor: float = 0,
                 entry_tightening=0, bars_till_cancel_triggered=3,
                 stop_entry: bool = False, delayed_entry: bool = True, delayed_cancel: bool = False):
        super().__init__(logger, directionFilter)
        self.myId = "KuegiBot"
        self.max_channel_size_factor = max_channel_size_factor
        self.min_channel_size_factor = min_channel_size_factor
        self.stop_entry = stop_entry
        self.delayed_entry = delayed_entry
        self.entry_tightening = entry_tightening
        self.bars_till_cancel_triggered = bars_till_cancel_triggered
        self.delayed_cancel = delayed_cancel

    def init(self, bars: List[Bar], account: Account, symbol: Symbol, unique_id: str = ""):
        self.logger.info("init with %.0f %.1f  %.1f %i %s %s %s" %
                         (self.max_channel_size_factor, self.min_channel_size_factor, self.entry_tightening,
                          self.bars_till_cancel_triggered,
                          self.stop_entry, self.delayed_entry, self.delayed_cancel))
        super().init(bars, account, symbol, unique_id)

    def position_got_opened(self, position: Position, bars: List[Bar], account: Account):
        other_id = self.get_other_direction_id(position.id)
        if other_id in self.open_positions.keys():
            self.open_positions[other_id].markForCancel = bars[0].tstamp

        # add stop
        order = Order(orderId=self.generate_order_id(positionId=position.id,
                                                     type=OrderType.SL),
                      stop=position.initial_stop,
                      amount=-position.amount)
        self.order_interface.send_order(order)
        # added temporarily, cause sync with open orders is in the next loop and otherwise the orders vs
        # position check fails
        if order not in account.open_orders:  # outside world might have already added it
            account.open_orders.append(order)

    def manage_open_orders(self, bars: List[Bar], account: Account):
        super().manage_open_orders(bars, account)

        data: Data = self.channel.get_data(bars[1])
        if data is None:
            return

        # cancel marked positions
        pos_ids_to_cancel = []
        for p in self.open_positions.values():
            if hasattr(p, "markForCancel") and p.status == PositionStatus.PENDING and (
                    not self.delayed_cancel or p.markForCancel < bars[0].tstamp):
                self.logger.info("canceling position caused marked for cancel: " + p.id)
                self.cancel_all_orders_for_position(p.id, account)
                p.status = PositionStatus.CANCELLED
                pos_ids_to_cancel.append(p.id)

        for key in pos_ids_to_cancel:
            del self.open_positions[key]

        to_cancel = []
        for order in account.open_orders:
            posId = self.position_id_from_order_id(order.id)
            if posId not in self.open_positions.keys():
                continue
            pos = self.open_positions[posId]
            orderType = self.order_type_from_order_id(order.id)

            # check for triggered but not filled
            if order.stop_triggered:
                # clear other side
                other_id = self.get_other_direction_id(posId=posId)
                if other_id in self.open_positions.keys():
                    self.open_positions[other_id].markForCancel = bars[0].tstamp

                pos.status = PositionStatus.TRIGGERED
                if not hasattr(pos, 'waitingToFillSince'):
                    pos.waitingToFillSince = bars[0].tstamp
                if (bars[0].tstamp - pos.waitingToFillSince) > self.bars_till_cancel_triggered * (
                        bars[0].tstamp - bars[1].tstamp):
                    # cancel
                    pos.status = PositionStatus.MISSED
                    pos.exit_tstamp = bars[0].tstamp
                    super().position_closed(pos, account)
                    self.logger.info("canceling not filled position: " + pos.id)
                    to_cancel.append(order)

            if orderType == OrderType.ENTRY and (data.longSwing is None or data.shortSwing is None):
                if pos.status == PositionStatus.PENDING:  # don't delete if triggered
                    self.logger.info("canceling cause channel got invalid: " + pos.id)
                    to_cancel.append(order)
                    del self.open_positions[pos.id]

        for o in to_cancel:
            self.order_interface.cancel_order(o)


    def open_orders(self, bars: List[Bar], account: Account):
        if (not self.is_new_bar) or len(bars) < 5:
            return  # only open orders on beginning of bar

        last_data: Data = self.channel.get_data(bars[2])
        data: Data = self.channel.get_data(bars[1])
        if data is not None:
            self.logger.info("---- analyzing: %s atr: %.1f buffer: %.1f swings: %s/%s trails: %.1f/%.1f resets:%i/%i" %
                             (str(datetime.fromtimestamp(bars[0].tstamp)),
                              data.atr, data.buffer,
                              ("%.1f" % data.longSwing) if data.longSwing is not None else "-",
                              ("%.1f" % data.shortSwing) if data.shortSwing is not None else "-",
                              data.longTrail, data.shortTrail, data.sinceLongReset, data.sinceShortReset))
        if data is not None and last_data is not None and \
                data.shortSwing is not None and data.longSwing is not None and \
                (not self.delayed_entry or (last_data.shortSwing is not None and last_data.longSwing is not None)):
            swing_range = data.longSwing - data.shortSwing

            atr = clean_range(bars, offset=0, length=self.channel.max_look_back * 2)
            if atr * self.min_channel_size_factor < swing_range < atr * self.max_channel_size_factor:
                risk = self.risk_factor
                stopLong = int(max(data.shortSwing, data.longTrail))
                stopShort = int(min(data.longSwing, data.shortTrail))

                longEntry = int(max(data.longSwing, bars[0].high))
                shortEntry = int(min(data.shortSwing, bars[0].low))

                expectedEntrySplipagePerc = 0.0015 if self.stop_entry else 0
                expectedExitSlipagePerc = 0.0015

                # first check if we should update an existing one
                longAmount = self.calc_pos_size(risk=risk, exitPrice=stopLong * (1 - expectedExitSlipagePerc),
                                                entry=longEntry * (1 + expectedEntrySplipagePerc),
                                                data=data)
                shortAmount = self.calc_pos_size(risk=risk, exitPrice=stopShort * (1 + expectedExitSlipagePerc),
                                                 entry=shortEntry * (1 - expectedEntrySplipagePerc),
                                                 data=data)
                if longEntry < stopLong or shortEntry > stopShort:
                    self.logger.warn("can't put initial stop above entry")

                foundLong = False
                foundShort = False
                for position in self.open_positions.values():
                    if position.status == PositionStatus.PENDING:
                        if position.amount > 0:
                            foundLong = True
                            entry = longEntry
                            stop = stopLong
                            entryFac = (1 + expectedEntrySplipagePerc)
                            exitFac = (1 - expectedExitSlipagePerc)
                        else:
                            foundShort = True
                            entry = shortEntry
                            stop = stopShort
                            entryFac = (1 - expectedEntrySplipagePerc)
                            exitFac = (1 + expectedExitSlipagePerc)

                        for order in account.open_orders:
                            if self.position_id_from_order_id(order.id) == position.id:
                                newEntry = int(
                                    position.wanted_entry * (1 - self.entry_tightening) + entry * self.entry_tightening)
                                newStop = int(
                                    position.initial_stop * (1 - self.entry_tightening) + stop * self.entry_tightening)
                                amount = self.calc_pos_size(risk=risk, exitPrice=newStop * exitFac,
                                                            entry=newEntry * entryFac, data=data)
                                if amount * order.amount < 0:
                                    self.logger.warn("updating order switching direction")
                                changed = False
                                changed = changed or order.stop_price != newEntry
                                order.stop_price = newEntry
                                if not self.stop_entry:
                                    changed = changed or order.limit_price != newEntry - math.copysign(1, amount)
                                    order.limit_price = newEntry - math.copysign(1, amount)
                                changed = changed or order.amount != amount
                                order.amount = amount
                                if changed:
                                    self.order_interface.update_order(order)
                                else:
                                    self.logger.info("order didn't change: %s" % order.print_info())

                                position.initial_stop = newStop
                                position.amount = amount
                                position.wanted_entry = newEntry
                                break

                # if len(self.open_positions) > 0:
                # return

                signalId = str(bars[0].tstamp)
                if not foundLong and self.directionFilter >= 0:
                    posId = self.full_pos_id(signalId, PositionDirection.LONG)
                    self.order_interface.send_order(Order(orderId=self.generate_order_id(posId, OrderType.ENTRY),
                                                          amount=longAmount, stop=longEntry,
                                                          limit=longEntry - 1 if not self.stop_entry else None))
                    self.open_positions[posId] = Position(id=posId, entry=longEntry, amount=longAmount, stop=stopLong,
                                                          tstamp=bars[0].tstamp)
                if not foundShort and self.directionFilter <= 0:
                    posId = self.full_pos_id(signalId, PositionDirection.SHORT)
                    self.order_interface.send_order(Order(orderId=self.generate_order_id(posId, OrderType.ENTRY),
                                                          amount=shortAmount, stop=shortEntry,
                                                          limit=shortEntry + 1 if not self.stop_entry else None))
                    self.open_positions[posId] = Position(id=posId, entry=shortEntry, amount=shortAmount,
                                                          stop=stopShort, tstamp=bars[0].tstamp)
