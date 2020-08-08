# importing the requests library
import os

import requests
import json
import math
import sys
from time import sleep

from datetime import datetime
# ====================================
#
# api-endpoint
from kuegi_bot.utils.helper import history_file_name
from kuegi_bot.utils.trading_classes import parse_utc_timestamp

exchange = sys.argv[1] if len(sys.argv) > 1 else 'bybit'
symbol=  sys.argv[2] if len(sys.argv) > 1 else 'BTCUSD'
print("crawling from "+exchange)

batchsize = 50000

urls = {
    "bitmex": "https://www.bitmex.com/api/v1/trade/bucketed?binSize=1m&partial=false&symbol=##symbol##&count=1000&reverse=false",
    "bybit": "https://api.bybit.com/v2/public/kline/list?symbol=##symbol##&interval=1",
    "binance": "https://fapi.binance.com/fapi/v1/klines?symbol=##symbol##&interval=1m&limit=1000",
    "binanceSpot": "https://api.binance.com/api/v1/klines?symbol=##symbol##&interval=1m&limit=1000",
    "phemex":"https://api.phemex.com/phemex-user/public/md/kline?resolution=60&symbol=##symbol##"
}

URL = urls[exchange].replace("##symbol##",symbol)

result = []
start = 1 if exchange == 'bybit' else 0
if exchange == 'phemex':
    start= 1574726400 # start of phemex
offset = 0

# init
# TODO: adapt this to your number if you already have history files
filecount = {
    "bitmex_XBTUSD": 49,
    "bybit_BTCUSD": 17,
    "bybit_ETHUSD":16,
    "binance_BTCUSDT": 9,
    "binanceSpot_BTCUSD": 28,
    "phemex_BTCUSD":6
}
lastknown = filecount[exchange+symbol]

try:
    os.makedirs('history/'+exchange)
except Exception:
    pass

if lastknown >= 0:
    try:
        with open(history_file_name(lastknown,exchange,symbol), 'r') as file:
            result = json.load(file)
            if exchange == 'bitmex':
                start = lastknown * batchsize + len(result)
            elif exchange in ['bybit']:
                start = int(result[-1]['open_time']) + 1
            elif exchange in ['phemex']:
                start = int(result[-1][0]) + 1
            elif exchange in ['binance','binanceSpot']:
                start= int(result[-1][6])
            offset= lastknown*batchsize
    except Exception as e:
        print("lier! you didn't have any history yet! ("+str(e)+")")
        lastknown = 0

wroteData= False
lastSync= 0
while True:
    # sending get request and saving the response as response object
    url= URL+"&start="+str(start)
    if exchange == 'bybit':
        url = URL + "&from=" + str(start)
    elif exchange in ['binance','binanceSpot']:
        url= URL + "&startTime="+str(start)
    elif exchange == 'phemex':
        url = URL + "&from=" + str(start)+"&to="+str(start+2000*60)

    print(url+" __ "+str(len(result)))
    r = requests.get(url=url)
    # extracting data in json format
    jsonData= r.json()
    data=jsonData
    if exchange == 'bybit':
        data = jsonData["result"]
    if exchange == 'phemex':
        if jsonData['msg'] == 'OK':
            data = jsonData['data']['rows']
        else:
            data= []
    wasOk= len(data) >= 200
    if not wasOk:
        print(str(data)[:100])
        sleep(10)
    else:
        wroteData= False
        if exchange == 'bitmex':
            for b in data:
                b['tstamp'] = parse_utc_timestamp(b['timestamp'])
            result += data
        else:
            result += data
        lastSync += len(data)
        if exchange == 'bitmex':
            start= start +len(data)
        elif exchange == 'bybit':
            start = int(data[-1]['open_time'])+1
        elif exchange == 'phemex':
            if len(data) == 0:
                start += 2000*60
            else:
                start = int(data[-1][0]+1)
        elif exchange in ['binance','binanceSpot']:
            start= data[-1][6] # closeTime of last bar
    if lastSync > 15000 or (len(data) < 200 and not wroteData):
        wroteData= True
        lastSync= 0
        max= math.ceil((len(result)+offset)/batchsize)
        idx= max - 2
        while idx < max:
            if idx*batchsize-offset >= 0:
                with open(history_file_name(idx,exchange,symbol),'w') as file:
                    json.dump(result[idx*batchsize-offset:(idx+1)*batchsize-offset],file)
                    print("wrote file "+str(idx))
            idx += 1

#########################################
# live tests
########







