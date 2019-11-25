
from market_maker.market_maker import ExchangeInterface
from market_maker.utils.trading_classes import TradingBot,OrderInterface, Order, Account, Bar

ex= ExchangeInterface(False)
orders= ex.get_orders()

o= orders[0]
o.limit_price= 1

ex.update_order(o)