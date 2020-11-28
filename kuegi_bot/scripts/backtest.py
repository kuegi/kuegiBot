import logging
import random

from kuegi_bot.backtest_engine import BackTest
from kuegi_bot.bots.MultiStrategyBot import MultiStrategyBot
from kuegi_bot.bots.strategies.MACross import MACross
from kuegi_bot.bots.strategies.entry_filters import DayOfWeekFilter
from kuegi_bot.bots.strategies.SfpStrat import SfpStrategy
from kuegi_bot.bots.strategies.exit_modules import SimpleBE, ParaTrail, MaxSLDiff
from kuegi_bot.bots.strategies.kuegi_strat import KuegiStrategy
from kuegi_bot.utils.helper import load_bars, prepare_plot, load_funding
from kuegi_bot.utils import log
from kuegi_bot.indicators.kuegi_channel import KuegiChannel
from kuegi_bot.utils.trading_classes import Symbol

logger = log.setup_custom_logger(log_level=logging.INFO)


def plot(bars):
    forplot= bars[:]

    logger.info("initializing indicators")
    indis = [KuegiChannel()]

    logger.info("preparing plot")
    fig= prepare_plot(forplot, indis)
    fig.show()


def backtest(bars):
    bots= []
    for bot in bots:
        BackTest(bot,bars).run()


def increment(min,max,steps,current)->bool:
    current[0] += steps[0]
    for idx in range(len(current)):
        if min[idx] <= current[idx] <= max[idx]:
            return True
        current[idx]= min[idx]
        if idx < len(current)-1:
            current[idx+1] += steps[idx+1]
        else:
            return False


def runOpti(bars,funding,min,max,steps,symbol= None, randomCount= -1):
    v= min[:]
    while len(steps) < len(min):
        steps.append(1)
    while True:
        msg= ""
        if randomCount > 0:
            for i in range(len(v)):
                v[i] = min[i] + random.randint(0, int((max[i] - min[i]) / steps[i])) * steps[i]
            randomCount = randomCount-1
        for i in v:
            msg += str(i) + " "
        logger.info(msg)
        bot = MultiStrategyBot(logger=logger, directionFilter=0)
        bot.add_strategy(KuegiStrategy(
                min_channel_size_factor=0, max_channel_size_factor=16,
                entry_tightening=1, bars_till_cancel_triggered=5,
                limit_entry_offset_perc=-0.15, delayed_entry=False, delayed_cancel=True, cancel_on_filter= False)
                 .withChannel(max_look_back=11, threshold_factor=v[0]*0.1, buffer_factor=-0.11, max_dist_factor=2,max_swing_length=4)
                 .withRM(risk_factor=1, max_risk_mul=2, risk_type=1, atr_factor=2)
                 .withExitModule(SimpleBE(factor=0.5, buffer=-0.2))
                 .withExitModule(SimpleBE(factor=1.2, buffer=0.5))
                 .withExitModule(ParaTrail(accInit=0.011, accInc=0.006, accMax=0.25,resetToCurrent=True))
                 .withEntryFilter(DayOfWeekFilter(63))
                         )
        BackTest(bot, bars= bars,funding=funding, symbol=symbol).run()

        if randomCount == 0 or (randomCount < 0 and not increment(min,max,steps,v)):
            break


def checkDayFilterByDay(bars,symbol= None):
    for i in range(7):
        msg = str(i)
        logger.info(msg)
        bot = MultiStrategyBot(logger=logger, directionFilter=0)
        bot.add_strategy(SfpStrategy()
                         .withEntryFilter(DayOfWeekFilter(1 << i))
                         )

        b= BackTest(bot, bars,symbol).run()

#pair= "BTCUSD"
pair= "ETHUSD"

funding = load_funding('bybit',pair)

#bars_p = load_bars(30 * 12, 240,0,'phemex')
#bars_n = load_bars(30 * 12, 240,0,'binance_f')
#bars_ns = load_bars(30 * 24, 240,0,'binanceSpot')
bars_b = load_bars(30 * 18, 240,0,'bybit',pair)
#bars_m = load_bars(30 * 12, 240,0,'bitmex')

#bars_b = load_bars(30 * 12, 60,0,'bybit')
#bars_m = load_bars(30 * 24, 60,0,'bitmex')

#bars1= load_bars(24)
#bars2= process_low_tf_bars(m1_bars, 240, 60)
#bars3= process_low_tf_bars(m1_bars, 240, 120)
#bars4= process_low_tf_bars(m1_bars, 240, 180)

