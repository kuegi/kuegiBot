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


def strOrNone(input):
    if input is None:
        return None
    else:
        return str(input)


class ByBitInterface(ExchangeWithWS):

    def __init__(self, settings, logger, on_tick_callback=None, on_api_error=None, on_execution_callback=None):
        self.on_api_error = on_api_error
        self.pybit = HTTP(testnet = settings.IS_TEST, api_key=settings.API_KEY, api_secret=settings.API_SECRET)
        #self.pybit = HTTP(endpoint= 'https://api-testnet.bybit.com' if settings.IS_TEST else 'https://api.bybit.com',
        #                         api_key=settings.API_KEY,
        #                         api_secret=settings.API_SECRET,
        #                        logging_level=settings.LOG_LEVEL)
        #logging.root.handlers= [] # needed cause pybit adds to rootlogger
        logging.basicConfig(filename="pybit.log", level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")
        hosts = ["wss://stream-testnet.bybit.com/realtime"] if settings.IS_TEST \
            else ["wss://stream.bybit.com/realtime", "wss://stream.bytick.com/realtime"]
        super().__init__(settings, logger,
                         ws=BybitWebsocket(wsURLs=hosts,
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
        apiOrders += conditionalOrders
        self.processOrders(apiOrders)

        for order in self.orders.values():
            self.logger.debug(str(order))

    def initPositions(self):
        api_positions= self.handle_result(lambda: self.pybit.get_positions(category = 'inverse', symbol=self.symbol)).get("list")
        #wallet_balance = float(self.handle_result(lambda: self.pybit.get_wallet_balance(accountType='CONTRACT', coin=self.baseCurrency)).get("list")[0]['coin'][0]['walletBalance'])
        wallet_balance = self.handle_result(lambda: self.pybit.get_wallet_balance(accountType="CONTRACT", coin=self.baseCurrency)).get("list")
        for coin in wallet_balance[0]['coin']:
            if coin['coin'] == self.baseCurrency:
                balance = float(coin['walletBalance'])
                break
        self.positions[self.symbol] = AccountPosition(self.symbol, 0, 0, 0)
        if api_positions is not None:
            for pos in api_positions:
                if pos['positionValue']!=0:
                    sizefac = -1 if pos["side"] == "Sell" else 1
                    quantity = float(pos["size"]) * sizefac
                    self.positions[pos['symbol']] = AccountPosition(pos['symbol'],
                                                                    avgEntryPrice=float(pos["avgPrice"]),
                                                                    quantity=quantity,
                                                                    walletBalance=balance)

    def internal_cancel_order(self, order: Order):
        if order.exchange_id in self.orders.keys():
            self.orders[order.exchange_id].active = False
        #if order.stop_price is not None:
        self.handle_result(lambda:self.pybit.cancel_order(category='inverse',order_id=order.exchange_id, symbol=self.symbol)).get("list")
        #else:
            #self.handle_result(lambda:self.pybit.cancel_active_order(order_id=order.exchange_id, symbol=self.symbol)).get("list")

    def internal_send_order(self, order: Order):
        order_type = "Market"
        if order.limit_price is not None:
            order_type = "Limit"
        if order.stop_price is not None and (self.last - order.stop_price) * order.amount >= 0:
            order.stop_price = None  # already triggered

        if order.stop_price is not None:
            # conditional order
            base_side = self.symbol_info.tickSize * (
                1 if order.amount < 0 else -1)  # buy stops are triggered when price goes higher (so it is
            # considered lower before)
            normalizedStop = self.symbol_info.normalizePrice(order.stop_price, order.amount > 0)
            result = self.handle_result(lambda:self.pybit.place_order(
                side=("Buy" if order.amount > 0 else "Sell"),
                category="inverse",
                symbol=self.symbol,
                order_type=order_type,
                qty=strOrNone(int(abs(order.amount))),
                price=strOrNone(self.symbol_info.normalizePrice(order.limit_price, order.amount < 0)),
                stop_px=strOrNone(normalizedStop),
                order_link_id=order.id,
                base_price=strOrNone(round(normalizedStop + base_side, self.symbol_info.pricePrecision)),
                time_in_force="GTC").get("list"))#,# #trigger_by="LastPrice")
            if result is not None:
                order.exchange_id = result['stopOrderId']

        else:
            result =  self.handle_result(lambda:self.pybit.place_order(
                side=("Buy" if order.amount > 0 else "Sell"),
                symbol=self.symbol,
                category = "inverse",
                order_type=order_type,
                qty=strOrNone(int(abs(order.amount))),
                price=strOrNone(self.symbol_info.normalizePrice(order.limit_price, order.amount < 0)),
                order_link_id=order.id,
                time_in_force="GTC").get("list"))
            if result is not None:
                order.exchange_id = result['orderId']

    def internal_update_order(self, order: Order):
        if order.stop_price is not None:
            self.handle_result(lambda:self.pybit.amend_order(
                stop_order_id=order.exchange_id,
                category = "inverse",
                symbol=self.symbol,
                p_r_qty=strOrNone(int(abs(order.amount))),
                p_r_trigger_price=strOrNone(self.symbol_info.normalizePrice(order.stop_price, order.amount > 0)),
                p_r_price=strOrNone(self.symbol_info.normalizePrice(order.limit_price, order.amount < 0))).get("list"))
        else:
            self.handle_result(lambda:self.pybit.amend_order(
                order_id=order.exchange_id,
                category = "inverse",
                symbol=self.symbol,
                p_r_qty=strOrNone(int(abs(order.amount))),
                p_r_price=strOrNone(self.symbol_info.normalizePrice(order.limit_price,order.amount < 0))).get("list"))

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
                    self.orders[order.exchange_id] = order

    def socket_callback(self, topic):
        try:
            gotTick = False
            msgs = self.ws.get_data(topic)
            while len(msgs) > 0:
                if topic == 'order' or topic == 'stopOrder':
                    #print('order msg arrived:')
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
                    for o in msgs:
                        if o['symbol'] != self.symbol:
                            continue  # ignore orders not of my symbol
                        order = self.orderDictToOrder(o)
                        #print(order)
                        prev: Order = self.orders[
                            order.exchange_id] if order.exchange_id in self.orders.keys() else None
                        if prev is not None:
                            if prev.tstamp > order.tstamp or abs(prev.executed_amount) > abs(order.executed_amount):
                                # already got newer information, probably the info of the stop order getting
                                # triggered, when i already got the info about execution
                                self.logger.info("ignoring delayed update for %s " % prev.id)
                                continue
                            # ws removes stop price when executed
                            if order.stop_price is None:
                                order.stop_price = prev.stop_price
                                order.stop_triggered= True # there was a stop and its no longer there -> it was triggered and order turned to linear
                            if order.limit_price is None:
                                order.limit_price = prev.limit_price
                        prev = order
                        if not prev.active and prev.execution_tstamp == 0:
                            prev.execution_tstamp = datetime.utcnow().timestamp()
                        self.orders[order.exchange_id] = prev

                        self.logger.info("received order update: %s" % (str(order)))
                elif topic == 'execution':
                    #print('execution msg arrived:')
                    # {'symbol': 'BTCUSD', 'side': 'Buy', 'order_id': '96319991-c6ac-4ad5-bdf8-a5a79b624951',
                    # 'exec_id': '22add7a8-bb15-585f-b068-3a8648f6baff', 'order_link_id': '', 'price': '7307.5',
                    # 'order_qty': 1, 'exec_type': 'Trade', 'exec_qty': 1, 'exec_fee': '0.00000011', 'leaves_qty': 0,
                    # 'is_maker': False, 'trade_time': '2019-12-26T20:02:19.576Z'}
                    for execution in msgs:
                        #print(execution)
                        if execution['orderId'] in self.orders.keys():
                            sideMulti = 1 if execution['side'] == "Buy" else -1
                            order = self.orders[execution['orderId']]
                            order.executed_amount = (float(execution['orderQty']) - float(execution['leavesQty'])) * sideMulti
                            if (order.executed_amount - order.amount) * sideMulti >= 0:
                                order.active = False
                            self.on_execution_callback(order_id=order.id,
                                                       executed_price= float(execution['price']),
                                                       amount=float(execution['execQty']) * sideMulti,
                                                       tstamp=int(execution['tradeTime']))#/1000))
                                                       #tstamp= parse_utc_timestamp(execution['tradeTime']))

                            self.logger.info("got order execution: %s %.1f @ %.1f " % (
                                execution['orderLinkId'], float(execution['execQty']) * sideMulti,
                                float(execution['price'])))

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
                        #print(pos)
                        sizefac = -1 if pos["side"] == "Sell" else 1
                        if pos['symbol'] == self.symbol and self.positions[pos['symbol']].quantity != float(pos["size"]) * sizefac:
                            self.logger.info("position changed %.2f -> %.2f" % ( self.positions[pos['symbol']].quantity, float(pos["size"]) * sizefac))
                        if pos['symbol'] not in self.positions.keys():
                            self.positions[pos['symbol']] = AccountPosition(pos['symbol'], avgEntryPrice=float(pos["entryPrice"]),
                                                                            quantity=float(pos["size"]) * sizefac)#,
                                                                            #walletBalance=float(pos['walletBalance']))
                        else:
                            accountPos = self.positions[pos['symbol']]
                            accountPos.quantity = float(pos["size"]) * sizefac
                            accountPos.avgEntryPrice = float(pos["entryPrice"])
                            #accountPos.walletBalance = float(pos['walletBalance'])
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
                    #for wallet in msgs:
                        #print("wallet: ")
                        #print(wallet)
                        #accountPos.walletBalance = float(pos['walletBalance'])
                    pass
                else:
                    self.logger.error('got unkown topic in callback: ' + topic)
                msgs = self.ws.get_data(topic)

            # new bars is handling directly in the message, because we get a new one on each tick
            if topic in ["order", "stopOrder", "execution"]:
                gotTick = True
                self.reset_order_sync_timer() # only when something with orders changed
            if gotTick and self.on_tick_callback is not None:
                self.on_tick_callback(
                    fromAccountAction=topic in ["order", "stopOrder", "execution"])  # got something new
        except Exception as e:
            self.logger.error("error in socket data(%s): %s " % (topic, str(e)))

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
                      stop=float(stop) if stop is not None else None,
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
        order.tstamp = int(int(o['updatedTime'] if 'updatedTime' in o.keys() else o['createdTime'])/1000)
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
                      low=float(b[3]), close=float(b[4]), volume=0)
        #if 'timestamp' in b:
        #    bar.last_tick_tstamp = b['timestamp'] / 1000.0
        return bar
