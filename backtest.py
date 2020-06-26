import random

from kuegi_bot.backtest_engine import BackTest
from kuegi_bot.bots.MultiStrategyBot import MultiStrategyBot
from kuegi_bot.bots.strategies.entry_filters import DayOfWeekFilter
from kuegi_bot.bots.strategies.SfpStrat import SfpStrategy
from kuegi_bot.bots.strategies.exit_modules import SimpleBE, ParaTrail
from kuegi_bot.bots.strategies.kuegi_strat import KuegiStrategy
from kuegi_bot.utils.helper import load_bars, prepare_plot
from kuegi_bot.utils import log
from kuegi_bot.indicators.kuegi_channel import KuegiChannel
from kuegi_bot.utils.trading_classes import Symbol

logger = log.setup_custom_logger()


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


def runOpti(bars,min,max,steps,symbol= None, randomCount= -1):
    v= min[:]
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
        bot.add_strategy(SfpStrategy()
                         )
        BackTest(bot, bars,symbol).run()

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

bars_p = load_bars(30 * 12, 240,0,'phemex')
#bars_n = load_bars(30 * 12, 240,0,'binance')
#bars_ns = load_bars(30 * 24, 240,0,'binanceSpot')
#bars_b = load_bars(30 * 18, 240,0,'bybit')
#bars_m = load_bars(30 * 12, 240,0,'bitmex')

#bars_b = load_bars(30 * 12, 60,0,'bybit')
#bars_m = load_bars(30 * 24, 60,0,'bitmex')

#bars1= load_bars(24)
#bars2= process_low_tf_bars(m1_bars, 240, 60)
#bars3= process_low_tf_bars(m1_bars, 240, 120)
#bars4= process_low_tf_bars(m1_bars, 240, 180)

#runOpti(bars_m,[1],[63],[1])

'''
checkDayFilterByDay(bars_n,
    symbol=Symbol(symbol="BTCUSDT", isInverse=False, tickSize=0.001, lotSize=0.00001, makerFee=0.02,
                                     takerFee=0.04))

#'''

'''
runOpti(bars_n,
        min=   [6,0.2,5,50,25,-0.5],
        max=   [16,0.8,15,90,45,0.5],
        steps= [2,0.1,1,5,2,0.1],
        symbol=Symbol(symbol="BTCUSDT", isInverse=False, tickSize=0.001,
                                      lotSize=0.00001, makerFee=0.02,
                                     takerFee=0.04),
        randomCount=1000)

#'''


'''
bot=MultiStrategyBot(logger=logger, directionFilter= 0)
bot.add_strategy(KuegiStrategy(
...
                 )
                 
bot.add_strategy(SfpStrategy(
...
                 )
b= BackTest(bot, bars_b).run()

#binance is not inverse: needs different symbol:

b= BackTest(bot, bars_n,
        symbol=Symbol(symbol="BTCUSDT", isInverse=False, tickSize=0.001, lotSize=0.00001, makerFee=0.02,
                                     takerFee=0.04, quantityPrecision=5)).run()

#performance chart with lots of numbers
bot.create_performance_plot().show()

# chart with signals:
b.prepare_plot().show()

#'''
