import base64
import hmac
import hashlib
import json
import requests
import time

from math import trunc


class PhemexAPIException(Exception):

    def __init__(self, response):
        self.code = 0
        try:
            json_res = response.json()
        except ValueError:
            self.message = 'Invalid error message: {}'.format(response.text)
        else:
            if 'code' in json_res:
                self.code = json_res['code']
                self.message = json_res['msg']
            else:
                self.code = json_res['error']['code']
                self.message = json_res['error']['message']
        self.status_code = response.status_code
        self.response = response
        self.request = getattr(response, 'request', None)

    def __str__(self):  # pragma: no cover
        return 'HTTP(code=%s), API(errorcode=%s): %s' % (self.status_code, self.code, self.message)


class Client(object):
    MAIN_NET_API_URL = 'https://api.phemex.com'
    TEST_NET_API_URL = 'https://testnet-api.phemex.com'

    CURRENCY_BTC = "BTC"
    CURRENCY_USD = "USD"

    SYMBOL_BTCUSD = "BTCUSD"
    SYMBOL_ETHUSD = "ETHUSD"
    SYMBOL_XRPUSD = "XRPUSD"

    SIDE_BUY = "Buy"
    SIDE_SELL = "Sell"

    ORDER_TYPE_MARKET = "Market"
    ORDER_TYPE_LIMIT = "Limit"

    TIF_IMMEDIATE_OR_CANCEL = "ImmediateOrCancel"
    TIF_GOOD_TILL_CANCEL = "GoodTillCancel"
    TIF_FOK = "FillOrKill"

    ORDER_STATUS_NEW = "New"
    ORDER_STATUS_PFILL = "PartiallyFilled"
    ORDER_STATUS_FILL = "Filled"
    ORDER_STATUS_CANCELED = "Canceled"
    ORDER_STATUS_REJECTED = "Rejected"
    ORDER_STATUS_TRIGGERED = "Triggered"
    ORDER_STATUS_UNTRIGGERED = "Untriggered"

    def __init__(self, api_key=None, api_secret=None, is_testnet=False):
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_URL = self.MAIN_NET_API_URL
        if is_testnet:
            self.api_URL = self.TEST_NET_API_URL

        self.session = requests.session()

    @staticmethod
    def generate_signature(message, api_secret, body_string=None):
        expiry = trunc(time.time()) + 60
        message += str(expiry)
        if body_string is not None:
            message += body_string
        return [hmac.new(api_secret.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest(), expiry]

    def _send_request(self, method, endpoint, params={}, body={}):
        query_string = '&'.join(['{}={}'.format(k, v) for k, v in params.items()])
        message = endpoint + query_string
        body_str = ""
        if body:
            body_str = json.dumps(body, separators=(',', ':'))
        [signature, expiry] = self.generate_signature(message, self.api_secret, body_string=body_str)
        self.session.headers.update({
            'x-phemex-request-signature': signature,
            'x-phemex-request-expiry': str(expiry),
            'x-phemex-access-token': self.api_key,
            'Content-Type': 'application/json'})

        url = self.api_URL + endpoint
        if query_string:
            url += '?' + query_string
        response = self.session.request(method, url, data=body_str.encode())
        if not str(response.status_code).startswith('2'):
            raise PhemexAPIException(response)
        try:
            res_json = response.json()
        except ValueError:
            raise PhemexAPIException('Invalid Response: %s' % response.text)
        if "code" in res_json and res_json["code"] != 0:
            # accepted errorcodes
            if res_json['code'] in [10002]:
                res_json['data'] = None
            else:
                raise PhemexAPIException(response)
        if "error" in res_json and res_json["error"]:
            raise PhemexAPIException(response)
        return res_json

    def query_account_n_positions(self, currency: str):
        """
        https://github.com/phemex/phemex-api-docs/blob/master/Public-API-en.md#querytradeaccount
        """
        return self._send_request("get", "/accounts/accountPositions", {'currency': currency})

    def query_products(self):
        """
        https://github.com/phemex/phemex-api-docs/blob/master/Public-Contract-API-en.md#query-product-information
        """
        return self._send_request("get", "/v1/exchange/public/products", {})

    def query_kline(self, symbol: str, fromTimestamp: int, toTimestamp: int, resolutionSeconds: int):
        """
        """
        return self._send_request("get", "/phemex-user/public/md/kline",
                                  {"symbol": symbol,
                                   "from": fromTimestamp,
                                   "to": toTimestamp,
                                   "resolution": resolutionSeconds})

    def place_order(self, params={}):
        """
        https://github.com/phemex/phemex-api-docs/blob/master/Public-API-en.md#placeorder
        """
        return self._send_request("post", "/orders", body=params)

    def amend_order(self, symbol, orderID, params={}):
        """
        https://github.com/phemex/phemex-api-docs/blob/master/Public-API-en.md#622-amend-order-by-orderid
        """
        params["symbol"] = symbol
        params["orderID"] = orderID
        return self._send_request("put", "/orders/replace", params=params)

    def cancel_order(self, symbol, orderID):
        """
        https://github.com/phemex/phemex-api-docs/blob/master/Public-API-en.md#623-cancel-single-order
        """
        return self._send_request("delete", "/orders/cancel", params={"symbol": symbol, "orderID": orderID})

    def _cancel_all(self, symbol, untriggered_order=False):
        """
        https://github.com/phemex/phemex-api-docs/blob/master/Public-API-en.md#625-cancel-all-orders
        """
        return self._send_request("delete", "/orders/all",
                                  params={"symbol": symbol, "untriggered": str(untriggered_order).lower()})

    def cancel_all_normal_orders(self, symbol):
        self._cancel_all(symbol, untriggered_order=False)

    def cancel_all_untriggered_conditional_orders(self, symbol):
        self._cancel_all(symbol, untriggered_order=True)

    def cancel_all(self, symbol):
        self._cancel_all(symbol, untriggered_order=False)
        self._cancel_all(symbol, untriggered_order=True)

    def change_leverage(self, symbol, leverage=0):
        """
        https://github.com/phemex/phemex-api-docs/blob/master/Public-API-en.md#627-change-leverage
        """
        return self._send_request("PUT", "/positions/leverage", params={"symbol": symbol, "leverage": leverage})

    def change_risklimit(self, symbol, risk_limit=0):
        """
        https://github.com/phemex/phemex-api-docs/blob/master/Public-API-en.md#628-change-position-risklimit
        """
        return self._send_request("PUT", "/positions/riskLimit", params={"symbol": symbol, "riskLimit": risk_limit})

    def query_open_orders(self, symbol):
        """
        https://github.com/phemex/phemex-api-docs/blob/master/Public-API-en.md#6210-query-open-orders-by-symbol
        """
        return self._send_request("GET", "/orders/activeList", params={"symbol": symbol})

    def query_24h_ticker(self, symbol):
        """
        https://github.com/phemex/phemex-api-docs/blob/master/Public-API-en.md#633-query-24-hours-ticker
        """
        return self._send_request("GET", "/md/ticker/24hr", params={"symbol": symbol})
