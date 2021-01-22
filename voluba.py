import traceback
from time import sleep

from kuegi_bot.utils import log
from kuegi_bot.utils.helper import load_settings_from_args
from kuegi_bot.voluba.aggregator import VolubaAggregator


def run(settings):
    try:
        voluba= VolubaAggregator(logger=logger,settings=settings)
        while True:
            voluba.aggregate_data()
            voluba.serialize_current_data()
            sleep(10)
    except Exception as e:
        logger.error("exception in main loop:\n "+ traceback.format_exc())


if __name__ == '__main__':
    settings = load_settings_from_args()
    logger = log.setup_custom_logger("voluba",
                                     log_level=settings.LOG_LEVEL,
                                     logToConsole=settings.LOG_TO_CONSOLE,
                                     logToFile=settings.LOG_TO_FILE)
    run(settings)
