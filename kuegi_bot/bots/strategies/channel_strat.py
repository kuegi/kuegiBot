from typing import List
import math
import plotly.graph_objects as go

from kuegi_bot.bots.strategies.strat_with_exit_modules import StrategyWithExitModulesAndFilter
from kuegi_bot.bots.trading_bot import TradingBot
from kuegi_bot.indicators.kuegi_channel import KuegiChannel, Data
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType


class ChannelStrategy(StrategyWithExitModulesAndFilter):

    def __init__(self):
        super().__init__()
        self.channel: KuegiChannel = None
        self.trail_to_swing = False
        self.delayed_swing_trail = True
        self.trail_back = False
        self.trail_active = False

    def myId(self):
        return "ChannelStrategy"

    def withChannel(self, max_look_back, threshold_factor, buffer_factor, max_dist_factor, max_swing_length):
        self.channel = KuegiChannel(max_look_back, threshold_factor, buffer_factor, max_dist_factor, max_swing_length)
        return self

    def withTrail(self, trail_to_swing: bool = False, delayed_swing: bool = True, trail_back: bool = False):
        self.trail_active = True
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

