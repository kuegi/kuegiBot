from datetime import datetime
from typing import List

from kuegi_bot.bots.strategies.strat_with_exit_modules import EntryFilter
from kuegi_bot.utils.trading_classes import Bar


class DayOfWeekFilter(EntryFilter):

    def __init__(self, allowedDaysMask: int):
        super().__init__()
        self.allowedDaysMask= allowedDaysMask

    def init(self, logger):
        super().init(logger)
        self.logger.info("init DayOfWeek {0:b}".format(self.allowedDaysMask))

    def entries_allowed(self,bars:List[Bar]):
        dayOfWeek= datetime.fromtimestamp(bars[0].tstamp).weekday()
        mask = 1 << dayOfWeek
        return (self.allowedDaysMask & mask) != 0
