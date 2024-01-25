import math
from typing import List
import plotly.graph_objects as go

from kuegi_bot.bots.strategies.strat_with_exit_modules import StrategyWithExitModulesAndFilter
from kuegi_bot.bots.trading_bot import TradingBot, PositionDirection
from kuegi_bot.indicators.MeanStd import MeanStd
from kuegi_bot.indicators.indicator import SMA, BarSeries, highest, lowest
from kuegi_bot.indicators.swings import Swings, Data
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType, Position, Order, PositionStatus


class MeanReversion(StrategyWithExitModulesAndFilter):

    def __init__(self, lookback: int = 8, entry_factor: float = 1, tp_factor: float = 0.5, sl_factor: float = 2,
                 closeAfterBars: int= 0):
        super().__init__()
        self.entry_factor= entry_factor
        self.tp_factor= tp_factor
        self.sl_factor= sl_factor
        self.close_after_bars= closeAfterBars
        self.mean = MeanStd(lookback)

    def myId(self):
        return "MeanRev"

    def init(self, bars: List[Bar], account: Account, symbol: Symbol):
        super().init(bars, account, symbol)
        self.logger.info(f"init with {self.mean.period},{self.entry_factor},{self.tp_factor},{self.sl_factor}")
        self.mean.on_tick(bars)

    def min_bars_needed(self) -> int:
        return self.mean.period + 1

    def got_data_for_position_sync(self, bars: List[Bar]) -> bool:
        result = super().got_data_for_position_sync(bars)
        return result and (self.mean.get_data(bars[1]) is not None)

    def prep_bars(self, is_new_bar: bool, bars: list):
        if is_new_bar:
            self.mean.on_tick(bars)

    def owns_signal_id(self, signalId: str):
        return signalId.startswith(self.myId()+"+")

    def manage_open_position(self, position, bars, account, pos_ids_to_cancel):
        if self.close_after_bars >= 0 \
                and position.status == PositionStatus.OPEN \
                and position.entry_tstamp < bars[self.close_after_bars].tstamp:
            self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(positionId=position.id, type=OrderType.SL),
                                       amount=-position.currentOpenAmount))


    def position_got_opened(self, position: Position, bars: List[Bar], account: Account, open_positions):

        gotTP= False
        gotSL= False
        for order in position.connectedOrders:
            type = TradingBot.order_type_from_order_id(order.id)
            if type == OrderType.TP:
                gotTP= True
                amount = self.symbol.normalizeSize(-position.currentOpenAmount+order.executed_amount)
                if abs(order.amount - amount) > self.symbol.lotSize/2:
                    order.amount = amount
                    self.order_interface.update_order(order)
            if type == OrderType.SL:
                gotSL= True
                amount = self.symbol.normalizeSize(-position.currentOpenAmount)
                if abs(order.amount -amount) > self.symbol.lotSize/2:
                    order.amount = amount
                    self.order_interface.update_order(order)

        if not gotTP:
            slDiff = position.wanted_entry - position.initial_stop
            # reverse calc the std at time of signal and use tp factor accordingly
            tp = self.symbol.normalizePrice(position.wanted_entry + slDiff / (self.sl_factor-self.entry_factor) * (self.entry_factor - self.tp_factor),
                                           position.amount > 0)

            self.order_interface.send_order(
                Order(orderId=TradingBot.generate_order_id(position.id, OrderType.TP),
                      amount=-position.currentOpenAmount, trigger=None, limit=tp))
        if not gotSL:
            order= Order(orderId=TradingBot.generate_order_id(positionId=position.id, type=OrderType.SL),
                         trigger=position.initial_stop,
                         amount=-position.currentOpenAmount)
            self.order_interface.send_order(order)
            # added temporarily, cause sync with open orders is in the next loop and otherwise the orders vs
            # position check fails
            if order not in account.open_orders:  # outside world might have already added it
                account.open_orders.append(order)

    def open_new_trades(self, is_new_bar, directionFilter, bars, account, open_positions, all_open_pos: dict):
        if (not is_new_bar) or len(bars) < self.min_bars_needed():
            return  # only open orders on beginning of bar

        if not self.entries_allowed(bars):
            self.logger.info("no entries allowed")
            return

        # include the expected slipage in the risk calculation
        expectedExitSlipagePerc = 0.0015

        data= self.mean.get_data(bars[1])
        # long:
        longEntry= self.symbol.normalizePrice(data.mean - data.std*self.entry_factor,False)
        longStop = self.symbol.normalizePrice(data.mean - data.std*self.sl_factor,True)
        longAmount = self.calc_pos_size(risk=self.risk_factor, exitPrice=longStop * (1 - expectedExitSlipagePerc),
                                    entry=longEntry)

        # short:
        shortEntry= self.symbol.normalizePrice(data.mean + data.std*self.entry_factor,True)
        shortStop = self.symbol.normalizePrice(data.mean + data.std*self.sl_factor,False)
        shortAmount = self.calc_pos_size(risk=self.risk_factor, exitPrice=shortStop * (1 + expectedExitSlipagePerc),
                                    entry=shortEntry)

        gotLong= False
        gotShort= False

        for pos in open_positions.values():
            if pos.amount > 0:
                gotLong= True
                if pos.status == PositionStatus.PENDING:
                    pos.amount= longAmount
                    pos.initialStop= longStop
                    pos.wantedEntry= longEntry
                    for order in pos.connectedOrders:
                        if order.limit_price != longEntry or order.amount != longAmount:
                            order.limit_price= longEntry
                            order.amount= longAmount
                            self.order_interface.update_order(order)
            else:
                gotShort= True
                if pos.status == PositionStatus.PENDING:
                    pos.amount= shortAmount
                    pos.initialStop= shortStop
                    pos.wantedEntry= shortEntry
                    for order in pos.connectedOrders:
                        if order.limit_price != shortEntry or order.amount != shortAmount:
                            order.limit_price= shortEntry
                            order.amount= shortAmount
                            self.order_interface.update_order(order)

        if not gotLong and bars[0].close > longEntry:
            posId=TradingBot.full_pos_id(self.get_signal_id(bars, self.myId()),
                                                                       PositionDirection.LONG)
            open_positions[posId] = Position(id=posId,
                                  entry=longEntry,
                                  amount=longAmount,
                                  stop=longStop,
                                  tstamp=bars[0].tstamp)
            self.order_interface.send_order(
                Order(orderId=TradingBot.generate_order_id(posId, OrderType.ENTRY),
                      amount=longAmount,
                      limit=longEntry))

        if not gotShort and bars[0].close < shortEntry:
            posId=TradingBot.full_pos_id(self.get_signal_id(bars, self.myId()),
                                                                       PositionDirection.SHORT)
            open_positions[posId] = Position(id=posId,
                                  entry=shortEntry,
                                  amount=shortAmount,
                                  stop=shortStop,
                                  tstamp=bars[0].tstamp)
            self.order_interface.send_order(
                Order(orderId=TradingBot.generate_order_id(posId, OrderType.ENTRY),
                      amount=shortAmount,
                      limit=shortEntry))


    def add_to_plot(self, fig: go.Figure, bars: List[Bar], time):
        super().add_to_plot(fig, bars, time)
        styles = self.mean.get_line_styles()

        names = self.mean.get_line_names()
        offset = 0  # we take it with offset 1

        sub_data = list(map(lambda b: self.mean.get_data_for_plot(b)[0], bars))
        fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[0],
                        name=self.mean.id + "_" + names[0])
        sub_data = list(map(lambda b: self.mean.get_data_for_plot(b)[1], bars))
        fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[1],
                        name=self.mean.id + "_" + names[1])
        sub_data = list(map(lambda b: self.mean.get_data_for_plot(b)[2], bars))
        fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[2],
                        name=self.mean.id + "_" + names[2])

    def get_stop_for_unmatched_amount(self, amount: float, bars: List[Bar]):
        # TODO: implement, not needed for sample strat
        pass
