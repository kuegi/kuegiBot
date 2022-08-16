from typing import List

from kuegi_bot.bots.strategies.channel_strat import ChannelStrategy
from kuegi_bot.bots.trading_bot import TradingBot, PositionDirection
from kuegi_bot.indicators.kuegi_channel import Data, clean_range
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType, Position, Order, PositionStatus
from kuegi_bot.indicators.indicator import Indicator
from kuegi_bot.indicators.TAlib import TA
import talib
from talib import RSI
from datetime import datetime


class DegenStrategy(ChannelStrategy):

    def __init__(self, rsiPeriod: int = 20, trail_short_fac: float = 1, trail_long_fac: float = 1, atr_period: int = 7, extreme_period: int = 7,
                 entry_long_fac: float = 1, entry_short_fac: float = 1,
                 periodStoch: int = 10, fastMACD: int =7, slowMACD: int =15, signal_period: int = 10, rsi_high_limit: int = 15,
                 rsi_low_limit: int = 25, fastK_lim: int = 25, trail_past: int = 1,
                 close_on_opposite: bool = False, bars_till_cancel_triggered: int = 20, cancel_on_filter:bool = False, tp_fac: float = 0):
        super().__init__()
        self.minBars = max(rsiPeriod, extreme_period)
        self.ta = TA()
        self.degen = DegenIndicator(rsiPeriod, periodStoch, fastMACD, slowMACD, signal_period, rsi_high_limit, rsi_low_limit, fastK_lim)
        self.trail_short_fac = trail_short_fac
        self.trail_long_fac = trail_long_fac
        self.atr_period = atr_period
        self.extreme_period = extreme_period
        self.entry_long_fac = max(min(entry_long_fac, 0.95), -0.5)
        self.entry_short_fac = max(min(entry_short_fac, 0.95), -0.5)
        self.trail_past = trail_past
        self.close_on_opposite = close_on_opposite
        self.bars_till_cancel_triggered = bars_till_cancel_triggered
        self.cancel_on_filter = cancel_on_filter
        self.tp_fac = tp_fac

    def init(self, bars: List[Bar], account: Account, symbol: Symbol):
        super().init(bars, account, symbol)
        self.logger.info("Init with %i %.1f %.1f %i %i %.1f %.1f %i %s %i %s" %
                         (self.minBars, self.trail_short_fac, self.trail_long_fac, self.atr_period, self.extreme_period,
                          self.entry_long_fac, self.entry_short_fac, self.trail_past, self.close_on_opposite,
                          self.bars_till_cancel_triggered, self.cancel_on_filter))

    def myId(self):
        return "degen"

    def owns_signal_id(self, signalId: str):
        return signalId.startswith("degen+")

    def min_bars_needed(self) -> int:
        return self.minBars

    def prep_bars(self, is_new_bar: bool, bars: list):
        if is_new_bar:
            self.channel.on_tick(bars)
            self.ta.on_tick(bars)
            self.degen.on_tick(self.ta)

    def open_orders(self, is_new_bar, directionFilter, bars, account, open_positions, all_open_pos: dict):
        if (not is_new_bar) or len(bars) < self.min_bars_needed():
            return  # only open orders on beginning of bar

        if not self.entries_allowed(bars):
            self.logger.info(" no entries allowed")
            return

        channel: Data = self.channel.get_data(bars[self.trail_past])
        if channel is None:
            return

        longEntry, shortEntry, stopLong, stopShort = self.calc_stoplosses(channel, bars)

        self.logger.info("---- analyzing ---- Time: %s, goLong: %s, goShort: %s " %
                         (str(datetime.fromtimestamp(bars[0].tstamp)), str(self.degen.degenData.goLong), str(self.degen.degenData.goShort)))

        # LONG
        if self.degen.degenData.goLong:
            self.__open_position(PositionDirection.LONG, bars, stopLong,open_positions,all_open_pos, longEntry)  # to the moon

        # SHORT
        if self.degen.degenData.goShort:
            self.__open_position(PositionDirection.SHORT, bars, stopShort,open_positions,all_open_pos, shortEntry) # short the ponzi

    def __open_position(self, direction, bars, stop, open_positions, all_open_pos, entry):
        # SL && TP
        directionFactor = 1
        oppDirection = PositionDirection.SHORT
        if direction == PositionDirection.SHORT:
            directionFactor = -1
            oppDirection = PositionDirection.LONG
        oppDirectionFactor = directionFactor * -1

        expectedEntrySplipagePerc = 0.0015
        expectedExitSlipagePerc = 0.0015
        signalId = self.get_signal_id(bars)
        posId = TradingBot.full_pos_id(signalId, direction)
        amount = self.calc_pos_size(risk=self.risk_factor,
                                    exitPrice=stop * (1 + oppDirectionFactor * expectedExitSlipagePerc),
                                    entry=entry * (1 + directionFactor * expectedEntrySplipagePerc))
        pos = Position(id=posId, entry=entry, amount=amount, stop=stop, tstamp=bars[0].tstamp)
        open_positions[posId] = pos   # need to add to the bots open pos too, so the execution of the market is not missed

        self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(posId, OrderType.ENTRY),
                                              amount=amount, stop=entry, limit=entry))

        if self.close_on_opposite:
            for pos in open_positions.values():
                if pos.status == PositionStatus.OPEN and \
                        TradingBot.split_pos_Id(pos.id)[1] == oppDirection:
                    # execution will trigger close and cancel of other orders
                    self.order_interface.send_order(
                        Order(orderId=TradingBot.generate_order_id(pos.id, OrderType.SL),
                              amount=-pos.amount, stop=None, limit=None))

    def calc_stoplosses(self, channel, bars):
        trail_range_short = min(self.trail_short_fac * (channel.shortTrail - channel.longTrail), 0.3 * bars[0].open)
        trail_range_long = self.trail_long_fac * (channel.shortTrail - channel.longTrail)

        longEntry, shortEntry = self.calc_extreme(bars, self.extreme_period)

        longEntry = longEntry - self.entry_long_fac * trail_range_long
        shortEntry = shortEntry + self.entry_short_fac * trail_range_short

        longSL = longEntry - trail_range_long
        shortSL = shortEntry + trail_range_short

        return longEntry, shortEntry, longSL, shortSL

    def calc_extreme(self, bars, period):
        lowest = bars[0].low
        highest = bars[0].high
        idx = 1
        while idx <= period:
            if bars[idx].low<lowest:
                lowest = bars[idx].low
            if bars[idx].high>highest:
                highest = bars[idx].high
            idx = idx +1

        return lowest, highest

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        super().manage_open_order(order, position, bars, to_update, to_cancel, open_positions)

        #data: Data = self.channel.get_data(bars[1])
        #if data is None:
        #    return

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

        if orderType == OrderType.ENTRY and (self.cancel_on_filter and not self.entries_allowed(bars)):
            if position.status == PositionStatus.PENDING:  # don't delete if triggered
                self.logger.info("canceling, because entries not allowed: " + position.id)
                to_cancel.append(order)
                del open_positions[position.id]

    def position_got_opened_or_changed(self, position: Position, bars: List[Bar], account: Account, open_positions):
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
            order = Order(orderId=TradingBot.generate_order_id(positionId=position.id,
                                                               type=OrderType.SL),
                          stop=position.initial_stop,
                          amount=-position.amount)
            self.order_interface.send_order(order)
        if self.tp_fac > 0 and not gotTp:
            ref = position.filled_entry - position.initial_stop
            tp = position.filled_entry + ref * self.tp_fac
            order = Order(orderId=TradingBot.generate_order_id(positionId=position.id,
                                                               type=OrderType.TP),
                          limit=tp,
                          amount=-position.amount)
            self.order_interface.send_order(order)

