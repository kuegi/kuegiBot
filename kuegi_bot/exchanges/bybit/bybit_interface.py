import logging
import math
from datetime import datetime

from typing import List

import pybit
from pybit.unified_trading import HTTP

from kuegi_bot.exchanges.bybit.bybit_websocket import BybitWebsocket
from kuegi_bot.utils.trading_classes import Order, Bar, TickerData, AccountPosition, \
    Symbol, process_low_tf_bars, parse_utc_timestamp
from ..ExchangeWithWS import ExchangeWithWS
from kuegi_bot.bots.trading_bot import TradingBot
from kuegi_bot.utils.trading_classes import OrderType


def strOrNone(input):
    if input is None:
        return None
    else:
        return str(input)


class ByBitInterface(ExchangeWithWS):

    def __init__(self, settings, logger, on_tick_callback=None, on_api_error=None, on_execution_callback=None):
        self.on_api_error = on_api_error
        self.pybit = HTTP(testnet = settings.IS_TEST, api_key=settings.API_KEY, api_secret=settings.API_SECRET)
        logging.basicConfig(filename="pybit.log", level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")
        #hosts = ["wss://stream-testnet.bybit.com/realtime"] if settings.IS_TEST \
        #    else ["wss://stream.bybit.com/realtime", "wss://stream.bytick.com/realtime"]
        self.longPos = AccountPosition(settings.SYMBOL, 0, 0, 0)
        self.shortPos = AccountPosition(settings.SYMBOL, 0, 0, 0)
        super().__init__(settings, logger,
                         ws=BybitWebsocket(wsURLs=None,
                                           api_key=settings.API_KEY,
                                           api_secret=settings.API_SECRET,
                                           logger=logger,
                                           callback=self.socket_callback,
                                           symbol=settings.SYMBOL,
                                           minutesPerBar=settings.MINUTES_PER_BAR),
                         on_tick_callback=on_tick_callback,
                         on_execution_callback= on_execution_callback)
        self.handles_executions= True

    def is_open(self):
        # ws is always a BybitLinearWebsocket which has a publicWS
        return not self.ws.exited and not self.ws.public.exited

    def initOrders(self):
        apiOrders = self.handle_result(lambda:self.pybit.get_open_orders(category = 'inverse', symbol=self.symbol, orderFilter = 'Order')).get("list")
        conditionalOrders = self.handle_result(lambda:self.pybit.get_open_orders(category = 'inverse', symbol=self.symbol, orderFilter = 'StopOrder')).get("list")
        tpslOrders = self.handle_result(lambda: self.pybit.get_open_orders(category='inverse', symbol=self.symbol, orderFilter='tpslOrder')).get("list")
        apiOrders += conditionalOrders
        apiOrders += tpslOrders
        self.processOrders(apiOrders)

        for order in self.orders.values():
            self.logger.debug(str(order))

    def initPositions(self):
        api_positions= self.handle_result(lambda: self.pybit.get_positions(category = 'inverse', symbol=self.symbol)).get("list")
        api_wallet = self.handle_result(lambda: self.pybit.get_wallet_balance(accountType="CONTRACT", coin=self.baseCurrency)).get("list")
        for coin in api_wallet[0]['coin']:
            if coin['coin'] == self.baseCurrency:
                balance = float(coin['walletBalance'])
                break
        self.longPos = AccountPosition(self.symbol, 0, 0, balance)
        self.shortPos = AccountPosition(self.symbol, 0, 0, balance)
        if api_positions is not None:
            for pos in api_positions:
                if pos["side"] == "Sell":
                    self.shortPos.avgEntryPrice = float(pos["avgPrice"])
                    self.shortPos.quantity = -1 * float(pos["size"])
                else:
                    self.longPos.avgEntryPrice = float(pos["avgPrice"])
                    self.longPos.quantity = float(pos["size"])
        self.updatePosition_internally()

    def updatePosition_internally(self):
        if self.longPos.quantity > -self.shortPos.quantity:
            entry = self.longPos.avgEntryPrice
        else:
            entry = self.shortPos.avgEntryPrice

        if self.symbol in self.positions.keys() and \
                self.positions[self.symbol].quantity != self.longPos.quantity + self.shortPos.quantity:
            self.logger.info("position changed %.2f -> %.2f" % (
                self.positions[self.symbol].quantity, self.longPos.quantity + self.shortPos.quantity))

        self.positions[self.symbol] = AccountPosition(self.symbol,
                                                      quantity=self.longPos.quantity + self.shortPos.quantity,
                                                      avgEntryPrice=entry,
                                                      walletBalance=self.longPos.walletBalance)

    def internal_cancel_order(self, order: Order):
        if order.exchange_id in self.orders.keys():
            self.orders[order.exchange_id].active = False
        result = self.handle_result(lambda:self.pybit.cancel_order(category='inverse',order_id=order.exchange_id, symbol=self.symbol))
        self.logger.info("cancel order result:: %s" % (str(result)))

    def internal_send_order(self, order: Order):

        if order.trigger_price is not None:
            # conditional
            # types: entry / stop-limit, SL, TP, etc.
            # execution type: Market and Limit
            if self.last < order.trigger_price:
                triggerDirection = 1
            else:
                triggerDirection = 2

            if (self.last - order.trigger_price) * order.amount >= 0:
                # condition is already true
                order.trigger_price = None

        if order.limit_price is not None:
            # limit order
            # types: entry / stop-limit, (TP)
            # execution type: Limit
            order_type = "Limit"
        else:
            # execution type: Market
            order_type = "Market"

        if order.trigger_price is not None:
            if self.last < order.trigger_price:
                triggerDirection = 1
            else:
                triggerDirection = 2

        orderType = TradingBot.order_type_from_order_id(order.id)
        if orderType == OrderType.ENTRY:
            if order.trigger_price is not None:
                # conditional order
                result = self.handle_result(lambda:self.pybit.place_order(
                    side=("Buy" if order.amount > 0 else "Sell"),
                    category="inverse",
                    symbol=self.symbol,
                    orderType=order_type,
                    qty=strOrNone(int(abs(order.amount))),
                    price=strOrNone(order.limit_price),
                    triggerDirection = int(triggerDirection),
                    triggerPrice=strOrNone(order.trigger_price),
                    orderLinkId=order.id,
                    timeInForce="GTC"))
                if result is not None:
                    order.exchange_id = result['orderId']
            else:
                result =  self.handle_result(lambda:self.pybit.place_order(
                    side=("Buy" if order.amount > 0 else "Sell"),
                    symbol=self.symbol,
                    category = "inverse",
                    orderType=order_type,
                    qty=strOrNone(int(abs(order.amount))),
                    price=strOrNone(order.limit_price),
                    orderLinkId=order.id,
                    timeInForce="GTC"))
                if result is not None:
                    order.exchange_id = result['orderId']
        elif orderType == OrderType.SL:
            if order.trigger_price is not None:
                # conditional order
                result = self.handle_result(lambda: self.pybit.place_order(
                    side=("Buy" if order.amount > 0 else "Sell"),
                    category="inverse",
                    symbol=self.symbol,
                    orderType=order_type,
                    slOrderType = "Market",
                    qty=strOrNone(int(abs(order.amount))),
                    triggerDirection=int(triggerDirection),
                    triggerPrice=strOrNone(order.trigger_price),
                    tpslMode = "Full",
                    orderLinkId=order.id,
                    timeInForce="GTC"))
                if result is not None:
                    order.exchange_id = result['orderId']

    def internal_update_order(self, order: Order):
        orderType = TradingBot.order_type_from_order_id(order.id)
        if order.trigger_price is not None:
            if self.last < order.trigger_price:
                triggerDirection = 1
            else:
                triggerDirection = 2
        if orderType == OrderType.ENTRY:
            if order.trigger_price is not None:
                self.handle_result(lambda:self.pybit.amend_order(
                    orderId=order.exchange_id,
                    category = "inverse",
                    symbol=self.symbol,
                    qty=strOrNone(int(abs(order.amount))),
                    triggerPrice=strOrNone(self.symbol_info.normalizePrice(order.trigger_price, order.amount > 0)),
                    price=strOrNone(self.symbol_info.normalizePrice(order.limit_price, order.amount < 0))))
            else:
                self.handle_result(lambda:self.pybit.amend_order(
                    orderId=order.exchange_id,
                    category = "inverse",
                    symbol=self.symbol,
                    qty=strOrNone(int(abs(order.amount))),
                    price=strOrNone(self.symbol_info.normalizePrice(order.limit_price,order.amount < 0))))
        elif orderType == OrderType.SL:
            if order.trigger_price is not None:
                # conditional order
                result = self.handle_result(lambda: self.pybit.amend_order(
                    orderId=order.exchange_id,
                    side=("Buy" if order.amount > 0 else "Sell"),
                    category="inverse",
                    symbol=self.symbol,
                    orderType="Market",
                    slOrderType = "Market",
                    qty=strOrNone(int(abs(order.amount))),
                    triggerDirection=int(triggerDirection),
                    triggerPrice=strOrNone(order.trigger_price),
                    tpslMode = "Full",
                    orderLinkId=order.id,
                    timeInForce="GTC"))
                if result is not None:
                    order.exchange_id = result['orderId']
        else:
            print("Case not covered")

    def get_current_liquidity(self) -> tuple:
        book =  self.handle_result(lambda:self.pybit.get_orderbook(symbol=self.symbol)).get("list")
        buy = 0
        sell = 0
        for entry in book:
            if entry['side'] == "Buy":
                buy += entry['size']
            else:
                sell += entry['size']

        return buy, sell

    def get_bars(self, timeframe_minutes, start_offset_minutes, min_bars_needed=600) -> List[Bar]:
        limit = 200                                         # entries per message
        tf = 1 if timeframe_minutes <= 60 else 60           # minutes per candle requested from exchange
        time_now = int(datetime.now().timestamp()*1000)
        start = int(time_now - (limit-1) * tf * 60 * 1000)  # request 200 * tf
        apibars =  self.handle_result(lambda:self.pybit.get_kline(category = 'inverse', symbol = self.symbol, interval = str(tf),
                                                                  start = start, limit = limit)).get("list")

        # get more history to fill enough
        mult = timeframe_minutes / tf                                       # multiplier
        min_needed_tf_candles = min_bars_needed * mult                      # number of required tf-sized candles
        number_of_requests = 1+ math.ceil(min_needed_tf_candles/limit)      # number of requests
        for idx in range(number_of_requests):
            start = int(apibars[-1][0]) - limit * tf * 60 * 1000
            bars1 =  self.handle_result(lambda:self.pybit.get_kline(category = 'inverse', symbol = self.symbol, interval = str(tf),
                                                                  start = start, limit = limit)).get("list")
            apibars = apibars + bars1

        return self._aggregate_bars(reversed(apibars), timeframe_minutes, start_offset_minutes)

    def _aggregate_bars(self, apibars, timeframe_minutes, start_offset_minutes) -> List[Bar]:
        subbars = []
        for b in apibars:
            if 'open' in b:
                if b['open'] is None:
                    continue

            subbars.append(self.barDictToBar(b))
        return process_low_tf_bars(subbars, timeframe_minutes, start_offset_minutes)

    def get_instrument(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        fees = self.handle_result(lambda:self.pybit.get_fee_rates(symbol =symbol)).get("list")
        makerFeeRate = float(fees[0].get("makerFeeRate"))
        takerFeeRate = float(fees[0].get("takerFeeRate"))
        instr = self.handle_result(lambda:self.pybit.get_instruments_info(category = 'inverse'))
        for entry in instr['list']:
            if entry['symbol'] == symbol:
                return Symbol(symbol=entry['symbol'],
                              basecoin=self.baseCurrency,
                              isInverse=True,  # all bybit is inverse
                              lotSize=float(entry['lotSizeFilter']['qtyStep']),
                              tickSize=float(entry['priceFilter']['tickSize']),
                              makerFee=makerFeeRate,
                              takerFee=takerFeeRate,
                              pricePrecision=int(entry['priceScale']),
                              quantityPrecision=0)  # hardcoded full dollars
        return None

    def get_ticker(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        symbolData = self.handle_result(lambda:self.pybit.get_orderbook(category = "inverse", symbol= symbol, limit = 1))
        tickerData = self.handle_result(lambda: self.pybit.get_tickers(category="inverse", symbol=symbol))
        lastPrice = float(tickerData['list'][0]['lastPrice'])
        bid = float(symbolData['b'][0][0])
        ask = float(symbolData['a'][0][0])
        if bid is not None and ask is not None and lastPrice is not None:
            return TickerData(bid=bid, ask=ask, last=lastPrice)
        return None

    # internal methods

    def processOrders(self, apiOrders):
        if apiOrders is not None:
            for o in apiOrders:
                order = self.orderDictToOrder(o)
                if order.active:
                    self.logger.info("order: %s" % (str(order)))
                    self.orders[order.exchange_id] = order

    def socket_callback(self, topic):
        try:
            gotTick = False
            msgs = self.ws.get_data(topic)
            while len(msgs) > 0:
                if topic == 'order' or topic == 'stopOrder':
                    # {'orderId': 'c9cc56cb-164c-4978-811e-2d2e4ef6153a', 'orderLinkId': '', 'blockTradeId': '',
                    # 'symbol': 'BTCUSD', 'price': '0.00', 'qty': '10', 'side': 'Buy', 'isLeverage': '', 'positionIdx': 0,
                    # 'orderStatus': 'Untriggered', 'cancelType': 'UNKNOWN', 'rejectReason': 'EC_NoError', 'avgPrice': '0',
                    # 'leavesQty': '10', 'leavesValue': '0', 'cumExecQty': '0', 'cumExecValue': '0', 'cumExecFee': '0',
                    # 'timeInForce': 'IOC', 'orderType': 'Market', 'stopOrderType': 'StopLoss', 'orderIv': '',
                    # 'triggerPrice': '38000.00', 'takeProfit': '0.00', 'stopLoss': '0.00', 'tpTriggerBy': 'UNKNOWN',
                    # 'slTriggerBy': 'UNKNOWN', 'triggerDirection': 1, 'triggerBy': 'LastPrice',
                    # 'lastPriceOnCreated': '36972.00', 'reduceOnly': True, 'closeOnTrigger': True, 'smpType': 'None',
                    # 'smpGroup': 0, 'smpOrderId': '', 'tpslMode': 'Full', 'tpLimitPrice': '', 'slLimitPrice': '',
                    # 'placeType': '', 'createdTime': '1701099868909', 'updatedTime': '1701099868909'}
                    #self.logger.info("order msg arrived")
                    for o in msgs:
                        if o['symbol'] != self.symbol:
                            continue  # ignore orders not of my symbol
                        order = self.orderDictToOrder(o)
                        prev: Order = self.orders[
                            order.exchange_id] if order.exchange_id in self.orders.keys() else None
                        if prev is not None:
                            if prev.tstamp > order.tstamp or abs(prev.executed_amount) > abs(order.executed_amount):
                                # already got newer information, probably the info of the stop order getting
                                # triggered, when i already got the info about execution
                                self.logger.info("ignoring delayed update for %s " % prev.id)
                                continue
                            # ws removes stop price when executed
                            if order.trigger_price is None:
                                order.trigger_price = prev.trigger_price
                                order.stop_triggered= True # there was a stop and its no longer there -> it was triggered and order turned to linear
                            if order.limit_price is None:
                                order.limit_price = prev.limit_price
                        prev = order
                        if not prev.active and prev.execution_tstamp == 0:
                            prev.execution_tstamp = datetime.utcnow().timestamp()
                        self.orders[order.exchange_id] = prev
                elif topic == 'execution':
                    #{'blockTradeId': '', 'category': 'inverse', 'execFee': '0.00000006',
                    # 'execId': '4e995905-e9f5-51f1-bdf6-5c4d03a27b7d',
                    # 'execPrice': '43022.00', 'execQty': '4', 'execTime': '1706556378218', 'execType': 'Trade',
                    # 'execValue': '0.00009297', 'feeRate': '0.00055', 'indexPrice': '0.00', 'isLeverage': '',
                    # 'isMaker': False, 'leavesQty': '0', 'markIv': '', 'markPrice': '43025.24',
                    # 'orderId': 'f8cebf1d-128c-4352-862a-97338ce1b813',
                    # 'orderLinkId': 'strategyOne+BTCUSD.f0a.504-LONG_ENTRY', 'orderPrice': '45172.50',
                    # 'orderQty': '4', 'orderType': 'Market', 'symbol': 'BTCUSD', 'stopOrderType': 'UNKNOWN',
                    # 'side': 'Buy', 'tradeIv': '', 'underlyingPrice': '', 'closedSize': '0',
                    # 'seq': 34198439752, 'createType': 'CreateByUser'}
                    for execution in msgs:
                        #self.logger.info("execution msg arrived: %s" % (str(execution)))
                        if execution['orderId'] in self.orders.keys():
                            sideMulti = 1 if execution['side'] == "Buy" else -1
                            order = self.orders[execution['orderId']]
                            order.executed_amount = (float(execution['orderQty']) - float(execution['leavesQty'])) * sideMulti
                            if (order.executed_amount - order.amount) * sideMulti >= 0:
                                order.active = False
                            self.on_execution_callback(order_id=order.id,
                                                       executed_price= float(execution['execPrice']),
                                                       amount=float(execution['execQty']) * sideMulti,
                                                       tstamp=int(int(execution['execTime'])/1000))
                                                       #tstamp= parse_utc_timestamp(execution['tradeTime']))

                            self.logger.info("got order execution: %s %.1f @ %.1f " % (
                                execution['orderLinkId'], float(execution['execQty']) * sideMulti,
                                float(execution['execPrice'])))
                        #else:
                        #    self.logger.info("could not find the right order")
                elif topic == 'position':
                    #print('position msg arrived:')
                    # {'bustPrice': '0.00', 'category': 'inverse', 'createdTime': '1627542388255',
                    # 'cumRealisedPnl': '0.04030169', 'entryPrice': '0', 'leverage': '100', 'liqPrice': '',
                    # 'markPrice': '41835.00', 'positionBalance': '0', 'positionIdx': 0, 'positionMM': '0',
                    # 'positionIM': '0', 'positionStatus': 'Normal', 'positionValue': '0', 'riskId': 1,
                    # 'riskLimitValue': '150', 'side': 'None', 'size': '0', 'stopLoss': '0.00', 'symbol': 'BTCUSD',
                    # 'takeProfit': '0.00', 'tpslMode': 'Full', 'tradeMode': 0, 'autoAddMargin': 1,
                    # 'trailingStop': '0.00', 'unrealisedPnl': '0', 'updatedTime': '1702819920894',
                    # 'adlRankIndicator': 0, 'seq': 31244873358, 'isReduceOnly': False, 'mmrSysUpdateTime': '',
                    # 'leverageSysUpdatedTime': ''}
                    for pos in msgs:
                        #self.logger.info("pos message arrived: %s" % (str(pos)))
                        if pos['symbol'] == self.symbol:
                            if pos["side"] == "Sell":
                                self.shortPos.quantity = -float(pos['size'])
                                self.shortPos.avgEntryPrice = float(pos['entryPrice'])
                            else:
                                self.longPos.quantity = float(pos['size'])
                                self.longPos.avgEntryPrice = float(pos['entryPrice'])

                            self.updatePosition_internally()


                    #for pos in msgs:
                    #    self.logger.info("pos message arrived: %s" % (str(pos)))
                    #    sizefac = -1 if pos["side"] == "Sell" else 1
                    #    if pos['symbol'] == self.symbol and self.positions[pos['symbol']].quantity != float(pos["size"]) * sizefac:
                    #        self.logger.info("position changed %.2f -> %.2f" % ( self.positions[pos['symbol']].quantity, float(pos["size"]) * sizefac))
                    #    if pos['symbol'] not in self.positions.keys():
                    #        self.positions[pos['symbol']] = AccountPosition(pos['symbol'], avgEntryPrice=float(pos["entryPrice"]),
                    #                                                        quantity=float(pos["size"]) * sizefac)#,
                    #                                                        #walletBalance=float(pos['walletBalance']))
                    #    else:
                    #        self.logger.info("don´t know what to do")
                    #        #pass
                    #        #accountPos = self.positions[pos['symbol']]
                    #        #accountPos.quantity = float(pos["size"]) * sizefac
                    #        #accountPos.avgEntryPrice = float(pos["entryPrice"])
                    #        #accountPos.walletBalance = float(pos['walletBalance'])
                elif topic.startswith('kline.') and topic.endswith('.' + self.symbol):
                    for b in msgs:
                        #print('kline message: ')
                        #print(b)
                        b['start'] = int(int(b['start'])/1000)
                        b['end'] = int(int(b['end']) / 1000)
                        b['timestamp'] = int(int(b['timestamp']) / 1000)
                    msgs.sort(key=lambda temp: temp['start'], reverse=True)
                    if len(self.bars) > 0:
                        for b in reversed(msgs):
                            if int(self.bars[0]['start']) >= b['start'] >= self.bars[-1]['start']:
                                # find bar to fix
                                for idx in range(0, len(self.bars)):
                                    if b['start'] == self.bars[idx]['start']:
                                        self.bars[idx] = b
                                        break
                            elif b['start'] > self.bars[0]['start']:
                                self.bars.insert(0, b)
                                gotTick = True
                            # ignore old bars
                    else:
                        self.bars = msgs
                        gotTick = True

                elif topic == 'instrument_info.100ms.' + self.symbol:
                    obj = msgs
                    if 'update' in obj.keys():
                        obj = obj['update'][0]
                    if obj['symbol'] == self.symbol and 'last_price_e4' in obj.keys():
                        self.last = float(obj['last_price_e4'])# / 10000
                elif topic == 'tickers.'+self.symbol:
                    #print('ticker message: ')
                    #print(msgs)
                    pass
                elif topic == 'wallet':
                    #print(str(topic))
                    for wallet in msgs:
                        for coin in wallet['coin']:
                            #print(coin)
                            if self.baseCurrency == coin['coin']:
                                #print("wallet balance is:")
                                #print(float(wallet["walletBalance"]))
                                self.longPos.walletBalance = float(coin["walletBalance"])
                                self.shortPos.walletBalance = float(coin["walletBalance"])
                    self.updatePosition_internally()
                    #for coin in wallet['coin']:
                    #    #pass
                    #self.logger.info("wallet message arrived")
                    #    if self.baseCurrency == coin['coin']:
                    #        self.longPos.walletBalance = float(wallet["walletBalance"])
                    #        self.shortPos.walletBalance = float(wallet["walletBalance"])
                    #        self.update_account()
                    ##        self.positions[pos['symbol']]
                    #        accountPos.walletBalance = float(pos['walletBalance'])
                else:
                    self.logger.error('got unkown topic in callback: ' + topic)
                msgs = self.ws.get_data(topic)

            # new bars is handling directly in the message, because we get a new one on each tick
            if topic in ["order", "stopOrder", "execution", "wallet"]:
                gotTick = True
                self.reset_order_sync_timer() # only when something with orders changed
            if gotTick and self.on_tick_callback is not None:
                self.on_tick_callback(
                    fromAccountAction=topic in ["order", "stopOrder", "execution", "wallet"])  # got something new
        except Exception as e:
            self.logger.error("error in socket data (%s): %s " % (topic, str(e)))

    def handle_result(self,call):
        try:
            result= call()
            if result is not None and 'result' in result.keys() and result['result'] is not None:
                return result['result']
            else:
                self.logger.error(f"empty result: {result}")
                self.on_api_error(f"problem in request: {str(call)}")
                return None
        except pybit.exceptions.InvalidRequestError as e:#pybit.unified_trading.InvalidChannelTypeError.
            self.logger.error(str(e))
            self.on_api_error(f"problem in request: {e.message}")
            return None

    @staticmethod
    def orderDictToOrder(o):
        #print('translating order')
        # {'orderId': 'c9cc56cb-164c-4978-811e-2d2e4ef6153a', 'orderLinkId': '', 'blockTradeId': '',
        # 'symbol': 'BTCUSD', 'price': '0.00', 'qty': '10', 'side': 'Buy', 'isLeverage': '', 'positionIdx': 0,
        # 'orderStatus': 'Untriggered', 'cancelType': 'UNKNOWN', 'rejectReason': 'EC_NoError', 'avgPrice': '0',
        # 'leavesQty': '10', 'leavesValue': '0', 'cumExecQty': '0', 'cumExecValue': '0', 'cumExecFee': '0',
        # 'timeInForce': 'IOC', 'orderType': 'Market', 'stopOrderType': 'StopLoss', 'orderIv': '',
        # 'triggerPrice': '38000.00', 'takeProfit': '0.00', 'stopLoss': '0.00', 'tpTriggerBy': 'UNKNOWN',
        # 'slTriggerBy': 'UNKNOWN', 'triggerDirection': 1, 'triggerBy': 'LastPrice',
        # 'lastPriceOnCreated': '36972.00', 'reduceOnly': True, 'closeOnTrigger': True, 'smpType': 'None',
        # 'smpGroup': 0, 'smpOrderId': '', 'tpslMode': 'Full', 'tpLimitPrice': '', 'slLimitPrice': '',
        # 'placeType': '', 'createdTime': '1701099868909', 'updatedTime': '1701099868909'}
        sideMulti = 1 if o["side"] == "Buy" else -1
        ext = o['extFields'] if 'extFields' in o.keys() else None
        stop = float(o['triggerPrice']) if 'triggerPrice' in o.keys() else None
        if stop is None:
            stop = o['stopPx'] if 'stopPx' in o.keys() else None
        if stop is None and ext is not None and 'triggerPrice' in ext.keys():
            stop = ext['triggerPrice']
        order = Order(orderId=o["orderLinkId"],
                      trigger=float(stop) if stop is not None else None,
                      limit=float(o["price"]) if o['orderType'] == 'Limit' else None,
                      amount=float(o["qty"]) * sideMulti)
        if "orderStatus" in o.keys():
            order.stop_triggered = o["orderStatus"] == "New" and stop is not None
            order.active = o['orderStatus'] in ['New', 'Untriggered' , "PartiallyFilled"]
        elif "stopOrderStatus" in o.keys():
            order.stop_triggered = o["stopOrderStatus"] == 'Triggered' or o['stopOrderStatus'] == 'Active'
            order.active = o['stopOrderStatus'] in ['Triggered' , 'Untriggered' ]
        execution = o['cumExecQty'] if 'cumExecQty' in o.keys() else 0
        order.executed_amount = float(execution) * sideMulti
        #order.tstamp = parse_utc_timestamp(o['updatedTime'] if 'updatedTime' in o.keys() else o['createdTime'])
        #order.tstamp = int(int(o['updatedTime'] if 'updatedTime' in o.keys() else o['createdTime'])/1000)
        order.tstamp = int(o['updatedTime'] if 'updatedTime' in o.keys() else o['createdTime'])
        order.exchange_id = o["orderId"] if 'orderId' in o.keys() else o['stopOrderId']
        order.executed_price = None
        if 'cumExecValue' in o.keys() and 'cumExecQty' in o.keys() \
                and o['cumExecValue'] is not None and float(o['cumExecValue']) != 0:
            order.executed_price = float(o['cumExecQty']) / float(o["cumExecValue"])  # cause of inverse
        return order

    @staticmethod
    def barDictToBar(b):
        #tstamp = int(b['open_time'] if 'open_time' in b.keys() else b['start'])
        #bar = Bar(tstamp=tstamp, open=float(b['open']), high=float(b['high']),
        #          low=float(b['low']), close=float(b['close']), volume=float(b['volume']))

        if 'open_time' in b:
            tstamp = int(b['open_time'])
            bar = Bar(tstamp=tstamp, open=float(b['open']), high=float(b['high']),
                      low=float(b['low']), close=float(b['close']), volume=float(b['volume']))
        elif 'start' in b:
            tstamp = int(b['start'])
            bar = Bar(tstamp=tstamp, open=float(b['open']), high=float(b['high']),
                      low=float(b['low']), close=float(b['close']), volume=float(b['volume']))
        else: # bybit
            bar = Bar(tstamp = int(int(b[0])/1000), open=float(b[1]), high=float(b[2]),
                      low=float(b[3]), close=float(b[4]), volume=float(b[5]))
        #if 'timestamp' in b:
        #    bar.last_tick_tstamp = b['timestamp'] / 1000.0
        return bar
