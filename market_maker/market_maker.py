from __future__ import absolute_import
from time import sleep
import sys
from datetime import datetime
from os.path import getmtime
import random
import requests
import atexit
import signal

from typing import List

from market_maker import bitmex
from market_maker.settings import settings
from market_maker.utils import log, constants, errors, math
from market_maker.utils.trading_classes import Order,Account,Bar
from market_maker.ws.ws_thread import OnTickHook
from market_maker.exchange_interface import process_low_tf_bars

# Used for reloading the bot - saves modified times of key files
import os
watched_files_mtimes = [(f, getmtime(f)) for f in settings.WATCHED_FILES]


#
# Helpers
#
logger = log.setup_custom_logger('root')


class ExchangeInterface:
    def __init__(self, dry_run=False,onTickHook:OnTickHook= None):
        self.dry_run = dry_run
        if len(sys.argv) > 1:
            self.symbol = sys.argv[1]
        else:
            self.symbol = settings.SYMBOL
        self.bitmex = bitmex.BitMEX(base_url=settings.BASE_URL, symbol=self.symbol,
                                    apiKey=settings.API_KEY, apiSecret=settings.API_SECRET,
                                    orderIDPrefix=settings.ORDERID_PREFIX, postOnly=settings.POST_ONLY,
                                    timeout=settings.TIMEOUT, onTickHook=onTickHook)

    def cancel_order(self, order:Order):
        tickLog = self.get_instrument()['tickLog']
        logger.info("Canceling: %s %f @ %.*f" % (order.id, order.amount, tickLog, order.limit_price))
        while True:
            try:
                self.bitmex.cancel_order(order.id)
                sleep(settings.API_REST_INTERVAL)
            except ValueError as e:
                logger.info(e)
                sleep(settings.API_ERROR_INTERVAL)
            else:
                break

    def send_order(self, order:Order):
        tickLog = self.get_instrument()['tickLog']
        logger.info("Placing: %s %f @ %.*f" % (order.id, order.amount,tickLog, order.limit_price))
        while True:
            try:
                self.bitmex.place_order(order)
                sleep(settings.API_REST_INTERVAL)
            except ValueError as e:
                logger.info(e)
                sleep(settings.API_ERROR_INTERVAL)
            else:
                break

    def update_order(self, order:Order):
        tickLog = self.get_instrument()['tickLog']
        logger.info("Updating: %s %f @ %.*f" % (order.id, order.amount, tickLog,order.limit_price))
        while True:
            try:
                self.bitmex.update_order(order)
                sleep(settings.API_REST_INTERVAL)
            except ValueError as e:
                logger.info(e)
                sleep(settings.API_ERROR_INTERVAL)
            else:
                break

    def get_orders(self) -> List[Order]:
        if self.dry_run:
            return []
        mexOrders= self.bitmex.open_orders()
        result :List[Order]= []
        for o in mexOrders:
            order = Order(orderId=o["clOrdID"],stop=o["stopPx"],limit=o["price"],amount=o["orderQty"])
            order.stop_triggered= o["triggered"] == "StopOrderTriggered"
            order.executed_amount= o["orderQty"] - o["leavesQty"]
            order.tstamp= datetime.strptime(o['timestamp'], '%Y-%m-%dT%H:%M:%S.%fZ').timestamp()
            order.active= o['ordStatus'] == 'New'
            order.exchange_id= o["orderID"]
            order.executed_price= o["avgPx"]
            result.append(order)

        return result

    def get_bars(self,timeframe_minutes,start_offset_minutes)->List[Bar]:
        bars = self.bitmex.get_bars(timeframe='1h',start_time=None,reverse=False)
        return process_low_tf_bars(bars,timeframe_minutes,start_offset_minutes=start_offset_minutes)

    def recent_bars(self,timeframe_minutes,start_offset_minutes)->List[Bar]:
        bars= self.bitmex.recent_H1_bars()
        return process_low_tf_bars(bars,timeframe_minutes,start_offset_minutes)

    def cancel_all_orders(self):
        if self.dry_run:
            return

        logger.info("Resetting current position. Canceling all existing orders.")
        tickLog = self.get_instrument()['tickLog']

        # In certain cases, a WS update might not make it through before we call this.
        # For that reason, we grab via HTTP to ensure we grab them all.
        orders = self.bitmex.http_open_orders()

        for order in orders:
            logger.info("Canceling: %s %d @ %.*f" % (order['side'], order['orderQty'], tickLog, order['price']))

        if len(orders):
            self.bitmex.cancel([order['orderID'] for order in orders])

        sleep(settings.API_REST_INTERVAL)

    def get_portfolio(self):
        contracts = settings.CONTRACTS
        portfolio = {}
        for symbol in contracts:
            position = self.bitmex.position(symbol=symbol)
            instrument = self.bitmex.instrument(symbol=symbol)

            if instrument['isQuanto']:
                future_type = "Quanto"
            elif instrument['isInverse']:
                future_type = "Inverse"
            elif not instrument['isQuanto'] and not instrument['isInverse']:
                future_type = "Linear"
            else:
                raise NotImplementedError("Unknown future type; not quanto or inverse: %s" % instrument['symbol'])

            if instrument['underlyingToSettleMultiplier'] is None:
                multiplier = float(instrument['multiplier']) / float(instrument['quoteToSettleMultiplier'])
            else:
                multiplier = float(instrument['multiplier']) / float(instrument['underlyingToSettleMultiplier'])

            portfolio[symbol] = {
                "currentQty": float(position['currentQty']),
                "futureType": future_type,
                "multiplier": multiplier,
                "markPrice": float(instrument['markPrice']),
                "spot": float(instrument['indicativeSettlePrice'])
            }

        return portfolio

    def calc_delta(self):
        """Calculate currency delta for portfolio"""
        portfolio = self.get_portfolio()
        spot_delta = 0
        mark_delta = 0
        for symbol in portfolio:
            item = portfolio[symbol]
            if item['futureType'] == "Quanto":
                spot_delta += item['currentQty'] * item['multiplier'] * item['spot']
                mark_delta += item['currentQty'] * item['multiplier'] * item['markPrice']
            elif item['futureType'] == "Inverse":
                spot_delta += (item['multiplier'] / item['spot']) * item['currentQty']
                mark_delta += (item['multiplier'] / item['markPrice']) * item['currentQty']
            elif item['futureType'] == "Linear":
                spot_delta += item['multiplier'] * item['currentQty']
                mark_delta += item['multiplier'] * item['currentQty']
        basis_delta = mark_delta - spot_delta
        delta = {
            "spot": spot_delta,
            "mark_price": mark_delta,
            "basis": basis_delta
        }
        return delta

    def get_delta(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        return self.get_position(symbol)['currentQty']

    def get_instrument(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        return self.bitmex.instrument(symbol)

    def get_margin(self):
        if self.dry_run:
            return {'marginBalance': float(settings.DRY_BTC), 'availableFunds': float(settings.DRY_BTC)}
        return self.bitmex.funds()

    def get_highest_buy(self):
        buys = [o for o in self.get_orders() if o['side'] == 'Buy']
        if not len(buys):
            return {'price': -2**32}
        highest_buy = max(buys or [], key=lambda o: o['price'])
        return highest_buy if highest_buy else {'price': -2**32}

    def get_lowest_sell(self):
        sells = [o for o in self.get_orders() if o['side'] == 'Sell']
        if not len(sells):
            return {'price': 2**32}
        lowest_sell = min(sells or [], key=lambda o: o['price'])
        return lowest_sell if lowest_sell else {'price': 2**32}  # ought to be enough for anyone

    def get_position(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        return self.bitmex.position(symbol)

    def get_ticker(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        return self.bitmex.ticker_data(symbol)

    def is_open(self):
        """Check that websockets are still open."""
        return not self.bitmex.ws.exited

    def check_market_open(self):
        instrument = self.get_instrument()
        if instrument["state"] != "Open" and instrument["state"] != "Closed":
            raise errors.MarketClosedError("The instrument %s is not open. State: %s" %
                                           (self.symbol, instrument["state"]))

    def check_if_orderbook_empty(self):
        """This function checks whether the order book is empty"""
        instrument = self.get_instrument()
        if instrument['midPrice'] is None:
            raise errors.MarketEmptyError("Orderbook is empty, cannot quote")

    def update_account(self,account:Account):
        funds = self.bitmex.funds()
        last= self.get_ticker()['last']
        account.open_position= self.get_position()['currentQty']
        account.balance = convert_to_XBT(funds['walletBalance'], funds['currency']) * last
        account.equity = convert_to_XBT(funds['marginBalance'], funds['currency']) * last
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