class DegenData:
    def __init__(self):
        self.goLong = False
        self.goShort = False
        self.fastk = []
        self.fastd =[]
        self.macd = []
        self.macdsignal = []
        self.macdhist = []


class DegenIndicator(Indicator):
    ''' Market trend based on SMAs '''

    def __init__(self, rsiPeriod: int = 20, periodStoch: int = 10, fastMACD: int =7, slowMACD: int =15, signal_period: int = 10,
                 rsi_high_limit: int = 50, rsi_low_limit: int = 20, fastK_lim: int = 25):
        super().__init__('DegenIndicator: %i %i %i %i %i %i %i %i'%
                         (rsiPeriod, periodStoch, fastMACD, slowMACD, signal_period, rsi_high_limit,
                          rsi_low_limit, fastK_lim))
        self.degenData = DegenData()
        self.rsiPeriod = rsiPeriod
        self.periodStoch = periodStoch
        self.fastMACD = fastMACD
        self.slowMACD = slowMACD
        self.signal_period = signal_period
        self.rsi_high_limit = rsi_high_limit
        self.rsi_low_limit = rsi_low_limit
        self.fastK_lim = fastK_lim

    def on_tick(self, ta: TA()):
        self.calc_market_trend(ta)

    def calc_market_trend(self, ta: TA()):
        # Stoch RSI
        smoothK = 3
        smoothD = 3
        self.degenData.rsi = RSI(ta.close, self.rsiPeriod)
        self.degenData.fastk, self.degenData.fastd = talib.STOCHRSI(
            ta.close, self.periodStoch, fastk_period=smoothK, fastd_period=smoothD,fastd_matype=0)

        # MACD
        self.degenData.macd, self.degenData.macdsignal, self.degenData.macdhist = \
            talib.MACD(ta.close, fastperiod=self.fastMACD, slowperiod=self.slowMACD, signalperiod=self.signal_period)

        self.degenData.goLong = False
        self.degenData.goShort = False

        if self.degenData.fastk[-1] == self.fastK_lim and self.degenData.rsi[-1] < self.rsi_low_limit:
            self.degenData.goLong = True
        if self.degenData.macd[-1] < self.degenData.macdsignal[-1] and self.degenData.macd[-2] > self.degenData.macdsignal[-2] and \
                self.degenData.rsi[-1] > self.rsi_high_limit:
            self.degenData.goShort = True


    def get_line_names(self):
        return ["MarketTrend",  "slowMA", "midMA", "fastMA", "verfastMA"]

    def get_number_of_lines(self):
        return 1

    def get_line_styles(self):
        return [{"width": 1, "color": "blue"},
                {"width": 1, "color": "red"},
                {"width": 1, "color": "orange"},
                {"width": 1, "color": "yellow"},
                {"width": 1, "color": "cyan"}]

    def get_data_for_plot(self, bar: Bar):
        test = 1
