import atexit
import json
import os
import signal
import sys
import threading
import traceback
from time import sleep, time
from typing import List

from kuegi_bot.bots.MultiStrategyBot import MultiStrategyBot
from kuegi_bot.bots.kuegi_bot import KuegiBot
from kuegi_bot.bots.strategies.SfpStrat import SfpStrategy
from kuegi_bot.bots.strategies.entry_filters import DayOfWeekFilter
from kuegi_bot.bots.strategies.kuegi_strat import KuegiStrategy
from kuegi_bot.bots.strategies.exit_modules import SimpleBE, ParaTrail, ExitModule
from kuegi_bot.bots.trading_bot import TradingBot
from kuegi_bot.trade_engine import LiveTrading
from kuegi_bot.utils import log
from kuegi_bot.utils.telegram import TelegramBot
from kuegi_bot.utils.dotdict import dotdict
from kuegi_bot.utils.helper import load_settings_from_args


def start_bot(botSettings,telegram:TelegramBot=None):
    bot = MultiStrategyBot()
    originalSettings= dotdict(dict(botSettings))
    if "strategies" in botSettings.keys():
        strategies = dict(botSettings.strategies)
        del botSettings.strategies  # settings is now just the meta settings
        for stratId in strategies.keys():
            stratSettings = dict(botSettings)
            stratSettings = dotdict(stratSettings)
            stratSettings.update(strategies[stratId])
            if stratSettings.KB_RISK_FACTOR <= 0:
                logger.error("if you don't want to risk money, you shouldn't even run this bot!")
                continue

            if stratId == "kuegi":
                strat = KuegiStrategy(min_channel_size_factor=stratSettings.KB_MIN_CHANNEL_SIZE_FACTOR,
                                      max_channel_size_factor=stratSettings.KB_MAX_CHANNEL_SIZE_FACTOR,
                                      entry_tightening=stratSettings.KB_ENTRY_TIGHTENING,
                                      bars_till_cancel_triggered=stratSettings.KB_BARS_TILL_CANCEL_TRIGGERED,
                                      stop_entry=stratSettings.KB_STOP_ENTRY,
                                      delayed_entry=stratSettings.KB_DELAYED_ENTRY,
                                      delayed_cancel=stratSettings.KB_DELAYED_CANCEL,
                                      cancel_on_filter=stratSettings.KB_CANCEL_ON_FILTER) \
                    .withChannel(max_look_back=stratSettings.KB_MAX_LOOK_BACK,
                                 threshold_factor=stratSettings.KB_THRESHOLD_FACTOR,
                                 buffer_factor=stratSettings.KB_BUFFER_FACTOR,
                                 max_dist_factor=stratSettings.KB_MAX_DIST_FACTOR,
                                 max_swing_length=stratSettings.KB_MAX_SWING_LENGTH)
                if "KB_TRAIL_TO_SWING" in stratSettings.keys():
                    strat.withTrail(trail_to_swing=stratSettings.KB_TRAIL_TO_SWING,
                                    delayed_swing=stratSettings.KB_DELAYED_ENTRY,
                                    trail_back=stratSettings.KB_ALLOW_TRAIL_BACK)
            elif stratId == "sfp":
                strat = SfpStrategy(init_stop_type=stratSettings.SFP_STOP_TYPE,
                                    tp_fac=stratSettings.SFP_TP_FAC,
                                    min_wick_fac=stratSettings.SFP_MIN_WICK_FAC,
                                    min_swing_length=stratSettings.SFP_MIN_SWING_LENGTH,
                                    range_length=stratSettings.SFP_RANGE_LENGTH,
                                    min_rej_length=stratSettings.SFP_MIN_REJ_LENGTH,
                                    range_filter_fac=stratSettings.SFP_RANGE_FILTER_FAC,
                                    close_on_opposite=stratSettings.SFP_CLOSE_ON_OPPOSITE) \
                    .withChannel(max_look_back=stratSettings.KB_MAX_LOOK_BACK,
                                 threshold_factor=stratSettings.KB_THRESHOLD_FACTOR,
                                 buffer_factor=stratSettings.KB_BUFFER_FACTOR,
                                 max_dist_factor=stratSettings.KB_MAX_DIST_FACTOR,
                                 max_swing_length=stratSettings.KB_MAX_SWING_LENGTH)
                if "KB_TRAIL_TO_SWING" in stratSettings.keys():
                    strat.withTrail(trail_to_swing=stratSettings.KB_TRAIL_TO_SWING,
                                    delayed_swing=stratSettings.KB_DELAYED_ENTRY,
                                    trail_back=stratSettings.KB_ALLOW_TRAIL_BACK)
            else:
                strat = None
                logger.warn("unkown strategy: " + stratId)
            if strat is not None:
                strat.with_telegram(telegram)
                strat.withRM(risk_factor=stratSettings.KB_RISK_FACTOR,
                             risk_type=stratSettings.KB_RISK_TYPE,
                             max_risk_mul=stratSettings.KB_MAX_RISK_MUL,
                             atr_factor=stratSettings.KB_RISK_ATR_FAC)
                if "KB_BE_FACTOR" in stratSettings.keys():
                    strat.withExitModule(SimpleBE(factor=stratSettings.KB_BE_FACTOR,
                                                  buffer=stratSettings.KB_BE_BUFFER))
                for i in range(1,8):
                    factorKey= "KB_BE"+str(i)+"_FACTOR"
                    bufferKey= "KB_BE"+str(i)+"_BUFFER"
                    if factorKey in stratSettings.keys():
                        strat.withExitModule(SimpleBE(factor=stratSettings[factorKey],
                                                      buffer=stratSettings[bufferKey]))
                if "EM_PARA_INIT" in stratSettings.keys():
                    resetToCurrent= False
                    if "EM_PARA_RESET" in stratSettings.keys():
                        resetToCurrent= stratSettings.EM_PARA_RESET
                    strat.withExitModule(ParaTrail(accInit=stratSettings.EM_PARA_INIT,
                                                   accInc=stratSettings.EM_PARA_INC,
                                                   accMax=stratSettings.EM_PARA_MAX,
                                                   resetToCurrent=resetToCurrent))
                if "FILTER_DAYWEEK" in stratSettings.keys():
                    strat.withEntryFilter(DayOfWeekFilter(stratSettings.FILTER_DAYWEEK))
                bot.add_strategy(strat)
    else:
        if botSettings.KB_RISK_FACTOR <= 0:
            logger.error("if you don't want to risk money, you shouldn't even run this bot!")
        else:
            bot.add_strategy(KuegiStrategy(min_channel_size_factor=botSettings.KB_MIN_CHANNEL_SIZE_FACTOR,
                                           max_channel_size_factor=botSettings.KB_MAX_CHANNEL_SIZE_FACTOR,
                                           entry_tightening=botSettings.KB_ENTRY_TIGHTENING,
                                           bars_till_cancel_triggered=botSettings.KB_BARS_TILL_CANCEL_TRIGGERED,
                                           stop_entry=botSettings.KB_STOP_ENTRY,
                                           delayed_entry=botSettings.KB_DELAYED_ENTRY,
                                           delayed_cancel=botSettings.KB_DELAYED_CANCEL,
                                           cancel_on_filter=botSettings.KB_CANCEL_ON_FILTER)
                             .withChannel(max_look_back=botSettings.KB_MAX_LOOK_BACK,
                                          threshold_factor=botSettings.KB_THRESHOLD_FACTOR,
                                          buffer_factor=botSettings.KB_BUFFER_FACTOR,
                                          max_dist_factor=botSettings.KB_MAX_DIST_FACTOR,
                                          max_swing_length=botSettings.KB_MAX_SWING_LENGTH)
                             .withRM(risk_factor=botSettings.KB_RISK_FACTOR,
                                     risk_type=botSettings.KB_RISK_TYPE,
                                     max_risk_mul=botSettings.KB_MAX_RISK_MUL,
                                     atr_factor=botSettings.KB_RISK_ATR_FAC)
                             .withExitModule(SimpleBE(factor=botSettings.KB_BE_FACTOR,
                                                      buffer=botSettings.KB_BE_BUFFER))
                             .withTrail(trail_to_swing=botSettings.KB_TRAIL_TO_SWING,
                                        delayed_swing=botSettings.KB_DELAYED_ENTRY,
                                        trail_back=botSettings.KB_ALLOW_TRAIL_BACK)
                             )
    live = LiveTrading(settings=botSettings, trading_bot=bot,telegram=telegram)
    t = threading.Thread(target=live.run_loop)
    t.bot: LiveTrading = live
    t.originalSettings= originalSettings
    t.start()
    return t


