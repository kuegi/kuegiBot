from market_maker.trade_engine import BackTest, Bar, load_bars, prepare_plot
from market_maker.indicator import SMA
from market_maker.random_bot import RandomBot
from market_maker.utils import log
from market_maker.kuegi_channel import KuegiChannel

from typing import List


logger = log.setup_custom_logger('backtest')

logger.info("loading bars")
bars:List[Bar]= load_bars(30*3,240)

forplot= bars[:]

logger.info("initializing indicators")
indis = [KuegiChannel()]

logger.info("preparing plot")
fig= prepare_plot(forplot, indis)
#fig.show()

# bot= RandomBot()
# backtest= BackTest(bot,bars)
# for i in range(5):
#   backtest.run()