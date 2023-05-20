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
from kuegi_bot.bots.strategies.SfpStrat import SfpStrategy
from kuegi_bot.bots.strategies.strategy_one import StrategyOne
from kuegi_bot.bots.strategies.entry_filters import DayOfWeekFilter
from kuegi_bot.bots.strategies.kuegi_strat import KuegiStrategy
from kuegi_bot.bots.strategies.DegenStrat import DegenStrategy
from kuegi_bot.bots.strategies.exit_modules import SimpleBE, ParaTrail, ExitModule, FixedPercentage
from kuegi_bot.bots.strategies.strat_w_trade_man import ATRrangeSL
from kuegi_bot.trade_engine import LiveTrading
from kuegi_bot.utils import log
from kuegi_bot.utils.telegram import TelegramBot
from kuegi_bot.utils.dotdict import dotdict
from kuegi_bot.utils.helper import load_settings_from_args
from kuegi_bot.bots.strategies.MACross import MACross


def start_bot(botSettings,telegram:TelegramBot=None):
    bot = MultiStrategyBot()
    originalSettings= dotdict(dict(botSettings))
    if "strategies" in botSettings.keys():
        risk_reference= 1
        if "RISK_REFERENCE" in botSettings.keys():
            risk_reference= botSettings.RISK_REFERENCE
        if risk_reference <= 0:
            logger.error("if you don't want to risk money, you shouldn't even run this bot!")
        bot.risk_reference= risk_reference
        strategies = dict(botSettings.strategies)
        del botSettings.strategies  # settings is now just the meta settings
        for stratId in strategies.keys():
            stratSettings = dict(botSettings)
            stratSettings = dotdict(stratSettings)
            stratSettings.update(strategies[stratId])
            if stratSettings.KB_RISK_FACTOR <= 0:
                logger.error("if you don't want to risk money, you shouldn't even run this bot!")
                continue

            if stratId == "macross":
                strat = MACross(fastMA = stratSettings.MAC_FAST_MA,
                                slowMA =stratSettings.MAC_SLOW_MA)
            elif stratId == "kuegi":
                strat = KuegiStrategy(min_channel_size_factor=stratSettings.KB_MIN_CHANNEL_SIZE_FACTOR,
                                      max_channel_size_factor=stratSettings.KB_MAX_CHANNEL_SIZE_FACTOR,
                                      entry_tightening=stratSettings.KB_ENTRY_TIGHTENING,
                                      bars_till_cancel_triggered=stratSettings.KB_BARS_TILL_CANCEL_TRIGGERED,
                                      limit_entry_offset_perc=stratSettings.KB_LIMIT_OFFSET,
                                      delayed_entry=stratSettings.KB_DELAYED_ENTRY,
                                      delayed_cancel=stratSettings.KB_DELAYED_CANCEL,
                                      cancel_on_filter=stratSettings.KB_CANCEL_ON_FILTER,
                                      tp_fac=stratSettings.KB_TP_FAC,
                                      maxPositions = stratSettings.MAX_POSITIONS)\
                    .withChannel(max_look_back=stratSettings.KB_MAX_LOOK_BACK,
                                 threshold_factor=stratSettings.KB_THRESHOLD_FACTOR,
                                 buffer_factor=stratSettings.KB_BUFFER_FACTOR,
                                 max_dist_factor=stratSettings.KB_MAX_DIST_FACTOR,
                                 max_swing_length=stratSettings.KB_MAX_SWING_LENGTH)
                if "KB_TRAIL_TO_SWING" in stratSettings.keys():
                    strat.withTrail(trail_to_swing=stratSettings.KB_TRAIL_TO_SWING,
                                    delayed_swing=stratSettings.KB_DELAYED_ENTRY,
                                    trail_back=stratSettings.KB_ALLOW_TRAIL_BACK)
            elif stratId == "degen":
                strat = DegenStrategy(trail_short_fac=stratSettings.TRAIL_SHORT_FAC,
                                      trail_long_fac=stratSettings.TRAIL_LONG_FAC,
                                      atr_period=stratSettings.ATR_PERIOD,
                                      extreme_period=stratSettings.EXTREME_PERIOD,
                                      entry_short_fac=stratSettings.ENTRY_SHORT_FAC,
                                      entry_long_fac=stratSettings.ENTRY_LONG_FAC,
                                      rsiPeriod=stratSettings.RSI_PERIOD,
                                      periodStoch=stratSettings.PERIOD_STOCH,
                                      fastMACD=stratSettings.FAST_MACD,
                                      slowMACD=stratSettings.SLOW_MACD,
                                      signal_period=stratSettings.SIGNAL_PERIOD,
                                      rsi_high_limit=stratSettings.RSI_HIGH_LIMIT,
                                      rsi_low_limit=stratSettings.RSI_LOW_LIMIT,
                                      fastK_lim=stratSettings.FASTK_LIM,
                                      trail_past=stratSettings.TRAIL_PAST,
                                      close_on_opposite=stratSettings.CLOSE_ON_OPPOSITE,
                                      bars_till_cancel_triggered=stratSettings.BARS_TILL_CANCEL,
                                      cancel_on_filter=stratSettings.CANEL_ON_FILTER,
                                      tp_fac = stratSettings.TP_FAC)\
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
                strat = SfpStrategy(min_stop_diff_perc=stratSettings.SFP_MIN_STOP_DIFF,
                                    init_stop_type=stratSettings.SFP_STOP_TYPE,
                                    stop_buffer_fac=stratSettings.SFP_STOP_BUFFER_FAC,
                                    tp_fac=stratSettings.SFP_TP_FAC,
                                    min_wick_fac=stratSettings.SFP_MIN_WICK_FAC,
                                    min_air_wick_fac=stratSettings.SFP_MIN_AIR_WICK_FAC,
                                    min_wick_to_body=stratSettings.SFP_MIN_WICK_TO_BODY,
                                    min_swing_length=stratSettings.SFP_MIN_SWING_LENGTH,
                                    range_length=stratSettings.SFP_RANGE_LENGTH,
                                    min_rej_length=stratSettings.SFP_MIN_REJ_LENGTH,
                                    range_filter_fac=stratSettings.SFP_RANGE_FILTER_FAC,
                                    close_on_opposite=stratSettings.SFP_CLOSE_ON_OPPOSITE,
                                    tp_use_atr = stratSettings.SFP_USE_ATR,
                                    ignore_on_tight_stop = stratSettings.SFP_IGNORE_TIGHT_STOP,
                                    entries = stratSettings.SFP_ENTRIES) \
                    .withChannel(max_look_back=stratSettings.KB_MAX_LOOK_BACK,
                                 threshold_factor=stratSettings.KB_THRESHOLD_FACTOR,
                                 buffer_factor=stratSettings.KB_BUFFER_FACTOR,
                                 max_dist_factor=stratSettings.KB_MAX_DIST_FACTOR,
                                 max_swing_length=stratSettings.KB_MAX_SWING_LENGTH)
                if "KB_TRAIL_TO_SWING" in stratSettings.keys():
                    strat.withTrail(trail_to_swing=stratSettings.KB_TRAIL_TO_SWING,
                                    delayed_swing=stratSettings.KB_DELAYED_ENTRY,
                                    trail_back=stratSettings.KB_ALLOW_TRAIL_BACK)
            elif stratId == "strategyOne":
                strat = StrategyOne(# Strategy One
                                    std_fac_sell_off=stratSettings.STD_FAC_SELL_OFF,
                                    std_fac_reclaim=stratSettings.STD_FAC_RECLAIM,
                                    std_fac_sell_off_2=stratSettings.STD_FAC_SELL_OFF_2,
                                    std_fac_reclaim_2=stratSettings.STD_FAC_RECLAIM_2,
                                    std_fac_sell_off_3=stratSettings.STD_FAC_SELL_OFF_3,
                                    std_fac_reclaim_3=stratSettings.STD_FAC_RECLAIM_3,
                                    h_highs_trail_period=stratSettings.H_HIGHS_TRAIL_PERIOD,
                                    h_lows_trail_period=stratSettings.H_LOWS_TRAIL_PERIOD,
                                    nmb_bars_entry=stratSettings.NMB_BARS_ENTRY,
                                    const_trail_period=stratSettings.CONST_TRAIL_PERIOD,
                                    longBreakouts=stratSettings.LONGBREAKOUTS,
                                    longReclaimBBand=stratSettings.LONGRECLAIMBBAND,
                                    shortBreakdown=stratSettings.SHORTBREAKDOWN,
                                    shortLostBBand=stratSettings.SHORTLOSTBBAND,
                                    entry_upper_bb_std_fac=stratSettings.ENTRY_UPPER_BB_STD_FAC,
                                    entry_lower_bb_std_fac=stratSettings.ENTRY_LOWER_BB_STD_FAC,
                                    longReversals=stratSettings.LONGREVERSALS,
                                    shortReversals=stratSettings.SHORTREVERSALS,
                                    rsi_limit_breakout_long=stratSettings.RSI_LIMIT_BREAKOUT_LONG,
                                    # TrendStrategy
                                    timeframe=stratSettings.TIMEFRAME,
                                    ema_w_period=stratSettings.EMA_W_PERIOD,
                                    highs_trail_4h_period=stratSettings.HIGHS_TRAIL_4H_PERIOD,
                                    lows_trail_4h_period=stratSettings.LOWS_TRAIL_4H_PERIOD,
                                    trend_d_period=stratSettings.TREND_D_PERIOD,
                                    trend_w_period=stratSettings.TREND_W_PERIOD,
                                    atr_4h_period=stratSettings.ATR_4H_PERIOD,
                                    natr_4h_period_slow=stratSettings.NATR_4H_PERIOD_SLOW,
                                    bbands_4h_period=stratSettings.BBANDS_4H_PERIOD,
                                    plotIndicators=stratSettings.PLOTINDICATORS,
                                    trend_var_1=stratSettings.TREND_VAR_1,
                                    # Risk
                                    risk_with_trend=stratSettings.RISK_WITH_TREND,
                                    # SL
                                    risk_counter_trend=stratSettings.RISK_COUNTER_TREND,
                                    risk_ranging=stratSettings.RISK_RANGING,
                                    sl_atr_fac=stratSettings.SL_ATR_FAC,
                                    be_by_middleband=stratSettings.BE_BY_MIDDLEBAND,
                                    be_by_opposite=stratSettings.BE_BY_OPPOSITE,
                                    stop_at_middleband=stratSettings.STOP_AT_MIDDLEBAND,
                                    tp_at_middleband=stratSettings.TP_AT_MIDDLEBAND,
                                    atr_buffer_fac=stratSettings.ATR_BUFFER_FAC,
                                    tp_on_opposite=stratSettings.TP_ON_OPPOSITE,
                                    stop_at_new_entry=stratSettings.STOP_AT_NEW_ENTRY,
                                    trail_sl_with_bband=stratSettings.TRAIL_SL_WITH_BBAND,
                                    stop_short_at_middleband=stratSettings.STOP_SHORT_AT_MIDDLEBAND,
                                    moving_sl_atr_fac=stratSettings.MOVING_SL_ATR_FAC,
                                    sl_upper_bb_std_fac=stratSettings.SL_UPPER_BB_STD_FAC,
                                    sl_lower_bb_std_fac=stratSettings.SL_LOWER_BB_STD_FAC,
                                    # StrategyWithTradeManagement
                                    maxPositions=stratSettings.MAXPOSITIONS,
                                    close_on_opposite=stratSettings.CLOSE_ON_OPPOSITE,
                                    bars_till_cancel_triggered=stratSettings.BARS_TILL_CANCEL_TRIGGERED,
                                    limit_entry_offset_perc=stratSettings.LIMIT_ENTRY_OFFSET_PERC,
                                    delayed_cancel=stratSettings.DELAYED_CANCEL,
                                    cancel_on_filter=stratSettings.CANCEL_ON_FILTER
                                    )
            else:
                strat = None
                logger.warning("unkown strategy: " + stratId)
            if strat is not None:
                strat.with_telegram(telegram)
                strat.withRM(risk_factor=stratSettings.KB_RISK_FACTOR*risk_reference,
                             risk_type=stratSettings.KB_RISK_TYPE,
                             max_risk_mul=stratSettings.KB_MAX_RISK_MUL,
                             atr_factor=stratSettings.KB_RISK_ATR_FAC)
                if "KB_BE_FACTOR" in stratSettings.keys():
                    strat.withExitModule(SimpleBE(factor=stratSettings.KB_BE_FACTOR,
                                                  buffer=stratSettings.KB_BE_BUFFER))
                for i in range(1,10):
                    factorKey= "KB_BE"+str(i)+"_FACTOR"
                    bufferLongsKey= "KB_BE"+str(i)+"_BUFFERLONGS"
                    bufferShortsKey = "KB_BE" + str(i) + "_BUFFERSHORTS"
                    atrKey = "KB_BE" + str(i) + "_ATR"
                    if factorKey in stratSettings.keys():
                        strat.withExitModule(SimpleBE(factor=stratSettings[factorKey],
                                                      bufferLongs=stratSettings[bufferLongsKey],
                                                      bufferShorts=stratSettings[bufferShortsKey],
                                                      atrPeriod=stratSettings[atrKey]))
                for i in range(1,10):
                    rangeFacTriggerKey= "RANGE_FAC_TRIGGER_"+str(i)
                    longRangefacSLKey = "LONG_RANGE_FAC_SL_" + str(i)
                    shortRangefacSLKey = "SHORT_RANGE_FAC_SL_" + str(i)
                    rangeATRfactorKey = "RANGE_ATR_FAC_" + str(i)
                    atrPeriodKey = "ATR_PERIOD_" + str(i)
                    if rangeFacTriggerKey in stratSettings.keys():
                        strat.withExitModule(ATRrangeSL(rangeFacTrigger=stratSettings[rangeFacTriggerKey],
                                                        longRangefacSL=stratSettings[longRangefacSLKey],
                                                        shortRangefacSL=stratSettings[shortRangefacSLKey],
                                                        rangeATRfactor=stratSettings[rangeATRfactorKey],
                                                        atrPeriod=stratSettings[atrPeriodKey]
                                                        ))
                if "EM_PARA_INIT" in stratSettings.keys():
                    resetToCurrent= False
                    if "EM_PARA_RESET" in stratSettings.keys():
                        resetToCurrent= stratSettings.EM_PARA_RESET
                    strat.withExitModule(ParaTrail(accInit=stratSettings.EM_PARA_INIT,
                                                   accInc=stratSettings.EM_PARA_INC,
                                                   accMax=stratSettings.EM_PARA_MAX,
                                                   resetToCurrent=resetToCurrent))
                if "SL_PERC" in stratSettings.keys():
                    strat.withExitModule(FixedPercentage(slPercentage = stratSettings.SL_PERC,
                                                         useInitialSLRange= stratSettings.USE_INIT_SL,
                                                         rangeFactor =stratSettings.RANGE_FAC))
                if "FILTER_DAYWEEK" in stratSettings.keys():
                    strat.withEntryFilter(DayOfWeekFilter(stratSettings.FILTER_DAYWEEK))
                bot.add_strategy(strat)
    else:
        logger.error("only multistrat bot supported")
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
            engine: LiveTrading = thread.bot
            if engine.alive:
                bot= engine.bot
                result[engine.id] = {
                    'alive': engine.alive,
                    "last_time": bot.last_time,
                    "last_tick": str(bot.last_tick_time),
                    "last_tick_tstamp": bot.last_tick_time.timestamp() if bot.last_tick_time is not None else None,
                    "equity": engine.account.equity,
                    "risk_reference":bot.risk_reference,
                    "max_equity":bot.max_equity,
                    "time_of_max_equity":bot.time_of_max_equity
                }
                data = result[engine.id]
                data['positions'] = []
                for pos in engine.bot.open_positions:
                    data['positions'].append(engine.bot.open_positions[pos].to_json())
                data['moduleData'] = {}
                data['moduleData'][engine.bars[0].tstamp] = ExitModule.get_data_for_json(engine.bars[0])
                data['moduleData'][engine.bars[1].tstamp] = ExitModule.get_data_for_json(engine.bars[1])

            else:
                result[engine.id] = {"alive": engine.alive}
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
                try:
                    activeThreads.append(start_bot(botSettings=usedSettings, telegram=telegram_bot))
                except Exception as e:
                    if telegram_bot is not None:
                        telegram_bot.send_log("error in init of "+usedSettings.id)
                        telegram_bot.send_execution("error in init of "+usedSettings.id)
                    logger.error("exception in main loop:\n "+ traceback.format_exc())
                    stop_all_and_exit()

    logger.info("init done")
    if telegram_bot is not None:
        telegram_bot.send_log("init_done")
        telegram_bot.send_execution("init_done")

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
                        if telegram_bot is not None:
                            telegram_bot.send_log(thread.bot.id+" died. restarting")
                            telegram_bot.send_execution(thread.bot.id+" died. restarting")
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