def stop_all_and_exit():
    logger.info("closing bots")
    for t in activeThreads:
        t.bot.exit()

    logger.info("bye")
    atexit.unregister(stop_all_and_exit)
    sys.exit()


def term_handler(signum, frame):
    logger.info("got SIG %i" % signum)
    stop_all_and_exit()


def write_dashboard(dashboardFile):
    result = {}
    for thread in activeThreads:
        try:
            bot: LiveTrading = thread.bot
            if bot.alive:
                result[bot.id] = {
                    'alive': bot.alive,
                    "last_time": bot.bot.last_time,
                    "last_tick": str(bot.bot.last_tick_time)}
                data = result[bot.id]
                data['positions'] = []
                for pos in bot.bot.open_positions:
                    data['positions'].append(bot.bot.open_positions[pos].to_json())
                data['moduleData'] = {}
                data['moduleData'][bot.bars[0].tstamp] = ExitModule.get_data_for_json(bot.bars[0])
                data['moduleData'][bot.bars[1].tstamp] = ExitModule.get_data_for_json(bot.bars[1])

            else:
                result[bot.id] = {"alive": False}
        except Exception as e:
            logger.error("exception in writing dashboard: " + traceback.format_exc())
            thread.bot.alive= False

    try:
        os.makedirs(os.path.dirname(dashboardFile))
    except Exception:
        pass
    with open(dashboardFile, 'w') as file:
        json.dump(result, file, sort_keys=False, indent=4)

