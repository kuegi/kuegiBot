from market_maker.trade_engine import BackTest, Bar, load_bars, process_low_tf_bars, prepare_plot
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
bars2= process_low_tf_bars(m1_bars, 240, 60)
bars3= process_low_tf_bars(m1_bars, 240, 120)
bars4= process_low_tf_bars(m1_bars, 240, 180)

bot=KuegiBot(
    max_look_back=13, threshold_factor=2.5, buffer_factor=-0.0618,
    max_dist_factor=1, max_swing_length=3,
    max_channel_size_factor=6, risk_factor=1000, entry_tightening=0.618,
    stop_entry=False, trail_to_swing=True, delayed_entry=False
)
BackTest(bot, bars1).run()
BackTest(bot, bars2).run()
BackTest(bot, bars3).run()
BackTest(bot, bars4).run()


bars1= process_low_tf_bars(m1_bars, 300, 0)
BackTest(bot, bars1).run()

''' results on 24 month test     
Fokus top curve (low underwater): 211  DD:32.8 rel:6.4 UW: 619 pos: 643
    max_look_back=13, threshold_factor=2.5, buffer_factor=-0.0618,
    max_dist_factor=1, max_swing_length=3,
    max_channel_size_factor=6, risk_factor=1000, entry_tightening=0.618,
    stop_entry=False, trail_to_swing=True, delayed_entry=False

Fokus on Profit/DD: 142 DD: 14.6 rel: 9.7 UW: 447 pos: 389
    max_look_back=13, threshold_factor=2.5, buffer_factor=-0.0618,
    max_dist_factor=1, max_swing_length=3,
    max_channel_size_factor=6, risk_factor=1000, entry_tightening=0,
    stop_entry=False, trail_to_swing=False, delayed_entry=True

'''