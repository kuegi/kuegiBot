import math
from datetime import datetime
from typing import List

from kuegi_bot.bots.strategies.channel_strat import ChannelStrategy
from kuegi_bot.bots.trading_bot import TradingBot, PositionDirection
from kuegi_bot.indicators.kuegi_channel import Data, clean_range
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType, Position, Order, PositionStatus


class SfpStrategy(ChannelStrategy):
    def __init__(self, tp_fac: float = 0, tp_use_atr: bool= False, init_stop_type: int = 0,
                 min_wick_fac: float = 0.2, min_swing_length: int = 2,
                 range_length: int = 50, min_rej_length: int= 25, range_filter_fac: float = 0,
                 close_on_opposite: bool = False, entries: int = 0):
        super().__init__()
        self.min_wick_fac = min_wick_fac
        self.min_swing_length = min_swing_length
        self.init_stop_type = init_stop_type
        self.tp_fac = tp_fac
        self.tp_use_atr= tp_use_atr
        self.range_length = range_length
        self.min_rej_length= min_rej_length
        self.range_filter_fac = range_filter_fac
        self.close_on_opposite = close_on_opposite
        self.entries = entries

    def myId(self):
        return "SFPStrategy"

    def init(self, bars: List[Bar], account: Account, symbol: Symbol):
        self.logger.info("init with %.1f %i %.1f | %i %i %i %.1f | %i %i" %
                         (self.tp_fac,self.init_stop_type, self.min_wick_fac,
                          self.min_swing_length, self.range_length, self.min_rej_length, self.range_filter_fac,
                          self.close_on_opposite, self.entries))
        super().init(bars, account, symbol)

    def owns_signal_id(self, signalId: str):
        return signalId.startswith("sfp+")

    def open_orders(self, is_new_bar, directionFilter, bars, account, open_positions):
        if (not is_new_bar) or len(bars) < 5:
            return  # only open orders on beginning of bar

        if not self.entries_allowed(bars):
            self.logger.info(" no entries allowed")
            return

        atr = clean_range(bars, offset=0, length=self.channel.max_look_back * 2)
        risk = self.risk_factor

        # test for SFP:
        # High > HH der letzten X
        # Close < HH der vorigen X
        # ? min Wick size?
        # initial SL

        data: Data = self.channel.get_data(bars[1])
        maxLength = min(len(bars), self.range_length)
        minRejLength = min(len(bars),self.min_rej_length)
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

        signalId = "sfp+" + str(bars[0].tstamp)

        # SHORT
        longSFP = self.entries != 1 and gotHighSwing and bars[1].close + data.buffer < swingHigh
        longRej = self.entries != 2 and bars[1].high > hh > bars[1].close + data.buffer and \
                    highSupreme > minRejLength and bars[1].high - bars[1].close > (bars[1].high - bars[1].low) / 2

        # LONG
        shortSFP = self.entries != 1 and gotLowSwing and bars[1].close - data.buffer > swingLow
        shortRej = self.entries != 2 and bars[1].low < ll < bars[1].close - data.buffer and lowSupreme > minRejLength \
                   and bars[1].close - bars[1].low > (bars[1].high - bars[1].low) / 2

        self.logger.info("---- analyzing: %s: %.1f %.1f %.0f | %s %.0f %i or %i %.0f %.0f | %s %.0f %i or %i %.0f %.0f " %
                         (str(datetime.fromtimestamp(bars[0].tstamp)), data.buffer, atr, rangeMedian,
                          gotHighSwing, swingHigh, hhBack, highSupreme, hh ,bars[1].high - bars[1].close,
                          gotLowSwing, swingLow, llBack, lowSupreme, ll ,bars[1].close - bars[1].low ))
        
        if (longSFP or longRej) and (bars[1].high - bars[1].close) > atr * self.min_wick_fac \
                and directionFilter <= 0 and bars[1].high > rangeMedian + atr * self.range_filter_fac:
            self.send_signal_message("sfp strat: short entry triggered")
            # close existing short pos
            if self.close_on_opposite:
                for pos in open_positions.values():
                    if pos.status == PositionStatus.OPEN and TradingBot.split_pos_Id(pos.id)[1] == PositionDirection.LONG:
                        # execution will trigger close and cancel of other orders
                        self.order_interface.send_order(
                            Order(orderId=TradingBot.generate_order_id(pos.id, OrderType.SL),
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
                                        entry=entry * (1 - expectedEntrySplipagePerc), atr=data.atr)

            posId = TradingBot.full_pos_id(signalId, PositionDirection.SHORT)
            pos = Position(id=posId, entry=entry, amount=amount, stop=stop,
                                             tstamp=bars[0].tstamp)
            open_positions[posId]= pos
            self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(posId, OrderType.ENTRY),
                                                  amount=amount, stop=None, limit=None))
            self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(posId, OrderType.SL),
                                                  amount=-amount, stop=stop, limit=None))
            if self.tp_fac > 0:
                ref = entry - stop
                if self.tp_use_atr:
                   ref = math.copysign(data.atr, entry - stop)
                tp = entry + ref * self.tp_fac
                self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(posId, OrderType.TP),
                                                      amount=-amount, stop=None, limit=tp))
            pos.status= PositionStatus.OPEN

        if (shortSFP or shortRej) and (bars[1].close - bars[1].low) > atr * self.min_wick_fac \
                and directionFilter >= 0 and bars[1].low < rangeMedian - self.range_filter_fac:
            self.send_signal_message("sfp strat: long entry triggered")
            # close existing short pos
            if self.close_on_opposite:
                for pos in open_positions.values():
                    if pos.status == PositionStatus.OPEN and TradingBot.split_pos_Id(pos.id)[1] == PositionDirection.SHORT:
                        # execution will trigger close and cancel of other orders
                        self.order_interface.send_order(
                            Order(orderId=TradingBot.generate_order_id(pos.id, OrderType.SL),
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
                                        entry=entry * (1 + expectedEntrySplipagePerc), atr=data.atr)

            posId = TradingBot.full_pos_id(signalId, PositionDirection.LONG)
            pos = Position(id=posId, entry=entry, amount=amount, stop=stop,
                                             tstamp=bars[0].tstamp)
            pos.status= PositionStatus.TRIGGERED
            open_positions[posId]= pos
            self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(posId, OrderType.ENTRY),
                                                  amount=amount, stop=None, limit=None))
            self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(posId, OrderType.SL),
                                                  amount=-amount, stop=stop, limit=None))
            if self.tp_fac > 0:
                tp = entry + (entry - stop) * self.tp_fac
                self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(posId, OrderType.TP),
                                                      amount=-amount, stop=None, limit=tp))