def run(settings):
    signal.signal(signal.SIGTERM, term_handler)
    signal.signal(signal.SIGINT, term_handler)
    atexit.register(stop_all_and_exit)

    if not settings:
        print("error: no settings defined. nothing to do. exiting")
        sys.exit()
    if settings.TELEGRAM_BOT is not None:
      telegram_bot:TelegramBot = TelegramBot(logger=logger,settings=dotdict(settings.TELEGRAM_BOT))
    else:
      telegram_bot= None
    logger.info("###### loading %i bots #########" % len(settings.bots))
    if settings.bots is not None:
        sets = settings.bots[:]
        del settings.bots  # settings is now just the meta settings
        for botSetting in sets:
            usedSettings = dict(settings)
            usedSettings = dotdict(usedSettings)
            usedSettings.update(botSetting)
            if len(usedSettings.API_KEY) == 0 or len(usedSettings.API_SECRET) == 0:
                logger.error("You have to put in apiKey and secret before starting!")
            else:
                logger.info("starting " + usedSettings.id)
                activeThreads.append(start_bot(botSettings=usedSettings, telegram=telegram_bot))

    logger.info("init done")
    if telegram_bot is not None:
        telegram_bot.send_log("init_done")

    if len(activeThreads) > 0:
        failures= 0
        lastError= 0
        while True:
            try:
                sleep(1)
                toRestart= []
                toRemove= []
                for thread in activeThreads:
                    if not thread.is_alive() or not thread.bot.alive:
                        logger.info("%s died. stopping" % thread.bot.id)
                        telegram_bot.send_log(thread.bot.id+" died. restarting")
                        toRestart.append(thread.originalSettings)
                        thread.bot.exit()
                        toRemove.append(thread)
                        failures = failures + 1
                        lastError= time()
                for thread in toRemove:
                    activeThreads.remove(thread)
                if time() - lastError > 60*15:
                    failures= 0 # reset errorCount after 15 minutes. only restart if more than 5 errors in 15 min
                if failures > 5:
                    logger.info("too many failures, restart the whole thing")
                    stop_all_and_exit()
                    break

                for usedSettings in toRestart:
                    logger.info("restarting " + usedSettings.id)
                    sleep(10)
                    activeThreads.append(start_bot(botSettings=usedSettings, telegram=telegram_bot))

                write_dashboard(settings.DASHBOARD_FILE)
            except Exception as e:
                logger.error("exception in main loop:\n "+ traceback.format_exc())
    else:
        logger.warn("no bots defined. nothing to do")


activeThreads: List[threading.Thread] = []
logger = None

if __name__ == '__main__':
    settings = load_settings_from_args()
    logger = log.setup_custom_logger("cryptobot",
                                     log_level=settings.LOG_LEVEL,
                                     logToConsole=settings.LOG_TO_CONSOLE,
                                     logToFile=settings.LOG_TO_FILE)
    run(settings)
else:
    logger = log.setup_custom_logger("cryptobot-pkg")
