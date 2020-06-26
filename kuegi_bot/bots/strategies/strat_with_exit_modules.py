from typing import List
from functools import reduce

from kuegi_bot.bots.strategies.exit_modules import ExitModule
from kuegi_bot.bots.trading_bot import TradingBot
from kuegi_bot.bots.MultiStrategyBot import Strategy
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType


class EntryFilter:
    def __init__(self):
        self.logger= None

    def init(self, logger):
        self.logger = logger

    def entries_allowed(self,bars:List[Bar]):
        pass

class StrategyWithExitModulesAndFilter(Strategy):

    def __init__(self):
        super().__init__()
        self.exitModules = []
        self.entryFilters= []

    def withExitModule(self, module: ExitModule):
        self.exitModules.append(module)
        return self

    def withEntryFilter(self, filter: EntryFilter):
        self.entryFilters.append(filter)
        return self

    def init(self, bars: List[Bar], account: Account, symbol: Symbol):
        super().init(bars, account, symbol)
        for module in self.exitModules:
            module.init(self.logger)
        for fil in self.entryFilters:
            fil.init(self.logger)

    def got_data_for_position_sync(self, bars: List[Bar]) -> bool:
        return reduce((lambda x, y: x and y.got_data_for_position_sync(bars)), self.exitModules, True)

    def get_stop_for_unmatched_amount(self, amount: float, bars: List[Bar]):
        for module in self.exitModules:
            exit = module.get_stop_for_unmatched_amount(amount, bars)
            if exit is not None:
                return exit
        return None

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        orderType = TradingBot.order_type_from_order_id(order.id)
        if orderType == OrderType.SL:
            for module in self.exitModules:
                module.manage_open_order(order, position, bars, to_update, to_cancel, open_positions)

    def entries_allowed(self,bars:List[Bar]):
        for filter in self.entryFilters:
            if not filter.entries_allowed(bars):
                return False

        return True


