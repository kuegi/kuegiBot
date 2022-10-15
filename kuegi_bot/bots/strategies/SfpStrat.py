import math
from datetime import datetime
from typing import List

from kuegi_bot.bots.strategies.channel_strat import ChannelStrategy
from kuegi_bot.bots.trading_bot import TradingBot, PositionDirection
from kuegi_bot.indicators.kuegi_channel import Data, clean_range
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType, Position, Order, PositionStatus


class SfpStrategy(ChannelStrategy):
    def __init__(self, tp_fac: float = 0, tp_use_atr: bool= False,
                 init_stop_type: int = 0,stop_buffer_fac:int=2, min_stop_diff_perc:float = 0, ignore_on_tight_stop:bool = False,
                 min_wick_fac: float = 0.2, min_air_wick_fac: float = 0.0, min_wick_to_body:float= 0.5,
                 min_swing_length: int = 2,
                 range_length: int = 50, min_rej_length: int= 25, range_filter_fac: float = 0,
                 close_on_opposite: bool = False, entries: int = 0):
        super().__init__()
        self.min_wick_fac = min_wick_fac
        self.min_air_wick_fac = min_air_wick_fac
        self.min_wick_to_body= min_wick_to_body
        self.min_swing_length = min_swing_length
        self.init_stop_type = init_stop_type
        self.stop_buffer_fac=stop_buffer_fac
        self.min_stop_diff_perc= min_stop_diff_perc
        self.ignore_on_tight_stop= ignore_on_tight_stop
        self.tp_fac = tp_fac
        self.tp_use_atr= tp_use_atr
        self.range_length = range_length
        self.min_rej_length= min_rej_length
        self.range_filter_fac = range_filter_fac
        self.close_on_opposite = close_on_opposite
        self.entries = entries

    def myId(self):
        return "sfp"

    def init(self, bars: List[Bar], account: Account, symbol: Symbol):
        self.logger.info("init with %.1f %i %i | %.1f %.2f  %.2f | %i %i %i %.1f | %i %i | %.1f %s" %
                         (self.tp_fac,self.init_stop_type, self.stop_buffer_fac,
                          self.min_wick_fac, self.min_air_wick_fac, self.min_wick_to_body,
                          self.min_swing_length, self.range_length, self.min_rej_length, self.range_filter_fac,
                          self.close_on_opposite, self.entries,
                          self.min_stop_diff_perc,self.ignore_on_tight_stop))
        super().init(bars, account, symbol)

    def owns_signal_id(self, signalId: str):
        return signalId.startswith("sfp+")

    def open_orders(self, is_new_bar, directionFilter, bars, account, open_positions, all_open_pos: dict):
        if (not is_new_bar) or len(bars) < 5:
            return  # only open orders on beginning of bar

        if not self.entries_allowed(bars):
            self.logger.info(" no entries allowed")
            return

        atr = clean_range(bars, offset=0, length=self.channel.max_look_back * 2)

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

        # SHORT
        longSFP = self.entries != 1 and gotHighSwing and bars[1].close + data.buffer < swingHigh
        longRej = self.entries != 2 and bars[1].high > hh > bars[1].close + data.buffer and highSupreme > minRejLength

        # LONG
        shortSFP = self.entries != 1 and gotLowSwing and bars[1].close - data.buffer > swingLow
        shortRej = self.entries != 2 and bars[1].low < ll < bars[1].close - data.buffer and lowSupreme > minRejLength

        self.logger.info("---- analyzing: %s: %.1f %.1f %.0f | %s %.0f %i or %i %.0f %.0f | %s %.0f %i or %i %.0f %.0f " %
                         (str(datetime.fromtimestamp(bars[0].tstamp)), data.buffer, atr, rangeMedian,
                          gotHighSwing, swingHigh, hhBack, highSupreme, hh ,bars[1].high - bars[1].close,
                          gotLowSwing, swingLow, llBack, lowSupreme, ll ,bars[1].close - bars[1].low ))
        
        if (longSFP or longRej) and (bars[1].high - bars[1].close) > atr * self.min_wick_fac \
                and (bars[1].high - hh) > (bars[1].high - bars[1].close)*self.min_air_wick_fac \
                and directionFilter <= 0 and bars[1].high > rangeMedian + atr * self.range_filter_fac \
                    and bars[1].high - bars[1].close > (bars[1].high - bars[1].low) * self.min_wick_to_body:
            self.__open_position(PositionDirection.SHORT, bars, swingHigh if gotHighSwing else hh,open_positions,all_open_pos)

        if (shortSFP or shortRej) and (bars[1].close - bars[1].low) > atr * self.min_wick_fac \
                and (ll - bars[1].low) > (bars[1].close - bars[1].low)*self.min_air_wick_fac \
                and directionFilter >= 0 and bars[1].low < rangeMedian - atr * self.range_filter_fac\
                   and bars[1].close - bars[1].low > (bars[1].high - bars[1].low) * self.min_wick_to_body:
            self.__open_position(PositionDirection.LONG, bars, swingLow if gotLowSwing else ll,open_positions,all_open_pos)

    def __open_position(self, direction, bars, swing ,open_positions,all_open_pos):
        directionFactor= 1
        oppDirection= PositionDirection.SHORT
        extreme= bars[1].low
        capFunc= min
        if direction == PositionDirection.SHORT:
            directionFactor= -1
            oppDirection= PositionDirection.LONG
            extreme= bars[1].high
            capFunc= max
        oppDirectionFactor= directionFactor*-1

        expectedEntrySplipagePerc = 0.0015
        expectedExitSlipagePerc = 0.0015

        data: Data = self.channel.get_data(bars[1])

        if self.close_on_opposite:
            for pos in open_positions.values():
                if pos.status == PositionStatus.OPEN and \
                        TradingBot.split_pos_Id(pos.id)[1] == oppDirection:
                    # execution will trigger close and cancel of other orders
                    self.order_interface.send_order(
                        Order(orderId=TradingBot.generate_order_id(pos.id, OrderType.SL),
                              amount=-pos.amount, stop=None, limit=None))

        if self.init_stop_type == 1:
            stop = extreme
        elif self.init_stop_type == 2:
            stop = extreme + (extreme - bars[1].close) * 0.5
        else:
            stop = capFunc(swing, (extreme + bars[1].close) / 2)
        stop = stop + oppDirectionFactor*self.symbol.tickSize*self.stop_buffer_fac  # buffer

        entry = bars[0].open
        signalId = self.get_signal_id(bars)

        #case long: entry * (1 + oppDirectionFactor*self.min_stop_diff_perc / 100) >= stop
        if 0 <= directionFactor*(entry * (1 + oppDirectionFactor*self.min_stop_diff_perc / 100) - stop) \
                or not self.ignore_on_tight_stop:
            stop = capFunc(stop, entry * (1 + oppDirectionFactor*self.min_stop_diff_perc / 100))
            stop= self.symbol.normalizePrice(stop,roundUp=direction == PositionDirection.LONG)
            amount = self.calc_pos_size(risk=self.risk_factor,
                                        exitPrice=stop * (1 + oppDirectionFactor*expectedExitSlipagePerc),
                                        entry=entry * (1 + directionFactor*expectedEntrySplipagePerc),
                                        atr=data.atr)

            posId = TradingBot.full_pos_id(signalId, direction)
            pos = Position(id=posId, entry=entry, amount=amount, stop=stop,
                           tstamp=bars[0].tstamp)
            open_positions[posId] = pos
            #all_open_pos[posId] = pos # need to add to the bots open pos too, so the execution of the market is not missed
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
            pos.status = PositionStatus.OPEN