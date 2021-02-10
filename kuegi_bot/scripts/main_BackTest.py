from kuegi_bot.backtest_engine import BackTest
from kuegi_bot.bots.MultiStrategyBot import MultiStrategyBot
from kuegi_bot.utils.helper import load_bars, prepare_plot, load_funding
from kuegi_bot.bots.strategies.kuegi_strat import KuegiStrategy
from kuegi_bot.bots.strategies.exit_modules import ParaTrail, SimpleBE, MaxSLDiff
from kuegi_bot.utils import log
from kuegi_bot.bots.strategies.SfpStrat import SfpStrategy
from kuegi_bot.utils.trading_classes import Symbol
from kuegi_bot.bots.strategies.MACross import MACross

logger = log.setup_custom_logger()

# Define Strategies
# Strategie (BTC)
#pair = "BTCUSD"
#bot=MultiStrategyBot(logger=logger, directionFilter= 0)
#bot.add_strategy(MACross(fastMA = 20, slowMA =140, swingBefore = 6, swingAfter = 30)
#                 .withRM(risk_factor=5, max_risk_mul=1.2, risk_type=2, atr_factor=4)
#                 )

#bot.add_strategy(KuegiStrategy(min_channel_size_factor=0, max_channel_size_factor=65, entry_tightening=0.5,
#                                       bars_till_cancel_triggered=2, delayed_entry=True, delayed_cancel=True,
#                                       cancel_on_filter=False, limit_entry_offset_perc=-0.06)
#                         .withChannel(max_look_back=19, threshold_factor=2.6, buffer_factor=-0.025, max_dist_factor=2.1,
#                                      max_swing_length=2)
#                         .withRM(risk_factor=5, max_risk_mul=1.2, risk_type=1, atr_factor=0)
#                         .withExitModule(SimpleBE(factor=0.2, buffer=-0.05, atrPeriod=0))
#                         .withExitModule(SimpleBE(factor=0.27, buffer=-0.039, atrPeriod=0))
#                         .withExitModule(SimpleBE(factor=0.6, buffer=0.0, atrPeriod=0))
#                         .withExitModule(SimpleBE(factor=1, buffer=0.12, atrPeriod=0))
#                         .withExitModule(SimpleBE(factor=3, buffer=0.6, atrPeriod=0))#
#                         .withExitModule(SimpleBE(factor=10, buffer=6.6, atrPeriod=0))
#                         .withExitModule(SimpleBE(factor=22, buffer=20, atrPeriod=0))
#                         .withExitModule(ParaTrail(accInit=0.049, accInc=0.05, accMax=0.027, resetToCurrent=True))
#                         )
#bot.add_strategy(
#            SfpStrategy(tp_fac=0, tp_use_atr=True, init_stop_type=1, stop_buffer_fac=23, min_wick_fac=1.2,
#                        min_swing_length=0, range_length=9, ignore_on_tight_stop=False, range_filter_fac=0.3,
#                        close_on_opposite=True, min_wick_to_body=0.73, min_rej_length=5, min_air_wick_fac=0.42,
#                        min_stop_diff_perc=0, entries=3)
#            .withChannel(max_look_back=19, threshold_factor=2.6, buffer_factor=-0.025, max_dist_factor=2.1,
#                         max_swing_length=2)
#            .withRM(risk_factor=5, max_risk_mul=1.2, risk_type=1, atr_factor=1.5)
#            .withExitModule(SimpleBE(factor=0.289, buffer=0.05, atrPeriod=0))
#            .withExitModule(SimpleBE(factor=0.73, buffer=0.2, atrPeriod=0))
#            .withExitModule(SimpleBE(factor=2, buffer=1.37, atrPeriod=0))
#            .withExitModule(SimpleBE(factor=4, buffer=1.75, atrPeriod=0))
#            .withExitModule(SimpleBE(factor=8, buffer=3.4, atrPeriod=0))
#            .withExitModule(SimpleBE(factor=16, buffer=15.6, atrPeriod=0))
#            .withExitModule(SimpleBE(factor=30, buffer=29, atrPeriod=0))
#            .withExitModule(ParaTrail(accInit=0.005, accInc=0.004, accMax=0.01, resetToCurrent=True))
#            )
#bars = load_bars(days_in_history = 50, wanted_tf= 240, start_offset_minutes = 0, exchange = 'bybit', symbol="BTCUSD")

