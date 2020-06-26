"""BitMEX API Connector."""
from __future__ import absolute_import
import requests
import time
import datetime
import json
import base64
import uuid
from kuegi_bot.exchanges.bitmex.auth import APIKeyAuthWithExpires
from kuegi_bot.utils import constants, errors
from kuegi_bot.exchanges.bitmex.ws.ws_thread import BitMEXWebsocket
from kuegi_bot.utils.trading_classes import Order


# https://www.bitmex.com/api/explorer/
class BitMEX(object):
    """BitMEX API Connector."""

    def __init__(self,logger,settings, symbol=None, apiKey=None, apiSecret=None,
                  shouldWSAuth=True, postOnly=False, timeout=7,socketCallback= None):
        """Init connector."""
        self.logger = logger
        base_url= "https://testnet.bitmex.com/api/v1/"
        if not settings.IS_TEST:
            base_url= "https://www.bitmex.com/api/v1/"
        self.base_url = base_url
        self.symbol = symbol
        self.postOnly = postOnly
        if (apiKey is None):
            raise Exception("Please set an API key and Secret to get started."
                            )
        self.apiKey = apiKey
        self.apiSecret = apiSecret
        self.retries = 0  # initialize counter

        # Prepare HTTPS session
        self.session = requests.Session()
        # These headers are always sent
        self.session.headers.update({'user-agent': 'kuegi-bot-'})
        self.session.headers.update({'content-type': 'application/json'})
        self.session.headers.update({'accept': 'application/json'})

        # Create websocket for streaming data
        self.ws = BitMEXWebsocket(settings=settings,logger=logger,callback=socketCallback)
        self.ws.connect(base_url, symbol, shouldAuth=shouldWSAuth)

        self.timeout = timeout

    def __del__(self):
        self.exit()

    def exit(self):
        self.ws.exit()


    #
    # Public methods
    #
    def ticker_data(self, symbol=None):
        """Get ticker data."""
        if symbol is None:
            symbol = self.symbol
        return self.ws.get_ticker(symbol)

    def instrument(self, symbol):
        """Get an instrument's details."""
        return self.ws.get_instrument(symbol)

    def instruments(self, filter=None):
        query = {}
        if filter is not None:
            query['filter'] = json.dumps(filter)
        return self._curl_bitmex(path='instrument', query=query, verb='GET')

    def market_depth(self, symbol):
        """Get market depth / orderbook."""
        return self.ws.market_depth(symbol)

    def recent_H1_bars(self):
        return self.ws.recent_H1_bars()

    def recent_trades_and_clear(self):
        """Get recent trades.

        Returns
        -------
        A list of dicts:
              {u'amount': 60,
               u'date': 1306775375,
               u'price': 8.7401099999999996,
               u'tid': u'93842'},

        """
        return self.ws.recent_trades_and_clear()

    #
    # Authentication required methods
    #
    def authentication_required(fn):
        """Annotation for methods that require auth."""

        def wrapped(self, *args, **kwargs):
            if not (self.apiKey):
                msg = "You must be authenticated to use this method"
                raise errors.AuthenticationError(msg)
            else:
                return fn(self, *args, **kwargs)

        return wrapped

    @authentication_required
    def funds(self):
        """Get your current balance."""
        return self.ws.funds()

    @authentication_required
    def position(self, symbol):
        """Get your open position."""
        return self.ws.position(symbol)

    @authentication_required
    def isolate_margin(self, symbol, leverage, rethrow_errors=False):
        """Set the leverage on an isolated margin position"""
        path = "position/leverage"
        postdict = {
            'symbol': symbol,
            'leverage': leverage
        }
        return self._curl_bitmex(path=path, postdict=postdict, verb="POST", rethrow_errors=rethrow_errors)

    @authentication_required
    def delta(self):
        return self.position(self.symbol)['homeNotional']


    @authentication_required
    def amend_bulk_orders(self, orders):
        """Amend multiple orders."""
        # Note rethrow; if this fails, we want to catch it and re-tick
        return self._curl_bitmex(path='order/bulk', postdict={'orders': orders}, verb='PUT', rethrow_errors=True)

    @authentication_required
    def create_bulk_orders(self, orders):
        """Create multiple orders."""
        for order in orders:
            order['clOrdID'] = self.orderIDPrefix + base64.b64encode(uuid.uuid4().bytes).decode('utf8').rstrip('=\n')
            order['symbol'] = self.symbol
            if self.postOnly:
                order['execInst'] = 'ParticipateDoNotInitiate'
        return self._curl_bitmex(path='order/bulk', postdict={'orders': orders}, verb='POST')

    @authentication_required
    def open_orders(self):
        """Get open orders."""
        return self.ws.open_orders()

    def get_bars(self, timeframe, start_time,reverse='true',silent=False):
        path = "trade/bucketed"
        return self._curl_bitmex(
            path=path,
            query={
                "binSize": timeframe,
                "partial": "true",
                "symbol": self.symbol,
                "reverse": reverse,
                'count': 1000,
                'startTime': start_time
            },
            verb="GET",
            silent= silent
        )

    def _curl_bitmex(self, path, query=None, postdict=None, timeout=None, verb=None, rethrow_errors=False,
                     max_retries=None,silent=False):
        """Send a request to BitMEX Servers."""
        # Handle URL
        url = self.base_url + path

        if timeout is None:
            timeout = self.timeout

        # Default to POST if data is attached, GET otherwise
        if not verb:
            verb = 'POST' if postdict else 'GET'

        # By default don't retry POST or PUT. Retrying GET/DELETE is okay because they are idempotent.
        # In the future we could allow retrying PUT, so long as 'leavesQty' is not used (not idempotent),
        # or you could change the clOrdID (set {"clOrdID": "new", "origClOrdID": "old"}) so that an amend
        # can't erroneously be applied twice.
        if max_retries is None:
            max_retries = 0 if verb in ['POST', 'PUT'] else 3

        # Auth: API Key/Secret
        auth = APIKeyAuthWithExpires(self.apiKey, self.apiSecret)

        def exit_or_throw(e):
            self.logger.error("error while sending to bitmex: %s, rethrow" % str(e))
            raise e

        def retry():
            self.retries += 1
            if self.retries > max_retries:
                self.logger.error("Max retries on %s (%s) hit, raising exception." % (path, json.dumps(postdict or '')))
                return False
            return self._curl_bitmex(path, query, postdict, timeout, verb, rethrow_errors, max_retries)

        # Make the request
        response = None
        try:
            if not silent:
                self.logger.info("sending req %s to %s: %s" % (verb, url, json.dumps(postdict or query or '')))
            req = requests.Request(verb, url, json=postdict, auth=auth, params=query)
            prepped = self.session.prepare_request(req)
            response = self.session.send(prepped, timeout=timeout)
            # Make non-200s throw
            response.raise_for_status()

        except requests.exceptions.HTTPError as e:
            if response is None:
                raise e

            # 401 - Auth error. This is fatal.
            if response.status_code == 401:
                self.logger.error("API Key or Secret incorrect, please check and restart.")
                self.logger.error("Error: " + response.text)
                if postdict:
                    self.logger.error(postdict)
                # Always exit, even if rethrow_errors, because this is fatal
                exit(1)

            # 404, can be thrown if order canceled or does not exist.
            elif response.status_code == 404:
                if verb == 'DELETE':
                    self.logger.error("Order not found: %s" % postdict['orderID'])
                    return
                self.logger.error("Unable to contact the BitMEX API (404). " +
                                  "Request: %s \n %s" % (url, json.dumps(postdict)))
                exit_or_throw(e)

            # 429, ratelimit; cancel orders & wait until X-RateLimit-Reset
            elif response.status_code == 429:
                self.logger.error("Ratelimited on current request. Sleeping, then trying again. Try fewer " +
                                  "order pairs or contact support@bitmex.com to raise your limits. " +
                                  "Request: %s \n %s" % (url, json.dumps(postdict)))

                # Figure out how long we need to wait.
                ratelimit_reset = response.headers['X-RateLimit-Reset']
                to_sleep = int(ratelimit_reset) - int(time.time())
                reset_str = datetime.datetime.fromtimestamp(int(ratelimit_reset)).strftime('%X')

                # We're ratelimited, and we may be waiting for a long time. Cancel orders.
                self.logger.warning("Canceling all known orders in the meantime.")
                self.cancel([o['orderID'] for o in self.open_orders()])

                self.logger.error("Your ratelimit will reset at %s. Sleeping for %d seconds." % (reset_str, to_sleep))
                time.sleep(to_sleep)

                # Retry the request.
                return retry()

            # 503 - BitMEX temporary downtime, likely due to a deploy. Try again
            elif response.status_code == 503:
                self.logger.warning("Unable to contact the BitMEX API (503), retrying. " +
                                    "Request: %s \n %s" % (url, json.dumps(postdict)))
                time.sleep(5)
                max_retries= max(self.retries+1,max_retries) #503 always allows a retry
                return retry()

            elif response.status_code == 400:
                error = response.json()['error']
                message = error['message'].lower() if error else ''

                # Duplicate clOrdID: that's fine, probably a deploy, go get the order(s) and return it
                if 'duplicate clordid' in message:
                    self.logger.error("Duplicate clOrderID with message: %s" % error['message'])
                    return False

                elif 'insufficient available balance' in message:
                    self.logger.error('Account out of funds. The message: %s' % error['message'])
                    exit_or_throw(Exception('Insufficient Funds'))

            # If we haven't returned or re-raised yet, we get here.
            self.logger.error("Unhandled Error: %s: %s" % (e, response.text))
            self.logger.error("Endpoint was: %s %s: %s" % (verb, path, json.dumps(postdict)))
            exit_or_throw(e)

        except requests.exceptions.Timeout as e:
            # Timeout, re-run this request
            self.logger.warning("Timed out on request: %s (%s), retrying..." % (path, json.dumps(postdict or '')))
            return retry()

        except requests.exceptions.ConnectionError as e:
            self.logger.warning("Unable to contact the BitMEX API (%s). Please check the URL. Retrying. " +
                                "Request: %s %s \n %s" % (e, url, json.dumps(postdict)))
            time.sleep(1)
            return retry()

        # Reset retry counter on success
        self.retries = 0

        return response.json()

    #################
    # my stuff
    @authentication_required
    def place_order(self, order: Order):
        """Place an order."""

        endpoint = "order"
        execInst= None
        type= 'Limit'
        if order.limit_price is not None:
            if order.stop_price is not None:
                type = 'StopLimit'
                execInst= "LastPrice"
            else:
                type= 'Limit'
        else:
            if order.stop_price is not None:
                type = 'Stop'
                execInst= "LastPrice"
            else:
                type= 'Market'

        postdict = {
            'symbol': self.symbol,
            'orderQty': order.amount,
            'price': order.limit_price,
            'stopPx': order.stop_price,
            'execInst': execInst,
            'clOrdID': order.id,
            'ordType': type
        }
        return self._curl_bitmex(path=endpoint, postdict=postdict, verb="POST")

    @authentication_required
    def update_order(self, order: Order):
        """update an order."""

        endpoint = "order"
        postdict = {
            'orderQty': order.amount,
            'price': order.limit_price,
            'stopPx': order.stop_price,
            'origClOrdID': order.id
        }
        return self._curl_bitmex(path=endpoint, postdict=postdict, verb="PUT")


    @authentication_required
    def cancel_order(self, orderID):
        """Cancel an existing order."""
        path = "order"
        postdict = {
            'clOrdID': orderID,
        }
        return self._curl_bitmex(path=path, postdict=postdict, verb="DELETE")
