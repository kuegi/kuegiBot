import json
from datetime import datetime
from typing import List

from market_maker.indicator import Indicator
from market_maker.exchange_interface import process_low_tf_bars
from market_maker.utils import log

import plotly.graph_objects as go

logger = log.setup_custom_logger('helper')


def load_bars(days_in_history, wanted_tf, start_offset_minutes=0):
    end = 42
    start = end - int(days_in_history * 1440 / 50000)
    m1_bars = []
    logger.info("loading " + str(end - start) + " history files")
    for i in range(start, end + 1):
        with open('history/M1_' + str(i) + '.json') as f:
            m1_bars += json.load(f)
    logger.info("done loading files, now preparing them")
    return process_low_tf_bars(m1_bars, wanted_tf, start_offset_minutes)


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
