import math
from datetime import datetime

from typing import List

import pybit
from pybit.unified_trading import HTTP

from kuegi_bot.utils.trading_classes import Order, Bar, TickerData, AccountPosition, \
    Symbol, process_low_tf_bars, parse_utc_timestamp, OrderType
from .bybitlinear_websocket import BybitLinearWebsocket
from ..ExchangeWithWS import ExchangeWithWS
from ...bots.trading_bot import TradingBot


def strOrNone(input):
    if input is None:
        return None
    else:
        string = str(input)
        if string[-2:] == ".0":
            string = string[:-2]
        return string


class ByBitLinearInterface(ExchangeWithWS):

    def __init__(self, settings, logger, on_tick_callback=None, on_api_error=None, on_execution_callback=None):
        self.on_api_error = on_api_error
        self.pybit = HTTP(endpoint='https://api-testnet.bybit.com' if settings.IS_TEST else 'https://api.bybit.com',
                          api_key=settings.API_KEY,
                          api_secret=settings.API_SECRET,
                          logging_level=settings.LOG_LEVEL)
        hosts_private = ["wss://stream-testnet.bybit.com/realtime_private"] if settings.IS_TEST \
            else ["wss://stream.bybit.com/realtime_private", "wss://stream.bytick.com/realtime_private"]
        hosts_public = ["wss://stream-testnet.bybit.com/realtime_public"] if settings.IS_TEST \
            else ["wss://stream.bybit.com/realtime_public", "wss://stream.bytick.com/realtime_public"]
        self.longPos = AccountPosition(settings.SYMBOL, 0, 0, 0)
        self.shortPos = AccountPosition(settings.SYMBOL, 0, 0, 0)
        super().__init__(settings, logger,
                         ws=BybitLinearWebsocket(wspublicURLs=hosts_public, wsprivateURLs=hosts_private,
                                                 api_key=settings.API_KEY,
                                                 api_secret=settings.API_SECRET,
                                                 logger=logger,
                                                 callback=self.socket_callback,
                                                 symbol=settings.SYMBOL,
                                                 minutes_per_bar=settings.MINUTES_PER_BAR),
                         on_tick_callback=on_tick_callback, on_execution_callback=on_execution_callback)
        self.handles_executions = True

    def is_open(self):
        # ws is always a BybitLinearWebsocket which has a publicWS
        return not self.ws.exited and not self.ws.public_ws.exited

    def initOrders(self):
        apiOrders = self.handle_result(lambda: self.pybit.query_active_order(symbol=self.symbol))
        apiOrders += self.handle_result(lambda: self.pybit.query_conditional_order(symbol=self.symbol))
        self.processOrders(apiOrders)

        for order in self.orders.values():
            self.logger.debug(str(order))

    def initPositions(self):
        api_wallet = self.handle_result(lambda: self.pybit.get_wallet_balance(coin=self.baseCurrency))
        balance = api_wallet[self.baseCurrency]["wallet_balance"]
        api_positions = self.handle_result(lambda: self.pybit.my_position(symbol=self.symbol))
        self.longPos = AccountPosition(self.symbol, 0, 0, balance)
        self.shortPos = AccountPosition(self.symbol, 0, 0, balance)
        if api_positions is not None:
            for pos in api_positions:
                if pos["side"] == "Sell":
                    self.shortPos.avgEntryPrice = float(pos["entry_price"])
                    self.shortPos.quantity = -1 * pos["size"]
                else:
                    self.longPos.avgEntryPrice = float(pos["entry_price"])
                    self.longPos.quantity = pos["size"]
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
        if order.trigger_price is not None:
            self.handle_result(
                lambda: self.pybit.cancel_conditional_order(stop_order_id=order.exchange_id, symbol=self.symbol))
        else:
            self.handle_result(lambda: self.pybit.cancel_active_order(order_id=order.exchange_id, symbol=self.symbol))

    def internal_send_order(self, order: Order):
        order_type = "Market"
        if order.limit_price is not None:
            order_type = "Limit"
        if order.trigger_price is not None and (self.last - order.trigger_price) * order.amount >= 0:
            order.trigger_price = None  # already triggered

        orderType = TradingBot.order_type_from_order_id(order.id)

        if order.trigger_price is not None:
            # conditional order
            base_side = self.symbol_info.tickSize * (
                1 if order.amount < 0 else -1)  # buy stops are triggered when price goes higher (so it is
            # considered lower before)
            normalizedStop = self.symbol_info.normalizePrice(order.trigger_price, order.amount > 0)
            result = self.handle_result(
                lambda: self.pybit.place_conditional_order(side=("Buy" if order.amount > 0 else "Sell"),
                                                           symbol=self.symbol,
                                                           order_type=order_type,
                                                           qty=strOrNone(
                                                               self.symbol_info.normalizeSize(
                                                                   abs(order.amount))),
                                                           price=strOrNone(
                                                               self.symbol_info.normalizePrice(
                                                                   order.limit_price, order.amount < 0)),
                                                           stop_px=strOrNone(normalizedStop),
                                                           order_link_id=order.id,
                                                           base_price=strOrNone(round(
                                                                    normalizedStop + base_side,
                                                                    self.symbol_info.pricePrecision)),
                                                           time_in_force="GoodTillCancel",
                                                           trigger_by="LastPrice",
                                                           reduce_only=orderType != OrderType.ENTRY,
                                                           close_on_trigger=orderType != OrderType.ENTRY))
            if result is not None:
                order.exchange_id = result['stop_order_id']

        else:
            result = self.handle_result(
                lambda: self.pybit.place_active_order(side=("Buy" if order.amount > 0 else "Sell"),
                                                      symbol=self.symbol,
                                                      order_type=order_type,
                                                      qty=strOrNone(
                                                          self.symbol_info.normalizeSize(
                                                              abs(order.amount))),
                                                      price=strOrNone(
                                                          self.symbol_info.normalizePrice(order.limit_price,
                                                                                          order.amount < 0)),
                                                      order_link_id=order.id,
                                                      time_in_force="GoodTillCancel",
                                                      reduce_only=orderType != OrderType.ENTRY,
                                                      close_on_trigger=orderType != OrderType.ENTRY))
            if result is not None:
                order.exchange_id = result['order_id']

    def internal_update_order(self, order: Order):
        if order.trigger_price is not None:
            self.handle_result(lambda: self.pybit.replace_conditional_order(stop_order_id=order.exchange_id,
                                                                            symbol=self.symbol,
                                                                            p_r_qty=strOrNone(
                                                                                self.symbol_info.normalizeSize(
                                                                                    abs(order.amount))),
                                                                            p_r_trigger_price=
                                                                            self.symbol_info.normalizePrice(
                                                                                order.trigger_price, order.amount > 0),
                                                                            p_r_price=
                                                                            self.symbol_info.normalizePrice(
                                                                                order.limit_price, order.amount < 0)))
        else:
            self.handle_result(lambda: self.pybit.replace_active_order(order_id=order.exchange_id,
                                                                       symbol=self.symbol,
                                                                       p_r_qty=strOrNone(
                                                                           self.symbol_info.normalizeSize(
                                                                               abs(order.amount))),
                                                                       p_r_price=
                                                                       self.symbol_info.normalizePrice(
                                                                           order.limit_price,
                                                                           order.amount < 0)))

    def get_current_liquidity(self) -> tuple:
        book = self.handle_result(lambda: self.pybit.orderbook(symbol=self.symbol))
        buy = 0
        sell = 0
        for entry in book:
            if entry['side'] == "Buy":
                buy += entry['size']
            else:
                sell += entry['size']

        return buy, sell

    def get_bars(self, timeframe_minutes, start_offset_minutes, min_bars_needed) -> List[Bar]:
        tf = 1 if timeframe_minutes <= 60 else 60
        start = int(datetime.now().timestamp() - tf * 60 * 199)
        apibars = self.handle_result(lambda: self.pybit.query_kline(
            **{'symbol': self.symbol, 'interval': str(tf), 'from': str(start), 'limit': '200'}))
        # get more history to fill enough (currently 200 H4 bars.
        for idx in range(1 + math.ceil((min_bars_needed * timeframe_minutes) / (tf * 200))):
            start = int(apibars[0]['open_time']) - tf * 60 * 200
            bars1 = self.handle_result(lambda: self.pybit.query_kline(
                **{'symbol': self.symbol, 'interval': str(tf), 'from': str(start), 'limit': '200'}))
            apibars = bars1 + apibars

        return self._aggregate_bars(reversed(apibars), timeframe_minutes, start_offset_minutes)

    def _aggregate_bars(self, apibars, timeframe_minutes, start_offset_minutes) -> List[Bar]:
        subbars = []
        for b in apibars:
            if b['open'] is None:
                continue
            subbars.append(self.barDictToBar(b))
        return process_low_tf_bars(subbars, timeframe_minutes, start_offset_minutes)

    def get_instrument(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        instr = self.handle_result(lambda: self.pybit.query_symbol())
        for entry in instr:
            if entry['name'] == symbol:
                return Symbol(symbol=entry['name'],
                              isInverse=entry["quote_currency"] != "USDT",  # USDT is linear
                              lotSize=float(entry['lot_size_filter']['qty_step']),
                              tickSize=float(entry['price_filter']['tick_size']),
                              makerFee=float(entry['maker_fee']),
                              takerFee=float(entry['taker_fee']),
                              pricePrecision=entry['price_scale'],
                              quantityPrecision=3 if entry[
                                                         "quote_currency"] == "USDT" else 0)  # hardcoded 5 digits FIXME!
        return None

    def get_ticker(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        symbolData = self.handle_result(lambda: self.pybit.latest_information_for_symbol(symbol=symbol))
        for data in symbolData:
            if data["symbol"] == symbol:
                return TickerData(bid=float(data["bid_price"]), ask=float(data["ask_price"]),
                                  last=float(data["last_price"]))
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
                if topic == 'order' or topic == 'stop_order':
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
                            if order.trigger_price is None:
                                order.trigger_price = prev.trigger_price
                                order.stop_triggered = True  # there was a stop and its no longer there -> it was triggered and order turned to linear
                            if order.limit_price is None:
                                order.limit_price = prev.limit_price
                        prev = order
                        if not prev.active and prev.execution_tstamp == 0:
                            prev.execution_tstamp = datetime.utcnow().timestamp()
                        self.orders[order.exchange_id] = prev

                        self.logger.info("order update: %s" % (str(order)))
                elif topic == 'execution':
                    # {'symbol': 'BTCUSD', 'side': 'Buy', 'order_id': '96319991-c6ac-4ad5-bdf8-a5a79b624951',
                    # 'exec_id': '22add7a8-bb15-585f-b068-3a8648f6baff', 'order_link_id': '', 'price': '7307.5',
                    # 'order_qty': 1, 'exec_type': 'Trade', 'exec_qty': 1, 'exec_fee': '0.00000011', 'leaves_qty': 0,
                    # 'is_maker': False, 'trade_time': '2019-12-26T20:02:19.576Z'}
                    for execution in msgs:
                        if execution['order_id'] in self.orders.keys():
                            sideMulti = 1 if execution['side'] == "Buy" else -1
                            order = self.orders[execution['order_id']]
                            order.executed_amount = (execution['order_qty'] - execution['leaves_qty']) * sideMulti
                            if (order.executed_amount - order.amount) * sideMulti >= 0:
                                order.active = False
                            self.on_execution_callback(order_id=order.id,
                                                       executed_price=float(execution['price']),
                                                       amount=execution['exec_qty'] * sideMulti,
                                                       tstamp=parse_utc_timestamp(execution['trade_time']))
                            self.logger.info("got order execution: %s %.3f @ %.2f " % (
                                execution['order_link_id'], execution['exec_qty'] * sideMulti,
                                float(execution['price'])))
                elif topic == 'wallet':
                    for wallet in msgs:
                        self.longPos.walletBalance = float(wallet["wallet_balance"])
                        self.shortPos.walletBalance = float(wallet["wallet_balance"])
                    self.updatePosition_internally()
                elif topic == 'position':
                    # {'user_id': 712961, 'symbol': 'BTCUSD', 'size': 1, 'side': 'Buy', 'position_value':
                    # '0.00013684', 'entry_price': '7307.80473546', 'liq_price': '6674', 'bust_price': '6643.5',
                    # 'leverage': '10', 'order_margin': '0', 'position_margin': '0.00001369', 'available_balance':
                    # '0.17655005', 'take_profit': '0', 'stop_loss': '0', 'realised_pnl': '-0.00000011',
                    # 'trailing_stop': '0', 'wallet_balance': '0.17656386', 'risk_id': 1, 'occ_closing_fee':
                    # '0.00000012', 'occ_funding_fee': '0', 'auto_add_margin': 0, 'cum_realised_pnl': '0.00175533',
                    # 'position_status': 'Normal', 'position_seq': 505770784}
                    for pos in msgs:
                        if pos['symbol'] == self.symbol:
                            if pos["side"] == "Sell":
                                self.shortPos.quantity = -float(pos['size'])
                                self.shortPos.avgEntryPrice = float(pos['entry_price'])
                            else:
                                self.longPos.quantity = float(pos['size'])
                                self.longPos.avgEntryPrice = float(pos['entry_price'])

                            self.updatePosition_internally()

                elif topic.startswith('candle.') and topic.endswith('.' + self.symbol):
                    msgs.sort(key=lambda temp: temp['start'], reverse=True)
                    if len(self.bars) > 0:
                        for b in reversed(msgs):
                            if self.bars[0]['start'] >= b['start'] >= self.bars[-1]['start']:
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
                        self.last = float(obj['last_price_e4']) / 10000
                else:
                    self.logger.error('got unkown topic in callback: ' + topic)
                msgs = self.ws.get_data(topic)

            # new bars is handling directly in the messagecause we get a new one on each tick
            if topic in ["order", "stop_order", "execution", "wallet"]:
                gotTick = True
                self.reset_order_sync_timer()  # only when something with orders changed
            if gotTick and self.on_tick_callback is not None:
                self.on_tick_callback(
                    fromAccountAction=topic in ["order", "stop_order", "execution", "wallet"])  # got something new
        except Exception as e:
            self.logger.error("error in socket data(%s): %s " % (topic, str(e)))

    def handle_result(self, call):
        try:
            result = call()
            if result is not None and 'result' in result.keys() and result['result'] is not None:
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
        ext = o['ext_fields'] if 'ext_fields' in o.keys() else None
        stop = o['trigger_price'] if 'trigger_price' in o.keys() else None
        if stop is None:
            stop = o['stop_px'] if 'stop_px' in o.keys() else None
        if stop is None and ext is not None and 'trigger_price' in ext.keys():
            stop = ext['trigger_price']
        order = Order(orderId=o["order_link_id"],
                      trigger=float(stop) if stop is not None else None,
                      limit=float(o["price"]) if o['order_type'] == 'Limit' else None,
                      amount=float(o["qty"]) * sideMulti)
        if "order_status" in o.keys():
            order.stop_triggered = o["order_status"] == "New" and stop is not None
            order.active = o['order_status'] in ['New', 'Untriggered', "PartiallyFilled"]
        elif "stop_order_status" in o.keys():
            order.stop_triggered = o["stop_order_status"] == 'Triggered' or o['stop_order_status'] == 'Active'
            order.active = o['stop_order_status'] in ['Triggered', 'Untriggered']
        execution = o['cum_exec_qty'] if 'cum_exec_qty' in o.keys() else 0
        order.executed_amount = float(execution) * sideMulti
        order.tstamp = parse_utc_timestamp(o['updated_time'] if 'updated_time' in o.keys() else o['update_time'])
        order.exchange_id = o["order_id"] if 'order_id' in o.keys() else o['stop_order_id']
        order.executed_price = None
        if 'cum_exec_value' in o.keys() and 'cum_exec_qty' in o.keys() \
                and o['cum_exec_value'] is not None and float(o['cum_exec_value']) != 0:
            order.executed_price = float(o["cum_exec_value"]) / float(o['cum_exec_qty'])
        return order

    @staticmethod
    def barDictToBar(b):
        if 'open_time' in b:
            tstamp = int(b['open_time'])
            bar = Bar(tstamp=tstamp, open=float(b['open']), high=float(b['high']),
                      low=float(b['low']), close=float(b['close']), volume=float(b['volume']))
        elif 'start' in b:
            tstamp = int(b['start'])
            bar = Bar(tstamp=tstamp, open=float(b['open']), high=float(b['high']),
                      low=float(b['low']), close=float(b['close']), volume=float(b['volume']))
        else:  # bybit
            bar = Bar(tstamp=int(int(b[0]) / 1000), open=float(b[1]), high=float(b[2]),
                      low=float(b[3]), close=float(b[4]), volume=0)
        if 'timestamp' in b:
            bar.last_tick_tstamp = b['timestamp'] / 1000.0
        return bar