# Strategie (ETH)
pair = "ETHUSD"
bot=MultiStrategyBot(logger=logger, directionFilter= 0)
#bot.add_strategy(MACross(fastMA=40, slowMA=140, swingBefore=17, swingAfter=23)
#                 .withRM(risk_factor=5, max_risk_mul=1.2, risk_type=2, atr_factor=4)
#                 )
bot.add_strategy(KuegiStrategy(min_channel_size_factor=0.7, max_channel_size_factor=10, entry_tightening=1,
                                       bars_till_cancel_triggered=0, delayed_entry=False, delayed_cancel=False,
                                       cancel_on_filter=False, limit_entry_offset_perc=-0.01)
                         .withChannel(max_look_back=5, threshold_factor=0.7, buffer_factor=-0.045, max_dist_factor=2.0,
                                      max_swing_length=2)
                         .withRM(risk_factor=5, max_risk_mul=1.2, risk_type=1, atr_factor=2.2)
                         .withExitModule(SimpleBE(factor=0.4, buffer=0.08, atrPeriod=0))
                         .withExitModule(SimpleBE(factor=3, buffer=1, atrPeriod=0))
                         .withExitModule(SimpleBE(factor=6, buffer=1.4, atrPeriod=0))
                         .withExitModule(SimpleBE(factor=12, buffer=5.5, atrPeriod=0))
                         .withExitModule(ParaTrail(accInit=0.06, accInc=0.05, accMax=0.021, resetToCurrent=True))
                 )
#bot.add_strategy(SfpStrategy(tp_fac=32, tp_use_atr=True, init_stop_type=1, stop_buffer_fac=22, min_wick_fac=0.2,
#                                     min_swing_length=0, range_length=5, ignore_on_tight_stop=False,range_filter_fac=0.3,
#                                     close_on_opposite=False, min_wick_to_body=0.74, min_rej_length=2,min_air_wick_fac=0.7,
#                                     min_stop_diff_perc=0, entries=3)
#                         .withChannel(max_look_back=5, threshold_factor=0.7, buffer_factor=-0.2, max_dist_factor=2,
#                                      max_swing_length=2)
#                         .withRM(risk_factor=3, max_risk_mul=1.2, risk_type=1, atr_factor=0.9)
#                         .withExitModule(SimpleBE(factor=0.1, buffer=-0.85, atrPeriod=0))
#                         .withExitModule(SimpleBE(factor=5, buffer=0.5, atrPeriod=0))
#                         .withExitModule(SimpleBE(factor=10, buffer=7.5, atrPeriod=0))
#                         .withExitModule(SimpleBE(factor=20, buffer=14, atrPeriod=0))
#                         .withExitModule(ParaTrail(accInit=0.5, accInc=0.004, accMax=0, resetToCurrent=True))
#                         )
bars = load_bars(days_in_history = 800, wanted_tf= 240, start_offset_minutes = 0, exchange = 'bybit', symbol="ETHUSD")

#oos_cut = int(len(bars_b) / 3)
#bars = bars_b[oos_cut:]
#bars_oos = bars_b[:oos_cut]

symbol=None
if pair == "BTCUSD":
    symbol=Symbol(symbol="BTCUSD", isInverse=True, tickSize=0.5, lotSize=1.0, makerFee=-0.025,takerFee=0.075, quantityPrecision=2,pricePrecision=2)
elif pair == "XRPUSD":
    symbol=Symbol(symbol="XRPUSD", isInverse=True, tickSize=0.0001, lotSize=0.01, makerFee=-0.025,takerFee=0.075, quantityPrecision=2,pricePrecision=4)
elif pair == "ETHUSD":
    symbol=Symbol(symbol="ETHUSD", isInverse=True, tickSize=0.01, lotSize=0.1, makerFee=-0.025,takerFee=0.075, quantityPrecision=2,pricePrecision=2)

funding = load_funding('bybit',pair)

# Run BackTest
b = BackTest(bot, bars= bars,funding=funding, symbol=symbol).run()

# Plot
#bot.create_performance_plot(bars).show()
#b.prepare_plot().show()
