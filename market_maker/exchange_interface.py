from time import sleep
import sys

from datetime import datetime

from market_maker import bitmex
from market_maker.bitmex import OnTickHook
from market_maker.settings import settings
from market_maker.utils import log, errors
from market_maker.trade_engine import Bar

logger = log.setup_custom_logger('root')

def process_low_tf_bars(bars,timeframe_minutes,start_offset_minutes= 0):
    result: list = []
    for b in bars:
        if 'tstamp' not in b.keys():
            b['tstamp'] = datetime.strptime(b['timestamp'], '%Y-%m-%dT%H:%M:%S.%fZ').timestamp()
        bar_start = int((b['tstamp']-start_offset_minutes*60) / (60 * timeframe_minutes)) * (60 * timeframe_minutes)
        if result and result[-1].tstamp == bar_start:
            # add to bar
           result[-1].add_subbar(b)
        else:
            # create new bar
            result.append(Bar(tstamp=bar_start, open=b['open'], high=b['high'], low=b['low'], close=b['close'],
                              volume=b['volume'], subbars=[b]))

    # sort subbars
    for bar in result:
        bar.subbars.sort(key=lambda b: b['tstamp'], reverse=True)

    result.reverse()
    return result

class ExchangeInterface(OnTickHook):
    def __init__(self, dry_run=False,timeframes=[], onTickHook:OnTickHook=None):
        self.dry_run = dry_run
        self.bitmex= None
        self.onTickHook= onTickHook
        if len(sys.argv) > 1:
            self.symbol = sys.argv[1]
        else:
            self.symbol = settings.SYMBOL
        self.bitmex = bitmex.BitMEX(base_url=settings.BASE_URL, symbol=self.symbol,
                                    apiKey=settings.API_KEY, apiSecret=settings.API_SECRET,
                                    orderIDPrefix=settings.ORDERID_PREFIX, postOnly=settings.POST_ONLY,
                                    timeout=settings.TIMEOUT, onTickHook=self)

        #keep track of bar history so we dont have to request all the time
        self.bars={}
        for tf in timeframes:
            if tf < 60:
                logger.error("currently only timeframes above 1 hour are supported!")

            self.bars[str(tf)] = self.get_bars(tf,0)

    def tick_happened(self):
        if not self.bitmex:
            return

        #update bars
        trades= self.bitmex.recent_trades()

        for key in self.bars :
            pass

        if self.onTickHook :
            self.onTickHook.tick_happened()

    def cancel_order(self, order):
        tickLog = self.get_instrument()['tickLog']
        logger.info("Canceling: %s %d @ %.*f" % (order['side'], order['orderQty'], tickLog, order['price']))
        while True:
            try:
                self.bitmex.cancel(order['orderID'])
                sleep(settings.API_REST_INTERVAL)
            except ValueError as e:
                logger.info(e)
                sleep(settings.API_ERROR_INTERVAL)
            else:
                break

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

    def get_orders(self):
        if self.dry_run:
            return []
        return self.bitmex.open_orders()

    def get_bars(self, timeframe_minutes, start_time) -> list:
        '''returns the history bars for the given timeframe'''
        # available timeframes: [1m,5m,1h,1d]
        # so we need to get the best lower timeframe and aggregate
        timeframe = '1m'
        actual_tf_minutes = 1
        if timeframe_minutes < 5:
            timeframe = '1m'
            actual_tf_minutes = 1
        elif timeframe_minutes < 60:
            timeframe = '5m'
            actual_tf_minutes = 5
        elif timeframe_minutes < 1440:
            timeframe = '1h'
            actual_tf_minutes = 60
        else:
            timeframe = '1d'
            actual_tf_minutes = 1440

        bars = self.bitmex.get_bars(timeframe,start_time,reverse='false')
        # aggregate bars
        return process_low_tf_bars(bars,timeframe_minutes)

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

    def amend_bulk_orders(self, orders):
        if self.dry_run:
            return orders
        return self.bitmex.amend_bulk_orders(orders)

    def create_bulk_orders(self, orders):
        if self.dry_run:
            return orders
        return self.bitmex.create_bulk_orders(orders)

    def cancel_bulk_orders(self, orders):
        if self.dry_run:
            return orders
        return self.bitmex.cancel([order['orderID'] for order in orders])

def init():
    e= ExchangeInterface(False)
    return e