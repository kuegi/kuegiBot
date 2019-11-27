import bitmex
from bitmex_websocket import BitMEXWebsocket

from market_maker.settings import settings
from market_maker.utils.trading_classes import Order
from typing import List
from datetime import datetime

class BitMexInterface:
    def __init__(self):
        self.symbol= settings.SYMBOL
        self.bitmex= bitmex.bitmex(test=True, api_key=settings.API_KEY, api_secret=settings.API_SECRET)
        self.ws = BitMEXWebsocket(endpoint=settings.BASE_URL, symbol=self.symbol, api_key=settings.API_KEY, api_secret=settings.API_SECRET)

    def place_order(self, order: Order):
        """Place an order."""
        return self.bitmex.Order.Order_new(symbol=self.symbol,clOrderID=order.id,orderQty=order.amount,price=order.limit_price,stopPx=order.stop_price).result()

    def update_order(self, order: Order):
        """update an order."""
        return self.bitmex.Order.Order_amend(origClOrdID=order.id, orderQty=order.amount,
                                           price=order.limit_price, stopPx=order.stop_price).result()

    def cancel_order(self, orderID):
        """Cancel an existing order."""
        return self.bitmex.Order.Order_cancel(clOrdID=orderID).result()

    def get_orders(self):
        mexOrders = self.bitmex.Order.Order_getOrders().result()[0]
        result: List[Order] = []
        for o in mexOrders:
            order = Order(orderId=o["clOrdID"], stop=o["stopPx"], limit=o["price"], amount=o["orderQty"])
            order.stop_triggered = o["triggered"] == "StopOrderTriggered"
            order.executed_amount = o["orderQty"] - o["leavesQty"]
            order.tstamp = o['timestamp']
            order.active = o['ordStatus'] == 'New'
            order.exchange_id = o["orderID"]
            order.executed_price = o["avgPx"]
            result.append(order)

        return result

