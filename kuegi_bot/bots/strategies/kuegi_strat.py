import math
from datetime import datetime
from typing import List

from kuegi_bot.bots.strategies.channel_strat import ChannelStrategy
from kuegi_bot.bots.trading_bot import TradingBot, PositionDirection
from kuegi_bot.indicators.kuegi_channel import Data, clean_range
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType, Position, Order, PositionStatus


class KuegiStrategy(ChannelStrategy):
    def __init__(self, max_channel_size_factor: float = 6, min_channel_size_factor: float = 0,
                 entry_tightening=0, bars_till_cancel_triggered=3,
                 stop_entry: bool = False, delayed_entry: bool = True, delayed_cancel: bool = False,
                 cancel_on_filter:bool = False):
        super().__init__()
        self.max_channel_size_factor = max_channel_size_factor
        self.min_channel_size_factor = min_channel_size_factor
        self.stop_entry = stop_entry
        self.delayed_entry = delayed_entry
        self.entry_tightening = entry_tightening
        self.bars_till_cancel_triggered = bars_till_cancel_triggered
        self.delayed_cancel = delayed_cancel
        self.cancel_on_filter = cancel_on_filter

    def myId(self):
        return "KuegiStrategy"

    def init(self, bars: List[Bar], account: Account, symbol: Symbol):
        self.logger.info("init with %.0f %.1f  %.1f %i %s %s %s  %s" %
                         (self.max_channel_size_factor, self.min_channel_size_factor, self.entry_tightening,
                          self.bars_till_cancel_triggered,
                          self.stop_entry, self.delayed_entry, self.delayed_cancel,
                          self.cancel_on_filter))
        super().init(bars, account, symbol)

    def owns_signal_id(self, signalId: str):
        return signalId.startswith("kuegi+") or signalId.startswith('158') # old style pure tstamp

    def position_got_opened(self, position: Position, bars: List[Bar], account: Account, open_positions):
        other_id = TradingBot.get_other_direction_id(position.id)
        if other_id in open_positions.keys():
            open_positions[other_id].markForCancel = bars[0].tstamp

        # add stop
        gotStop= False # safety check needed to not add multiple SL in case of an error
        for order in account.open_orders:
            orderType = TradingBot.order_type_from_order_id(order.id)
            posId = TradingBot.position_id_from_order_id(order.id)
            if orderType == OrderType.SL and posId == position.id:
                gotStop= True
                break
        if not gotStop:
            order = Order(orderId=TradingBot.generate_order_id(positionId=position.id,
                                                           type=OrderType.SL),
                      stop=position.initial_stop,
                      amount=-position.amount)
            self.order_interface.send_order(order)
            # added temporarily, cause sync with open orders is in the next loop and otherwise the orders vs
            # position check fails
            if order not in account.open_orders:  # outside world might have already added it
                account.open_orders.append(order)

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        super().manage_open_order(order, position, bars, to_update, to_cancel, open_positions)

        data: Data = self.channel.get_data(bars[1])
        if data is None:
            return

        orderType = TradingBot.order_type_from_order_id(order.id)

        # check for triggered but not filled
        if order.stop_triggered:
            # clear other side
            other_id = TradingBot.get_other_direction_id(posId=position.id)
            if other_id in open_positions.keys():
                open_positions[other_id].markForCancel = bars[0].tstamp

            position.status = PositionStatus.TRIGGERED
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

        if orderType == OrderType.ENTRY and\
                (data.longSwing is None or data.shortSwing is None or
                 (self.cancel_on_filter and not self.entries_allowed(bars))):
            if position.status == PositionStatus.PENDING:  # don't delete if triggered
                self.logger.info("canceling cause channel got invalid: " + position.id)
                to_cancel.append(order)
                del open_positions[position.id]

    def manage_open_position(self, p, bars, account, pos_ids_to_cancel):
        # cancel marked positions
        if hasattr(p, "markForCancel") and p.status == PositionStatus.PENDING and (
                not self.delayed_cancel or p.markForCancel < bars[0].tstamp):
            self.logger.info("canceling position caused marked for cancel: " + p.id)
            p.status = PositionStatus.CANCELLED
            pos_ids_to_cancel.append(p.id)

    def open_orders(self, is_new_bar, directionFilter, bars, account, open_positions):
        if (not is_new_bar) or len(bars) < 5:
            return  # only open orders on beginning of bar

        entriesAllowed= self.entries_allowed(bars)
        if not entriesAllowed:
            self.logger.info("new entries not allowed by filter")


        last_data: Data = self.channel.get_data(bars[2])
        data: Data = self.channel.get_data(bars[1])
        if data is None:
            return

        self.logger.info("---- analyzing: %s atr: %.1f buffer: %.1f swings: %s/%s trails: %.1f/%.1f resets:%i/%i" %
                         (str(datetime.fromtimestamp(bars[0].tstamp)),
                          data.atr, data.buffer,
                          ("%.1f" % data.longSwing) if data.longSwing is not None else "-",
                          ("%.1f" % data.shortSwing) if data.shortSwing is not None else "-",
                          data.longTrail, data.shortTrail, data.sinceLongReset, data.sinceShortReset))
        if last_data is not None and \
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
                                                atr=data.atr)
                shortAmount = self.calc_pos_size(risk=risk, exitPrice=stopShort * (1 + expectedExitSlipagePerc),
                                                 entry=shortEntry * (1 - expectedEntrySplipagePerc),
                                                 atr=data.atr)
                if longEntry < stopLong or shortEntry > stopShort:
                    self.logger.warn("can't put initial stop above entry")

                foundLong = False
                foundShort = False
                for position in open_positions.values():
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
                            if TradingBot.position_id_from_order_id(order.id) == position.id:
                                newEntry = int(
                                    position.wanted_entry * (1 - self.entry_tightening) + entry * self.entry_tightening)
                                newStop = int(
                                    position.initial_stop * (1 - self.entry_tightening) + stop * self.entry_tightening)
                                amount = self.calc_pos_size(risk=risk, exitPrice=newStop * exitFac,
                                                            entry=newEntry * entryFac, atr=data.atr)
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

                self.send_signal_message("kuegi strat: active channel found between %.0f and %.0f" %
                                        ( shortEntry, longEntry))

                signalId = 'kuegi+' + str(bars[0].tstamp)
                if not foundLong and directionFilter >= 0 and entriesAllowed:
                    posId = TradingBot.full_pos_id(signalId, PositionDirection.LONG)
                    self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(posId, OrderType.ENTRY),
                                                          amount=longAmount, stop=longEntry,
                                                          limit=longEntry - 1 if not self.stop_entry else None))
                    open_positions[posId] = Position(id=posId, entry=longEntry, amount=longAmount, stop=stopLong,
                                                     tstamp=bars[0].tstamp)
                if not foundShort and directionFilter <= 0 and entriesAllowed:
                    posId = TradingBot.full_pos_id(signalId, PositionDirection.SHORT)
                    self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(posId, OrderType.ENTRY),
                                                          amount=shortAmount, stop=shortEntry,
                                                          limit=shortEntry + 1 if not self.stop_entry else None))
                    open_positions[posId] = Position(id=posId, entry=shortEntry, amount=shortAmount,
                                                     stop=stopShort, tstamp=bars[0].tstamp)
