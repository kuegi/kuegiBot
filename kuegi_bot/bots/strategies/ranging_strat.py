import math
from datetime import datetime
from typing import List
import plotly.graph_objects as go

from kuegi_bot.bots.strategies.channel_strat import ChannelStrategy
from kuegi_bot.bots.trading_bot import TradingBot, PositionDirection
from kuegi_bot.indicators.kuegi_channel import Data, clean_range
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType, Position, Order, PositionStatus
from kuegi_bot.indicators.indicator import Indicator, SMA, highest, lowest, BarSeries


class RangingStrategy(ChannelStrategy):
    def __init__(self, max_channel_size_factor: float = 6, min_channel_size_factor: float = 0,
                 entry_tightening=0, bars_till_cancel_triggered=3, limit_entry_offset_perc: float = None,
                 entry_range_fac_long: float = 0.05, entry_range_fac_short: float = 0.05, delayed_cancel: bool = False,
                 cancel_on_filter:bool = False, useSwings4Longs: bool = False, useTrail4SL: bool = False, maxPositions: int = 100,
                 tp_fac: float = 0, min_stop_diff_atr: float = 0, sl_fac_trail: float = 0.2, sl_fac_swing: float = 0.2,
                 sl_fac_trail4Swing: float = 0.9,
                 slowMA: int = 20, midMA: int = 18, fastMA: int = 16, veryfastMA: int = 14,
                 par_1: float = 1, var_2: float = 1):
        super().__init__()
        self.max_channel_size_factor = max_channel_size_factor
        self.min_channel_size_factor = min_channel_size_factor
        self.limit_entry_offset_perc = limit_entry_offset_perc
        self.entry_range_fac_long = entry_range_fac_long
        self.entry_range_fac_short = entry_range_fac_short
        self.useSwings4Longs = useSwings4Longs
        self.useTrail4SL = useTrail4SL
        self.entry_tightening = entry_tightening
        self.bars_till_cancel_triggered = bars_till_cancel_triggered
        self.delayed_cancel = delayed_cancel
        self.cancel_on_filter = cancel_on_filter
        self.tp_fac = tp_fac
        self.min_stop_diff_atr = min_stop_diff_atr
        self.sl_fac_trail = sl_fac_trail
        self.sl_fac_swing = sl_fac_swing
        self.sl_fac_trail4Swing = sl_fac_trail4Swing
        self.slowMA = slowMA
        self.midMA = midMA
        self.fastMA = fastMA
        self.veryfastMA = veryfastMA
        self.markettrend = MarketTrend(slowMA, midMA, fastMA, veryfastMA)
        self.var_2 = var_2
        self.par_1 = par_1
        self.maxPositions = maxPositions

    def myId(self):
        return "ranging"

    def init(self, bars: List[Bar], account: Account, symbol: Symbol):
        self.logger.info("init with %.0f %.1f %.1f %i %s %s %s %s %s %s %s %s" %
                         (self.max_channel_size_factor, self.min_channel_size_factor, self.entry_tightening,
                          self.bars_till_cancel_triggered, self.limit_entry_offset_perc, self.delayed_cancel,
                          self.cancel_on_filter, self.sl_fac_trail, self.slowMA, self.midMA, self.fastMA, self.veryfastMA))
        super().init(bars, account, symbol)
        self.markettrend.on_tick(bars)

    def prep_bars(self, is_new_bar: bool, bars: list):
        if is_new_bar:
            self.channel.on_tick(bars)
            self.markettrend.on_tick(bars)

    def position_got_opened_or_changed(self, position: Position, bars: List[Bar], account: Account, open_positions):
        other_id = TradingBot.get_other_direction_id(position.id)
        if other_id in open_positions.keys():
            open_positions[other_id].markForCancel = bars[0].tstamp

        # add stop
        gotStop = False  # safety check needed to not add multiple SL in case of an error
        gotTp = False
        for order in account.open_orders:
            orderType = TradingBot.order_type_from_order_id(order.id)
            posId = TradingBot.position_id_from_order_id(order.id)
            if orderType == OrderType.SL and posId == position.id:
                gotStop = True
                if abs(order.amount + position.current_open_amount) > self.symbol.lotSize / 2:
                    order.amount = -position.current_open_amount
                    self.order_interface.update_order(order)
            elif self.tp_fac > 0 and orderType == OrderType.TP and posId == position.id:
                gotTp = True
                amount = self.symbol.normalizeSize(-position.current_open_amount + order.executed_amount)
                if abs(order.amount - amount) > self.symbol.lotSize / 2:
                    order.amount = amount
                    self.order_interface.update_order(order)

        if not gotStop:
            order = Order(orderId=TradingBot.generate_order_id(positionId=position.id,
                                                               type=OrderType.SL),
                          stop=position.initial_stop,
                          amount=-position.amount)
            self.order_interface.send_order(order)

        if self.tp_fac > 0 and not gotTp:
            ref = position.filled_entry - position.initial_stop
            tp = max(0,position.filled_entry + ref * self.tp_fac)
            order = Order(orderId=TradingBot.generate_order_id(positionId=position.id,type=OrderType.TP),
                          limit=tp,amount=-position.amount)
            self.order_interface.send_order(order)

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        orderType = TradingBot.order_type_from_order_id(order.id)
        if orderType == OrderType.SL:
            for module in self.exitModules:
                module.manage_open_order(order, position, bars, to_update, to_cancel, open_positions)

        # check for triggered but not filled
        if order.stop_triggered:
            # clear other side
            other_id = TradingBot.get_other_direction_id(posId=position.id)
            if other_id in open_positions.keys():
                open_positions[other_id].markForCancel = bars[0].tstamp

            if not hasattr(position, 'waitingToFillSince'):
                position.waitingToFillSince = bars[0].tstamp
            if (bars[0].tstamp - position.waitingToFillSince) > self.bars_till_cancel_triggered * (
                    bars[0].tstamp - bars[1].tstamp):
                # cancel
                position.status = PositionStatus.MISSED
                position.exit_tstamp = bars[0].tstamp
                del open_positions[position.id]
                self.logger.info("canceling not filled position: " + position.id)
                to_cancel.append(order)

        # cancel if the trend has changed
        marketTrend = self.markettrend.get_market_trend()
        if orderType == OrderType.ENTRY and position.status == PositionStatus.PENDING and \
                ((self.cancel_on_filter and not self.entries_allowed(bars)) or
                 (position.amount > 0 and marketTrend == -1) or
                 (position.amount < 0 and marketTrend == 1)):
            self.logger.info("canceling cause channel got invalid: " + position.id)
            to_cancel.append(order)
            del open_positions[position.id]

    def manage_open_position(self, p, bars, account, pos_ids_to_cancel):
        # cancel marked positions
        if hasattr(p, "markForCancel") and p.status == PositionStatus.PENDING and (
                not self.delayed_cancel or p.markForCancel < bars[0].tstamp):
            self.logger.info("cancelling position, because marked for cancel: " + p.id)
            p.status = PositionStatus.CANCELLED
            pos_ids_to_cancel.append(p.id)

    def open_orders(self, is_new_bar, directionFilter, bars, account, open_positions, all_open_pos: dict):
        if (not is_new_bar) or len(bars) < 5:
            return  # only open orders on beginning of bar

        entriesAllowed = self.entries_allowed(bars)
        if not entriesAllowed:
            self.logger.info("new entries not allowed by filter")
            return

        data: Data = self.channel.get_data(bars[1])

        self.logger.info("---- analyzing: %s atr: %.1f buffer: %.1f swings: %s/%s trails: %.1f/%.1f resets:%i/%i" %
                         (str(datetime.fromtimestamp(bars[0].tstamp)),
                          data.atr, data.buffer,
                          ("%.1f" % data.longSwing) if data.longSwing is not None else "-",
                          ("%.1f" % data.shortSwing) if data.shortSwing is not None else "-",
                          data.longTrail, data.shortTrail, data.sinceLongReset, data.sinceShortReset))

        risk = self.risk_factor
        trailRange = data.shortTrail - data.longTrail

        if self.useSwings4Longs and data.shortSwing is not None:
            longEntry = self.symbol.normalizePrice(data.shortSwing- trailRange * self.entry_range_fac_long, roundUp=True)
            shortEntry = self.symbol.normalizePrice(data.shortTrail + trailRange * self.entry_range_fac_short, roundUp=False)

            if self.useTrail4SL or data.shortSwing is None or data.longSwing is None:
                stopLong = self.symbol.normalizePrice(longEntry - self.sl_fac_trail4Swing * trailRange,roundUp=False)
                stopShort = self.symbol.normalizePrice(shortEntry + self.sl_fac_trail * trailRange,roundUp=True)
            else:
                swingRange = data.longSwing - data.shortSwing
                stopLong = self.symbol.normalizePrice(longEntry - self.sl_fac_swing * swingRange, roundUp=False)
                stopShort = self.symbol.normalizePrice(shortEntry + self.sl_fac_trail * trailRange,roundUp=True)
        else:
            longEntry = self.symbol.normalizePrice(data.longTrail - trailRange * self.entry_range_fac_long, roundUp=True)
            shortEntry = self.symbol.normalizePrice(data.shortTrail + trailRange * self.entry_range_fac_short, roundUp=False)

            stopLong = self.symbol.normalizePrice(longEntry - self.sl_fac_trail * trailRange, roundUp=False)
            stopShort = self.symbol.normalizePrice(shortEntry + self.sl_fac_trail * trailRange, roundUp=True)

            if longEntry > bars[1].close:
                longEntry = bars[1].close - trailRange * self.par_1
                stopLong = self.symbol.normalizePrice(longEntry - trailRange, roundUp=False)
            elif shortEntry < bars[1].close:
                shortEntry = bars[1].close + trailRange * self.par_1
                stopShort = self.symbol.normalizePrice(shortEntry + trailRange, roundUp=True)

        marketTrend = self.markettrend.get_market_trend()

        expectedEntrySlippagePer = 0.0015 if self.limit_entry_offset_perc is None else 0
        expectedExitSlippagePer = 0.0015

        # first check if we should update an existing one
        longAmount = self.calc_pos_size(risk=risk, exitPrice=stopLong * (1 - expectedExitSlippagePer),
                                        entry=longEntry * (1 + expectedEntrySlippagePer),
                                        atr=data.atr)
        shortAmount = self.calc_pos_size(risk=risk, exitPrice=stopShort * (1 + expectedExitSlippagePer),
                                         entry=shortEntry * (1 - expectedEntrySlippagePer),
                                         atr=data.atr)
        if longEntry < stopLong or shortEntry > stopShort or longAmount < 0 or shortAmount > 0:
            self.logger.warn("can't put initial stop above entry")
            return

        foundLong = False
        foundShort = False
        for position in open_positions.values():
            if position.status == PositionStatus.PENDING:
                if position.amount > 0:
                    foundLong = True
                    entry = longEntry
                    stop = stopLong
                    entryFac = (1 + expectedEntrySlippagePer)
                    exitFac = (1 - expectedExitSlippagePer)
                else:
                    foundShort = True
                    entry = shortEntry
                    stop = stopShort
                    entryFac = (1 - expectedEntrySlippagePer)
                    exitFac = (1 + expectedExitSlippagePer)
                entryBuffer = entry * self.limit_entry_offset_perc * 0.01 if self.limit_entry_offset_perc is not None else None
                for order in account.open_orders:
                    if TradingBot.position_id_from_order_id(order.id) == position.id:
                        newEntry = position.wanted_entry * (
                                    1 - self.entry_tightening) + entry * self.entry_tightening
                        newEntry = self.symbol.normalizePrice(newEntry, roundUp=order.amount > 0)
                        newStop = position.initial_stop * (
                                    1 - self.entry_tightening) + stop * self.entry_tightening
                        newStop = self.symbol.normalizePrice(newStop, roundUp=order.amount < 0)
                        amount = self.calc_pos_size(risk=risk, exitPrice=newStop * exitFac,
                                                    entry=newEntry * entryFac, atr=data.atr)
                        if amount * order.amount < 0:
                            self.logger.warn("updating order switching direction")
                        changed = False
                        changed = changed or order.stop_price != newEntry
                        if changed:
                            self.logger.info("old entry: %.1f, new entry: %.1f" % (order.stop_price, newEntry))
                        order.stop_price = newEntry
                        if self.limit_entry_offset_perc is not None:
                            newLimit = newEntry - entryBuffer * math.copysign(1, amount)
                            changed = changed or order.limit_price != newLimit
                            if changed:
                                self.logger.info("old limit: %.1f, new limit: %.1f" % (order.limit_price, newLimit))
                            order.limit_price = newLimit
                        changed = changed or order.amount != amount
                        if changed:
                            self.logger.info("old amount: %.1f, new amount: %.1f" % (order.amount, amount))
                        order.amount = amount
                        if changed:
                            self.logger.info("changing order id: %s, amount: %.1f, stop price: %.1f, limit price: %.f, active: %s" %
                                             (order.id, order.amount, order.stop_price, order.limit_price, order.active))
                            self.order_interface.update_order(order)
                        else:
                            self.logger.info("order didn't change: %s" % order.print_info())

                        position.initial_stop = newStop
                        position.amount = amount
                        position.wanted_entry = newEntry
                        break

        signalId = self.get_signal_id(bars)
        if not foundLong and directionFilter >= 0 and entriesAllowed and (marketTrend == 0 or marketTrend == 1):
            posId = TradingBot.full_pos_id(signalId, PositionDirection.LONG)
            entryBuffer = longEntry * self.limit_entry_offset_perc * 0.01 if self.limit_entry_offset_perc is not None else None
            self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(posId, OrderType.ENTRY),
                                                  amount=longAmount, stop=longEntry,
                                                  limit=longEntry - entryBuffer if entryBuffer is not None else None))
            open_positions[posId] = Position(id=posId, entry=longEntry, amount=longAmount, stop=stopLong,
                                             tstamp=bars[0].tstamp)
        if not foundShort and directionFilter <= 0 and entriesAllowed and (marketTrend == 0 or marketTrend == -1):
            posId = TradingBot.full_pos_id(signalId, PositionDirection.SHORT)
            entryBuffer = shortEntry * self.limit_entry_offset_perc * 0.01 if self.limit_entry_offset_perc is not None else None
            self.order_interface.send_order(Order(orderId=TradingBot.generate_order_id(posId, OrderType.ENTRY),
                                                  amount=shortAmount, stop=shortEntry,
                                                  limit=shortEntry + entryBuffer if entryBuffer is not None else None))
            open_positions[posId] = Position(id=posId, entry=shortEntry, amount=shortAmount,
                                             stop=stopShort, tstamp=bars[0].tstamp)

    def add_to_plot(self, fig: go.Figure, bars: List[Bar], time):
        super().add_to_plot(fig, bars, time)
        lines = self.markettrend.get_number_of_lines()
        styles = self.markettrend.get_line_styles()
        names = self.markettrend.get_line_names()
        offset = 1
        self.logger.info("adding ranging")
        #for idx in range(0, lines):
        #    sub_data = list(map(lambda b: self.markettrend.get_data_for_plot(b)[idx], bars))
        #    fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[idx],
        #                    name=self.markettrend.id + "_" + names[idx])


