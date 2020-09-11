from datetime import datetime
from typing import List

from kuegi_bot.exchanges.ExchangeWithWS import ExchangeWithWS
from kuegi_bot.exchanges.phemex.client import Client
from kuegi_bot.exchanges.phemex.phemex_websocket import PhemexWebsocket
from kuegi_bot.utils.trading_classes import Order, Bar, AccountPosition, Symbol


class PhemexInterface(ExchangeWithWS):

    def __init__(self, settings, logger, on_tick_callback=None):
        host = "wss://testnet.phemex.com/ws" if settings.IS_TEST else "wss://phemex.com/ws"
        ws = PhemexWebsocket(wsURLs=[host],
                             api_key=settings.API_KEY,
                             api_secret=settings.API_SECRET,
                             logger=logger,
                             callback=self.socket_callback,
                             symbol= settings.symbol,
                             minutesPerBar=settings.MINUTES_PER_BAR)

        self.priceScale = 10000
        self.valueScale = 100000000
        self.ratioScale = 100000000
        self.client = Client(is_testnet=settings.IS_TEST,
                             api_key=settings.API_KEY,
                             api_secret=settings.API_SECRET)
        super().__init__(settings, logger, ws=ws, on_tick_callback=on_tick_callback)

    def init(self):
        if self.symbol != "BTCUSD":
            self.valueScale = 10000
        self.get_instrument(self.symbol)
        super().init()

    def socket_callback(self, messageType, data):
        gotTick = False
        if messageType == "kline":
            if data["type"] == "snapshot":
                self.bars = []
                for k in sorted(data["kline"], key=lambda b: b[0], reverse=True):
                    self.bars.append(self.barArrayToBar(k, self.priceScale))
            else:  # incremental
                for k in sorted(data["kline"], key=lambda b: b[0], reverse=True):
                    bar = self.barArrayToBar(k, self.priceScale)
                    if self.bars[0].tstamp >= bar.tstamp >= self.bars[-1].tstamp:
                        # find bar to fix
                        for idx in range(0, len(self.bars)):
                            if bar.tstamp == self.bars[idx].tstamp:
                                self.bars[idx] = bar
                                break
                    elif bar.tstamp > self.bars[0].tstamp:
                        self.bars.insert(0, bar)
                        gotTick = True

            self.last = self.bars[0].close

        if messageType == "account":
            '''{"accounts":[{"accountBalanceEv":9992165009,"accountID":604630001,"currency":"BTC",
            "totalUsedBalanceEv":10841771568,"userID":60463}],"orders":[{"accountID":604630001,...}],"positions":[{
            "accountID":604630001,...}],"sequence":11450, "timestamp":<timestamp>, "type":"<type>"} '''

            # snapshots and incremental are handled the same
            walletBalance = None
            for account in data['accounts']:
                if account['currency'] == self.baseCurrency:
                    walletBalance = account['accountBalanceEv'] / self.valueScale

            for pos in data['positions']:
                entryPrice = pos["avgEntryPrice"] if "avgEntryPrice" in pos \
                    else pos['avgEntryPriceEp'] / self.priceScale
                if pos['symbol'] in self.positions:
                    gotTick = True
                    sizefac = -1 if pos["side"] == Client.SIDE_SELL else 1
                    accountPos = self.positions[pos['symbol']]
                    if accountPos.quantity != pos["size"] * sizefac:
                        self.logger.info("position changed %.2f -> %.2f" % (accountPos.quantity, pos["size"] * sizefac))
                    accountPos.quantity = pos["size"] * sizefac
                    accountPos.avgEntryPrice = entryPrice
                    if pos['currency'] == self.baseCurrency and walletBalance is not None:
                        accountPos.walletBalance = walletBalance
                else:
                    sizefac = -1 if pos["side"] == Client.SIDE_SELL else 1
                    balance = walletBalance if pos['currency'] == self.baseCurrency else 0
                    self.positions[pos['symbol']] = AccountPosition(pos['symbol'],
                                                                    avgEntryPrice=entryPrice,
                                                                    quantity=pos["size"] * sizefac,
                                                                    walletBalance=balance)

            for json_order in data['orders']:
                if 'ordStatus' in json_order:  # otherwise its SettleFunding
                    order = self.orderDictToOrder(json_order)
                    self.orders[order.exchange_id] = order
                    if data['type'] != "snapshot":
                        self.logger.info("got order update: %s" % str(order))
                    gotTick = True

        if gotTick and self.on_tick_callback is not None:
            self.on_tick_callback(fromAccountAction=messageType == "account")  # got something new

    def initOrders(self):
        apiOrders = self.client.query_open_orders(self.symbol)
        if apiOrders['data'] is not None:
            for json_order in apiOrders['data']['rows']:
                order = self.orderDictToOrder(json_order)
                self.orders[order.exchange_id] = order

        self.logger.info("got %i orders on startup" % len(self.orders))

    def initPositions(self):
        account = self.client.query_account_n_positions(self.baseCurrency)
        self.positions[self.symbol] = AccountPosition(self.symbol, 0, 0, 0)
        if account is not None:
            walletBalance = account['data']['account']['accountBalanceEv'] / self.valueScale
            for pos in account['data']['positions']:
                sizefac = -1 if pos["side"] == Client.SIDE_SELL else 1
                entryPrice = pos["avgEntryPrice"] if "avgEntryPrice" in pos \
                    else self.unscale_price(pos['avgEntryPriceEp'])
                self.positions[pos['symbol']] = AccountPosition(pos['symbol'],
                                                                avgEntryPrice=entryPrice,
                                                                quantity=pos["size"] * sizefac,
                                                                walletBalance=walletBalance)

    def scale_price(self, price):
        if price is None:
            return 0
        else:
            return int(price * self.priceScale)

    def unscale_price(self, scaledPrice):
        if scaledPrice is None:
            return None
        else:
            return scaledPrice / self.priceScale

    def noneIfZero(self, price, scaled=False):
        if price == 0:
            return None
        else:
            if scaled:
                return self.unscale_price(price)
            else:
                return price

    def internal_cancel_order(self, order: Order):
        if order.exchange_id in self.orders.keys():
            self.orders[order.exchange_id].active = False
        self.client.cancel_order(self.symbol, order.exchange_id)

    def internal_send_order(self, order: Order):
        order_type = "Market"
        if order.stop_price is not None and (self.last - order.stop_price) * order.amount >= 0:
            order.stop_price = None  # already triggered
        if order.limit_price is not None:
            if order.stop_price is not None:
                order_type = "StopLimit"
            else:
                order_type = "Limit"
        elif order.stop_price is not None:
            order_type = "Stop"
            if (order.stop_price >= self.last and order.amount < 0) or \
                    (order.stop_price <= self.last and order.amount > 0):  # prevent error of "would trigger immediatly"
                order_type = "Market"

        params = dict(symbol=self.symbol,
                      clOrdID=order.id,
                      side="Buy" if order.amount > 0 else "Sell",
                      orderQty=abs(order.amount),
                      ordType=order_type,
                      stopPxEp=self.scale_price(order.stop_price),
                      priceEp=self.scale_price(order.limit_price),
                      triggerType="ByLastPrice" if order.stop_price is not None else None
                      )
        result = self.client.place_order(params)
        if "data" in result.keys() and "orderID" in result["data"]["orderID"]:
            order.exchange_id = result["data"]["orderID"]

    def internal_update_order(self, order: Order):
        order_type = "Market"
        if order.stop_price is not None and (self.last - order.stop_price) * order.amount >= 0:
            order.stop_price = None  # already triggered
        if order.limit_price is not None:
            if order.stop_price is not None:
                order_type = "StopLimit"
            else:
                order_type = "Limit"
        elif order.stop_price is not None:
            order_type = "Stop"
            if (order.stop_price >= self.last and order.amount < 0) or \
                    (order.stop_price <= self.last and order.amount > 0):  # prevent error of "would trigger immediatly"
                order_type = "Market"

        params = dict(symbol=self.symbol,
                      side="Buy" if order.amount > 0 else "Sell",
                      orderQty=abs(order.amount),
                      ordType=order_type,
                      stopPxEp=self.scale_price(order.stop_price),
                      priceEp=self.scale_price(order.limit_price),
                      triggerType="ByLastPrice" if order.stop_price is not None else None
                      )
        self.client.amend_order(symbol=self.symbol, orderID=order.exchange_id, params=params)

    def get_bars(self, timeframe_minutes, start_offset_minutes) -> List[Bar]:
        tf = 1 if timeframe_minutes <= 60 else 60
        start = int(datetime.now().timestamp() - tf * 60 * 1000)
        klines = self.client.query_kline(self.symbol,
                                         fromTimestamp=start,
                                         toTimestamp=int(datetime.now().timestamp() + 10),
                                         resolutionSeconds=tf * 60)
        bars: List[Bar] = []
        for k in reversed(klines['data']['rows']):
            bars.append(self.barArrayToBar(k, self.priceScale))

        return self._aggregate_bars(bars, timeframe_minutes, start_offset_minutes)

    def get_instrument(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        api_symb = self.client.query_products()
        for symb in api_symb["data"]:
            if symb['symbol'] == symbol:
                settle = symb['settlementCurrency']
                self.priceScale = pow(10, symb['priceScale'])
                self.valueScale = pow(10, symb['valueScale'])
                self.ratioScale = pow(10, symb['ratioScale'])
                return Symbol(symbol=symb['symbol'],
                              isInverse=True if symbol[:len(settle)] else False,
                              lotSize=float(symb['lotSize']),
                              tickSize=float(symb['tickSize']),
                              makerFee=symb['makerFeeRateEr'] / self.ratioScale,
                              takerFee=symb['takerFeeRateEr'] / self.ratioScale)
        return None

    @staticmethod
    def barArrayToBar(kline, priceScale):
        return Bar(tstamp=kline[0],
                   open=kline[3] / priceScale,
                   high=kline[4] / priceScale,
                   low=kline[5] / priceScale,
                   close=kline[6] / priceScale,
                   volume=kline[7]
                   )

    def orderDictToOrder(self, o) -> Order:
        """
        {
                "bizError": 0,
                "orderID": "9cb95282-7840-42d6-9768-ab8901385a67",
                "clOrdID": "7eaa9987-928c-652e-cc6a-82fc35641706",
                "symbol": "BTCUSD",
                "side": "Buy",
                "actionTimeNs": 1580533011677666800,
                "transactTimeNs": 1580533011677666800,
                "orderType": null,
                "priceEp": 84000000,
                "price": 8400,
                "orderQty": 1,
                "displayQty": 1,
                "timeInForce": null,
                "reduceOnly": false,
                "stopPxEp": 0,
                "closedPnlEv": 0,
                "closedPnl": 0,
                "closedSize": 0,
                "cumQty": 0,
                "cumValueEv": 0,
                "cumValue": 0,
                "leavesQty": 0,
                "leavesValueEv": 0,
                "leavesValue": 0,
                "stopPx": 0,
                "stopDirection": "Falling",
                "ordStatus": "Untriggered"
            },
        """
        sideMult = -1 if o['side'] == Client.SIDE_SELL else 1
        stop = self.noneIfZero(o['stopPx']) if 'stopPx' in o else self.noneIfZero(o['stopPxEp'], True)
        price = self.noneIfZero(o['price']) if 'price' in o else self.noneIfZero(o['priceEp'], True)
        order = Order(orderId=o['clOrdID'],
                      stop=stop,
                      limit=price,
                      amount=o['orderQty'] * sideMult)
        order.exchange_id = o['orderID']
        order.tstamp = o['actionTimeNs'] / 1000000000
        order.active = o['ordStatus'] in [Client.ORDER_STATUS_NEW, Client.ORDER_STATUS_UNTRIGGERED,
                                          Client.ORDER_STATUS_TRIGGERED]
        order.executed_amount = o['cumQty'] * sideMult
        val = o['cumValue'] if 'cumValue' in o else o['cumValueEv'] / self.valueScale
        order.executed_price = o['cumQty'] / val if val != 0 else 0
        if order.executed_amount != 0:
            order.execution_tstamp = o['transactTimeNs'] / 1000000000
        order.stop_triggered = order.stop_price is not None and o['ordStatus'] == Client.ORDER_STATUS_TRIGGERED
        return order
