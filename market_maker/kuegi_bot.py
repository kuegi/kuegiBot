from market_maker.trade_engine import TradingBot, Order, Account
from market_maker.kuegi_channel import KuegiChannel, Data, clean_range

class KuegiBot(TradingBot):

    def __init__(self,max_look_back: int = 15, threshold_factor: float = 0.9, buffer_factor: float = 0.05,
                 max_dist_factor: float = 2,
                 max_channel_size_factor : float = 6, risk_factor : float = 0.01):
        super().__init__()
        self.channel= KuegiChannel(max_look_back,threshold_factor,buffer_factor,max_dist_factor)
        self.max_channel_size_factor = max_channel_size_factor
        self.risk_factor= risk_factor

    def prep_bars(self,bars:list):
        self.channel.on_tick(bars)

    def manage_open_orders(self, bars: list, account: Account):
        # TODO: adapt stops to channel values
        pass

    def open_orders(self, bars: list, account: Account):
        if not self.check_for_new_bar(bars) or  len(bars) < 5:
            return # only open orders on begining of bar

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

                self.order_interface.send_order(Order(amount=risk/diffLong,stop = longEntry, limit=longEntry-1))
                self.order_interface.send_order(Order(amount=-risk/diffShort,stop = shortEntry, limit=shortEntry+1))
