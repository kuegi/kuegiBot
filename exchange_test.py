from kuegi_bot.exchanges.bitmex.bitmex_interface import BitmexInterface
from kuegi_bot.exchanges.bybit.bybit_interface import ByBitInterface
from kuegi_bot.exchanges.phemex.phemex_interface import PhemexInterface

from kuegi_bot.utils import log
from kuegi_bot.utils.helper import load_settings_from_args
from kuegi_bot.utils.trading_classes import Order

settings= load_settings_from_args()

logger = log.setup_custom_logger("cryptobot",
                                 log_level=settings.LOG_LEVEL,
                                 logToConsole=True,
                                 logToFile= False)


def onTick(fromAccountAction):
    logger.info("got Tick "+str(fromAccountAction))

'''phemex

client= PhemexInterface(settings=settings,logger=logger,on_tick_callback=onTick)

#'''



''' binance

from binance_f.exception.binanceapiexception import BinanceApiException
from binance_f.model.candlestickevent import Candlestick
from binance_f import RequestClient, SubscriptionClient
from binance_f.model import CandlestickInterval, OrderSide, OrderType, TimeInForce, SubscribeMessageType

request_client = RequestClient(api_key=apiKey, secret_key=apiSecret)

ws = SubscriptionClient(api_key=apiKey,secret_key=apiSecret)


def callback(data_type: SubscribeMessageType, event: any):
    if data_type == SubscribeMessageType.RESPONSE:
        print("Event ID: ", event)
    elif data_type == SubscribeMessageType.PAYLOAD:
        print("Event type: ", event.eventType)
        print("Event time: ", event.eventTime)
        print(event.__dict__)
        if(event.eventType == "kline"):
            candle : Candlestick = event.data
            print(candle.open,candle.close,candle.high,candle.close,candle.closeTime,candle.startTime,candle.interval)
        elif(event.eventType == "ACCOUNT_UPDATE"):
            print("Event Type: ", event.eventType)
        elif(event.eventType == "ORDER_TRADE_UPDATE"):
            print("Event Type: ", event.eventType)
        elif(event.eventType == "listenKeyExpired"):
            print("Event: ", event.eventType)
            print("CAUTION: YOUR LISTEN-KEY HAS BEEN EXPIRED!!!")
    else:
        print("Unknown Data:")
    print()


def error(e: BinanceApiException):
    print(e.error_code + e.error_message)
    

listen_key = request_client.start_user_data_stream()
ws.subscribe_user_data_event(listen_key, callback, error)

request_client.keep_user_data_stream()

bars = request_client.get_candlestick_data(symbol="BTCUSDT", interval=CandlestickInterval.MIN1,
                                            startTime=0, endTime=None, limit=1000)

result = request_client.close_user_data_stream()

'''

#'''
if settings.EXCHANGE == 'bybit':
    interface= ByBitInterface(settings= settings,logger= logger,on_tick_callback=onTick)
    b= interface.bybit
    w= interface.ws
else:
    interface= BitmexInterface(settings=settings,logger=logger,on_tick_callback=onTick)

bars= interface.get_bars(240,0)

#b.Wallet.Wallet_getRecords().response().result['result']['data']

# '''
