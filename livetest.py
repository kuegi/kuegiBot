
from market_maker.market_maker import ExchangeInterface
from market_maker.trade_engine import LiveTrading
from market_maker.kuegi_bot import KuegiBot

live= LiveTrading(KuegiBot())
live.handle_tick()

live.update_bars()
live.update_account()

ex= ExchangeInterface(False,None)

orders= ex.get_orders()

o= orders[-1]
o.amount= 2

ex.update_order(o)

from market_maker.bitmex_interface import BitMexInterface
interface= BitMexInterface()
orders= interface.get_orders()

o= orders[-1]
o.amount= 10

interface.update_order(o)