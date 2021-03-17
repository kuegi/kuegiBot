import math
from functools import reduce
from random import randint

import plotly.graph_objects as go
from kuegi_bot.bots.trading_bot import TradingBot
from kuegi_bot.utils.trading_classes import Position, Account, Bar, Symbol
from kuegi_bot.utils.telegram import TelegramBot
from typing import List


class Strategy:
    def __init__(self):
        self.logger = None
        self.order_interface = None
        self.symbol = None
        self.risk_factor = 1
        self.risk_type = 0  # 0= all equal, 1= 1 atr eq 1 R
        self.atr_factor_risk = 1
        self.max_risk_mul = 1
        self.telegram: TelegramBot = None

    def myId(self):
        return "gen"

    def get_signal_id(self, bars: List[Bar], sigId=None):
        delta = bars[0].tstamp - bars[1].tstamp

        timepart = f"{self.symbol.symbol}.{int((bars[0].tstamp / delta) % 0xFFF):0>3x}.{randint(0, 0xFFF):0>3x}"
        if sigId is None:
            sigId = self.myId()
        return sigId + "+" + timepart

    def prepare(self, logger, order_interface):
        self.logger = logger
        self.order_interface = order_interface

    def init(self, bars: List[Bar], account: Account, symbol: Symbol):
        self.symbol = symbol

    def min_bars_needed(self) -> int:
        return 5

    def owns_signal_id(self, signalId: str):
        return signalId.startswith(self.myId() + "+")

    def got_data_for_position_sync(self, bars: List[Bar]) -> bool:
        raise NotImplementedError

    def get_stop_for_unmatched_amount(self, amount: float, bars: List[Bar]):
        return None

    def prep_bars(self, is_new_bar: bool, bars: list):
        pass

    def position_got_opened_or_changed(self, position: Position, bars: List[Bar], account: Account, open_positions):
        pass

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        pass

    def manage_open_position(self, p, bars, account, pos_ids_to_cancel):
        pass

    def open_orders(self, is_new_bar, directionFilter, bars, account, open_positions: dict):
        pass

    def add_to_plot(self, fig: go.Figure, bars: List[Bar], time):
        pass

    def with_telegram(self, telegram: TelegramBot):
        self.telegram = telegram

    def withRM(self, risk_factor: float = 0.01, max_risk_mul: float = 2, risk_type: int = 0, atr_factor: float = 1):
        self.risk_factor = risk_factor
        self.risk_type = risk_type  # 0= all equal, 1= 1 atr eq 1 R
        self.max_risk_mul = max_risk_mul
        self.atr_factor_risk = atr_factor
        return self

    def calc_pos_size(self, risk, entry, exitPrice, atr: float = 0):
        if self.risk_type <= 2:
            delta = entry - exitPrice
            if self.risk_type == 1:
                # use atr as delta reference, but max X the actual delta. so risk is never more than X times the
                # wanted risk
                delta = math.copysign(max(abs(delta) / self.max_risk_mul, atr * self.atr_factor_risk), delta)

            if not self.symbol.isInverse:
                size = risk / delta
            else:
                size = -risk / (1 / entry - 1 / (entry - delta))
            size = self.symbol.normalizeSize(size)
            return size


class MultiStrategyBot(TradingBot):

    def __init__(self, logger=None, directionFilter=0):
        super().__init__(logger, directionFilter)
        self.myId = "MultiStrategy"
        self.strategies: List[Strategy] = []

    def add_strategy(self, strategy: Strategy):
        self.strategies.append(strategy)

    def prepare(self, logger, order_interface):
        super().prepare(logger, order_interface)
        for strat in self.strategies:
            strat.prepare(logger, order_interface)

    def init(self, bars: List[Bar], account: Account, symbol: Symbol, unique_id: str = ""):
        self.logger.info(
            "init with strategies: %s" % reduce((lambda result, strategy: result + ", " + strategy.myId()),
                                                self.strategies,
                                                ""))
        for strat in self.strategies:
            strat.init(bars, account, symbol)
        super().init(bars=bars, account=account, symbol=symbol, unique_id=unique_id)

    def min_bars_needed(self):
        return reduce(lambda x, y: max(x, y.min_bars_needed()), self.strategies, 5)

    def prep_bars(self, bars: list):
        newbar = self.is_new_bar
        if not self.got_data_for_position_sync(bars):
            newbar = True
        for strategy in self.strategies:
            strategy.prep_bars(newbar, bars)

    def got_data_for_position_sync(self, bars: List[Bar]):
        return reduce((lambda x, y: x and y.got_data_for_position_sync(bars)), self.strategies, True)

    def position_got_opened_or_changed(self, position: Position, bars: List[Bar], account: Account):
        [signalId, direction] = self.split_pos_Id(position.id)
        for strat in self.strategies:
            if strat.owns_signal_id(signalId):
                self.call_with_open_positions_for_strat(strat, lambda open_pos:
                strat.position_got_opened_or_changed(position, bars,
                                                     account, open_pos))
                break

    def get_stop_for_unmatched_amount(self, amount: float, bars: List[Bar]):
        if len(self.strategies) == 1:
            return self.strategies[0].get_stop_for_unmatched_amount(amount, bars)
        return None

    def call_with_open_positions_for_strat(self, strat, call):
        open_pos = {}
        pos_ids = set()
        for pos in self.open_positions.values():
            [signalId, direction] = self.split_pos_Id(pos.id)
            if strat.owns_signal_id(signalId):
                open_pos[pos.id] = pos
                pos_ids.add(pos.id)
        call(open_pos)
        for pos in open_pos.values():
            if pos.id in pos_ids:
                pos_ids.remove(pos.id)
            self.open_positions[pos.id] = pos
        for canceled_id in pos_ids:
            del self.open_positions[canceled_id]

    def manage_open_orders(self, bars: List[Bar], account: Account):
        self.sync_executions(bars, account)

        to_cancel = []
        to_update = []
        for order in account.open_orders:
            posId = self.position_id_from_order_id(order.id)
            if posId is None or posId not in self.open_positions.keys():
                continue
            [signalId, direction] = self.split_pos_Id(posId)
            for strat in self.strategies:
                if strat.owns_signal_id(signalId):
                    self.call_with_open_positions_for_strat(strat, lambda open_pos:
                    strat.manage_open_order(order,
                                            self.open_positions[posId],
                                            bars, to_update, to_cancel,
                                            open_pos))
                    break

        for order in to_cancel:
            self.order_interface.cancel_order(order)

        for order in to_update:
            self.order_interface.update_order(order)

        pos_ids_to_cancel = []
        for p in self.open_positions.values():
            [signalId, direction] = self.split_pos_Id(p.id)
            for strat in self.strategies:
                if strat.owns_signal_id(signalId):
                    strat.manage_open_position(p, bars, account, pos_ids_to_cancel)
                    break

        for posId in pos_ids_to_cancel:
            self.cancel_all_orders_for_position(posId, account)
            del self.open_positions[posId]

    def open_orders(self, bars: List[Bar], account: Account):
        for strat in self.strategies:
            self.call_with_open_positions_for_strat(strat, lambda open_pos:
            strat.open_orders(self.is_new_bar,
                              self.directionFilter, bars, account, open_pos))

    def add_to_plot(self, fig: go.Figure, bars: List[Bar], time):
        super().add_to_plot(fig, bars, time)
        for strat in self.strategies:
            strat.add_to_plot(fig, bars, time)
