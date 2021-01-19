from kuegi_bot.exchanges.binance_spot.binance_spot_interface import BinanceSpotInterface
from kuegi_bot.exchanges.bitfinex.bitfinex_interface import BitfinexInterface
from kuegi_bot.exchanges.bitmex.bitmex_interface import BitmexInterface
from kuegi_bot.exchanges.bitstamp.bitstmap_interface import BitstampInterface
from kuegi_bot.exchanges.bybit.bybit_interface import ByBitInterface
from kuegi_bot.exchanges.bybit_linear.bybitlinear_interface import ByBitLinearInterface
from kuegi_bot.exchanges.coinbase.coinbase_interface import CoinbaseInterface
from kuegi_bot.exchanges.huobi.huobi_interface import HuobiInterface
from kuegi_bot.exchanges.kraken.kraken_interface import KrakenInterface
from kuegi_bot.exchanges.phemex.phemex_interface import PhemexInterface

from kuegi_bot.utils import log
from kuegi_bot.utils.dotdict import dotdict
from kuegi_bot.utils.helper import load_settings_from_args
from kuegi_bot.utils.trading_classes import Order

settings= load_settings_from_args()

logger = log.setup_custom_logger("cryptobot",
                                 log_level=settings.LOG_LEVEL,
                                 logToConsole=True,
                                 logToFile= False)


def onTick(fromAccountAction):
    logger.info("got Tick "+str(fromAccountAction))

'''bitfinex

settings= dotdict({})
settings.SYMBOL = "tBTCUSD"
client= BitfinexInterface(settings=settings, logger=logger, on_tick_callback=onTick)

#'''

'''kraken

settings= dotdict({})
settings.SYMBOL = "XBT/USD"
client= KrakenInterface(settings=settings, logger=logger, on_tick_callback=onTick)

#'''

'''coinbase

settings= dotdict({})
settings.SYMBOL = "BTC-USD"
client= CoinbaseInterface(settings=settings, logger=logger, on_tick_callback=onTick)

#'''

'''huobi

settings= dotdict({})
settings.SYMBOL = "btcusdt"
client= HuobiInterface(settings=settings, logger=logger, on_tick_callback=onTick)

#'''

'''binance_spot
settings= dotdict({})
settings.SYMBOL = "btcusdt"
client= BinanceSpotInterface(settings=settings, logger=logger, on_tick_callback=onTick)

#'''

'''bitstamp
settings= dotdict({})
settings.SYMBOL = "btcusd"
client= BitstampInterface(settings=settings,logger=logger,on_tick_callback=onTick)


#'''

'''phemex

client= PhemexInterface(settings=settings,logger=logger,on_tick_callback=onTick)

#'''



''' binance_future

from binance_future.exception.binanceapiexception import BinanceApiException
from binance_future.model.candlestickevent import Candlestick
from binance_future import RequestClient, SubscriptionClient
from binance_future.model import CandlestickInterval, OrderSide, OrderType, TimeInForce, SubscribeMessageType

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

'''
if settings.EXCHANGE == 'bybit':
    interface= ByBitInterface(settings= settings,logger= logger,on_tick_callback=onTick)
    b= interface.bybit
    w= interface.ws
elif settings.EXCHANGE == 'bybit-linear':
        interface = ByBitLinearInterface(settings=settings, logger=logger, on_tick_callback=onTick)
        b = interface.bybit
        w = interface.ws
else:
    interface= BitmexInterface(settings=settings,logger=logger,on_tick_callback=onTick)

bars= interface.get_bars(240,0)


def get_wallet_records():
    result = []
    gotone = True
    page = 1
    while gotone:
        data = b.Wallet.Wallet_getRecords(start_date="2020-01-01", end_date="2021-01-01", limit="50",
                                          page=str(page)).response().result['result']['data']
        gotone = len(data) > 0
        result = result + data
        page = page + 1
    return result


#b.Wallet.Wallet_getRecords().response().result['result']['data']

# '''