symbol=None
if pair == "BTCUSD":
    symbol=Symbol(symbol="BTCUSD", isInverse=True, tickSize=0.5, lotSize=1.0, makerFee=-0.025,takerFee=0.075, quantityPrecision=2,pricePrecision=2)
elif pair == "XRPUSD":
    symbol=Symbol(symbol="XRPUSD", isInverse=True, tickSize=0.0001, lotSize=0.01, makerFee=-0.025,takerFee=0.075, quantityPrecision=2,pricePrecision=4)
elif pair == "ETHUSD":
    symbol=Symbol(symbol="ETHUSD", isInverse=True, tickSize=0.01, lotSize=0.1, makerFee=-0.025,takerFee=0.075, quantityPrecision=2,pricePrecision=2)
#
#for binance_f
#symbol=Symbol(symbol="BTCUSDT", isInverse=False, tickSize=0.001, lotSize=0.00001, makerFee=0.02, takerFee=0.04, quantityPrecision=5)

bars_full= bars_b
oos_cut=int(len(bars_full)/4)
bars= bars_full[oos_cut:]
bars_oos= bars_full[:oos_cut]


'''
checkDayFilterByDay(bars,symbol=symbol)

#'''

'''
# profiling stats
# run it `python -m cProfile -o profile.data backtest.py`

import pstats
from pstats import SortKey
p = pstats.Stats('profile.data')
p.strip_dirs() # remove extra paths

p.sort_stats(SortKey.CUMULATIVE).print_stats(20)
p.sort_stats(SortKey.TIME).print_stats(10)

p.print_callers('<functionName>')
'''

#'''
runOpti(bars_oos, funding=funding,
        min=   [17],
        max=   [22],
        steps= [1],
        randomCount=-1,
        symbol=symbol)

#'''


'''

bot=MultiStrategyBot(logger=logger, directionFilter= 0)
bot.add_strategy(KuegiStrategy(
    min_channel_size_factor=0, max_channel_size_factor=16,
    entry_tightening=1, bars_till_cancel_triggered=5,
    limit_entry_offset_perc=-0.15, delayed_entry=False, delayed_cancel=True, cancel_on_filter= False)
                 .withChannel(max_look_back=11, threshold_factor=1.8, buffer_factor=-0.11, max_dist_factor=2,max_swing_length=4)
                 .withRM(risk_factor=1, max_risk_mul=2, risk_type=1, atr_factor=2)
                 .withExitModule(SimpleBE(factor=0.5, buffer=-0.2))
                 .withExitModule(SimpleBE(factor=1.2, buffer=0.5))
                 .withExitModule(ParaTrail(accInit=0.011, accInc=0.006, accMax=0.25,resetToCurrent=True))
                 .withEntryFilter(DayOfWeekFilter(63))
                 )
bot.add_strategy(SfpStrategy(
    min_stop_diff_perc=0.5, ignore_on_tight_stop=False,
    init_stop_type=1, stop_buffer_fac=100, tp_fac=5,
    min_wick_fac=1.6, min_air_wick_fac= 0.1, min_wick_to_body=0.65,
    min_swing_length=10,
    range_length=35, min_rej_length= 30, range_filter_fac=0,
    close_on_opposite=False)
                 .withChannel(max_look_back=13, threshold_factor=0.8, buffer_factor=0.05, max_dist_factor=1,
                              max_swing_length=4)
                 .withRM(risk_factor=4, max_risk_mul=2, risk_type=0, atr_factor=1)
                 .withExitModule(SimpleBE(factor=0.6, buffer=0.2))
                 .withExitModule(SimpleBE(factor=0.8, buffer=0.5))
                 .withExitModule(SimpleBE(factor=1.4, buffer=0.9))
                 .withExitModule(SimpleBE(factor=1.5, buffer=1.1))
                 .withExitModule(SimpleBE(factor=1.9, buffer=1.2))
                 .withExitModule(ParaTrail(accInit=0.017, accInc=0.010, accMax=0.04,resetToCurrent=True))
                 .withEntryFilter(DayOfWeekFilter(63))
                 )

b= BackTest(bot, bars_full, funding=funding, symbol=symbol,market_slipage_percent=0.15).run()

#performance chart with lots of numbers
bot.create_performance_plot(bars).show()

# chart with signals:
b.prepare_plot().show()

#'''
