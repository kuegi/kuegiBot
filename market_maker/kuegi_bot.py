from market_maker.trade_engine import TradingBot, Order, Account, Bar, OrderInterface, Position
from market_maker.kuegi_channel import KuegiChannel, Data, clean_range
from market_maker.utils import log

from typing import List

logger = log.setup_custom_logger('kuegi_bot')


class KuegiBot(TradingBot):

    def __init__(self,max_look_back: int = 15, threshold_factor: float = 0.9, buffer_factor: float = 0.05,
                 max_dist_factor: float = 2, max_swing_length:int = 3,
                 max_channel_size_factor : float = 6, risk_factor : float = 0.01,
                 stop_entry: bool = False, trail_to_swing : bool = False,delayed_entry:bool = True):
        super().__init__()
        self.myId = "KuegiBot_" + str(max_look_back) + '_' + str(threshold_factor) + '_' + str(
            buffer_factor) + '_' + str(max_dist_factor) +'_' + str(max_swing_length) + '__' + str(max_channel_size_factor) + '_' + str(
            int(stop_entry)) + '_' + str(int(trail_to_swing)) + '_' + str(int(delayed_entry))
        self.channel = KuegiChannel(max_look_back, threshold_factor, buffer_factor, max_dist_factor, max_swing_length)
        self.max_channel_size_factor = max_channel_size_factor
        self.risk_factor = risk_factor
        self.stop_entry= stop_entry
        self.trail_to_swing= trail_to_swing
        self.delayed_entry= delayed_entry

    def uid(self) -> str:
        return self.myId

    def prep_bars(self,bars:list):
        self.channel.on_tick(bars)

    def cancel_other_orders(self,posId, account:Account,direction= None):
        to_cancel= []
        for o in account.open_orders:
            split= o.id.split("_")
            if split[0] == posId and (direction is None or split[1] == direction):
                to_cancel.append(o)
        for o in to_cancel:
            self.order_interface.cancel_order(o.id)

    def sync_executions(self,account: Account):
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
                    position.entry_tstamp= order.execution_tstamp
                    # clear other side
                    self.cancel_other_side(id_parts[0],id_parts[1],account)
                    # add stop
                    self.order_interface.send_order(Order(orderId=position.id+"_exit",stop=position.initial_stop,amount=-position.amount))

                if id_parts[2] == "exit" and position.status == "open":
                    position.status = "closed"
                    position.filled_exit = order.executed_price
                    position.exit_tstamp= order.execution_tstamp
                    self.position_history.append(position)
                    del self.open_positions[position.id]
                    self.cancel_other_orders(id_parts[0],account)

        self.known_order_history= len(account.order_history)

    def cancel_other_side(self, pos_id, direction ,account: Account):
        other = "short" if direction == "long" else "long"
        self.cancel_other_orders(pos_id,account,other)
        if pos_id+"_"+other in self.open_positions.keys():
            del self.open_positions[pos_id+"_"+other]

    def manage_open_orders(self, bars: list, account: Account):
        self.sync_executions(account)

        # check for triggered but not filled
        for order in account.open_orders:
            if order.stop_triggered:
                # clear other side
                id_parts = order.id.split("_")
                self.cancel_other_side(id_parts[0],id_parts[1],account)
                wait= order.waitingToFill if hasattr(order, 'waitingToFill') else 0
                if wait > 3 :
                    #cancel
                    if id_parts[0] + "_" + id_parts[1] not in self.open_positions.keys():
                        continue
                    position = self.open_positions[id_parts[0] + "_" + id_parts[1]]
                    position.status = "notFilled"
                    position.exit_tstamp= bars[0].tstamp
                    self.position_history.append(position)
                    del self.open_positions[position.id]
                    self.order_interface.cancel_order(order.id)
                else:
                    order.waitingToFill = wait +1


        if len(bars) < 5:
            return
        # trail stop
        last_data:Data= self.channel.get_data(bars[2])
        data:Data= self.channel.get_data(bars[1])
        if data is not None:
            stopLong = data.longTrail
            stopShort= data.shortTrail
            if self.trail_to_swing and \
                    data.longSwing is not None and data.shortSwing is not None and \
                    (not self.delayed_entry or (last_data is not None and \
                    last_data.longSwing is not None and last_data.shortSwing is not None)):
                stopLong= max(data.shortSwing, stopLong)
                stopShort= min(data.longSwing, stopShort)

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
                (not self.delayed_entry or (last_data.shortSwing is not None and last_data.longSwing is not None)):
            range= data.longSwing - data.shortSwing

            atr = clean_range(bars, offset=0, length=self.channel.max_look_back * 2)
            if 0 < range < atr*self.max_channel_size_factor:
                risk = account.equity*self.risk_factor
                if self.risk_factor > 1 :
                    risk= self.risk_factor
                stopLong= int(max(data.shortSwing,data.longTrail))
                stopShort= int(min(data.longSwing,data.shortTrail))

                longEntry= int(data.longSwing)
                shortEntry= int(data.shortSwing)

                diffLong= longEntry-stopLong if longEntry > stopLong else range
                diffShort= stopShort - shortEntry if stopShort > shortEntry else range

                posId= str(bars[0].tstamp)
                self.order_interface.send_order(Order(orderId= posId+"_long_entry", amount=risk/diffLong,stop = longEntry, limit= longEntry-1 if not self.stop_entry else None))
                self.open_positions[posId+"_long"]=Position(id=posId+"_long",entry=longEntry,amount=risk/diffLong,stop=stopLong,tstamp=bars[0].tstamp)
                self.order_interface.send_order(Order(orderId= posId+"_short_entry",amount=-risk/diffShort,stop = shortEntry, limit= shortEntry+1 if not self.stop_entry else None))
                self.open_positions[posId+"_short"]=Position(id= posId+"_short",entry=shortEntry,amount=-risk/diffShort,stop=stopShort,tstamp=bars[0].tstamp)
