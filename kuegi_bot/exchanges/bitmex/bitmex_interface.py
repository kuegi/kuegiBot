from __future__ import absolute_import

from typing import List

from kuegi_bot.exchanges.bitmex import bitmex
from kuegi_bot.utils import constants, errors
from kuegi_bot.utils.trading_classes import Order, Account, Bar, ExchangeInterface, TickerData, AccountPosition, Symbol, \
    process_low_tf_bars,parse_utc_timestamp


class BitmexInterface(ExchangeInterface):
    def __init__(self,settings,logger,on_tick_callback=None):
        super().__init__(settings,logger,on_tick_callback)
        self.symbol = settings.SYMBOL
        self.bitmex= None
        self.bitmex = bitmex.BitMEX(settings= settings, logger= logger, symbol=self.symbol,
                                    apiKey=settings.API_KEY, apiSecret=settings.API_SECRET,
                                    timeout=settings.TIMEOUT, socketCallback=self._websocket_callback)

        self.h1Bars: List[Bar] = []
        self.init_h1_bars()

    def init_h1_bars(self):
        bars = self.bitmex.get_bars(timeframe='1h',start_time=None,reverse=True)
        self.h1Bars = []
        for b in bars:
            if b['open'] is None:
                continue
            self.h1Bars.append(self.barDictToBar(b,60))

    def exit(self):
        self.bitmex.exit()

    def internal_cancel_order(self, order:Order):
        self.bitmex.cancel_order(order.id)

    def internal_send_order(self, order:Order):
        self.bitmex.place_order(order)

    def internal_update_order(self, order:Order):
        self.bitmex.update_order(order)

    def get_orders(self) -> List[Order]:
        mexOrders= self.bitmex.open_orders()
        result :List[Order]= []
        for o in mexOrders:
            sideMulti= 1 if o["side"] == "Buy" else -1
            order = Order(orderId=o["clOrdID"],stop=o["stopPx"],limit=o["price"],amount=o["orderQty"]*sideMulti)
            order.stop_triggered= o["triggered"] == "StopOrderTriggered"
            order.executed_amount= (o["cumQty"])*sideMulti
            order.tstamp= parse_utc_timestamp(o['timestamp'])
            order.execution_tstamp= order.tstamp
            order.active= o['ordStatus'] == 'New'
            order.exchange_id= o["orderID"]
            order.executed_price= o["avgPx"]
            result.append(order)

        return result

    def _websocket_callback(self, table):
        if self.bitmex is None:
            #not started yet
            return
        if table == 'trade':
            trades = self.bitmex.recent_trades_and_clear()
            if len(self.h1Bars) == 0:
                return
            for trade in trades:
                tstamp = parse_utc_timestamp(trade['timestamp'])
                bar = self.h1Bars[0]
                if bar is not None and bar.last_tick_tstamp > tstamp:
                    continue #trade already counted
                barstamp = int(tstamp/(60*60))*60*60
                price = float(trade['price'])
                size= float(trade['size'])
                if bar is not None and barstamp == bar.tstamp:
                    bar.high = max(bar.high, price)
                    bar.low = min(bar.low, price)
                    bar.close = price
                    bar.volume = bar.volume+size
                    bar.last_tick_tstamp= tstamp
                elif len(self.h1Bars) == 0 or barstamp > bar.tstamp:
                    self.h1Bars.insert(0,Bar(tstamp=barstamp,
                                             open=price,
                                             high=price,
                                             low=price,
                                             close=price,
                                             volume=size))

        elif table == 'tradeBin1h':
            dicts = self.bitmex.recent_H1_bars()
            bars= []
            for d in dicts:
                bars.append(self.barDictToBar(d,60))
            bars.sort(key=lambda b: b.tstamp, reverse=False) # order with latest bar first
            # merge into self.h1Bars
            for b in bars:
                if b.tstamp > self.h1Bars[0].tstamp:
                    #newer than newest in history
                    self.h1Bars.insert(0,b)
                else:
                    for i in range(len(self.h1Bars)):
                        if b.tstamp == self.h1Bars[i].tstamp:
                            self.h1Bars[i]= b
                            break

        if self.on_tick_callback is not None and table in ["tradeBin1h", "order", "execution"]:
            self.on_tick_callback(fromAccountAction=table in ["order", "execution"])

    def get_bars(self,timeframe_minutes,start_offset_minutes)->List[Bar]:
        return process_low_tf_bars(self.h1Bars, timeframe_minutes, start_offset_minutes=start_offset_minutes)

    def recent_bars(self,timeframe_minutes,start_offset_minutes)->List[Bar]:
        return process_low_tf_bars(self.h1Bars, timeframe_minutes, start_offset_minutes=start_offset_minutes)

    def get_instrument(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        instrument = self.bitmex.instrument(symbol)
        symbolInfo:Symbol= Symbol(symbol= instrument['symbol'],
                                       isInverse=instrument['isInverse'],
                                       lotSize= instrument['lotSize'],
                                       tickSize=instrument['tickSize'],
                                       makerFee= instrument['makerFee'],
                                       takerFee= instrument['takerFee'])
        return symbolInfo

    def get_position(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        pos= self.bitmex.position(symbol)
        return AccountPosition(symbol,avgEntryPrice= pos["avgEntryPrice"],quantity=pos["currentQty"])

    def is_open(self):
        """Check that websockets are still open."""
        return not self.bitmex.ws.exited

    def check_market_open(self):
        instrument = self.get_instrument()
        if instrument["state"] != "Open" and instrument["state"] != "Closed":
            raise errors.MarketClosedError("The instrument %s is not open. State: %s" %
                                           (self.symbol, instrument["state"]))

    def get_ticker(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        data= self.bitmex.ticker_data(symbol)
        return TickerData(bid=data["buy"],ask=data["sell"],last=data["last"])

    def update_account(self,account:Account):
        funds = self.bitmex.funds()
        last= self.get_ticker().last
        account.open_position= self.get_position()
        account.open_position.walletBalance = convert_to_XBT(funds['walletBalance'], funds['currency'])
        account.equity = convert_to_XBT(funds['marginBalance'], funds['currency'])
        account.usd_equity= account.equity*last

    @staticmethod
    def barDictToBar(b, barLengthMinutes):
        if 'tstamp' not in b.keys():
            b['tstamp'] =  parse_utc_timestamp(b['timestamp']) - barLengthMinutes*60 # bitmex uses endtime for bar timestamp
        return Bar(tstamp=b['tstamp'], open=b['open'], high=b['high'], low=b['low'], close=b['close'],
                           volume=b['volume'])

#
# Helpers
#


def convert_to_XBT(value,currency):
    if currency == 'XBt':
        return float(value) / constants.XBt_TO_XBT
    else:
        return value


def XBt_to_XBT(XBt):
    return float(XBt) / constants.XBt_TO_XBT


def cost(instrument, quantity, price):
    mult = instrument["multiplier"]
    P = mult * price if mult >= 0 else mult / price
    return abs(quantity * P)


def margin(instrument, quantity, price):
    return cost(instrument, quantity, price) * instrument["initMargin"]

