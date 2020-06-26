from kuegi_bot.trade_engine import TradingBot, Order, Account, OrderInterface
import random


class RandomBot(TradingBot):

    def __init__(self):
        super().__init__()

    def open_orders(self, bars: list, account: Account):
        if account.open_position.quantity != 0:
            if random.randint(0,100) > 80:
                self.order_interface.send_order(Order(amount=-account.open_position.quantity))
        else:
            if random.randint(0,100) > 50:
                amount= random.randint(-5,5)
                if amount != 0:
                    self.order_interface.send_order(Order(amount=amount))