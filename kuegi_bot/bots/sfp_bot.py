from datetime import datetime
from typing import List

from kuegi_bot.bots.bot_with_channel import BotWithChannel
from kuegi_bot.bots.trading_bot import PositionDirection
from kuegi_bot.indicators.kuegi_channel import Data, clean_range
from kuegi_bot.utils.trading_classes import Position, Order, Account, Bar, OrderType, PositionStatus


class SfpBot(BotWithChannel):

    def __init__(self, logger=None, directionFilter=0, tp_fac: float = 0, init_stop_type: int = 0,
                 min_wick_fac: float = 0.2, min_swing_length: int = 2,
                 range_length: int = 50, range_filter_fac: float = 0,
                 close_on_opposite: bool = False, entries: int = 0):
        super().__init__(logger, directionFilter)
        self.min_wick_fac = min_wick_fac
        self.min_swing_length = min_swing_length
        self.init_stop_type = init_stop_type
        self.tp_fac = tp_fac
        self.range_length = range_length
        self.range_filter_fac = range_filter_fac
        self.close_on_opposite = close_on_opposite
        self.entries = entries

    def uid(self) -> str:
        return "SFP"

    def position_got_opened(self, position: Position, bars: List[Bar], account: Account):
        pass

    def manage_open_orders(self, bars: List[Bar], account: Account):
        super().manage_open_orders(bars, account)

    def open_orders(self, bars: List[Bar], account: Account):
        if (not self.is_new_bar) or len(bars) < 5:
            return  # only open orders on beginning of bar

        self.logger.info("---- analyzing: %s" %
                         (str(datetime.fromtimestamp(bars[0].tstamp))))

        atr = clean_range(bars, offset=0, length=self.channel.max_look_back * 2)
        risk = self.risk_factor

        # test for SFP:
        # High > HH der letzten X
        # Close < HH der vorigen X
        # ? min Wick size?
        # initial SL

        data: Data = self.channel.get_data(bars[1])
        maxLength = min(len(bars), self.range_length)
        highSupreme = 0
        hhBack = 0
        hh = bars[2].high
        swingHigh = 0
        gotHighSwing = False
        for idx in range(2, maxLength):
            if bars[idx].high < bars[1].high:
                highSupreme = idx - 1
                if hh < bars[idx].high:
                    hh = bars[idx].high
                    hhBack = idx
                elif self.min_swing_length < hhBack <= idx - self.min_swing_length:
                    gotHighSwing = True
                    swingHigh = hh  # confirmed
            else:
                break

        lowSupreme = 0
        llBack = 0
        ll = bars[2].low
        swingLow = 0
        gotLowSwing = False
        for idx in range(2, maxLength):
            if bars[idx].low > bars[1].low:
                lowSupreme = idx - 1
                if ll > bars[idx].low:
                    ll = bars[idx].low
                    llBack = idx
                elif self.min_swing_length < llBack <= idx - self.min_swing_length:
                    gotLowSwing = True
                    swingLow = ll  # confirmed
            else:
                break

        rangeMedian = (bars[maxLength - 1].high + bars[maxLength - 1].low) / 2
        alpha = 2 / (maxLength + 1)
        for idx in range(maxLength - 2, 0, -1):
            rangeMedian = rangeMedian * alpha + (bars[idx].high + bars[idx].low) / 2 * (1 - alpha)

        expectedEntrySplipagePerc = 0.0015
        expectedExitSlipagePerc = 0.0015

        signalId = str(bars[0].tstamp)

        # SHORT
        longSFP = self.entries != 1 and gotHighSwing and bars[1].close + data.buffer < swingHigh
        longRej = self.entries != 2 and bars[1].high > hh > bars[1].close + data.buffer and highSupreme > maxLength / 2 \
                  and bars[1].high - bars[1].close > (bars[1].high - bars[1].low) / 2
        if (longSFP or longRej) and (bars[1].high - bars[1].close) > atr * self.min_wick_fac \
                and self.directionFilter <= 0 and bars[1].high > rangeMedian + atr * self.range_filter_fac:
            # close existing short pos
            if self.close_on_opposite:
                for pos in self.open_positions.values():
                    if pos.status == PositionStatus.OPEN and self.split_pos_Id(pos.id)[1] == PositionDirection.LONG:
                        # execution will trigger close and cancel of other orders
                        self.order_interface.send_order(Order(orderId=self.generate_order_id(pos.id, OrderType.SL),
                                                              amount=-pos.amount, stop=None, limit=None))

            if self.init_stop_type == 1:
                stop = bars[1].high
            elif self.init_stop_type == 2:
                stop = bars[1].high + (bars[0].high - bars[0].close) * 0.5
            else:
                stop = max(swingHigh, (bars[1].high + bars[1].close) / 2)
            stop = stop + 1  # buffer

            entry = bars[0].open
            amount = self.calc_pos_size(risk=risk, exitPrice=stop * (1 + expectedExitSlipagePerc),
                                        entry=entry * (1 - expectedEntrySplipagePerc), data=data)

            posId = self.full_pos_id(signalId, PositionDirection.SHORT)
            self.order_interface.send_order(Order(orderId=self.generate_order_id(posId, OrderType.ENTRY),
                                                  amount=amount, stop=None, limit=None))
            self.order_interface.send_order(Order(orderId=self.generate_order_id(posId, OrderType.SL),
                                                  amount=-amount, stop=stop, limit=None))
            if self.tp_fac > 0:
                tp = entry - (stop - entry) * self.tp_fac
                self.order_interface.send_order(Order(orderId=self.generate_order_id(posId, OrderType.TP),
                                                      amount=-amount, stop=None, limit=tp))
            self.open_positions[posId] = Position(id=posId, entry=entry, amount=amount, stop=stop,
                                                  tstamp=bars[0].tstamp)
        # LONG
        shortSFP = self.entries != 1 and gotLowSwing and bars[1].close - data.buffer > swingLow
        shortRej = self.entries != 2 and bars[1].low < ll < bars[1].close - data.buffer and lowSupreme > maxLength / 2 \
                   and bars[1].close - bars[1].low > (bars[1].high - bars[1].low) / 2
        if (shortSFP or shortRej) and (bars[1].close - bars[1].low) > atr * self.min_wick_fac \
                and self.directionFilter >= 0 and bars[1].low < rangeMedian - self.range_filter_fac:
            # close existing short pos
            if self.close_on_opposite:
                for pos in self.open_positions.values():
                    if pos.status == PositionStatus.OPEN and self.split_pos_Id(pos.id)[1] == PositionDirection.SHORT:
                        # execution will trigger close and cancel of other orders
                        self.order_interface.send_order(Order(orderId=self.generate_order_id(pos.id, OrderType.SL),
                                                              amount=-pos.amount, stop=None, limit=None))

            if self.init_stop_type == 1:
                stop = bars[1].low
            elif self.init_stop_type == 2:
                stop = bars[1].low + (bars[0].low - bars[0].close) * 0.5
            else:
                stop = min(swingLow, (bars[1].low + bars[1].close) / 2)
            stop = stop - 1  # buffer

            entry = bars[0].open
            amount = self.calc_pos_size(risk=risk, exitPrice=stop * (1 - expectedExitSlipagePerc),
                                        entry=entry * (1 + expectedEntrySplipagePerc), data=data)

            posId = self.full_pos_id(signalId, PositionDirection.LONG)
            self.order_interface.send_order(Order(orderId=self.generate_order_id(posId, OrderType.ENTRY),
                                                  amount=amount, stop=None, limit=None))
            self.order_interface.send_order(Order(orderId=self.generate_order_id(posId, OrderType.SL),
                                                  amount=-amount, stop=stop, limit=None))
            if self.tp_fac > 0:
                tp = entry + (entry - stop) * self.tp_fac
                self.order_interface.send_order(Order(orderId=self.generate_order_id(posId, OrderType.TP),
                                                      amount=-amount, stop=None, limit=tp))

            self.open_positions[posId] = Position(id=posId, entry=entry, amount=amount, stop=stop,
                                                  tstamp=bars[0].tstamp)
