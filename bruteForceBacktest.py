import logging
import random
import csv
from datetime import date
import os

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
    total= 1
    while len(steps) < len(min):
        steps.append(1)
    for i in range(len(min)):
        total *= 1+(max[i]-min[i])/steps[i]
    logger.info("running %d combinations" % total)
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
        bot.add_strategy(KuegiStrategy()
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

        b = BackTest(bot, bars, symbol).run()


pair = "BTCUSD"
exchange = 'bybit'

tf = 240
monthsBack = 1

exchange = 'bybit-linear'

funding = load_funding(exchange, pair)

bars_b = load_bars(1116, tf, 0, 'bybit', pair)

symbol = Symbol(symbol="BTCUSD", isInverse=True, tickSize=0.5, lotSize=1.0, makerFee=-0.025, takerFee=0.075, quantityPrecision=2, pricePrecision=2)

profits = []

settings = {'min_channel_size_factor': 0,
            'max_channel_size_factor': 1,
            'entry_tightening': 1,
            'bars_till_cancel_triggered': 1,
            'limit_entry_offset_perc': -0.1,
            'delayed_entry': False,
            'delayed_cancel': False,
            'cancel_on_filter': False
            }
ints = ['min_channel_size_factor', 'max_channel_size_factor',
        'entry_tightening', 'bars_till_cancel_triggered']
header = ['min_channel_size_factor', 'max_channel_size_factor',
          'entry_tightening', 'bars_till_cancel_triggered',
          'limit_entry_offset_perc', 'delayed_entry',
          'delayed_cancel', 'cancel_on_filter']

market_conditions = {'accumulation': [[[2018, 11, 27], [2019, 4, 1]], [[2020, 5, 6], [2020, 10, 5]], [[2021, 2, 10], [2021, 5, 12]]],
                     'bull': [[[2019, 4, 4], [2019, 6, 30]], [[2020, 1, 3], [2020, 2, 17]], [[2020, 10, 15], [2021, 2, 9]], [[2021, 7, 21], [10, 11, 10]]],
                     'accumulation_down': [[[2019, 6, 19], [2019, 12, 30]], [[2021, 5, 20], [2021, 7, 20]]],
                     'down': [[[2020, 2, 17], [2020, 4, 22]], [[2021, 11, 11], [2021, 12, 18]]]
                     }
first_date = date(2018, 11, 27)
last_date = date(2021, 12, 18)

for j in market_conditions:
    for k in market_conditions[j]:
        days_under = date(k[0][0], k[0][1], k[0][2])
        delta_under = days_under-first_date
        bars_under = delta_under.days*6
        days_upper = date(k[1][0], k[1][1], k[1][2])
        delta_upper = days_upper-first_date
        bars_upper = delta_upper.days*6
        bars_full = bars_b[bars_under:bars_upper]
        bars = bars_full

        new_settings1 = settings
        combinations = []

        file_name = f'allSettingsResults_{j}_{days_under}.csv'
        try:
            os.makedirs(j)
        except Exception:
            pass

        f = open(j+'/'+file_name, 'w')

        # create the csv writer
        writer = csv.writer(f)

        # write a row to the csv file
        writer.writerow(header)

        # close the file
        f.close()
        for i in range(9):
            new_settings1['max_channel_size_factor'] += 1
            new_settings1['min_channel_size_factor'] = 0
            while new_settings1['min_channel_size_factor'] < new_settings1['max_channel_size_factor']:
                new_settings1['entry_tightening'] = 1
                new_settings1['min_channel_size_factor'] += 1
                while new_settings1['entry_tightening'] <= 10:
                    new_settings1['entry_tightening'] += 1
                    new_settings1['bars_till_cancel_triggered'] = 1
                    while new_settings1['bars_till_cancel_triggered'] < 6:
                        new_settings1['bars_till_cancel_triggered'] += 1
                        new_settings1['limit_entry_offset_perc'] = -0.1
                        while new_settings1['limit_entry_offset_perc'] < 1:
                            new_settings1['limit_entry_offset_perc'] -= 0.1
                            combi = [new_settings1['min_channel_size_factor'],
                                     new_settings1['max_channel_size_factor'],
                                     new_settings1['entry_tightening'],
                                     new_settings1['bars_till_cancel_triggered']]
                            if combi not in combinations:
                                properties = [*new_settings1.values()]
                                bot = MultiStrategyBot(logger=logger, directionFilter=0)
                                bot.reset()

                                bot.add_strategy(KuegiStrategy(min_channel_size_factor=properties[0], max_channel_size_factor=properties[1],
                                    entry_tightening=properties[2], bars_till_cancel_triggered=properties[3],
                                    limit_entry_offset_perc=properties[4], delayed_entry=properties[5], delayed_cancel=properties[6], cancel_on_filter=properties[7])
                                                 .withChannel(max_look_back=13, threshold_factor=1, buffer_factor=0.1, max_dist_factor=2, max_swing_length=4)
                                                 .withRM(risk_factor=1, max_risk_mul=2, risk_type=1, atr_factor=2)
                                                 .withExitModule(SimpleBE(factor=1, buffer=0))
                                                 .withExitModule(ParaTrail(accInit=0.02, accInc=0.02, accMax=0.2, resetToCurrent=False))
                                                 .withEntryFilter(DayOfWeekFilter(127))
                                                 )

                                b = BackTest(bot, bars, funding=funding, symbol=symbol, market_slipage_percent=0.15).run()

                                profit = b.profit
                                if float(profit) != 0.0:
                                    if len(profits) > 0:
                                        profit_most = max(profits)
                                    else:
                                        profits.append(float(profit))
                                        profit_most = float(profit)
                                    if profit >= profit_most:
                                        profits.append(profit)

                                        fields = [*settings.values()]
                                        fields.append(float(profit))
                                        with open(j+'/'+file_name, 'a') as f:
                                            writer = csv.writer(f)
                                            writer.writerow(fields)
                                        f.close()
                            else:
                                combinations.append(combi)

                    # performance chart with lots of numbers
                    #bot.create_performance_plot(bars).show()

                    # chart with signals:
                    #b.prepare_plot().show()
