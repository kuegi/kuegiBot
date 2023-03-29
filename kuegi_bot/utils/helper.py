import json
import logging
import sys
from datetime import datetime
from typing import List

from kuegi_bot.exchanges.binance_future.binancef_interface import BinanceFuturesInterface
from kuegi_bot.exchanges.bybit.bybit_interface import ByBitInterface
from kuegi_bot.exchanges.bybit_linear.bybitlinear_interface import ByBitLinearInterface
from kuegi_bot.exchanges.phemex.phemex_interface import PhemexInterface
from kuegi_bot.indicators.indicator import Indicator
from kuegi_bot.exchanges.bitmex.bitmex_interface import BitmexInterface
from kuegi_bot.utils import log

import plotly.graph_objects as go

from kuegi_bot.utils.dotdict import dotdict
from kuegi_bot.utils.trading_classes import Bar, process_low_tf_bars

logger = log.setup_custom_logger()


def load_settings_from_args():
    with open("settings/defaults.json") as f:
        settings = json.load(f)

    settingsPath = sys.argv[1] if len(sys.argv) > 1 else None
    if not settingsPath:
        return None

    print("Importing settings from %s" % settingsPath)
    with open(settingsPath) as f:
        userSettings = json.load(f)
        settings.update(userSettings)

    settings = dotdict(settings)

    if settings.LOG_LEVEL == "ERROR":
        settings.LOG_LEVEL = logging.ERROR
    elif settings.LOG_LEVEL == "WARN":
        settings.LOG_LEVEL = logging.WARN
    elif settings.LOG_LEVEL == "INFO":
        settings.LOG_LEVEL = logging.INFO
    elif settings.LOG_LEVEL == "DEBUG":
        settings.LOG_LEVEL = logging.DEBUG
    else:
        settings.LOG_LEVEL = logging.INFO

    return settings


def history_file_name(index, exchange,symbol='') :
    if len(symbol) > 0:
        symbol += "_"
    return 'history/' + exchange + '/' + symbol + 'M1_' + str(index) + '.json'


known_history_files= {
    "bitmex_XBTUSD": 49,
    "bybit_BTCUSD": 45,
    "bybit_ETHUSD":43,
    "bybit_XRPUSD":14,
    "bybit_BTCUSDM21":1,
    "bybit-linear_BTCUSDT":30,
    "bybit-linear_LINKUSDT":3,
    "bybit-linear_ETHUSDT":3,
    "bybit-linear_LTCUSDT":3,
    "binance_BTCUSDT": 9,
    "binanceSpot_BTCUSD": 28,
    "phemex_BTCUSD": 6,
    "bitstamp_btceur": 99,
    "bitstamp_etheur": 35,
    "bitstamp_xrpeur": 42,
    "bitstamp_eurusd": 94
    }


def load_funding(exchange='bybit',symbol='BTCUSD'):
    try:
        funding= None
        with open('history/' + exchange + '/' + symbol + '_funding.json') as f:
            fund= json.load(f)
            funding= {}
            for tstamp, value in fund.items():
                funding[int(tstamp)] = value
        return funding
    except Exception as e:
        return None


def load_bars(days_in_history, wanted_tf, start_offset_minutes=0,exchange='bybit',symbol='BTCUSD'):
    #empty symbol is legacy and means btcusd
    end = known_history_files[exchange+"_"+symbol]
    start = max(0,end - int(days_in_history * 1440 / 50000)-1)
    m1_bars_temp = []
    logger.info("loading " + str(end - start+1) + " history files from "+exchange)
    for i in range(start, end + 1):
        with open(history_file_name(i,exchange,symbol)) as f:
            m1_bars_temp += json.load(f)
    logger.info("done loading files, now preparing them")
    start = int(max(0,len(m1_bars_temp)-(days_in_history * 1440)))
    m1_bars = m1_bars_temp[start:]

    subbars: List[Bar] = []
    for b in m1_bars:
        if exchange == 'bybit':
            if b['open'] is None:
                continue
            subbars.append(ByBitInterface.barDictToBar(b))
        elif exchange == 'bybit-linear':
            if b['open'] is None:
                continue
            subbars.append(ByBitLinearInterface.barDictToBar(b))
        elif exchange == 'bitmex':
            if b['open'] is None:
                continue
            subbars.append(BitmexInterface.barDictToBar(b,wanted_tf))
        elif exchange in ['binance_future','binanceSpot']:
            subbars.append(BinanceFuturesInterface.barArrayToBar(b))
        elif exchange == 'phemex':
            subbars.append(PhemexInterface.barArrayToBar(b,10000))
    subbars.reverse()
    return process_low_tf_bars(subbars, wanted_tf, start_offset_minutes)


def prepare_plot(bars, indis: List[Indicator]):
    logger.info("calculating " + str(len(indis)) + " indicators on " + str(len(bars)) + " bars")
    for indi in indis:
        indi.on_tick(bars)

    logger.info("running timelines")
    time = list(map(lambda b: datetime.fromtimestamp(b.tstamp), bars))
    open = list(map(lambda b: b.open, bars))
    high = list(map(lambda b: b.high, bars))
    low = list(map(lambda b: b.low, bars))
    close = list(map(lambda b: b.close, bars))

    logger.info("creating plot")
    fig = go.Figure(data=[go.Candlestick(x=time, open=open, high=high, low=low, close=close, name="XBTUSD")])

    logger.info("adding indicators")
    for indi in indis:
        lines = indi.get_number_of_lines()
        offset = indi.get_plot_offset()
        for idx in range(0, lines):
            sub_data = list(map(lambda b: indi.get_data_for_plot(b)[idx], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line_width=1, name=indi.id + "_" + str(idx))

    fig.update_layout(xaxis_rangeslider_visible=False)
    return fig
