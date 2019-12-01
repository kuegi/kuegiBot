
from market_maker.market_maker import ExchangeInterface
from market_maker.trade_engine import LiveTrading
from market_maker.kuegi_bot import KuegiBot
from market_maker.settings import settings

live= LiveTrading(KuegiBot(max_look_back=settings.KB_MAX_LOOK_BACK,
                           threshold_factor=settings.KB_THRESHOLD_FACTOR,
                           buffer_factor=settings.KB_BUFFER_FACTOR,
                           max_dist_factor=settings.KB_MAX_DIST_FACTOR,
                           max_swing_length=settings.KB_MAX_SWING_LENGTH,
                           max_channel_size_factor=settings.KB_MAX_CHANNEL_SIZE_FACTOR,
                           risk_factor=settings.KB_RISK_FACTOR,
                           entry_tightening=settings.KB_ENTRY_TIGHTENING,
                           bars_till_cancel_triggered=settings.KB_BARS_TILL_CANCEL_TRIGGERED,
                           stop_entry=settings.KB_STOP_ENTRY,
                           trail_to_swing=settings.KB_TRAIL_TO_SWING,
                           delayed_entry=settings.KB_DELAYED_ENTRY,
                           delayed_cancel=settings.KB_DELAYED_CANCEL
                           ))
# for breakpoints
a=1

live.run_loop()
#live.handle_tick()

