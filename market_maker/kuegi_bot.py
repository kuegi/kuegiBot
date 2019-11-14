from market_maker.trade_engine import TradingBot, Order, Account, Bar, OrderInterface
from market_maker.kuegi_channel import KuegiChannel, Data, clean_range
from market_maker.utils import log

from typing import List

logger = log.setup_custom_logger('kuegi_bot')

class Position:
    def __init__(self, id, entry, stop, amount):
        self.id= id
        self.status= "pending"
        self.wanted_entry= entry
        self.initial_stop= stop
        self.amount= amount

class KuegiBot(TradingBot):

    def __init__(self,max_look_back: int = 15, threshold_factor: float = 0.9, buffer_factor: float = 0.05,
                 max_dist_factor: float = 2,
                 max_channel_size_factor : float = 6, risk_factor : float = 0.01):
        super().__init__()
        self.channel= KuegiChannel(max_look_back,threshold_factor,buffer_factor,max_dist_factor)
        self.max_channel_size_factor = max_channel_size_factor
        self.risk_factor= risk_factor
        self.open_positions = {}
        self.known_order_history = 0
        self.position_history= []

    def prep_bars(self,bars:list):
        self.channel.on_tick(bars)

    def cancel_other_orders(self,posId,account:Account):
        to_cancel= []
        for o in account.open_orders:
            if o.id.split("_")[0] == posId:
                to_cancel.append(o)
        for o in to_cancel:
            self.order_interface.cancel_order(o.id)

    def manage_open_orders(self, bars: list, account: Account):
        for order in account.order_history[self.known_order_history:]:
            if order.executed_amount == 0:
                continue
            id_parts= order.id.split("_")
            if id_parts[0]+"_"+id_parts[1] not in self.open_positions.keys():
                continue
            position= self.open_positions[id_parts[0]+"_"+id_parts[1]]

            if position is not None:
                if id_parts[2] == "entry" and position.status == "pending":
                    position.status= "open"
                    position.filled_entry= order.executed_price
                    # clear other side
                    self.cancel_other_orders(id_parts[0],account)
                    other = "short" if id_parts[1] == "long" else "long"
                    del self.open_positions[id_parts[0]+"_"+other]
                    # add stop
                    self.order_interface.send_order(Order(orderId=position.id+"_exit",stop=position.initial_stop,amount=-position.amount))

                if id_parts[2] == "exit" and position.status == "open":
                    position.status = "closed"
                    position.filled_exit = order.executed_price
                    self.position_history.append(position)
                    del self.open_positions[position.id]
                    self.cancel_other_orders(id_parts[0],account)

        self.known_order_history= len(account.order_history)

        data:Data= self.channel.get_data(bars[1])
        if data is not None:
            stopLong = data.longTrail
            stopShort= data.shortTrail
            for order in account.open_orders:
                id_parts= order.id.split("_")
                if id_parts[2] == "exit":
                    # trail
                    if order.amount < 0 and order.stop_price < stopLong:
                        order.stop_price = stopLong
                        self.order_interface.update_order(order)
                    if order.amount > 0 and order.stop_price > stopShort:
                        order.stop_price = stopShort
                        self.order_interface.update_order(order)

    def open_orders(self, bars: List[Bar], account: Account):
        if not self.check_for_new_bar(bars) or  len(bars) < 5:
            return # only open orders on begining of bar

        for position in self.open_positions.values() :
            if position.status == "pending":
                return #no new pendings

        last_data:Data= self.channel.get_data(bars[2])
        data:Data= self.channel.get_data(bars[1])
        if data is not None and last_data is not None and \
                data.shortSwing is not None and data.longSwing is not None and \
                last_data.shortSwing is not None and last_data.longSwing is not None:
            range= data.longSwing - data.shortSwing

            atr = clean_range(bars, offset=0, length=self.channel.max_look_back * 2)
            if 0 < range < atr*self.max_channel_size_factor:
                risk = account.balance*self.risk_factor
                stopLong= max(data.shortSwing,data.longTrail)
                stopShort= min(data.longSwing,data.shortTrail)

                longEntry= data.longSwing
                shortEntry= data.shortSwing

                diffLong= longEntry-stopLong if longEntry > stopLong else range
                diffShort= stopShort - shortEntry if stopShort > shortEntry else range

                posId= str(bars[0].tstamp)
                self.order_interface.send_order(Order(orderId= posId+"_long_entry", amount=risk/diffLong,stop = longEntry, limit=longEntry-1))
                self.open_positions[posId+"_long"]=Position(id=posId+"_long",entry=longEntry,amount=risk/diffLong,stop=stopLong)
                self.order_interface.send_order(Order(orderId= posId+"_short_entry",amount=-risk/diffShort,stop = shortEntry, limit=shortEntry+1))
                self.open_positions[posId+"_short"]=Position(id= posId+"_short",entry=shortEntry,amount=-risk/diffShort,stop=stopShort)
