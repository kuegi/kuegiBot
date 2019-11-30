from market_maker.backtest_engine import BackTest
from market_maker.utils.helper import load_bars, prepare_plot
from market_maker.exchange_interface import process_low_tf_bars
from market_maker.utils import log
from market_maker.kuegi_channel import KuegiChannel
from market_maker.kuegi_bot import KuegiBot

from typing import List


logger = log.setup_custom_logger('backtest')

def plot(bars):
    forplot= bars[:]

    logger.info("initializing indicators")
    indis = [KuegiChannel()]

    logger.info("preparing plot")
    fig= prepare_plot(forplot, indis)
    fig.show()

def backtest(bars):
    bots= [KuegiBot(max_look_back=13, threshold_factor=3, buffer_factor=0.1,
                  max_dist_factor=1, max_swing_length=2,
                  max_channel_size_factor=6, risk_factor=1000, entry_tightening=1,
                  stop_entry=False, trail_to_swing=True, delayed_entry=True),
           KuegiBot(max_look_back=13, threshold_factor=3, buffer_factor=0.1,
                    max_dist_factor=1, max_swing_length=2,
                    max_channel_size_factor=6, risk_factor=1000, entry_tightening=1,
                    stop_entry=True, trail_to_swing=True, delayed_entry=True)]
    for bot in bots:
        BackTest(bot,bars).run()


logger.info("loading bars")
#bars: List[Bar] = load_bars(30 * 24, 240,60)
#backtest(bars)

import json


end = 42
start = end - int(24*30 * 1440 / 50000)
m1_bars = []
logger.info("loading " + str(end - start) + " history files")
for i in range(start, end + 1):
    with open('history/M1_' + str(i) + '.json') as f:
        m1_bars += json.load(f)
logger.info("done loading files, now preparing them")


bars1= process_low_tf_bars(m1_bars, 240, 0)
#bars2= process_low_tf_bars(m1_bars, 240, 60)
#bars3= process_low_tf_bars(m1_bars, 240, 120)
#bars4= process_low_tf_bars(m1_bars, 240, 180)

bot=KuegiBot(
    max_look_back=13, threshold_factor=2.5, buffer_factor=-0.0618,
    max_dist_factor=1, max_swing_length=3,
    max_channel_size_factor=6, risk_factor=1000, entry_tightening=1, bars_till_cancel_triggered=5,
    stop_entry=False, trail_to_swing=True, delayed_entry=False, delayed_cancel=False
)
BackTest(bot, bars1).run()

#BackTest(bot, bars1).run().prepare_plot().show()

#BackTest(bot, bars2).run()
#BackTest(bot, bars3).run()
#BackTest(bot, bars4).run()


#bars1= process_low_tf_bars(m1_bars, 300, 0)
#BackTest(bot, bars1).run()

''' results on 24 month test     
original: pos: 319 | profit: 69275 | maxDD: 40632 | rel: 1.70 | UW days: 218.5
    max_look_back=13, threshold_factor=0.9, buffer_factor=0.05,
    max_dist_factor=2, max_swing_length=3,
    max_channel_size_factor=6, risk_factor=1000, entry_tightening=1, bars_till_cancel_triggered=5,
    stop_entry=True, trail_to_swing=True, delayed_entry=True, delayed_cancel=True
    
Fokus low underwater: pos: 599 | profit: 182864 | maxDD: 36573 | rel: 5.00 | UW days: 102.5
    max_look_back=13, threshold_factor=2.5, buffer_factor=-0.0618,
    max_dist_factor=1, max_swing_length=3,
    max_channel_size_factor=6, risk_factor=1000, entry_tightening=0.618, bars_till_cancel_triggered=3,
    stop_entry=True, trail_to_swing=True, delayed_entry=False, delayed_cancel=True

Fokus on Profit/DD: pos: 341 | profit: 133345 | maxDD: 29100 | rel: 4.58 | UW days: 102.5
    max_look_back=13, threshold_factor=2.5, buffer_factor=-0.0618,
    max_dist_factor=1, max_swing_length=3,
    max_channel_size_factor=6, risk_factor=1000, entry_tightening=0,bars_till_cancel_triggered=3,
    stop_entry=True, trail_to_swing=False, delayed_entry=True, delayed_cancel=True

'''