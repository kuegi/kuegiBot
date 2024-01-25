
########
# some simple exit modules for reuse
##########
import math
from typing import List

from kuegi_bot.indicators.indicator import Indicator, clean_range
from kuegi_bot.utils.dotdict import dotdict
from kuegi_bot.utils.trading_classes import Position, Bar, Symbol


class ExitModule:
    def __init__(self):
        self.logger = None
        self.symbol= None
        pass

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        pass

    def init(self, logger, symbol: Symbol):
        self.logger = logger
        self.symbol= symbol

    def got_data_for_position_sync(self, bars: List[Bar]) -> bool:
        return True

    def get_stop_for_unmatched_amount(self, amount: float, bars: List[Bar]):
        return None

    def get_data(self, bar: Bar, dataId):
        if 'modules' in bar.bot_data.keys() and dataId in bar.bot_data['modules'].keys():
            return bar.bot_data["modules"][dataId]
        else:
            return None

    def write_data(self, bar: Bar, dataId, data):
        if "modules" not in bar.bot_data.keys():
            bar.bot_data['modules'] = {}

        bar.bot_data["modules"][dataId] = data

    @staticmethod
    def get_data_for_json(bar:Bar):
        result= {}
        if bar is not None and bar.bot_data is not None and 'modules' in bar.bot_data.keys():
            for key in bar.bot_data['modules'].keys():
                if isinstance(bar.bot_data['modules'][key],dict):
                    result[key]= bar.bot_data['modules'][key]
                else:
                    result[key]= bar.bot_data['modules'][key].__dict__
        return result

    @staticmethod
    def set_data_from_json(bar:Bar,jsonData):
        if "modules" not in bar.bot_data.keys():
            bar.bot_data['modules'] = {}
        for key in jsonData.keys():
            if len(jsonData[key].keys()) > 0:
                bar.bot_data['modules'][key]= dotdict(jsonData[key])


class SimpleBE(ExitModule):
    ''' trails the stop to "break even" when the price move a given factor of the entry-risk in the right direction
        "break even" includes a buffer (multiple of the entry-risk).
    '''

    def __init__(self, factor, bufferLongs, bufferShorts, atrPeriod: int = 0):
        super().__init__()
        self.factor = factor
        self.bufferLongs = bufferLongs
        self.bufferShorts = bufferShorts
        self.atrPeriod = atrPeriod

    def init(self, logger,symbol):
        super().init(logger,symbol)
        self.logger.info("init BE %.2f %.2f %.2f %i" % (self.factor, self.bufferLongs, self.bufferShorts, self.atrPeriod))

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        if position is not None and self.factor > 0:
            # trail
            newStop = order.trigger_price
            refRange = 0
            if self.atrPeriod > 0:
                atrId = "atr_4h" + str(self.atrPeriod)
                refRange = Indicator.get_data_static(bars[1], atrId)
                if refRange is None:
                    refRange = clean_range(bars, offset=1, length=self.atrPeriod)
                    Indicator.write_data_static(bars[1], refRange, atrId)

            elif position.wanted_entry is not None and position.initial_stop is not None:
                refRange = (position.wanted_entry - position.initial_stop)

            if refRange != 0:
                ep = bars[0].high if position.amount > 0 else bars[0].low
                buffer = self.bufferLongs if position.amount > 0 else self.bufferShorts
                be = position.wanted_entry + refRange * buffer
                if newStop is not None:
                    if (ep - (position.wanted_entry + refRange * self.factor)) * position.amount > 0 \
                            and (be - newStop) * position.amount > 0:
                        newStop= self.symbol.normalizePrice(be, roundUp=position.amount < 0)

            if newStop != order.trigger_price:
                order.trigger_price = newStop
                to_update.append(order)


class QuickBreakEven(ExitModule):
    ''' trails the stop to "break even" within the provided time period as long as the stop is not in profit '''
    def __init__(self, seconds_to_BE: int = 999999, factor: float = 1.0):
        super().__init__()
        self.seconds_to_BE = seconds_to_BE
        self.factor = factor

    def init(self, logger,symbol):
        super().init(logger,symbol)
        self.logger.info("init QuickBreakEven %i" % (self.seconds_to_BE))

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        newStop = order.trigger_price
        current_tstamp = bars[0].last_tick_tstamp if bars[0].last_tick_tstamp is not None else bars[0].tstamp

        refRange = abs(position.wanted_entry - position.initial_stop)
        seconds_since_entry = current_tstamp - position.entry_tstamp

        if self.seconds_to_BE is not None and self.seconds_to_BE != 0:
            equity_per_second = refRange / self.seconds_to_BE

            if (newStop < (position.wanted_entry + self.factor * refRange) and position.amount > 0) or \
                    (newStop > max((position.wanted_entry - refRange * self.factor),0) and position.amount < 0):
                if position.amount > 0:
                    newStop = position.initial_stop + equity_per_second * seconds_since_entry
                else:
                    newStop = position.initial_stop - equity_per_second * seconds_since_entry

                newStop = self.symbol.normalizePrice(newStop, roundUp=position.amount < 0)

            if newStop != order.trigger_price:
                order.trigger_price = newStop
                to_update.append(order)