class TrendData:
    def __init__(self,  trend, slowMA, midMA, fastMA, verfastMA):
        self.trend = trend
        self.slowMA = slowMA
        self.midMA = midMA
        self.fastMA = fastMA
        self.verfastMA = verfastMA


class MarketTrend(Indicator):
    ''' Market trend based on SMAs
    '''

    def __init__(self, slowMA: int, midMA: int, fastMA: int, veryfastMA: int):
        super().__init__('MarketTrend(' + str(slowMA) + ',' + str(midMA) + ',' + str(fastMA) + ',' + str(
            veryfastMA) + ')')
        self.slowMA = SMA(slowMA)
        self.midMA = SMA(midMA)
        self.fastMA = SMA(fastMA)
        self.veryfastMA = SMA(veryfastMA)
        self.markettrend = 0
        self.trend_buffer = 5

    def on_tick(self, bars: List[Bar]):
        self.slowMA.on_tick(bars)
        self.midMA.on_tick(bars)
        self.fastMA.on_tick(bars)
        self.veryfastMA.on_tick(bars)
        self.markettrend = self.calc_market_trend(bars)

    def get_market_trend(self):
        return self.markettrend

    def calc_market_trend(self, bars: List[Bar]):
        slowMA = self.slowMA.get_data(bars[1])
        midMA = self.midMA.get_data(bars[1])
        fastMA = self.fastMA.get_data(bars[1])
        veryfastMA = self.veryfastMA.get_data(bars[1])
        bar = bars[1]
        trend_buffer_threshold = 0
        buffer = 5

        if slowMA is not None and midMA is not None and fastMA is not None:
            if slowMA < midMA < fastMA < veryfastMA:
                self.trend_buffer -= 1
                if self.trend_buffer <= trend_buffer_threshold:
                    trend = 1  # bull
                else:
                    trend = 0  # ranging

                data = TrendData(trend * 1000, slowMA, midMA, fastMA, veryfastMA)
                self.write_data(bars[1], data)
                return trend
            elif slowMA > midMA > fastMA > veryfastMA:
                self.trend_buffer -= 1
                if self.trend_buffer <= trend_buffer_threshold:
                    trend = -1 # bear
                else:
                    trend = 0  # ranging

                data = TrendData(trend*1000, slowMA, midMA, fastMA, veryfastMA)
                self.write_data(bars[1], data)
                return trend
            else:
                trend = 0 # ranging
                self.trend_buffer = buffer # low pass filter for the ranging condition
                data = TrendData(trend * 1000, slowMA, midMA, fastMA, veryfastMA)
                self.write_data(bars[1],data)
                return trend
        else:
            trend = 0 #invalid
            self.trend_buffer = buffer
            data = TrendData(trend * 1000, bar.close, bar.close, bar.close, bar.close)
            self.write_data(bars[1], data)
            return trend

    def get_line_names(self):
        return ["MarketTrend",  "slowMA", "midMA", "fastMA", "verfastMA"]

    def get_number_of_lines(self):
        return 5

    def get_line_styles(self):
        return [{"width": 1, "color": "blue"},
                {"width": 1, "color": "red"},
                {"width": 1, "color": "orange"},
                {"width": 1, "color": "yellow"},
                {"width": 1, "color": "cyan"}]

    def get_data_for_plot(self, bar: Bar):
        data: TrendData = self.get_data(bar)
        if data is not None:
            return [data.trend, data.slowMA, data.midMA, data.fastMA, data.verfastMA]
        else:
            return [0, bar.close, bar.close, bar.close, bar.close]
