# importing the requests library
import os

import requests
import json
import math
import sys
from time import sleep

import datetime
# ====================================
#
# api-endpoint
from kuegi_bot.utils.helper import history_file_name, get_last_known
from kuegi_bot.utils.trading_classes import parse_utc_timestamp

exchange = sys.argv[1] if len(sys.argv) > 1 else 'bybit'
# only accept USDT
if exchange in ['bybit-linear', 'binance_future', 'binanceSpot']:
    if len(sys.argv) > 2 and sys.argv[2][len(sys.argv[2])-1] == 'T':
        symbol = sys.argv[2]
    else:
        symbol = 'BTCUSDT'
elif exchange == 'bitmex':
    if len(sys.argv) > 2 and sys.argv[2][len(sys.argv[2])-1] == 'T':
        symbol = sys.argv[2]
    else:
        symbol = 'XBT'
else:
    symbol = sys.argv[2] if len(sys.argv) > 2 else 'BTCUSD'
print(f'crywling from: {exchange}, with symbol: {symbol}')

batchsize = 50000

urls = {
    "bitmex": "https://www.bitmex.com/api/v1/trade/bucketed?binSize=1m&partial=false&symbol=##symbol##&count=1000&reverse=false",
    "bybit": "https://api.bybit.com/v2/public/kline/list?symbol=##symbol##&interval=1",
    "bybit-linear": "https://api.bybit.com/public/linear/kline?symbol=##symbol##&interval=1",
    "binance_future": "https://fapi.binance.com/fapi/v1/klines?symbol=##symbol##&interval=1m&limit=1000",
    "binanceSpot": "https://api.binance.com/api/v1/klines?symbol=##symbol##&interval=1m&limit=1000",
    "phemex": "https://api.phemex.com/phemex-user/public/md/kline?resolution=60&symbol=##symbol##"
    # "bitstamp": "https://www.bitstamp.net/api/v2/ohlc/##symbol##/?step=60&limit=1000"
}

URL = urls[exchange].replace("##symbol##", symbol)

result = []
start = 1 if exchange in ['bybit', 'bybit-linear'] else 0
if exchange == 'phemex':
    start = 1574726400  # start of phemex
'''elif exchange == 'bitstamp':
    if symbol == "btceur":
        start = 1313670000
    elif symbol == "etheur":
        start = 1502860000
    elif symbol == "xrpeur":
        start = 1483410000
    else:
        start = 1327090000
'''

offset = 0

# init
# TODO: adapt this to your number if you already have history files

try:
    os.makedirs('history/'+exchange)
except Exception:
    pass

lastknown = get_last_known(exchange)

if lastknown >= 0:
    try:
        with open(history_file_name(lastknown,exchange,symbol), 'r') as file:
            result = json.load(file)
            if exchange == 'bitmex':
                start = lastknown * batchsize + len(result)
            elif exchange in ['bybit','bybit-linear']:
                start = int(result[-1]['open_time']) + 1
            elif exchange in ['phemex']:
                start = int(result[-1][0]) + 1
            elif exchange in ['binance_future','binanceSpot']:
                start= int(result[-1][6])
            # elif exchange in ['bitstamp']:
            #     start= int(result[-1]['timestamp'])
            offset= lastknown*batchsize
    except Exception as e:
        print("lier! you didn't have any history yet! ("+str(e)+")")
        lastknown = 0

wroteData = False
lastSync = 0
while True:
    # sending get request and saving the response as response object
    url = URL+"&start="+str(start)
    if exchange in ['bybit', 'bybit-linear']:
        url = URL + "&from=" + str(start)
    elif exchange in ['binance_future', 'binanceSpot']:
        url = URL + "&startTime="+str(start)
    elif exchange == 'phemex':
        url = URL + "&from=" + str(start)+"&to="+str(start+2000*60)

    print(url+" __ "+str(len(result)))
    r = requests.get(url=url)
    # extracting data in json format
    jsonData = r.json()
    data = jsonData
    if exchange in ['bybit', 'bybit-linear']:
        data = jsonData["result"]
        print(datetime.datetime.fromtimestamp(int(start)))
    elif exchange == 'phemex':
        if jsonData['msg'] == 'OK':
            data = jsonData['data']['rows']
            print(datetime.datetime.fromtimestamp(int(start)))
        else:
            data = []
    # elif exchange == "bitstamp":
    #     data = jsonData['data']['ohlc']

    wasOk = len(data) >= 200
    if not wasOk:
        print(str(data)[:100])
        # if exchange == "bitstamp" and len(result) == 0:
        #     start += 1000*60
    else:
        wroteData = False
        if exchange == 'bitmex':
            for b in data:
                b['tstamp'] = parse_utc_timestamp(b['timestamp'])
            result += data
        else:
            result += data

        lastSync += len(data)
        if exchange == 'bitmex':
            start = start + len(data)
            print(result[-1]['timestamp'])
        elif exchange in ['bybit', 'bybit-linear']:
            start = int(data[-1]['open_time'])+1
        elif exchange == 'phemex':
            if len(data) == 0:
                start += 2000*60
            else:
                start = int(data[-1][0]+1)
        elif exchange in ['binance_future', 'binanceSpot']:
            start = data[-1][6]  # closeTime of last bar
            print(datetime.datetime.fromtimestamp(result[-1][6]/1000))
        # elif exchange == 'bitstamp':
        #     start= data[-1]['timestamp']
        #     print(result[-1].tstamp)
    if lastSync > 15000 or (len(data) < 200 and not wroteData):
        wroteData = True
        lastSync = 0
        max = math.ceil((len(result)+offset)/batchsize)
        idx = max - 2
        while idx < max:
            if idx*batchsize-offset >= 0:
                with open(history_file_name(idx, exchange, symbol), 'w') as file:
                    json.dump(result[idx*batchsize-offset:(idx+1)*batchsize-offset], file)
                    print("wrote file "+str(idx))
            idx += 1

    if not wasOk:
        sleep(10)

#########################################
# live tests
########