class MaxSLDiff(ExitModule):
    ''' trails the stop to a max dist in atr_4h from the extreme point '''

    def __init__(self, maxATRDiff: float , atrPeriod: int = 0):
        super().__init__()
        self.maxATRDiff = maxATRDiff
        self.atrPeriod = atrPeriod

    def init(self, logger,symbol):
        super().init(logger,symbol)
        self.logger.info("init maxATRDiff %.1f %i" % (self.maxATRDiff, self.atrPeriod))

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        if position is not None and self.maxATRDiff > 0 and self.atrPeriod > 0:
            # trail
            newStop = order.trigger_price
            atrId = "atr_4h" + str(self.atrPeriod)
            refRange = Indicator.get_data_static(bars[1], atrId)
            if refRange is None:
                refRange = clean_range(bars, offset=1, length=self.atrPeriod)
                Indicator.write_data_static(bars[1], refRange, atrId)

            if refRange != 0:
                ep = bars[0].high if position.amount > 0 else bars[0].low
                maxdistStop= ep - math.copysign(refRange*self.maxATRDiff,position.amount)
                if (maxdistStop - newStop) * position.amount > 0:
                    newStop= self.symbol.normalizePrice(maxdistStop, roundUp=position.amount < 0)

            if math.fabs(newStop - order.trigger_price) > 0.5*self.symbol.tickSize:
                order.trigger_price = newStop
                to_update.append(order)


class TimedExit(ExitModule):
    ''' trails the stop to a max dist in atr_4h from the extreme point
    '''

    def __init__(self, minutes_till_exit:int= 240):
        super().__init__()
        self.minutes_till_exit = minutes_till_exit

    def init(self, logger,symbol):
        super().init(logger,symbol)
        self.logger.info(f"init timedExit {self.minutes_till_exit}" )

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        current_tstamp= bars[0].last_tick_tstamp if bars[0].last_tick_tstamp is not None else bars[0].tstamp
        if position is not None and position.entry_tstamp is not None\
                and current_tstamp - position.entry_tstamp > self.minutes_till_exit*60:
            order.trigger_price= None # make it market
            order.limit_price= None
            to_update.append(order)


class RsiExit(ExitModule):
    """ closes positions at oversold and overbougt RSI """
    def __init__(self, rsi_high_lim: float = 100, rsi_low_lim: int = 0):
        super().__init__()
        self.rsi_high_lim = rsi_high_lim
        self.rsi_low_lim = rsi_low_lim

    def init(self, logger,symbol):
        super().init(logger,symbol)
        self.logger.info("init RSI TP at high: %i and low %i" % (self.rsi_high_lim, self.rsi_low_lim))

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        test = 1


class FixedPercentage(ExitModule):
    """ trails the stop to a specified percentage from the highest high reached """
    def __init__(self, slPercentage: float= 0.0, useInitialSLRange: bool = False, rangeFactor: float = 1):
        super().__init__()
        self.slPercentage = min(slPercentage,1)     # trailing stop in fixed percentage
        self.useInitialSLRange = useInitialSLRange  # use initials SL range
        self.rangeFactor = abs(rangeFactor)         # SL range factor

    def init(self, logger,symbol):
        super().init(logger,symbol)
        self.logger.info("init Percentage Trail %.1f %s %.1f" % (self.slPercentage, self.useInitialSLRange, self.rangeFactor))

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        if order.trigger_price is None:
            return

        if position is not None:
            extremePoint = bars[0].high if position.amount > 0 else bars[0].low     # new highest/lowest price
            currentStop = sl_perc = sl_range= order.trigger_price                      # current SL price
            refRange = abs(position.wanted_entry - position.initial_stop)           # initial SL range in $
            refRangePercent = refRange/position.wanted_entry                        # initial SL range in %

            if position.amount > 0:
                sl1 = extremePoint * (1-self.slPercentage)                                      # SL in fixed percentage from extreme point
                sl2 = max(extremePoint * (1 - refRangePercent * self.rangeFactor),currentStop)  # SL in initial SL range percentage from extreme point
                if currentStop < sl1 and self.slPercentage > 0:
                    sl_perc = self.symbol.normalizePrice(sl1, roundUp=position.amount < 0)
                if currentStop < sl2 and self.useInitialSLRange:
                    sl_range = self.symbol.normalizePrice(sl2, roundUp=position.amount < 0)
                newStop = max(sl_perc,sl_range,currentStop)
            else:
                sl1 = extremePoint * (1 + self.slPercentage)
                sl2 = min(extremePoint * (1 + refRangePercent * self.rangeFactor),currentStop)
                if currentStop > sl1 and self.slPercentage > 0:
                    sl_perc = self.symbol.normalizePrice(sl1,roundUp=position.amount < 0)
                if currentStop > sl2 and self.useInitialSLRange:
                    sl_range = self.symbol.normalizePrice(sl2, roundUp=position.amount < 0)
                newStop = min(sl_perc, sl_range, currentStop)

            if newStop != order.trigger_price:
                self.logger.info("changing SL. Previous Stop: " + str(order.trigger_price) + "; New Stop: " + str(newStop))
                order.trigger_price = newStop
                to_update.append(order)


