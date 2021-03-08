import math
from typing import List
from time import sleep
from datetime import datetime

import atexit
from enum import Enum


class AccountPosition:
    def __init__(self, symbol: str, quantity: float, avgEntryPrice: float, walletBalance: float = 0):
        self.symbol = symbol
        self.quantity = quantity
        self.avgEntryPrice = avgEntryPrice
        self.walletBalance = walletBalance

    def __str__(self):
        return str(self.__dict__)


class TickerData:
    def __init__(self, bid, ask, last):
        self.last = last
        self.bid = bid
        self.ask = ask

    def __str__(self):
        return str(self.__dict__)


class Bar:
    def __init__(self, tstamp: int, open: float, high: float, low: float, close: float, volume: float,
                 subbars: list = None):
        self.tstamp: int = tstamp
        self.open: float = open
        self.high: float = high
        self.low: float = low
        self.close: float = close
        self.volume: float = volume
        self.buyVolume: float = 0
        self.sellVolume: float = 0
        self.subbars: List[Bar] = subbars if subbars is not None else []
        self.bot_data = {"indicators": {}}
        self.did_change: bool = True
        self.last_tick_tstamp: float = tstamp if subbars is None or len(subbars) == 0 else\
                                        subbars[0].last_tick_tstamp

    def __str__(self):
        result = "%s (%i) %.1f/%.1f\\%.1f-%.1f %.1f" % (
            datetime.fromtimestamp(self.tstamp), self.tstamp, self.open, self.high, self.low, self.close, self.volume)
        if len(self.subbars) > 0:
            result += "\n         ["
            for sub in self.subbars:
                result += "\n           " + str(sub) + ","
            result += "\n         ]"
        return result

    def add_subbar(self, subbar):
        if subbar is None or subbar.close is None or self.close is None:
            return
        self.high = max(self.high, subbar.high)
        self.low = min(self.low, subbar.low)
        self.close = subbar.close
        self.volume += subbar.volume
        self.subbars.insert(0, subbar)
        self.last_tick_tstamp = max(self.last_tick_tstamp,subbar.last_tick_tstamp)
        self.did_change = True


class Account:
    def __init__(self):
        self.equity = 0
        self.usd_equity = 0
        self.open_position:AccountPosition = AccountPosition(symbol="dummy",quantity=0,avgEntryPrice=0,walletBalance=0)
        self.open_orders = []
        self.order_history = []

    def __str__(self):
        return str(self.__dict__)


class Symbol:
    def __init__(self, symbol: str, isInverse, lotSize, tickSize, makerFee, takerFee,pricePrecision = 2, quantityPrecision= 2):
        self.symbol: str = symbol
        self.isInverse = isInverse
        self.lotSize = lotSize
        self.tickSize = tickSize
        self.makerFee = makerFee
        self.takerFee = takerFee
        self.pricePrecision= pricePrecision
        self.quantityPrecision= quantityPrecision

    def __str__(self):
        return str(self.__dict__)

    def normalizePrice(self,price, roundUp):
        if price is None:
            return None
        rou= math.ceil if roundUp else math.floor
        closestTicks= round(price / self.tickSize)
        if math.fabs(closestTicks - price/self.tickSize) < 0.01: #already rounded close enough
            toTicks= closestTicks*self.tickSize
        else:
            toTicks= rou(price/self.tickSize)*self.tickSize
        return round(toTicks,self.pricePrecision)

    def normalizeSize(self,size):
        if size is None:
            return None
        closestLot= round(size / self.lotSize)
        if math.fabs(closestLot-size/self.lotSize) < 0.01: #already rounded close enough
            toTicks= closestLot*self.lotSize
        else:
            toTicks= math.floor(size/self.lotSize)*self.lotSize
        return round(toTicks,self.quantityPrecision)


class OrderType(Enum):
    ENTRY = "ENTRY"
    SL = "SL"
    TP = "TP"


class Order:
    def __init__(self, orderId=None, stop=None, limit=None, amount: float = 0):
        self.id = orderId
        self.stop_price = stop
        self.limit_price = limit
        self.amount = amount
        self.executed_amount = 0
        self.executed_price = None
        self.active = True
        self.stop_triggered = False
        self.tstamp:float = 0
        self.execution_tstamp:float = 0
        self.exchange_id: str = None

    def __str__(self):
        string= f"{self.id} ({'active'if self.active else 'inactive'}, " \
                f"{self.exchange_id[-8:]if self.exchange_id is not None else None})" \
               f" {self.amount}@{self.limit_price}/{self.stop_price} at {datetime.fromtimestamp(self.tstamp)}"
        if self.executed_price is not None:
            string += f" ex: {self.executed_amount}@{self.executed_price} at " \
                      f"{datetime.fromtimestamp(self.execution_tstamp) if self.execution_tstamp is not None else None}"
        return string

    def print_info(self):
        precision= 1
        if abs(self.amount) < 1:
            precision= 3
        format= "{:."+str(precision)+"f}"
        amount= format.format(self.amount)
        if self.limit_price is None and self.stop_price is None:
            return "%s %s @ market" % (self.id, amount)
        else:
            price= ""
            if self.stop_price is not None:
                price += "%.3f" % self.stop_price
            if self.limit_price is not None:
                price += "/%.3f" % self.limit_price
            return "%s %s @ %s" % (
                self.id,
                amount,
                price)


class OrderInterface:

    def __init__(self):
        self.handles_executions = False

    def send_order(self, order: Order):
        pass

    def update_order(self, order: Order):
        pass

    def cancel_order(self, order: Order):
        pass

