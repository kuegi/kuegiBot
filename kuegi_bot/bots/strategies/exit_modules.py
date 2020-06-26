
########
# some simple exit modules for reuse
##########
import math
from typing import List

from kuegi_bot.indicators.indicator import Indicator, clean_range
from kuegi_bot.utils.dotdict import dotdict
from kuegi_bot.utils.trading_classes import Position, Bar


class ExitModule:
    def __init__(self):
        self.logger = None
        pass

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        pass

    def init(self, logger):
        self.logger = logger

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

    def __init__(self, factor, buffer, atrPeriod: int = 0):
        super().__init__()
        self.factor = factor
        self.buffer = buffer
        self.atrPeriod = atrPeriod

    def init(self, logger):
        super().init(logger)
        self.logger.info("init BE %.1f %.1f %i" % (self.factor, self.buffer, self.atrPeriod))

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        if position is not None and self.factor > 0:
            # trail
            newStop = order.stop_price
            refRange = 0
            if self.atrPeriod > 0:
                atrId = "ATR" + str(self.atrPeriod)
                refRange = Indicator.get_data_static(bars[1], atrId)
                if refRange is None:
                    refRange = clean_range(bars, offset=1, length=self.atrPeriod)
                    Indicator.write_data_static(bars[1], refRange, atrId)

            elif position.wanted_entry is not None and position.initial_stop is not None:
                refRange = (position.wanted_entry - position.initial_stop)

            if refRange != 0:
                ep = bars[0].high if position.amount > 0 else bars[0].low
                be = position.wanted_entry + refRange * self.buffer
                if (ep - (position.wanted_entry + refRange * self.factor)) * position.amount > 0 \
                        and (be - newStop) * position.amount > 0:
                    newStop = math.floor(be) if position.amount < 0 else math.ceil(be)

            if newStop != order.stop_price:
                order.stop_price = newStop
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

    def init(self, logger):
        super().init(logger)
        self.logger.info("init ParaTrail %.2f %.2f %.2f %s" %
                         (self.accInit, self.accInc, self.accMax, self.resetToCurrent))

    def data_id(self,position:Position):
        return position.id + '_paraExit'

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        if position is None:
            return

        self.update_bar_data(position, bars)
        data = self.get_data(bars[0],self.data_id(position))
        newStop = order.stop_price

        # trail
        if data is not None and (data.stop - newStop) * position.amount > 0:
            newStop = math.floor(data.stop) if position.amount < 0 else math.ceil(data.stop)

        if data is not None and data.actualStop != newStop:
            data.actualStop = newStop
            self.write_data(bar=bars[0], dataId=self.data_id(position), data=data)
        # if restart, the last actual is not set and we might miss increments cause of regular restarts.
        lastdata= self.get_data(bars[1],self.data_id(position))
        if lastdata is not None and lastdata.actualStop is None:
            lastdata.actualStop= order.stop_price
            self.write_data(bar=bars[1], dataId=self.data_id(position), data=lastdata)

        if newStop != order.stop_price:
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
