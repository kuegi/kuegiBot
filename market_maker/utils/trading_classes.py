from typing import List


class Bar:
    def __init__(self, tstamp: int, open: float, high: float, low: float, close: float, volume: float, subbars: list):
        self.tstamp: int = tstamp
        self.open: float = open
        self.high: float = high
        self.low: float = low
        self.close: float = close
        self.volume: float = volume
        self.subbars: list = subbars
        self.bot_data = {"indicators": {}}
        self.did_change: bool = True

    def __str__(self):
        return str(self.__dict__)

    def add_subbar(self, subbar):
        self.high = max(self.high, subbar['high'])
        self.low = min(self.low, subbar['low'])
        self.close = subbar['close']
        self.volume += subbar['volume']
        self.subbars.insert(0, subbar)
        self.did_change = True


class Account:
    def __init__(self):
        self.balance = 0
        self.equity = 0
        self.usd_equity= 0
        self.open_position = 0
        self.open_orders = []
        self.order_history = []

    def __str__(self):
        return str(self.__dict__)

class Symbol:
    def __init__(self,symbol,isInverse,lotSize, tickSize,makerFee,takerFee):
        self.symbol= symbol
        self.isInverse=isInverse
        self.lotSize= lotSize
        self.tickSize= tickSize
        self.makerFee= makerFee
        self.takerFee= takerFee

    def __str__(self):
        return str(self.__dict__)


class Order:
    def __init__(self, orderId=None, stop=None, limit=None, amount:float=0):
        self.id = orderId
        self.stop_price = stop
        self.limit_price = limit
        self.amount = amount
        self.executed_amount = 0
        self.executed_price = None
        self.active = True
        self.stop_triggered = False
        self.tstamp = 0
        self.execution_tstamp = 0
        self.exchange_id:str = None

    def __str__(self):
        return str(self.__dict__)


class OrderInterface:
    def send_order(self, order: Order):
        pass

    def update_order(self, order: Order):
        pass

    def cancel_order(self, orderId):
        pass


class Position:
    def __init__(self, id, entry, stop, amount, tstamp):
        self.id = id
        self.signal_tstamp = tstamp
        self.status = "pending"
        self.wanted_entry = entry
        self.initial_stop = stop
        self.amount = amount
        self.filled_entry: float = None
        self.filled_exit: float = None
        self.entry_tstamp = 0
        self.exit_tstamp = 0
        self.exit_equity= 0

    def __str__(self):
        return str(self.__dict__)


class TradingBot:
    def __init__(self):
        self.order_interface: OrderInterface = None
        self.symbol:Symbol= None
        self.last_time = 0
        self.open_positions = {}
        self.known_order_history = 0
        self.position_history: List[Position] = []
        self.reset()

    def uid(self) -> str:
        return "GenericBot"

    def reset(self):
        self.last_time = 0
        self.open_positions = {}
        self.known_order_history = 0
        self.position_history = []

    def init(self,bars:List[Bar],account:Account,symbol:Symbol):
        '''init open position etc.'''
        self.symbol= symbol
        pass

    def on_tick(self, bars: List[Bar], account: Account):
        """checks price and levels to manage current orders and set new ones"""
        self.prep_bars(bars)
        self.manage_open_orders(bars, account)
        self.open_orders(bars, account)

    def prep_bars(self, bars: List[Bar]):
        pass

    ###
    # Order Management
    ###

    def manage_open_orders(self, bars: list, account: Account):
        pass

    def open_orders(self, bars: list, account: Account):
        # new_bar= check_for_new_bar(bars)
        pass

    def check_for_new_bar(self, bars: List[Bar]) -> bool:
        """checks if this tick started a new bar.
        only works on the first call of a bar"""
        if bars[0].tstamp != self.last_time:
            self.last_time = bars[0].tstamp
            return True
        else:
            return False

    ####
    # additional stuff
    ###

    def add_to_plot(self, fig, bars, time):
        pass
