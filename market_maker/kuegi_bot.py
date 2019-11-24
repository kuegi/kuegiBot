from market_maker.trade_engine import TradingBot, Order, Account, Bar, OrderInterface, Position
from market_maker.kuegi_channel import KuegiChannel, Data, clean_range
from market_maker.utils import log
import plotly.graph_objects as go

import math

from typing import List

from datetime import datetime

logger = log.setup_custom_logger('kuegi_bot')


class KuegiBot(TradingBot):

    def __init__(self,max_look_back: int = 13, threshold_factor: float = 2.5, buffer_factor: float = -0.0618,
                 max_dist_factor: float = 1, max_swing_length:int = 3,
                 max_channel_size_factor : float = 6, risk_factor : float = 0.01, entry_tightening= 0, bars_till_cancel_triggered= 3,
                 stop_entry: bool = False, trail_to_swing : bool = False,delayed_entry:bool = True,delayed_cancel:bool= False):
        super().__init__()
        self.myId = "KuegiBot_" + str(max_look_back) + '_' + str(threshold_factor) + '_' + str(
            buffer_factor) + '_' + str(max_dist_factor) + '_' + str(max_swing_length) + '__' + str(max_channel_size_factor) + '_' + str(
            int(stop_entry)) + '_' + str(int(trail_to_swing)) + '_' + str(int(delayed_entry))
        self.channel = KuegiChannel(max_look_back, threshold_factor, buffer_factor, max_dist_factor, max_swing_length)
        self.max_channel_size_factor = max_channel_size_factor
        self.risk_factor = risk_factor
        self.stop_entry= stop_entry
        self.trail_to_swing= trail_to_swing
        self.delayed_entry= delayed_entry
        self.entry_tightening= entry_tightening
        self.bars_till_cancel_triggered= bars_till_cancel_triggered
        self.delayed_cancel= delayed_cancel
        self.is_new_bar= False

    def uid(self) -> str:
        return self.myId

    def prep_bars(self,bars:list):
        self.is_new_bar= self.check_for_new_bar(bars)
        if self.is_new_bar:
            self.channel.on_tick(bars)

    def sync_executions(self,bars:List[Bar], account: Account):
        for order in account.order_history[self.known_order_history:]:
            if order.executed_amount == 0:
                continue
            id_parts= order.id.split("_")
            if id_parts[0]+"_"+id_parts[1] not in self.open_positions.keys():
                continue
            position= self.open_positions[id_parts[0]+"_"+id_parts[1]]

            if position is not None:
                if id_parts[2] == "entry" and (position.status == "pending" or position.status == "triggered"):
                    position.status= "open"
                    position.filled_entry= order.executed_price
                    position.entry_tstamp= order.execution_tstamp
                    # clear other side
                    other_id = id_parts[0] + "_" + ("short" if id_parts[1] == "long" else "long")
                    if other_id in self.open_positions.keys():
                        self.open_positions[other_id].markForCancel = bars[0].tstamp
                    # add stop
                    self.order_interface.send_order(Order(orderId=position.id+"_exit",stop=position.initial_stop,amount=-position.amount))

                if id_parts[2] == "exit" and position.status == "open":
                    position.status = "closed"
                    position.filled_exit = order.executed_price
                    position.exit_tstamp= order.execution_tstamp
                    self.position_history.append(position)
                    del self.open_positions[position.id]

        self.known_order_history= len(account.order_history)
        open_position= 0
        for pos in self.open_positions.values():
            if pos.status == "open":
                open_position += pos.amount
        if abs(open_position - account.open_position) > 0.1:
            logger.error("open position doesnt match")

    def cancel_other_entry(self, pos_id, direction ,account: Account):
        other = "short" if direction == "long" else "long"
        self.cancel_entry(pos_id,other,account)

    def cancel_entry(self,pos_id,direction, account:Account):
        to_cancel= pos_id+"_"+direction+"_entry"
        for o in account.open_orders:
            if o.id == to_cancel:
                self.order_interface.cancel_order(o.id)
                #only cancel position if entry was still there
                if pos_id+"_"+direction in self.open_positions.keys():
                    del self.open_positions[pos_id+"_"+direction]
                break


    def manage_open_orders(self, bars: List[Bar], account: Account):
        self.sync_executions(bars,account)

        to_cancel_ids= []
        # check for triggered but not filled
        for order in account.open_orders:
            if order.stop_triggered:
                # clear other side
                id_parts = order.id.split("_")
                if id_parts[0] + "_" + id_parts[1] not in self.open_positions.keys():
                    continue
                other_id = id_parts[0]+"_"+ ("short" if id_parts[1] == "long" else "long")
                if other_id in self.open_positions.keys():
                    self.open_positions[other_id].markForCancel= bars[0].tstamp

                position = self.open_positions[id_parts[0] + "_" + id_parts[1]]
                position.status = "triggered"
                if not hasattr(position, 'waitingToFillSince'):
                    position.waitingToFillSince = bars[0].tstamp
                if (bars[0].tstamp - position.waitingToFillSince) > self.bars_till_cancel_triggered*(bars[0].tstamp - bars[1].tstamp):
                    #cancel
                    position.status = "notFilled"
                    position.exit_tstamp= bars[0].tstamp
                    self.position_history.append(position)
                    del self.open_positions[position.id]
                    to_cancel_ids.append(order.id)

        for id in to_cancel_ids:
            self.order_interface.cancel_order(id)

        # cancel others
        to_cancel=[]
        for p in self.open_positions.values():
            if hasattr(p,"markForCancel") and p.status == "pending" and (not self.delayed_cancel or p.markForCancel < bars[0].tstamp):
                id_to_cancel= p.id+"_"+"entry"
                self.order_interface.cancel_order(id_to_cancel)
                to_cancel.append(p.id)

        for key in to_cancel:
            del self.open_positions[key]

        if not self.is_new_bar or len(bars) < 5:
            return

        # trail stop only on new bar
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

            to_update= []
            to_cancel= []
            for order in account.open_orders:
                id_parts= order.id.split("_")
                if id_parts[2] == "exit":
                    # trail
                    if order.amount < 0 and order.stop_price < stopLong:
                        order.stop_price = stopLong
                        to_update.append(order)
                    if order.amount > 0 and order.stop_price > stopShort:
                        order.stop_price = stopShort
                        to_update.append(order)
                if id_parts[2] == "entry" and (data.longSwing is None or data.shortSwing is None):
                    pos= self.open_positions[id_parts[0]+"_"+id_parts[1]]
                    if pos.status == "pending": #dont delete if triggered
                        to_cancel.append(order.id)
                        del self.open_positions[id_parts[0]+"_"+id_parts[1]]
            for order in to_update:
                self.order_interface.update_order(order)
            for id in to_cancel:
                self.order_interface.cancel_order(id)

    @staticmethod
    def belongs_to(position:Position, order:Order) ->bool:
        id_parts= order.id.split("_")
        return id_parts[0]+'_'+id_parts[1] == position.id


    def open_orders(self, bars: List[Bar], account: Account):
        if not self.is_new_bar or len(bars) < 5:
            return # only open orders on begining of bar


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

                #first check if we should update an existing one
                longAmount= risk/diffLong
                shortAmount= risk/diffShort

                foundLong= False
                foundShort= False
                for position in self.open_positions.values():
                    if position.status == "pending":
                        if position.amount > 0:
                            foundLong= True
                            entry= longEntry
                            stop= stopLong
                        else:
                            foundShort= True
                            entry= shortEntry
                            stop= stopShort

                        for order in account.open_orders:
                             if self.belongs_to(position,order):
                                newEntry= position.wanted_entry*(1-self.entry_tightening)+entry*self.entry_tightening
                                newStop= position.initial_stop*(1-self.entry_tightening)+stop*self.entry_tightening
                                newDiff= newEntry - newStop
                                amount= risk/newDiff
                                order.stop_price = newEntry
                                if not self.stop_entry:
                                    order.limit_price= newEntry-math.copysign(1,amount)
                                order.amount= amount
                                self.order_interface.update_order(order)

                                position.initial_stop= newStop
                                position.amount= amount
                                position.wanted_entry= newEntry
                                break



                posId= str(bars[0].tstamp)
                if not foundLong:
                    self.order_interface.send_order(Order(orderId= posId+"_long_entry", amount=longAmount,stop = longEntry, limit=longEntry-1 if not self.stop_entry else None))
                    self.open_positions[posId+"_long"]=Position(id=posId+"_long",entry=longEntry,amount=longAmount,stop=stopLong,tstamp=bars[0].tstamp)
                if not foundShort:
                    self.order_interface.send_order(Order(orderId= posId+"_short_entry",amount=-shortAmount,stop = shortEntry, limit= shortEntry+1 if not self.stop_entry else None))
                    self.open_positions[posId+"_short"]=Position(id= posId+"_short",entry=shortEntry,amount=-shortAmount,stop=stopShort,tstamp=bars[0].tstamp)

    def add_to_plot(self,fig: go.Figure,bars:List[Bar],time):
        lines = self.channel.get_number_of_lines()
        styles= self.channel.get_line_styles()
        names= self.channel.get_line_names()
        offset = 1 #we take it with offset 1
        logger.info("adding channel")
        for idx in range(0, lines):
            sub_data = list(map(lambda b: self.channel.get_data_for_plot(b)[idx], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[idx], name=self.channel.id + "_" + names[idx])

        logger.info("adding trades")
        #trades
        for pos in self.position_history:
            if pos.status == "closed":
                fig.add_shape(go.layout.Shape(
                    type="line",
                    x0=datetime.fromtimestamp(pos.entry_tstamp),
                    y0=pos.filled_entry,
                    x1=datetime.fromtimestamp(pos.exit_tstamp),
                    y1=pos.filled_exit,
                    line=dict(
                        color="Green" if pos.amount > 0 else "Red",
                        width=2,
                        dash="solid"
                    )
                ))
            if pos.status == "notFilled":
                fig.add_shape(go.layout.Shape(
                    type="line",
                    x0=datetime.fromtimestamp(pos.signal_tstamp),
                    y0=pos.wanted_entry,
                    x1=datetime.fromtimestamp(pos.exit_tstamp),
                    y1=pos.wanted_entry,
                    line=dict(
                        color="Blue",
                        width=1,
                        dash="dot"
                    )
                ))

        fig.update_shapes(dict(xref='x', yref='y'))
