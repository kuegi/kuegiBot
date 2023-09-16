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
        self.pybit= HTTP(testnet= settings.IS_TEST,
                                 api_key=settings.API_KEY,
                                 api_secret=settings.API_SECRET,
                                logging_level=settings.LOG_LEVEL)
        logging.root.handlers= [] # needed cause pybit adds to rootlogger
        hosts = ["wss://stream-testnet.bybit.com/realtime"] if settings.IS_TEST \
            else ["wss://stream.bybit.com/realtime", "wss://stream.bytick.com/realtime"]
        super().__init__(settings, logger,
                         ws=BybitWebsocket(publicURL="wss://stream-testnet.bybit.com/v5/public/inverse" if settings.IS_TEST else "wss://stream.bybit.com/v5/public/inverse",
                                           privateURL="wss://stream-testnet.bybit.com/v5/private" if settings.IS_TEST else "wss://stream.bybit.com/v5/private",
                                           api_key=settings.API_KEY,
                                           api_secret=settings.API_SECRET,
                                           logger=logger,
                                           callback=self.socket_callback,
                                           symbol=settings.SYMBOL,
                                           minutesPerBar=settings.MINUTES_PER_BAR),
                         on_tick_callback=on_tick_callback,
                         on_execution_callback= on_execution_callback)
        self.handles_executions= True


    def initOrders(self):
        apiOrders =  self.handle_result(lambda:self.pybit.get_open_orders(category="inverse",symbol=self.symbol))
        self.processOrders(apiOrders)

        for order in self.orders.values():
            self.logger.debug(str(order))

    def initPositions(self):
        balance= -1
        wallet= self.handle_result(lambda: self.pybit.get_wallet_balance(accountType="CONTRACT",coin=self.symbol_info.basecoin))
        for coin in wallet[0]['coin']:
            if coin['coin'] == self.symbol_info.basecoin:
                balance= float(coin['walletBalance'])
                break
        api_positions= self.handle_result(lambda: self.pybit.get_positions(category='inverse',symbol=self.symbol))
        self.positions[self.symbol] = AccountPosition(self.symbol, 0, 0, 0)
        if api_positions is not None:
            for pos in api_positions:
                sizefac = -1 if pos["side"] == "Sell" else 1
                self.positions[pos['symbol']] = AccountPosition(pos['symbol'],
                                                                        avgEntryPrice=float(pos["avgPrice"]),
                                                                        quantity=float(pos["size"]) * sizefac,
                                                                        walletBalance=balance)

    def internal_cancel_order(self, order: Order):
        if order.exchange_id in self.orders.keys():
            self.orders[order.exchange_id].active = False
        self.handle_result(lambda:self.pybit.cancel_order(category='inverse', orderId=order.exchange_id, symbol=self.symbol))

    def internal_send_order(self, order: Order):
        order_type = "Market"
        if order.limit_price is not None:
            order_type = "Limit"
        if order.stop_price is not None and (self.last - order.stop_price) * order.amount >= 0:
            order.stop_price = None  # already triggered
        triggerPrice= None
        triggerDirection= None
        if order.stop_price is not None:
            triggerPrice= self.symbol_info.normalizePrice(order.stop_price, order.amount > 0)
            triggerDirection= 1 if order.amount > 0 else 2 # 1= triggered when price goes above (=STOP BUY),2 = trigger when below

        result =  self.handle_result(lambda:self.pybit.place_order(side=("Buy" if order.amount > 0 else "Sell"),
                                                          symbol=self.symbol,
                                                          orderType=order_type,
                                                          triggerPrice= triggerPrice,
                                                          triggerDirection=triggerDirection,
                                                          qty=strOrNone(int(abs(order.amount))),
                                                          price=strOrNone(
                                                              self.symbol_info.normalizePrice(order.limit_price,
                                                                                              order.amount < 0)),
                                                          orderLinkId=order.id,
                                                          timeInForce="GTC"))
        if result is not None:
            order.exchange_id = result['orderId']

    def internal_update_order(self, order: Order):
        triggerPrice= None
        if order.stop_price is not None:
            triggerPrice= strOrNone(self.symbol_info.normalizePrice(order.stop_price, order.amount > 0))
        self.handle_result(lambda:self.pybit.amend_order(category="inverse",
                                                              orderId=order.exchange_id,
                                                         symbol=self.symbol,
                                                         qty=strOrNone(int(abs(order.amount))),
                                                         price=strOrNone(
                                                             self.symbol_info.normalizePrice(order.limit_price,
                                                                                             order.amount < 0)),
                                                         triggerPrice= triggerPrice
                           ))

    def get_current_liquidity(self) -> tuple:
        book =  self.handle_result(lambda:self.pybit.get_orderbook(category="inverse",symbol=self.symbol))
        buy = 0
        sell = 0
        for entry in book:
            if entry['side'] == "Buy":
                buy += entry['size']
            else:
                sell += entry['size']

        return buy, sell

    def get_bars(self, timeframe_minutes, start_offset_minutes, min_bars_needed=600) -> List[Bar]:
        tf = 1 if timeframe_minutes <= 60 else 60
        apibars =  self.handle_result(lambda:self.pybit.get_kline(
            **{'categoriy':'inverse','symbol': self.symbol, 'interval': str(tf), 'limit': '1000'}))
        # get more history to fill enough (currently 200 H4 bars.
        for idx in range(1+ math.ceil((min_bars_needed*timeframe_minutes)/(tf*1000))):
            end = int(apibars[-1][0])-1
            bars1 =  self.handle_result(lambda:self.pybit.get_kline(
                **{'categoriy':'inverse','symbol': self.symbol, 'interval': str(tf), 'end': str(end), 'limit': '1000'}))
            apibars = apibars +bars1

        return self._aggregate_bars(apibars, timeframe_minutes, start_offset_minutes)

    def _aggregate_bars(self, apibars, timeframe_minutes, start_offset_minutes) -> List[Bar]:
        subbars = []
        for b in apibars:
            if b[1] is None:
                continue
            subbars.append(self.barDataToBar(b))
        return process_low_tf_bars(subbars, timeframe_minutes, start_offset_minutes)

    def get_instrument(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        fees= self.handle_result(lambda :self.pybit.get_fee_rates(category="inverse",symbol=symbol))[0]
        if fees is None:
            fees= {'makerFeeRate':-0.0025,'takerFeeRate':0.0075} # fallback

        instr =  self.handle_result(lambda:self.pybit.get_instruments_info(category="inverse",symbol=symbol))
        for entry in instr:
            if entry['symbol'] == symbol:
                return Symbol(symbol=entry['symbol'],
                              isInverse=True,  # all bybit is inverse
                              lotSize=float(entry['lotSizeFilter']['qtyStep']),
                              tickSize=float(entry['priceFilter']['tickSize']),
                              makerFee=float(fees['makerFeeRate']),
                              takerFee=float(fees['takerFeeRate']),
                              basecoin=entry['baseCoin'],
                              pricePrecision=float(entry['priceScale']),
                              quantityPrecision=0)  # hardcoded full dollars
        return None

    def get_ticker(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        symbolData =  self.handle_result(lambda:self.pybit.get_tickers(category="inverse",symbol= symbol))
        for data in symbolData:
            if data["symbol"] == symbol:
                return TickerData(bid=float(data["bid1Price"]), ask=float(data["ask1Price"]),
                                  last=float(data["lastPrice"]))
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
                if topic == 'order':
                    # {'order_id': '96319991-c6ac-4ad5-bdf8-a5a79b624951', 'order_link_id': '', 'symbol': 'BTCUSD',
                    # 'side': 'Buy', 'order_type': 'Limit', 'price': '7325.5', 'qty': 1, 'time_in_force':
                    # 'GoodTillCancel', 'order_status': 'Filled', 'leaves_qty': 0, 'cum_exec_qty': 1,
                    # 'cum_exec_value': '0.00013684', 'cum_exec_fee': '0.00000011', 'timestamp':
                    # '2019-12-26T20:02:19.576Z', 'take_profit': '0', 'stop_loss': '0', 'trailing_stop': '0',
                    # 'last_exec_price': '7307.5'}
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
                    # {'symbol': 'BTCUSD', 'side': 'Buy', 'order_id': '96319991-c6ac-4ad5-bdf8-a5a79b624951',
                    # 'exec_id': '22add7a8-bb15-585f-b068-3a8648f6baff', 'order_link_id': '', 'price': '7307.5',
                    # 'order_qty': 1, 'exec_type': 'Trade', 'exec_qty': 1, 'exec_fee': '0.00000011', 'leaves_qty': 0,
                    # 'is_maker': False, 'trade_time': '2019-12-26T20:02:19.576Z'}
                    for execution in msgs:
                        if execution['orderId'] in self.orders.keys():
                            sideMulti = 1 if execution['side'] == "Buy" else -1
                            order = self.orders[execution['orderId']]
                            order.executed_amount = (float(execution['orderQty']) - float(execution['leavesQty'])) * sideMulti
                            if (order.executed_amount - order.amount) * sideMulti >= 0:
                                order.active = False
                            self.on_execution_callback(order_id=order.id,
                                                       executed_price= float(execution['execPrice']),
                                                       amount=float(execution['execQty']) * sideMulti,
                                                       tstamp= int(execution['execTime'])/1000)

                            self.logger.info("got order execution: %s %.1f @ %.1f " % (
                                execution['orderLinkId'], float(execution['execQty']) * sideMulti,
                                float(execution['execPrice'])))
                        else:
                            sideMulti = 1 if execution['side'] == "Buy" else -1
                            self.logger.info("got unkown order execution: %s/%s %.1f @ %.1f " % (
                                execution['orderId'], execution['orderLinkId'], float(execution['execQty']) * sideMulti,
                                float(execution['execPrice'])))
                elif topic == 'wallet':
                    for wallet in msgs:
                        for coin in wallet['coin']:
                            if coin['coin'] == self.symbol_info.basecoin:
                                if self.symbol in self.positions.keys():
                                    accountPos = self.positions[self.symbol]
                                    if accountPos.walletBalance != float(coin['walletBalance']):
                                        self.logger.info(f"got account update: {coin['walletBalance']} {coin['coin']}")
                                    accountPos.walletBalance= float(coin['walletBalance'])
                                break
                elif topic == 'position':
                    # {'user_id': 712961, 'symbol': 'BTCUSD', 'size': 1, 'side': 'Buy', 'position_value':
                    # '0.00013684', 'entry_price': '7307.80473546', 'liq_price': '6674', 'bust_price': '6643.5',
                    # 'leverage': '10', 'order_margin': '0', 'position_margin': '0.00001369', 'available_balance':
                    # '0.17655005', 'take_profit': '0', 'stop_loss': '0', 'realised_pnl': '-0.00000011',
                    # 'trailing_stop': '0', 'wallet_balance': '0.17656386', 'risk_id': 1, 'occ_closing_fee':
                    # '0.00000012', 'occ_funding_fee': '0', 'auto_add_margin': 0, 'cum_realised_pnl': '0.00175533',
                    # 'position_status': 'Normal', 'position_seq': 505770784}
                    for pos in msgs:
                        sizefac = -1 if pos["side"] == "Sell" else 1
                        if pos['symbol'] == self.symbol and \
                                self.positions[pos['symbol']].quantity != float(pos["size"]) * sizefac:
                            self.logger.info("position changed %.2f -> %.2f" % (
                                self.positions[pos['symbol']].quantity, float(pos["size"]) * sizefac))
                        if pos['symbol'] not in self.positions.keys():
                            self.positions[pos['symbol']] = AccountPosition(pos['symbol'],
                                                                            avgEntryPrice=float(pos["entryPrice"]),
                                                                            quantity=float(pos["size"]) * sizefac,
                                                                            walletBalance=0) # not there in v5
                        else:
                            accountPos = self.positions[pos['symbol']]
                            accountPos.quantity = float(pos["size"]) * sizefac
                            accountPos.avgEntryPrice = float(pos["entryPrice"])
                elif topic.startswith('kline.') and topic.endswith('.' + self.symbol):
                    msgs.sort(key=lambda temp: temp['start'], reverse=True)
                    if len(self.bars) > 0:
                        for b in reversed(msgs):
                            start= b['start']/1000
                            if self.bars[0].tstamp >= start >= self.bars[-1].tstamp:
                                # find bar to fix
                                for idx in range(0, len(self.bars)):
                                    if start == self.bars[idx].tstamp:
                                        self.bars[idx] = self.barDictToBar(b)
                                        gotTick = True
                                        break
                            elif start > self.bars[0].tstamp:
                                self.bars.insert(0, self.barDictToBar(b))
                                gotTick = True
                            # ignore old bars
                    else:
                        mapped= list(map(lambda b: self.barDictToBar(b),msgs))
                        mapped.sort(key= lambda b:b.tstamp, reverse=True)
                        self.bars = mapped
                        gotTick = True

                elif topic == 'tickers.' + self.symbol:
                    obj = msgs
                    if obj['symbol'] == self.symbol and 'lastPrice' in obj.keys():
                        self.last = obj['lastPrice']
                else:
                    self.logger.error('got unkown topic in callback: ' + topic)
                msgs = self.ws.get_data(topic)

            # new bars is handling directly in the messagecause we get a new one on each tick
            if topic in ["order", "execution"]:
                gotTick = True
                self.reset_order_sync_timer() # only when something with orders changed
            if gotTick and self.on_tick_callback is not None:
                self.on_tick_callback(
                    fromAccountAction=topic in ["order", "execution"])  # got something new
        except Exception as e:
            self.logger.error("error in socket data(%s): %s " % (topic, str(e)))

    def handle_result(self,call):
        try:
            result= call()
            if result is not None and 'result' in result.keys() and result['result'] is not None:
                if 'list' in result['result']:
                    return result['result']['list']
                return result['result']
            else:
                self.logger.error(f"empty result: {result}")
                self.on_api_error(f"problem in request: {str(call)}")
                return None
        except pybit.exceptions.InvalidRequestError as e:
            self.logger.error(str(e))
            self.on_api_error(f"problem in request: {e.message}")
            return None

    @staticmethod
    def orderDictToOrder(o):
        sideMulti = 1 if o["side"] == "Buy" else -1
        stop = float(o['triggerPrice']) if 'triggerPrice' in o.keys() else None
        order = Order(orderId=o["orderLinkId"],
                      stop=float(stop) if stop is not None else None,
                      limit=float(o["price"]) if 'price' in o and float(o['price']) > 0 else None,
                      amount=float(o["qty"]) * sideMulti)
        if "orderStatus" in o.keys():
            order.stop_triggered = (o["orderStatus"] == "New" and stop is not None) or o["orderStatus"] in ['Triggered','Active']
            order.active = o['orderStatus'] in ['New', 'Untriggered' , "PartiallyFilled"]
        execution = float(o['cumExecQty']) if 'cumExecQty' in o.keys() else 0
        order.executed_amount = execution * sideMulti
        #TODO: check timestamp
        order.tstamp = float(o['updatedTime'] if 'updatedTime' in o.keys() else o['createdTime'])/1000
        order.exchange_id = o["orderId"]
        order.executed_price = float(o['avgPrice']) if len(o['avgPrice']) and float(o['avgPrice']) > 0 else None
        return order

    @staticmethod
    def barDataToBar(b):
        tstamp = int(int(b[0])/1000)
        bar = Bar(tstamp=tstamp, open=float(b[1]), high=float(b[2]),
                  low=float(b[3]), close=float(b[4]), volume=float(b[5]))
        bar.last_tick_tstamp = tstamp
        return bar

    @staticmethod
    def barDictToBar(b):
        tstamp = int(b['start']/1000)
        bar = Bar(tstamp=tstamp, open=float(b['open']), high=float(b['high']),
                  low=float(b['low']), close=float(b['close']), volume=float(b['volume']))
        if 'timestamp' in b:
            bar.last_tick_tstamp = b['timestamp'] / 1000.0
        return bar
