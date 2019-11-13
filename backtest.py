from market_maker.trade_engine import BackTest, Bar, load_bars, prepare_plot
from market_maker.indicator import SMA
from market_maker.random_bot import RandomBot
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
    bot= KuegiBot()
    backtest= BackTest(bot,bars)
    backtest.run()


logger.info("loading bars")
bars: List[Bar] = load_bars(30 * 3, 240)
backtest(bars)