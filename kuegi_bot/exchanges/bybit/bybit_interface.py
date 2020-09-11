from datetime import datetime

from typing import List

import bybit
from bravado.http_future import HttpFuture

from kuegi_bot.exchanges.bybit.bybit_websocket import BybitWebsocket
from kuegi_bot.utils.trading_classes import Order, Bar, TickerData, AccountPosition, \
    Symbol, process_low_tf_bars, parse_utc_timestamp
from ..ExchangeWithWS import ExchangeWithWS


class ByBitInterface(ExchangeWithWS):

    def __init__(self, settings, logger, on_tick_callback=None):
        self.bybit = bybit.bybit(test=settings.IS_TEST,
                                 api_key=settings.API_KEY,
                                 api_secret=settings.API_SECRET)
        hosts = ["wss://stream-testnet.bybit.com/realtime"] if settings.IS_TEST \
            else ["wss://stream.bybit.com/realtime","wss://stream.bytick.com/realtime"]
        super().__init__(settings, logger,
                         ws=BybitWebsocket(wsURLs=hosts,
                                           api_key=settings.API_KEY,
                                           api_secret=settings.API_SECRET,
                                           logger=logger,
                                           callback=self.socket_callback,
                                           symbol= settings.SYMBOL,
                                           minutesPerBar=settings.MINUTES_PER_BAR),
                         on_tick_callback=on_tick_callback)


    def initOrders(self):
        apiOrders = self._execute(self.bybit.Order.Order_getOrders(order_status='Untriggered,New', symbol=self.symbol))
        self.processOrders(apiOrders)

        apiOrders = self._execute(self.bybit.Conditional.Conditional_getOrders(symbol=self.symbol))
        self.processOrders(apiOrders)

        self.logger.info("got %i orders on startup" % len(self.orders))
        for order in self.orders.values():
            self.logger.debug(str(order))

    def initPositions(self):
        api_positions = self._execute(self.bybit.Positions.Positions_myPosition())
        self.positions[self.symbol] = AccountPosition(self.symbol, 0, 0, 0)
        if api_positions is not None:
            for pos in api_positions:
                sizefac = -1 if pos["side"] == "Sell" else 1
                self.positions[pos['symbol']] = AccountPosition(pos['symbol'],
                                                                avgEntryPrice=pos["entry_price"],
                                                                quantity=pos["size"] * sizefac,
                                                                walletBalance=float(pos['wallet_balance']))

    def internal_cancel_order(self, order: Order):
        if order.exchange_id in self.orders.keys():
            self.orders[order.exchange_id].active = False
        if order.stop_price is not None:
            self._execute(self.bybit.Conditional.Conditional_cancel(stop_order_id=order.exchange_id,symbol=self.symbol))
        else:
            self._execute(self.bybit.Order.Order_cancelV2(order_id=order.exchange_id,symbol=self.symbol))

    def internal_send_order(self, order: Order):
        order_type = "Market"
        if order.limit_price is not None:
            order_type = "Limit"
        if order.stop_price is not None and (self.last - order.stop_price) * order.amount >= 0:
            order.stop_price = None  # already triggered

        if order.stop_price is not None:
            # conditional order
            base_side = 1 if order.amount < 0 else -1  # buy stops are triggered when price goes higher (so it is
            # considered lower before)
            result = self._execute(self.bybit.Conditional.Conditional_new(side=("Buy" if order.amount > 0 else "Sell"),
                                                                          symbol=self.symbol,
                                                                          order_type=order_type,
                                                                          qty=abs(order.amount),
                                                                          price=self.symbol_info.normalizePrice(
                                                                              order.limit_price, order.amount < 0),
                                                                          stop_px=self.symbol_info.normalizePrice(
                                                                              order.stop_price, order.amount > 0),
                                                                          order_link_id=order.id,
                                                                          base_price=order.stop_price + base_side,
                                                                          time_in_force="GoodTillCancel"))
            if result is not None:
                order.exchange_id = result['stop_order_id']

        else:
            result = self._execute(self.bybit.Order.Order_newV2(side=("Buy" if order.amount > 0 else "Sell"),
                                                                symbol=self.symbol,
                                                                order_type=order_type,
                                                                qty=abs(order.amount),
                                                                price=self.symbol_info.normalizePrice(order.limit_price,
                                                                                                      order.amount < 0),
                                                                order_link_id=order.id,
                                                                time_in_force="GoodTillCancel"))
            if result is not None:
                order.exchange_id = result['order_id']

    def internal_update_order(self, order: Order):
        if order.stop_price is not None:
            self._execute(self.bybit.Conditional.Conditional_replace(order_id=order.exchange_id,
                                                                     symbol=self.symbol,
                                                                     p_r_qty=abs(order.amount),
                                                                     p_r_trigger_price=self.symbol_info.normalizePrice(
                                                                         order.stop_price, order.amount > 0),
                                                                     p_r_price=self.symbol_info.normalizePrice(
                                                                         order.limit_price, order.amount < 0)))
        else:
            self._execute(self.bybit.Order.Order_replace(order_id=order.exchange_id,
                                                         symbol=self.symbol,
                                                         p_r_qty=abs(order.amount),
                                                         p_r_price=self.symbol_info.normalizePrice(order.limit_price,
                                                                                                   order.amount < 0)))

    def get_bars(self, timeframe_minutes, start_offset_minutes) -> List[Bar]:
        tf = 1 if timeframe_minutes <= 60 else 60
        start = int(datetime.now().timestamp() - tf * 60 * 199)
        apibars = self._execute(self.bybit.Kline.Kline_get(
            **{'symbol': self.symbol, 'interval': str(tf), 'from': str(start), 'limit': '200'}))
        # get more history to fill enough (currently 200 H4 bars.
        for idx in range(3):
            start = int(apibars[0]['open_time']) - tf * 60 * 200
            bars1 = self._execute(self.bybit.Kline.Kline_get(
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
        instr = self._execute(self.bybit.Symbol.Symbol_get())
        for entry in instr:
            if entry['name'] == symbol:
                return Symbol(symbol=entry['name'],
                              isInverse=True,  # all bybit is inverse
                              lotSize=float(entry['lot_size_filter']['qty_step']),
                              tickSize=float(entry['price_filter']['tick_size']),
                              makerFee=float(entry['maker_fee']),
                              takerFee=float(entry['taker_fee']))
        return None

    def get_ticker(self, symbol=None):
        if symbol is None:
            symbol = self.symbol
        symbolData = self._execute(self.bybit.Market.Market_symbolInfo())
        for data in symbolData:
            if data["symbol"] == symbol:
                return TickerData(bid=float(data["bid_price"]), ask=float(data["ask_price"]),
                                  last=float(data["last_price"]))
        return None

    # internal methods

    def processOrders(self, apiOrders):
        if len(apiOrders) > 0 and 'data' in apiOrders.keys():
            apiOrders = apiOrders['data']
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
                            if order.stop_price is None:
                                order.stop_price = prev.stop_price
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
                        if execution['order_id'] in self.orders.keys():
                            sideMulti = 1 if execution['side'] == "Buy" else -1
                            order = self.orders[execution['order_id']]
                            order.executed_amount = (execution['order_qty'] - execution['leaves_qty']) * sideMulti
                            if (order.executed_amount - order.amount) * sideMulti >= 0:
                                order.active = False
                            self.logger.info("got order execution: %s %.1f @ %.1f " % (
                                execution['order_link_id'], execution['exec_qty'] * sideMulti,
                                float(execution['price'])))

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
                                self.positions[pos['symbol']].quantity != pos["size"] * sizefac:
                            self.logger.info("position changed %.2f -> %.2f" % (
                                self.positions[pos['symbol']].quantity, pos["size"] * sizefac))
                        if pos['symbol'] not in self.positions.keys():
                            self.positions[pos['symbol']] = AccountPosition(pos['symbol'],
                                                                            avgEntryPrice=float(pos["entry_price"]),
                                                                            quantity=pos["size"] * sizefac,
                                                                            walletBalance=float(pos['wallet_balance']))
                        else:
                            accountPos = self.positions[pos['symbol']]
                            accountPos.quantity = pos["size"] * sizefac
                            accountPos.avgEntryPrice = float(pos["entry_price"])
                            accountPos.walletBalance = float(pos['wallet_balance'])
                elif topic.startswith('klineV2.') and topic.endswith('.' + self.symbol):
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
                        self.last = obj['last_price_e4'] / 10000
                else:
                    self.logger.error('got unkown topic in callback: ' + topic)
                msgs = self.ws.get_data(topic)

            # new bars is handling directly in the messagecause we get a new one on each tick
            if topic in ["order", "stop_order", "execution"]:
                gotTick = True
            if gotTick and self.on_tick_callback is not None:
                self.on_tick_callback(
                    fromAccountAction=topic in ["order", "stop_order", "execution"])  # got something new
        except Exception as e:
            self.logger.error("error in socket data(%s): %s " % (topic, str(e)))

    def _execute(self, call: HttpFuture, silent=False, remainingRetries=0):
        if not silent:
            self.logger.info("executing %s %s" % (str(call.operation.http_method).upper(), call.operation.path_name))
        # TODO: handle exception
        result = call.response().result
        if 'result' in result.keys() and result['result'] is not None:
            return result['result']
        else:
            if remainingRetries > 0:
                self.logger.debug('retry after empty result for %s: %s' % (call.operation.operation_id, str(result)))
                return self._execute(call, silent, remainingRetries - 1)
            else:
                self.logger.error('got empty result for %s: %s' % (call.operation.operation_id, str(result)))
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
                      stop=float(stop) if stop is not None else None,
                      limit=float(o["price"]) if o['order_type'] == 'Limit' else None,
                      amount=float(o["qty"] * sideMulti))
        if "order_status" in o.keys():
            order.stop_triggered = o["order_status"] == "New" and stop is not None
            order.active = o['order_status'] == 'New' or o['order_status'] == 'Untriggered'
        elif "stop_order_status" in o.keys():
            order.stop_triggered = o["stop_order_status"] == 'Triggered' or o['stop_order_status'] == 'Active'
            order.active = o['stop_order_status'] == 'Triggered' or o['stop_order_status'] == 'Untriggered'
        execution = o['cum_exec_qty'] if 'cum_exec_qty' in o.keys() else 0
        order.executed_amount = float(execution) * sideMulti
        order.tstamp = parse_utc_timestamp(o['timestamp'] if 'timestamp' in o.keys() else o['created_at'])
        order.exchange_id = o["order_id"] if 'order_id' in o.keys() else o['stop_order_id']
        order.executed_price = None
        if 'cum_exec_value' in o.keys() and 'cum_exec_qty' in o.keys() and float(o['cum_exec_value']) != 0:
            order.executed_price = o['cum_exec_qty'] / float(o["cum_exec_value"])  # cause of inverse
        return order

    @staticmethod
    def barDictToBar(b):
        tstamp = int(b['open_time'] if 'open_time' in b.keys() else b['start'])
        return Bar(tstamp=tstamp, open=float(b['open']), high=float(b['high']),
                   low=float(b['low']), close=float(b['close']), volume=float(b['volume']))
