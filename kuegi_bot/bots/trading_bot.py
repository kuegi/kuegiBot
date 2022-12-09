import time

from kuegi_bot.bots.strategies.exit_modules import ExitModule
from kuegi_bot.utils.trading_classes import Bar, Position, Symbol, OrderInterface, Account, OrderType, Order, \
    PositionStatus, ExchangeInterface

import plotly.graph_objects as go

from typing import List, Dict
from datetime import datetime
from random import randint
from enum import Enum

import os
import json
import csv


class PositionDirection(Enum):
    LONG = "long",
    SHORT = "short"


class TradingBot:
    def __init__(self, logger, directionFilter: int = 0):
        self.myId = "GenericBot"
        self.logger = logger
        self.directionFilter = directionFilter
        self.order_interface: ExchangeInterface = None
        self.symbol: Symbol = None
        self.unique_id: str = ""
        self.last_time = 0
        self.last_tick_time: datetime = None
        self.is_new_bar = True
        self.open_positions: Dict[str, Position] = {}
        self.known_order_history = 0
        self.risk_reference = 1
        self.max_equity = 0
        self.time_of_max_equity = 0
        self.position_history: List[Position] = []
        self.open_position_rolling = 1
        self.unaccounted_position_cool_off = 0
        self.reset()

    def uid(self) -> str:
        return self.myId

    def prepare(self, logger, order_interface):
        self.logger = logger
        self.order_interface = order_interface

    def min_bars_needed(self):
        return 5

    def reset(self):
        self.last_time = 0
        self.open_positions = {}
        self.known_order_history = 0
        self.position_history = []

    def _get_pos_file(self, rolling: int = 0):
        roll = "" if rolling == 0 else "_" + str(rolling)
        return self.symbol.symbol + "_" + self.unique_id + roll + ".json" if self.unique_id is not None else None

    def init(self, bars: List[Bar], account: Account, symbol: Symbol, unique_id: str = ""):
        '''init open position etc.'''
        self.symbol = symbol
        self.unique_id = unique_id
        # init positions from existing orders
        self.read_open_positions(bars)
        self.sync_connected_orders(account)
        self.sync_positions_with_open_orders(bars, account)

    ############### ids of pos, signal and order

    @staticmethod
    def generate_order_id(positionId: str, type: OrderType):
        if "_" in positionId:
            print("position id must not include '_' but does: " + positionId)
        orderId = positionId + "_" + str(type.name)
        if type == OrderType.SL or type == OrderType.TP:
            # add random part to prevent conflicts if the order was canceled before
            orderId = orderId + "_" + str(randint(0, 999))
        return orderId

    @staticmethod
    def position_id_and_type_from_order_id(order_id: str):
        id_parts = order_id.split("_")
        posId = None
        order_type = None
        if len(id_parts) >= 1:
            posId = id_parts[0]
        if len(id_parts) >= 2:
            type = id_parts[1]
            if type[0] == OrderType.ENTRY.name[0]:
                order_type = OrderType.ENTRY
            elif type[0] == OrderType.SL.name[0]:
                order_type = OrderType.SL
            elif type[0] == OrderType.TP.name[0]:
                order_type = OrderType.TP
        return [posId, order_type]

    @staticmethod
    def position_id_from_order_id(order_id: str):
        id_parts = order_id.split("_")
        if len(id_parts) >= 1:
            return id_parts[0]
        return None

    @staticmethod
    def order_type_from_order_id(order_id: str) -> OrderType:
        id_parts = order_id.split("_")
        if len(id_parts) >= 2:
            type = id_parts[1]
            if type[0] == OrderType.ENTRY.name[0]:
                return OrderType.ENTRY
            elif type[0] == OrderType.SL.name[0]:
                return OrderType.SL
            elif type[0] == OrderType.TP.name[0]:
                return OrderType.TP
        return None

    @staticmethod
    def full_pos_id(signalId: str, direction: PositionDirection):
        if "-" in signalId:
            print("signal id must not include '-' but does: " + signalId)
        return signalId + "-" + str(direction.name)

    @staticmethod
    def split_pos_Id(posId: str):
        parts = posId.split("-")
        if len(parts) >= 2:
            if parts[1] == str(PositionDirection.SHORT.name):
                return [parts[0], PositionDirection.SHORT]
            elif parts[1] == str(PositionDirection.LONG.name):
                return [parts[0], PositionDirection.LONG]
        return [posId, None]

    @staticmethod
    def get_other_direction_id(posId: str):
        parts = TradingBot.split_pos_Id(posId)
        if parts[1] is not None:
            return TradingBot.full_pos_id(parts[0],
                                          PositionDirection.LONG if parts[1] == PositionDirection.SHORT
                                          else PositionDirection.SHORT)
        return None

    ############### handling of open orders

    def check_open_orders_in_position(self, position: Position):
        gotSL = False
        for order in position.connectedOrders:
            if self.order_type_from_order_id(order.id) == OrderType.SL:
                if gotSL:
                    # double SL: cancel
                    self.order_interface.cancel_order(order)
                else:
                    gotSL = True
        # TODO: move handling of missing SL to here

    def cancel_entry(self, positionId, account: Account):
        to_cancel = self.generate_order_id(positionId, OrderType.ENTRY)
        for o in account.open_orders:
            if o.id == to_cancel:
                self.order_interface.cancel_order(o)
                # only cancel position if entry was still there
                if positionId in self.open_positions.keys():
                    del self.open_positions[positionId]
                break

    def position_got_opened_or_changed(self, position: Position, bars: List[Bar], account: Account):
        # empty hook for actual bot to maybe clear linked positions etc.
        pass

    def handle_opened_or_changed_position(self, position: Position, account: Account, bars: List[Bar]):
        position.status = PositionStatus.OPEN
        self.position_got_opened_or_changed(position, bars, account)

    def on_execution(self, order_id, amount, executed_price, tstamp):
        pos_id = self.position_id_from_order_id(order_id)
        if pos_id not in self.open_positions.keys():
            self.logger.info("executed order not found in positions: " + order_id)
            return
        position: Position = self.open_positions[pos_id]

        order_type = self.order_type_from_order_id(order_id)
        position.changed = True
        if order_type == OrderType.ENTRY:
            position.status = PositionStatus.OPEN
            if position.filled_entry is not None:
                position.filled_entry = (position.filled_entry * position.max_filled_amount + executed_price * amount) \
                                        / (position.max_filled_amount + amount)
            else:
                position.filled_entry = executed_price
            position.last_filled_entry = executed_price
            position.entry_tstamp = tstamp
            position.max_filled_amount += amount
            self.logger.info(f"position got increased/opened: {position.id} to {position.current_open_amount}")
        if order_type in [OrderType.TP, OrderType.SL]:
            # completly closed
            if abs(position.current_open_amount + amount) < self.symbol.lotSize / 2:
                position.status = PositionStatus.CLOSED
            if position.filled_exit is not None and (position.max_filled_amount - position.current_open_amount - amount) != 0:
                position.filled_exit = (position.filled_exit * (
                        position.max_filled_amount - position.current_open_amount) + executed_price * (-amount)) \
                                       / (position.max_filled_amount - position.current_open_amount - amount)
            else:
                position.filled_exit = executed_price
            position.exit_tstamp = tstamp
            self.logger.info(f"position got reduced: {position.id} to {position.current_open_amount}")

        position.current_open_amount += amount

    def sync_connected_orders(self, account: Account):
        # update connected orders in position
        for pos in self.open_positions.values():
            pos.connectedOrders = []  # will be filled now

        for order in account.open_orders:
            if not order.active:
                continue  # got cancelled during run
            [posId, orderType] = self.position_id_and_type_from_order_id(order.id)
            if orderType is None:
                continue  # none of ours
            if posId in self.open_positions.keys():
                pos = self.open_positions[posId]
                pos.connectedOrders.append(order)

    def sync_executions(self, bars: List[Bar], account: Account):
        self.sync_connected_orders(account)
        closed_pos = []
        changed = False
        for position in self.open_positions.values():
            if position.changed:
                if position.status == PositionStatus.OPEN:
                    self.logger.info("open position %s got changed" % position.id)
                    self.handle_opened_or_changed_position(position=position, account=account, bars=bars)
                    changed = True
                elif position.status == PositionStatus.CLOSED:
                    self.logger.info("position %s got closed" % position.id)
                    closed_pos.append(position)
                position.changed = False

        for position in closed_pos:
            self.position_closed(position, account)

        if changed:
            self.sync_connected_orders(account)

        # old way (fallback if executions wheren't there)
        if not self.order_interface.handles_executions:
            self.logger.error("your exchange interface doesn't handle executions yet. please upgrade")
            for order in account.order_history[self.known_order_history:]:
                if order.executed_amount == 0:
                    continue
                posId = self.position_id_from_order_id(order.id)
                if posId not in self.open_positions.keys():
                    self.logger.info("executed order not found in positions: " + order.id)
                    continue
                position = self.open_positions[posId]
                if position is not None:
                    orderType = self.order_type_from_order_id(order.id)
                    if orderType == OrderType.ENTRY and position.status in [PositionStatus.PENDING,
                                                                            PositionStatus.TRIGGERED]:
                        self.logger.warn(
                            "order executed, but position not updated yet, are executions not implemented? " + order.id + " for position " + str(
                                position))
                        self.on_execution(order.id, order.executed_amount, order.executed_price, order.execution_tstamp)
                    elif orderType in [OrderType.SL, OrderType.TP] and position.status == PositionStatus.OPEN:
                        self.logger.warn(
                            "order executed, but position not updated yet, are executions not implemented? " + order.id + " for position " + str(
                                position))
                        self.on_execution(order.id, order.executed_amount, order.executed_price, order.execution_tstamp)
                    else:
                        self.logger.info(
                            "don't know what to do with execution of " + order.id + ". probably a multiple entry for position " + str(
                                position))
                else:
                    self.logger.warn("no position found on execution of " + order.id)

        self.known_order_history = len(account.order_history)
        self.sync_positions_with_open_orders(bars, account)

    def got_data_for_position_sync(self, bars: List[Bar]):
        raise NotImplementedError

    def get_stop_for_unmatched_amount(self, amount: float, bars: List[Bar]):
        return None

    def sync_positions_with_open_orders(self, bars: List[Bar], account: Account):
        open_pos = 0
        for pos in self.open_positions.values():
            if pos.status == PositionStatus.OPEN:
                open_pos += pos.current_open_amount

        if not self.got_data_for_position_sync(bars):
            self.logger.warn("got no initial data, can't sync positions")
            self.unaccounted_position_cool_off = 0
            return

        remaining_pos_ids = []
        remaining_pos_ids += self.open_positions.keys()
        remaining_orders = []
        remaining_orders += account.open_orders

        # first check if there even is a diparity (positions without stops, or orders without position)
        for order in account.open_orders:
            if not order.active:
                remaining_orders.remove(order)
                continue  # got cancelled during run
            [posId, orderType] = self.position_id_and_type_from_order_id(order.id)
            if orderType is None:
                remaining_orders.remove(order)
                continue  # none of ours
            if posId in self.open_positions.keys():
                pos = self.open_positions[posId]
                remaining_orders.remove(order)
                if posId in remaining_pos_ids:
                    if (orderType == OrderType.SL and pos.status == PositionStatus.OPEN) \
                            or (orderType == OrderType.ENTRY and pos.status in [PositionStatus.PENDING,
                                                                                PositionStatus.TRIGGERED]):
                        # only remove from remaining if its open with SL or pending with entry. every position needs
                        # a stoploss!
                        remaining_pos_ids.remove(posId)

        for pos in self.open_positions.values():
            self.check_open_orders_in_position(pos)

        if len(remaining_orders) == 0 and len(remaining_pos_ids) == 0 and abs(
                open_pos - account.open_position.quantity) < self.symbol.lotSize / 10:
            self.unaccounted_position_cool_off = 0
            return

        self.logger.info("Has to start order/pos sync with bot vs acc: %.3f vs. %.3f and %i vs %i, remaining: %i,  %i"
                         % (
                             open_pos, account.open_position.quantity, len(self.open_positions),
                             len(account.open_orders),
                             len(remaining_orders), len(remaining_pos_ids)))

        remainingPosition = account.open_position.quantity
        for pos in self.open_positions.values():
            if pos.status == PositionStatus.OPEN:
                remainingPosition -= pos.current_open_amount

        waiting_tps = []

        # now remaining orders and remaining positions contain the not matched ones
        for order in remaining_orders:
            orderType = self.order_type_from_order_id(order.id)
            posId = self.position_id_from_order_id(order.id)
            if not order.active:  # already canceled or executed
                continue

            if orderType == OrderType.ENTRY:
                # add position for unkown order
                stop = self.get_stop_for_unmatched_amount(order.amount, bars)
                if stop is not None:
                    newPos = Position(id=posId,
                                      entry=order.limit_price if order.limit_price is not None else order.stop_price,
                                      amount=order.amount,
                                      stop=stop,
                                      tstamp=bars[0].tstamp)
                    newPos.status = PositionStatus.PENDING if not order.stop_triggered else PositionStatus.TRIGGERED
                    self.open_positions[posId] = newPos
                    self.logger.warn("found unknown entry %s %.1f @ %.1f, added position"
                                     % (order.id, order.amount,
                                        order.stop_price if order.stop_price is not None else order.limit_price))
                else:
                    self.logger.warn(
                        "found unknown entry %s %.1f @ %.1f, but don't know what stop to use -> canceling"
                        % (order.id, order.amount,
                           order.stop_price if order.stop_price is not None else order.limit_price))
                    self.order_interface.cancel_order(order)

            elif orderType == OrderType.SL and remainingPosition * order.amount < 0 and abs(
                    round(remainingPosition, self.symbol.quantityPrecision)) > abs(
                order.amount):
                # only assume open position for the waiting SL with the remainingPosition also indicates it, 
                # otherwise it might be a pending cancel (from executed TP) or already executed
                newPos = Position(id=posId, entry=None, amount=-order.amount,
                                  stop=order.stop_price, tstamp=bars[0].tstamp)
                newPos.status = PositionStatus.OPEN
                remainingPosition -= newPos.amount
                self.open_positions[posId] = newPos
                self.logger.warn("found unknown exit %s %.1f @ %.1f, opened position for it" % (
                    order.id, order.amount,
                    order.stop_price if order.stop_price is not None else order.limit_price))
            else:
                waiting_tps.append(order)

        # cancel orphaned TPs
        for order in waiting_tps:
            orderType = self.order_type_from_order_id(order.id)
            posId = self.position_id_from_order_id(order.id)
            if posId not in self.open_positions.keys():  # still not in (might have been added in previous for)
                self.logger.warn(
                    "didn't find matching position for order %s %.1f @ %.1f -> canceling"
                    % (order.id, order.amount,
                       order.stop_price if order.stop_price is not None else order.limit_price))
                self.order_interface.cancel_order(order)

        self.logger.info("found " + str(len(self.open_positions)) + " existing positions on sync")

        # positions with no exit in the market
        for posId in remaining_pos_ids:
            pos = self.open_positions[posId]
            if pos.status == PositionStatus.PENDING or pos.status == PositionStatus.TRIGGERED:
                # should have the opening order in the system, but doesn't
                # not sure why: in doubt: not create wrong orders
                if remainingPosition * pos.amount > 0 and abs(
                        round(remainingPosition, self.symbol.quantityPrecision)) >= abs(pos.amount):
                    # assume position was opened without us realizing (during downtime)
                    self.logger.warn(
                        "pending position with no entry order but open position looks like it was opened: %s" % (posId))
                    pos.last_filled_entry = pos.wanted_entry
                    pos.entry_tstamp = time.time()
                    pos.max_filled_amount += pos.amount
                    pos.current_open_amount = pos.amount
                    self.handle_opened_or_changed_position(position=pos, bars=bars, account=account)
                    remainingPosition -= pos.amount
                else:
                    self.logger.warn(
                        "pending position with no entry order and no sign of opening -> close missed: %s" % (posId))
                    pos.status = PositionStatus.MISSED
                    self.position_closed(pos, account)
            elif pos.status == PositionStatus.OPEN:
                if pos.changed:
                    self.logger.info(f"pos has no exit, but is marked changed, so its probably just a race {pos}")
                    continue
                if pos.initial_stop is not None:
                    # for some reason we are missing the stop in the market
                    self.logger.warn(
                        "found position with no stop in market. added stop for it: %s with %.1f contracts" % (
                            posId, pos.current_open_amount))
                    self.order_interface.send_order(
                        Order(orderId=self.generate_order_id(posId, OrderType.SL), amount=-pos.current_open_amount,
                              stop=pos.initial_stop))
                else:
                    self.logger.warn(
                        "found position with no stop in market. %s with %.1f contracts. but no initial stop on position had to close" % (
                            posId, pos.current_open_amount))
                    self.order_interface.send_order(
                        Order(orderId=self.generate_order_id(posId, OrderType.SL), amount=-pos.current_open_amount))
            else:
                self.logger.warn(
                    "pending position with noconnected order not pending or open? closed: %s" % (posId))
                self.position_closed(pos, account)

        remainingPosition = round(remainingPosition, self.symbol.quantityPrecision)
        # now there should not be any mismatch between positions and orders.
        if remainingPosition != 0:
            if self.unaccounted_position_cool_off > 1:
                unmatched_stop = self.get_stop_for_unmatched_amount(remainingPosition, bars)
                signalId = str(bars[1].tstamp) + '+' + str(randint(0, 99))
                if unmatched_stop is not None:
                    posId = self.full_pos_id(signalId,
                                             PositionDirection.LONG if remainingPosition > 0 else PositionDirection.SHORT)
                    newPos = Position(id=posId, entry=None, amount=remainingPosition,
                                      stop=unmatched_stop, tstamp=bars[0].tstamp)
                    newPos.status = PositionStatus.OPEN
                    self.open_positions[posId] = newPos
                    # add stop
                    self.logger.info(
                        "couldn't account for " + str(
                            newPos.current_open_amount) + " open contracts. Adding position with stop for it")
                    self.order_interface.send_order(Order(orderId=self.generate_order_id(posId, OrderType.SL),
                                                          stop=newPos.initial_stop, amount=-newPos.current_open_amount))
                elif account.open_position.quantity * remainingPosition > 0:
                    self.logger.info(
                        "couldn't account for " + str(remainingPosition) + " open contracts. Market close")
                    self.order_interface.send_order(Order(orderId=signalId + "_marketClose", amount=-remainingPosition))
                else:
                    self.logger.info(
                        "couldn't account for " + str(
                            remainingPosition) + " open contracts. But close would increase exposure-> mark positions as closed")

                    for pos in self.open_positions.values():
                        if pos.status == PositionStatus.OPEN and abs(
                                remainingPosition + pos.current_open_amount) < self.symbol.lotSize:
                            self.logger.info(f"marked position {pos.id} with exact size as closed ")
                            self.position_closed(pos, account)
                            remainingPosition += pos.current_open_amount
                            break

                    if abs(remainingPosition) >= self.symbol.lotSize:
                        # close orders until size closed
                        # TODO: sort by size, close until position flips side
                        pos_to_close = []
                        for pos in self.open_positions.values():
                            if pos.status == PositionStatus.OPEN and pos.current_open_amount * remainingPosition < 0:
                                # rough sorting to have the smallest first
                                if len(pos_to_close) > 0 and abs(pos.current_open_amount) <= abs(
                                        pos_to_close[0].current_open_amount):
                                    pos_to_close.insert(0, pos)
                                else:
                                    pos_to_close.append(pos)
                        direction = 1 if remainingPosition > 0 else -1
                        for pos in pos_to_close:
                            if direction * remainingPosition <= 0 or abs(remainingPosition) < self.symbol.lotSize:
                                break
                            self.logger.info(f"marked position {pos.id} as closed ")
                            remainingPosition += pos.current_open_amount
                            self.position_closed(pos, account)


            else:
                self.logger.info(
                    "couldn't account for " + str(
                        remainingPosition) + " open contracts. cooling off, hoping it's a glitch")
                self.unaccounted_position_cool_off += 1
        else:
            self.unaccounted_position_cool_off = 0

    #####################################################

    def save_open_positions(self, bars: List[Bar]):
        if self.unique_id is None:
            return
        base = 'openPositions/'
        try:
            os.makedirs(base)
        except Exception:
            pass

        try:
            pos_json = []
            for pos in self.open_positions:
                pos_json.append(self.open_positions[pos].to_json())
            moduleData = {}
            for idx in range(5):
                moduleData[bars[idx].tstamp] = ExitModule.get_data_for_json(bars[idx])

            data = {"last_time": self.last_time,
                    "last_tick_tstamp": self.last_tick_time.timestamp(),
                    "last_tick": str(self.last_tick_time),
                    "positions": pos_json,
                    "moduleData": moduleData,
                    "risk_reference": self.risk_reference,
                    "max_equity": self.max_equity,
                    "time_of_max_equity": self.time_of_max_equity}
            string = json.dumps(data, sort_keys=False, indent=4)
            with open(base + self._get_pos_file(), 'w') as file:
                file.write(string)
            # backup if no error happened: this is need to have a backup of the status
            # for manual intervention when something breaks massivly
            with open(base + self._get_pos_file(self.open_position_rolling), 'w') as file:
                file.write(string)
            self.open_position_rolling += 1
            if self.open_position_rolling > 3:
                self.open_position_rolling = 1
        except Exception as e:
            self.logger.error("Error saving positions " + str(e))
            raise e

    def fill_openpositions(self, data, bars: List[Bar]):
        self.last_time = data["last_time"]
        if "last_tick_tstamp" in data:
            self.last_tick_time = datetime.fromtimestamp(data["last_tick_tstamp"])
        if "max_equity" in data.keys():
            self.max_equity = data["max_equity"]
            self.time_of_max_equity = data["time_of_max_equity"]
        for pos_json in data["positions"]:
            pos: Position = Position.from_json(pos_json)
            self.open_positions[pos.id] = pos
        if "moduleData" in data.keys():
            for idx in range(5):
                if str(bars[idx].tstamp) in data["moduleData"].keys():
                    moduleData = data['moduleData'][str(bars[idx].tstamp)]
                    ExitModule.set_data_from_json(bars[idx], moduleData)

    def read_position_backup(self, bars: List[Bar]):
        self.logger.warn("trying backups")
        if self.unique_id is not None:
            base = 'openPositions/'
            try:
                os.makedirs(base)
            except Exception:
                pass
            success = False
            for idx in range(10):
                try:
                    with open(base + self._get_pos_file(idx), 'r') as file:
                        data = json.load(file)
                        if self.last_tick_time is None or \
                                self.last_tick_time.timestamp() < data["last_tick_tstamp"]:
                            self.fill_openpositions(data, bars)
                            success = True
                except Exception as e:
                    pass
            if success:
                self.logger.info("done loading " + str(
                    len(self.open_positions)) + " positions from " + self._get_pos_file() + " last time " + str(
                    self.last_time))

    def read_open_positions(self, bars: List[Bar]):
        if self.unique_id is not None:
            base = 'openPositions/'
            try:
                os.makedirs(base)
            except Exception:
                pass
            try:
                with open(base + self._get_pos_file(), 'r') as file:
                    data = json.load(file)
                    self.fill_openpositions(data, bars)
                    self.logger.info("done loading " + str(
                        len(self.open_positions)) + " positions from " + self._get_pos_file() + " last time " + str(
                        self.last_time))
            except Exception as e:
                self.logger.warn("Error loading open positions: " + str(e))
                self.open_positions = {}
                self.read_position_backup(bars)
            if self.last_tick_time is None:
                self.read_position_backup(bars)

    def cancel_all_orders_for_position(self, positionId, account: Account):
        to_cancel = []
        for order in account.open_orders:
            if self.position_id_from_order_id(order.id) == positionId:
                to_cancel.append(order)

        for o in to_cancel:
            self.order_interface.cancel_order(o)

    def position_closed(self, position: Position, account: Account):
        if position.exit_tstamp == 0:
            position.exit_tstamp = time.time()
        position.exit_equity = account.equity
        self.position_history.append(position)
        del self.open_positions[position.id]

        # cancel other open orders of this position (sl/tp etc)
        self.logger.info("canceling remaining orders for position: " + position.id)
        self.cancel_all_orders_for_position(position.id, account)

        if self.unique_id is None:
            return
        base = 'positionHistory/'
        filename = base + self._get_pos_file()
        size = 0
        try:
            os.makedirs(base)
        except Exception:
            pass
        try:
            size = os.path.getsize(filename)
        except Exception:
            pass
        with open(filename, 'a') as file:
            writer = csv.writer(file)
            if size == 0:
                csv_columns = ['signalTStamp', 'size', 'wantedEntry', 'initialStop', 'openTime', 'openPrice',
                               'closeTime',
                               'closePrice', 'equityOnExit']
                writer.writerow(csv_columns)
            writer.writerow([
                datetime.fromtimestamp(position.signal_tstamp).isoformat(),
                position.amount,
                position.wanted_entry,
                position.initial_stop,
                datetime.fromtimestamp(position.entry_tstamp).isoformat(),
                position.filled_entry,
                datetime.fromtimestamp(position.exit_tstamp).isoformat(),
                position.filled_exit,
                position.exit_equity
            ])

    def on_tick(self, bars: List[Bar], account: Account):
        """checks price and levels to manage current orders and set new ones"""
        if bars[0].last_tick_tstamp is not None and bars[0].last_tick_tstamp > 0:
            self.last_tick_time = datetime.fromtimestamp(bars[0].last_tick_tstamp)
        else:
            self.last_tick_time = bars[0].tstamp

        self.update_new_bar(bars)
        if account.equity > self.max_equity:
            self.max_equity = account.equity
            self.time_of_max_equity = time.time()
        self.prep_bars(bars)
        try:
            self.manage_open_orders(bars, account)
            self.open_orders(bars, account)
            self.consolidate_open_positions(bars, account)
        except Exception as e:
            self.save_open_positions(bars)
            raise e
        self.save_open_positions(bars)

    def prep_bars(self, bars: List[Bar]):
        pass

    ###
    # Order Management
    ###

    def manage_open_orders(self, bars: list, account: Account):
        pass

    def open_orders(self, bars: list, account: Account):
        pass

    def consolidate_open_positions(self, bars: list, account: Account):
        pass

    def update_new_bar(self, bars: List[Bar]):
        """checks if this tick started a new bar.
        only works on the first call of a bar"""
        if bars[0].tstamp != self.last_time:
            self.last_time = bars[0].tstamp
            self.is_new_bar = True
        else:
            self.is_new_bar = False

    ####
    # additional stuff
    ###

    def create_performance_plot(self, bars: List[Bar]):
        self.logger.info("preparing stats")
        if len(self.position_history) == 0:
            self.logger.info("no positions done.")
            return go.Figure()
        stats = {
            "dd": 0,
            "maxDD": 0,
            "hh": 1,
            "underwaterDays": 0,
            "percWin": 0,
            "avgResult": 0,
            "tradesInRange": 0,
            "maxWinner": 0,
            "maxLoser": 0
        }

        yaxis = {
            "equity": 'y1',
            "dd": 'y2',
            "maxDD": 'y2',
            "hh": 'y1',
            "underwaterDays": 'y5',
            "tradesInRange": 'y6',
            "percWin": 'y7',
            "avgResult": 'y4',
            "maxWinner": 'y4',
            "maxLoser": 'y4'
        }

        months_in_range = 1
        alpha = 0.3
        firstPos = self.position_history[0]
        if firstPos.status != PositionStatus.CLOSED:
            for pos in self.position_history:
                if pos.status == PositionStatus.CLOSED:
                    firstPos = pos
                    break
        lastHHTstamp = firstPos.signal_tstamp
        if firstPos.filled_exit is not None:
            startEquity = firstPos.exit_equity - firstPos.amount * (
                    1 / firstPos.filled_entry - 1 / firstPos.filled_exit)
        else:
            startEquity = 100
        #startEquity = 100

        stats_range = []
        # temporarily add filled exit to have position in the result
        for pos in self.position_history:
            if pos.status == PositionStatus.OPEN:
                pos.filled_exit = bars[0].close

        actual_history = list(
            filter(lambda p1: p1.filled_entry is not None and p1.filled_exit is not None, self.position_history))
        actual_history.sort(reverse=False, key=lambda p: p.exit_tstamp)
        for pos in actual_history:
            # update range
            stats_range.append(pos)
            range_start = pos.exit_tstamp - months_in_range * 30 * 60 * 60 * 60
            while stats_range[0].exit_tstamp < range_start:
                stats_range.pop(0)

            avg = 0.0
            stats['tradesInRange'] = alpha * len(stats_range) + stats['tradesInRange'] * (1 - alpha)
            winners = 0.0
            maxWinner = 0
            maxLoser = 0
            for p in stats_range:
                # BEWARE: assumes inverse swap
                result = p.amount / p.filled_entry - p.amount / p.filled_exit
                maxLoser = min(result, maxLoser)
                maxWinner = max(result, maxWinner)
                avg += result / len(stats_range)
                if result > 0:
                    winners += 1.0

            stats['percWin'] = alpha * (100.0 * winners / len(stats_range)) + stats['percWin'] * (1 - alpha)
            stats['avgResult'] = alpha * avg + stats['avgResult'] * (1 - alpha)
            stats['maxWinner'] = alpha * maxWinner + stats['maxWinner'] * (1 - alpha)
            stats['maxLoser'] = alpha * (-maxLoser) + stats['maxLoser'] * (1 - alpha)

            if stats['hh'] < pos.exit_equity:
                stats['hh'] = pos.exit_equity
                lastHHTstamp = pos.exit_tstamp

            stats['underwaterDays'] = (pos.exit_tstamp - lastHHTstamp) / (60 * 60 * 24)
            dd = stats['hh'] - pos.exit_equity
            if dd > stats['maxDD']:
                stats['maxDD'] = dd
            stats['dd'] = dd
            stats['equity'] = pos.exit_equity

            pos.stats = stats.copy()
            pos.stats['equity'] = pos.exit_equity - startEquity
            pos.stats['hh'] = pos.stats['hh'] - startEquity

        self.logger.info("creating equityline")
        time = list(map(lambda p1: datetime.fromtimestamp(p1.exit_tstamp), actual_history))

        # undo temporarily filled exit
        for pos in self.position_history:
            if pos.status == PositionStatus.OPEN:
                pos.filled_exit = None

        data = []
        for key in yaxis.keys():
            sub_data = list(map(lambda p1: p1.stats[key], actual_history))
            data.append(
                go.Scatter(x=time, y=sub_data, mode='lines', yaxis=yaxis[key], name=key + ":" + "%.1f" % (stats[key])))

        layout = go.Layout(
            xaxis=dict(
                anchor='y5'
            ),
            yaxis=dict(
                domain=[0.4, 1]
            ),
            yaxis2=dict(
                domain=[0.4, 1],
                range=[0, 2 * stats['maxDD']],
                overlaying='y',
                side='right'
            ),
            yaxis3=dict(
                domain=[0.2, 0.39]
            ),
            yaxis4=dict(
                domain=[0.2, 0.39],
                overlaying='y3',
                side='right'
            ),
            yaxis5=dict(
                domain=[0, 0.19]
            ),
            yaxis6=dict(
                domain=[0, 0.19],
                overlaying='y5',
                side='right'
            ),
            yaxis7=dict(
                domain=[0, 0.19],
                range=[0, 100],
                overlaying='y5',
                side='right'
            )
        )

        fig = go.Figure(data=data, layout=layout)
        fig.update_layout(xaxis_rangeslider_visible=False)
        return fig

    def add_to_plot(self, fig, bars, time):
        self.logger.info("adding trades")
        # trades

        for pos in self.open_positions.values():
            if pos.status == PositionStatus.OPEN:
                fig.add_shape(go.layout.Shape(
                    type="line",
                    x0=datetime.fromtimestamp(pos.entry_tstamp),
                    y0=pos.filled_entry,
                    x1=datetime.fromtimestamp(bars[0].tstamp),
                    y1=bars[0].close,
                    line=dict(
                        color="Green" if pos.amount > 0 else "Red",
                        width=2,
                        dash="dash"
                    )
                ))

        for pos in self.position_history:
            if pos.status == PositionStatus.CLOSED:
                fig.add_shape(go.layout.Shape(
                    type="line",
                    x0=datetime.fromtimestamp(pos.entry_tstamp),
                    y0=pos.filled_entry,
                    x1=datetime.fromtimestamp(pos.exit_tstamp),
                    y1=pos.filled_exit,
                    line=dict(
                        color="Green" if pos.amount > 0 else "Red",
                        width=2,
                        dash="solid"
                    )
                ))

            if pos.status == PositionStatus.MISSED:
                fig.add_shape(go.layout.Shape(
                    type="line",
                    x0=datetime.fromtimestamp(pos.signal_tstamp),
                    y0=pos.wanted_entry,
                    x1=datetime.fromtimestamp(pos.exit_tstamp),
                    y1=pos.wanted_entry,
                    line=dict(
                        color="Blue",
                        width=1,
                        dash="dot"
                    )
                ))

        fig.update_shapes(dict(xref='x', yref='y'))