class ParaData:
    def __init__(self):
        self.acc = 0
        self.ep = 0
        self.stop = 0
        self.actualStop= None


class ParaTrail(ExitModule):
    '''
    trails the stop according to a parabolic SAR. ep is resetted on the entry of the position.
    lastEp and factor is stored in the bar data with the positionId
    '''

    def __init__(self, accInit, accInc, accMax, resetToCurrent= False):
        super().__init__()
        self.accInit = accInit
        self.accInc = accInc
        self.accMax = accMax
        self.resetToCurrent= resetToCurrent

    def init(self, logger,symbol):
        super().init(logger,symbol)
        self.logger.info("init ParaTrail %.2f %.2f %.2f %s" %
                         (self.accInit, self.accInc, self.accMax, self.resetToCurrent))

    def data_id(self,position:Position):
        return position.id + '_paraExit'

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        if position is None or order is None or order.stop_price is None:
            return

        self.update_bar_data(position, bars)
        data = self.get_data(bars[0],self.data_id(position))
        newStop = order.stop_price

        # trail
        if data is not None and (data.stop - newStop) * position.amount > 0:
            newStop= self.symbol.normalizePrice(data.stop, roundUp=position.amount < 0)

        if data is not None and data.actualStop != newStop:
            data.actualStop = newStop
            self.write_data(bar=bars[0], dataId=self.data_id(position), data=data)
        # if restart, the last actual is not set and we might miss increments cause of regular restarts.
        lastdata= self.get_data(bars[1],self.data_id(position))
        if lastdata is not None and lastdata.actualStop is None:
            lastdata.actualStop= order.stop_price
            self.write_data(bar=bars[1], dataId=self.data_id(position), data=lastdata)

        if math.fabs(newStop - order.stop_price) > 0.5*self.symbol.tickSize:
            order.stop_price = newStop
            to_update.append(order)

    def update_bar_data(self, position: Position, bars: List[Bar]):
        if position.initial_stop is None or position.entry_tstamp is None or position.entry_tstamp == 0:
            return  # cant trail with no initial and not defined entry
        dataId = self.data_id(position)
        # find first bar with data (or entry bar)
        lastIdx = 1
        while self.get_data(bars[lastIdx], dataId) is None and bars[lastIdx].tstamp > position.entry_tstamp:
            lastIdx += 1
            if lastIdx == len(bars):
                break
        if self.get_data(bars[lastIdx - 1], dataId) is None and bars[lastIdx].tstamp > position.entry_tstamp:
            lastIdx += 1  # didn't see the current bar before: make sure we got the latest update on the last one too

        while lastIdx > 0:
            lastbar = bars[lastIdx]
            currentBar = bars[lastIdx - 1]
            last: ParaData = self.get_data(lastbar, dataId)
            prev: ParaData = self.get_data(currentBar, dataId)
            current: ParaData = ParaData()
            if last is not None:
                current.ep = max(last.ep, currentBar.high) if position.amount > 0 else min(last.ep, currentBar.low)
                current.acc = last.acc
                if current.ep != last.ep:
                    current.acc = min(current.acc + self.accInc, self.accMax)
                lastStop = last.stop
                if self.resetToCurrent and last.actualStop is not None and (last.actualStop - last.stop) * position.amount > 0:
                    lastStop= last.actualStop
                current.stop = lastStop + (current.ep - last.stop) * current.acc
            else:  # means its the first bar of the position
                current.ep = currentBar.high if position.amount > 0 else currentBar.low
                current.acc = self.accInit
                current.stop = position.initial_stop
            if prev is not None:
                current.actualStop = prev.actualStop # not to loose it
            self.write_data(bar=currentBar, dataId=dataId, data=current)
            lastIdx -= 1
