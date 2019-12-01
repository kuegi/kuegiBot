
from market_maker.market_maker import ExchangeInterface
from market_maker.trade_engine import LiveTrading
from market_maker.kuegi_bot import KuegiBot

live= LiveTrading(KuegiBot())
#live.handle_tick()

live.update_bars()
live.update_account()