class PositionStatus(Enum):
    PENDING = "pending"
    TRIGGERED = "triggered"
    OPEN = "open"
    CLOSED = "closed"
    MISSED = "missed"
    CANCELLED = "cancelled"


class Position:
    def __init__(self, id: str, entry: float, stop: float, amount: float, tstamp):
        self.id: str = id
        self.signal_tstamp = tstamp
        self.status: PositionStatus = PositionStatus.PENDING
        self.changed= False
        self.wanted_entry = entry
        self.initial_stop = stop
        self.amount = amount
        self.maxFilledAmount= 0
        self.currentOpenAmount= 0
        self.last_filled_entry: float= None
        self.filled_entry: float = None
        self.filled_exit: float = None
        self.entry_tstamp = 0
        self.exit_tstamp = 0
        self.exit_equity = 0
        self.customData= {}
        self.connectedOrders :List[Order] = []
        self.stats = {}

    def __str__(self):
        return str(self.__dict__)

    def to_json(self):
        tempdic = dict(self.__dict__)
        tempdic['status'] = self.status.value
        orders= tempdic['connectedOrders']
        tempdic['connectedOrders']= []
        for order in orders:
            if isinstance(order,dict):
                tempdic['connectedOrders'].append(order)
            else:
                tempdic['connectedOrders'].append(order.__dict__)
        return tempdic

    @staticmethod
    def from_json(pos_json):
        pos = Position("", 0, 0, 0, 0)
        for prop in pos.__dict__.keys():
            if prop in pos_json.keys():
                setattr(pos, prop, pos_json[prop])
        state= PositionStatus.MISSED
        for status in PositionStatus:
            if pos.status == status.value:
                state = status
                break
        pos.status= state

        # backward compatibility
        if pos.status == PositionStatus.OPEN and (pos.currentOpenAmount == 0 or pos.maxFilledAmount == 0):
            # happens when old open positions file gets read in
            pos.maxFilledAmount= pos.amount
            pos.currentOpenAmount= pos.amount
        return pos

    def daysInPos(self):
        if self.entry_tstamp is None or self.entry_tstamp is None:
            return 0
        return (self.exit_tstamp-self.entry_tstamp)/(60*60*24)


def parse_utc_timestamp(timestamp: str) -> float:
    import calendar
    if "." in timestamp:
        if timestamp[-1] == 'Z' and len(timestamp)> 27:
            timestamp= timestamp[:26]+"Z"
        d = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%fZ')
    else:
        d = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%SZ')

    return calendar.timegm(d.timetuple())+d.microsecond/1000000.0


def process_low_tf_bars(subbars: List[Bar], timeframe_minutes, start_offset_minutes=0):
    ''' subbars need to be ordered newest bar = index 0 '''
    result: list = []
    if len(subbars) > 1 and subbars[0].tstamp < subbars[-1].tstamp:
        print("Had to order subbars before processing them!")
        subbars.sort(key=lambda b: b.tstamp, reverse=True)
    for bar in reversed(subbars):
        bar_start = int((bar.tstamp - start_offset_minutes * 60) / (60 * timeframe_minutes)) * (60 * timeframe_minutes)
        if result and result[-1].tstamp == bar_start:
            # add to bar
            result[-1].add_subbar(bar)
        else:
            # create new bar
            result.append(Bar(tstamp=bar_start, open=bar.open, high=bar.high, low=bar.low, close=bar.close,
                              volume=bar.volume, subbars=[bar]))

    # sort subbars
    for bar in result:
        bar.subbars.sort(key=lambda b: b.tstamp, reverse=True)

    result.sort(key=lambda b: b.tstamp, reverse=True)
    return result


class ExchangeInterface(OrderInterface):
    def __init__(self, settings, logger,on_tick_callback=None,on_execution_callback= None):
        self.settings = settings
        self.logger = logger
        self.symbol = None
        self.on_tick_callback= on_tick_callback
        self.on_execution_callback= on_execution_callback

        atexit.register(lambda: self.exit())

    def cancel_order(self, order: Order):
        self.logger.info("Canceling: %s" % order.id)
        while True:
            try:
                self.internal_cancel_order(order)
            except ValueError as e:
                self.logger.info(e)
                sleep(self.settings.API_ERROR_INTERVAL)
            else:
                break

    def send_order(self, order: Order):
        self.logger.info("Placing: %s" % order.print_info())
        while True:
            try:
                self.internal_send_order(order)
            except ValueError as e:
                self.logger.info(e)
                sleep(self.settings.API_ERROR_INTERVAL)
            else:
                break

    def update_order(self, order: Order):
        self.logger.info("Updating: %s" % order.print_info())
        while True:
            try:
                self.internal_update_order(order)
            except ValueError as e:
                self.logger.info(e)
                sleep(self.settings.API_ERROR_INTERVAL)
            else:
                break

    def exit(self):
        pass

    def internal_cancel_order(self, order: Order):
        pass

    def internal_send_order(self, order: Order):
        pass

    def internal_update_order(self, order: Order):
        pass

    def resyncOrders(self):
        raise NotImplementedError

    def get_orders(self) -> List[Order]:
        return []

    def get_bars(self, timeframe_minutes, start_offset_minutes, min_bars_needed=600) -> List[Bar]:
        return []

    def recent_bars(self, timeframe_minutes, start_offset_minutes) -> List[Bar]:
        return []

    def get_instrument(self, symbol=None):
        pass

    def get_position(self, symbol=None):
        pass

    def is_open(self):
        return False

    def check_market_open(self):
        return False

    def update_account(self, account: Account):
        pass
