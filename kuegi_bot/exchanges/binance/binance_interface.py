import time
from datetime import datetime
from typing import List

import binance_f
from binance_f import RequestClient
from binance_f.model import OrderSide, OrderType, TimeInForce, CandlestickInterval, SubscribeMessageType
from binance_f.model.accountupdate import Balance, Position
from binance_f.model.candlestickevent import Candlestick

from kuegi_bot.exchanges.binance.binance_websocket import BinanceWebsocket
from kuegi_bot.utils.trading_classes import ExchangeInterface, Order, Bar, Account, AccountPosition, \
    process_low_tf_bars, Symbol


class BinanceInterface(ExchangeInterface):

    def __init__(self, settings, logger, on_tick_callback=None):
        super().__init__(settings, logger, on_tick_callback)
        self.symbol: str = settings.SYMBOL
        self.client = RequestClient(api_key=settings.API_KEY,
                                    secret_key=settings.API_SECRET)
        self.ws = BinanceWebsocket(wsURL="wss://fstream.binance.com/ws",
                                   api_key=settings.API_KEY,
                                   api_secret=settings.API_SECRET,
                                   logger=logger,
                                   callback=self.callback)

        # for binance the key is the internal id (not the exchange id) cause we can't update order but have to cancel
        # and reopen with same id. that leads to different exchange id, but we need to know its the same.
        self.orders = {}
        self.positions = {}
        self.symbol_object: Symbol = None
        self.candles: List[Candlestick] = []
        self.last = 0
        self.listen_key = ""
        self.lastUserDataKeep = None
        self.wantedResponses = 0  # needed to wait for realtime
        self.init()

    def init(self):
        self.logger.info("loading market data. this may take a moment")
        self.initOrders()
        self.initPositions()
        self.symbol_object = self.get_instrument()
        self.logger.info("got all data. subscribing to live updates.")
        self.listen_key = self.client.start_user_data_stream()
        self.lastUserDataKeep = time.time()
        self.wantedResponses = 2
        subInt = CandlestickInterval.MIN1 if self.settings.MINUTES_PER_BAR <= 60 else CandlestickInterval.HOUR1
        self.ws.subscribe_candlestick_event(self.symbol.lower(), subInt)
        self.ws.subscribe_user_data_event(self.listen_key)
        waitingTime = 0
        while self.wantedResponses > 0 and waitingTime < 100:
            waitingTime += 1
            time.sleep(0.1)

        if self.wantedResponses > 0:
            self.logger.error("got no response to subscription. outa here")
            self.ws.exit()
        else:
            self.logger.info("ready to go")

    def callback(self, data_type: 'SubscribeMessageType', event: 'any'):
        gotTick = False
        fromAccount = False
        # refresh userdata every 5 min
        if self.lastUserDataKeep < time.time() - 5 * 60:
            self.lastUserDataKeep = time.time()
            self.client.keep_user_data_stream()

        if data_type == SubscribeMessageType.RESPONSE:
            self.wantedResponses -= 1  # tell the waiting init that we got it. otherwise we might be too fast
        elif data_type == SubscribeMessageType.PAYLOAD:
            if event.eventType == "kline":
                # {'eventType': 'kline', 'eventTime': 1587064627164, 'symbol': 'BTCUSDT',
                # 'data': <binance_f.model.candlestickevent.Candlestick object at 0x0000016B89856760>}
                if event.symbol == self.symbol:
                    candle: Candlestick = event.data
                    if len(self.candles) > 0:
                        if self.candles[0].startTime >= candle.startTime > self.candles[-1].startTime:
                            # somewhere inbetween to replace
                            for idx in range(0, len(self.candles)):
                                if candle.startTime == self.candles[idx].startTime:
                                    self.candles[idx] = candle
                                    break
                        elif candle.startTime > self.candles[0].startTime:
                            self.candles.insert(0, candle)
                            gotTick = True
                    else:
                        self.candles.append(candle)
                        gotTick = True
            elif event.eventType == "ACCOUNT_UPDATE":
                # {'eventType': 'ACCOUNT_UPDATE', 'eventTime': 1587063874367, 'transactionTime': 1587063874365,
                # 'balances': [<binance_f.model.accountupdate.Balance object at 0x000001FAF470E100>,...],
                # 'positions': [<binance_f.model.accountupdate.Position object at 0x000001FAF470E1C0>...]}
                usdBalance = 0
                gotTick = True
                fromAccount = True
                for b in event.balances:
                    bal: Balance = b
                    if bal.asset == "USDT":
                        usdBalance = bal.walletBalance
                for p in event.positions:
                    pos: Position = p
                    if pos.symbol not in self.positions.keys():
                        self.positions[pos.symbol] = AccountPosition(
                            symbol=pos.symbol,
                            avgEntryPrice=float(pos.entryPrice),
                            quantity=float(pos.amount),
                            walletBalance=usdBalance if "USDT" in pos.symbol else 0)
                    else:
                        accountPos = self.positions[pos.symbol]
                        accountPos.quantity = float(pos.amount)
                        accountPos.avgEntryPrice = float(pos.entryPrice)
                        if "USDT" in pos.symbol:
                            accountPos.walletBalance = usdBalance

            elif event.eventType == "ORDER_TRADE_UPDATE":
                # {'eventType': 'ORDER_TRADE_UPDATE', 'eventTime': 1587063513592, 'transactionTime': 1587063513589,
                # 'symbol': 'BTCUSDT', 'clientOrderId': 'web_ybDNrTjCi765K3AvOMRK', 'side': 'BUY', 'type': 'LIMIT',
                # 'timeInForce': 'GTC', 'origQty': 0.01, 'price': 6901.0, 'avgPrice': 0.0, 'stopPrice': 0.0,
                # 'executionType': 'NEW', 'orderStatus': 'NEW', 'orderId': 2705199704, 'lastFilledQty': 0.0,
                # 'cumulativeFilledQty': 0.0, 'lastFilledPrice': 0.0, 'commissionAsset': None, 'commissionAmount': None,
                # 'orderTradeTime': 1587063513589, 'tradeID': 0, 'bidsNotional': 138.81, 'asksNotional': 0.0,
                # 'isMarkerSide': False, 'isReduceOnly': False, 'workingType': 'CONTRACT_PRICE'}
                gotTick = True
                fromAccount = True
                sideMulti = 1 if event.side == 'BUY' else -1
                order: Order = Order(orderId=event.clientOrderId,
                                     stop=event.stopPrice if event.stopPrice > 0 else None,
                                     limit=event.price if event.price > 0 else None,
                                     amount=event.origQty * sideMulti
                                     )
                order.exchange_id = event.orderId
                # trigger of a stoplimit in Binance means "update for order -> expired" then "update -> as limit"
                order.stop_triggered = event.type == "LIMIT" and event.stopPrice > 0
                order.executed_amount = event.cumulativeFilledQty * sideMulti
                order.executed_price = event.avgPrice
                order.tstamp = event.transactionTime
                order.execution_tstamp = event.orderTradeTime / 1000
                order.active = event.orderStatus in ["NEW", "PARTIALLY_FILLED"]

                prev: Order = self.orders[order.id] if order.id in self.orders.keys() else None
                if prev is not None:
                    if prev.tstamp > order.tstamp or abs(prev.executed_amount) > abs(order.executed_amount):
                        # already got newer information, probably the info of the stop order getting
                        # triggered, when i already got the info about execution
                        self.logger.info("ignoring delayed update for %s " % prev.id)
                    if order.stop_price is None:
                        order.stop_price = prev.stop_price
                    if order.limit_price is None:
                        order.limit_price = prev.limit_price
                prev = order
                if not prev.active and prev.execution_tstamp == 0:
                    prev.execution_tstamp = datetime.utcnow().timestamp()
                self.orders[order.id] = prev

                self.logger.info("received order update: %s" % (str(order)))
        else:
            self.logger.warn("Unknown Data in websocket callback")

        if gotTick and self.on_tick_callback is not None:
            self.on_tick_callback(fromAccountAction=fromAccount)  # got something new

    def initOrders(self):
        apiOrders = self.client.get_open_orders()
        for o in apiOrders:
            order = self.convertOrder(o)
            if order.active:
                self.orders[order.id] = order

    @staticmethod
    def convertOrder(apiOrder: binance_f.model.Order) -> Order:
        direction = 1 if apiOrder.side == OrderSide.BUY else -1
        order = Order(orderId=apiOrder.clientOrderId,
                      amount=apiOrder.origQty * direction,
                      limit=apiOrder.price if apiOrder.price > 0 else None,
                      stop=apiOrder.stopPrice if apiOrder.stopPrice > 0 else None)
        order.executed_amount = apiOrder.executedQty * direction
        order.executed_price = apiOrder.avgPrice
        order.active = apiOrder.status in ["NEW", "PARTIALLY_FILLED"]
        order.exchange_id = apiOrder.orderId
        return order

    def initPositions(self):
        balance = self.client.get_balance()
        usdBalance = 0
        for bal in balance:
            if bal.asset == "USDT":
                usdBalance = bal.balance
        api_positions = self.client.get_position()
        self.positions[self.symbol] = AccountPosition(self.symbol,
                                                      avgEntryPrice=0,
                                                      quantity=0,
                                                      walletBalance=usdBalance if "USDT" in self.symbol else 0)
        if api_positions is not None:
            for pos in api_positions:
                self.positions[pos.symbol] = AccountPosition(pos.symbol,
                                                             avgEntryPrice=pos.entryPrice,
                                                             quantity=pos.positionAmt,
                                                             walletBalance=usdBalance if "USDT" in pos.symbol else 0)

        self.logger.info(
            "starting with %.2f in wallet and pos  %.2f @ %.2f" % (self.positions[self.symbol].walletBalance,
                                                                   self.positions[self.symbol].quantity,
                                                                   self.positions[self.symbol].avgEntryPrice))

    def exit(self):
        self.ws.exit()
        self.client.close_user_data_stream()

    def internal_cancel_order(self, order: Order):
        if order.id in self.orders.keys():
            self.orders[order.id].active = False
        self.client.cancel_order(symbol=self.symbol, origClientOrderId=order.id)

    def internal_send_order(self, order: Order):
        if order.limit_price is not None:
            order.limit_price = round(order.limit_price, self.symbol_object.pricePrecision)
            if order.stop_price is not None:
                order.stop_price = round(order.stop_price, self.symbol_object.pricePrecision)
                order_type = OrderType.STOP
            else:
                order_type = OrderType.LIMIT
        elif order.stop_price is not None:
            order.stop_price = round(order.stop_price, self.symbol_object.pricePrecision)
            order_type = OrderType.STOP_MARKET
        else:
            order_type = OrderType.MARKET

        order.amount = round(order.amount, self.symbol_object.quantityPrecision)
        quantityFormat = "{:." + str(self.symbol_object.quantityPrecision) + "f}"
        priceFormat = "{:." + str(self.symbol_object.pricePrecision) + "f}"
        # yes have to send the price and quantity in as str (although it wants float) cause otherwise it converts it
        # inernally and that sometimes fuck up the precision (0.023 -> 0.02299999999)
        resultOrder: binance_f.model.Order = self.client.post_order(
            symbol=self.symbol,
            side=OrderSide.BUY if order.amount > 0 else OrderSide.SELL,
            ordertype=order_type,
            timeInForce=TimeInForce.GTC if order_type in [OrderType.LIMIT, OrderType.STOP] else None,
            quantity=quantityFormat.format(abs(order.amount)),
            price=priceFormat.format(order.limit_price) if order.limit_price is not None else None,
            stopPrice=priceFormat.format(order.stop_price) if order.stop_price is not None else None,
            newClientOrderId=order.id)
        order.exchange_id = resultOrder.orderId

    def internal_update_order(self, order: Order):
        self.cancel_order(order)  # stupid binance can't update orders
        self.on_tick_callback(True)  # triggers a reset of the tick-delay.
        # otherwise we risk a tick to be calced after the cancel, before the new order
        self.send_order(order)
        self.on_tick_callback(True)  # triggers a reset of the tick-delay

    def get_orders(self) -> List[Order]:
        return list(self.orders.values())

    def get_bars(self, timeframe_minutes, start_offset_minutes) -> List[Bar]:
        tf = CandlestickInterval.MIN1 if timeframe_minutes <= 60 else CandlestickInterval.HOUR1

        bars = self.client.get_candlestick_data(symbol=self.symbol, interval=tf, limit=1000)

        subbars = []
        for b in reversed(bars):
            subbars.append(self.convertBar(b))
        return process_low_tf_bars(subbars, timeframe_minutes, start_offset_minutes)

    def recent_bars(self, timeframe_minutes, start_offset_minutes) -> List[Bar]:
        subbars = []
        for b in self.candles:
            subbars.append(self.convertBarevent(b))
        return process_low_tf_bars(subbars, timeframe_minutes, start_offset_minutes)

    @staticmethod
    def convertBar(apiBar: binance_f.model.candlestick.Candlestick):
        return Bar(tstamp=apiBar.openTime / 1000, open=float(apiBar.open), high=float(apiBar.high),
                   low=float(apiBar.low),
                   close=float(apiBar.close),
                   volume=float(apiBar.volume))

    @staticmethod
    def convertBarevent(apiBar: binance_f.model.candlestickevent.Candlestick):
        return Bar(tstamp=apiBar.startTime / 1000, open=float(apiBar.open), high=float(apiBar.high),
                   low=float(apiBar.low),
                   close=float(apiBar.close),
                   volume=float(apiBar.volume))

    @staticmethod
    def barArrayToBar(b):
        return Bar(tstamp=b[0] / 1000, open=float(b[1]), high=float(b[2]), low=float(b[3]),
                   close=float(b[4]), volume=float(b[5]))

    def get_instrument(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        instr: binance_f.model.exchangeinformation.ExchangeInformation = self.client.get_exchange_information()
        for symb in instr.symbols:
            if symb.symbol == symbol:
                baseLength = len(symb.baseAsset)
                lotSize = 0
                tickSize = 0
                for filterIt in symb.filters:
                    if filterIt['filterType'] == 'LOT_SIZE':
                        lotSize = filterIt['stepSize']
                    if filterIt['filterType'] == 'PRICE_FILTER':
                        tickSize = filterIt['tickSize']

                return Symbol(symbol=symb.symbol,
                              isInverse=symb.baseAsset != symb.symbol[:baseLength],
                              lotSize=lotSize,
                              tickSize=tickSize,
                              makerFee=0.02,
                              takerFee=0.04,
                              pricePrecision=symb.pricePrecision,
                              quantityPrecision=symb.quantityPrecision)
        return None

    def get_position(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        return self.positions[symbol] if symbol in self.positions.keys() else None

    def is_open(self):
        return not self.ws.exited

    def check_market_open(self):
        return self.is_open()

    def update_account(self, account: Account):
        pos = self.positions[self.symbol]
        account.open_position = pos
        account.equity = pos.walletBalance
        account.usd_equity = account.equity
