import json

from market_maker.exchange_interface import process_low_tf_bars
from market_maker.trade_engine import BackTest, TradingBot
from market_maker.random_bot import RandomBot
from market_maker.utils import log

logger = log.setup_custom_logger('backtest')

start = 33 # 33
end = 42
m1_bars= []
logger.info("loading "+str(end-start)+" history files")
for i in range(start, end+1):
    with open('history/M1_'+str(i)+'.json') as f:
        m1_bars += json.load(f)

bars= process_low_tf_bars(m1_bars,240)

bot= RandomBot()
backtest= BackTest(bot,bars)
for i in range(5):
    backtest.run()