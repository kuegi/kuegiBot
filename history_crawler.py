import os
import requests
import json
import sys
from time import sleep
from datetime import datetime
from kuegi_bot.utils.utilities import history_file_name, load_existing_history, is_future_time


exchange = sys.argv[1] if len(sys.argv) > 1 else 'bybit'
symbol = sys.argv[2] if len(sys.argv) > 2 else 'BTCUSD'
print("Pulling "+ symbol + " price data from " + exchange)

try:
    os.makedirs('history/'+exchange)
except Exception:
    pass

exclude_current_candle = True
batch_size = 50000
acc_data = []
milli = True if exchange in ['bybit','bybit-linear', 'okx', 'bitfinex'] else False
jump = False

limits = {
    "bybit": 1000,
    "bybit-linear": 1000,
    "bitstamp": 1000,
    "kucoin-spot": 1500,
    "kucoin-futures": 1500,
    "okx": 100,
    "bitfinex": 1000
}

limit = limits[exchange]

urls = {
    "bybit": f"https://api.bybit.com/v5/market/kline?category=inverse&symbol={symbol}&interval=1&limit={limit}",
    "bybit-linear": f"https://api.bybit.com/v5/market/mark-price-kline?category=linear&symbol={symbol}&interval=1&limit={limit}",
    "bitstamp": f"https://www.bitstamp.net/api/v2/ohlc/{symbol}/?step=60&limit={limit}&exclude_current_candle={exclude_current_candle}",
    "kucoin-spot": f"https://api.kucoin.com/api/v1/market/candles?type=1min&symbol={symbol}",
    "kucoin-futures": f"https://api-futures.kucoin.com/api/v1/market/candles?type=1min&symbol={symbol}",
    "okx": f"https://www.okx.com/api/v5/market/history-candles?instId={symbol}&limit={limit}",
    "bitfinex": f"https://api-pub.bitfinex.com/v2/candles/trade:1m:t{symbol}/hist?sort=1&limit={limit}"
}

if exchange == 'bybit':
    if symbol == 'ETHUSD':
        start = 1548633600000
    elif symbol == 'BTCUSD':
        start = 1542502800000
    else:
        sys.exit("symbol not found")
elif exchange == "bitstamp":
    if symbol == "btcusd":
        start = 1322312400
    else:
        sys.exit("symbol not found")
elif exchange == "kucoin-spot":
    if symbol == "BTC-USDT":
        start = 1508720400
    else:
        sys.exit("symbol not found")
elif exchange == "okx":
    if symbol == "BTC-USDT":
        start = 1534294800000
    else:
        sys.exit("symbol not found")
elif exchange == "bitfinex":
    if symbol == "BTCUSD":
        start = 1372467600000
    else:
        sys.exit("symbol not found")
else:
    sys.exit("exchange not found")

acc_data, nmb_files = load_existing_history(exchange, symbol)

while True:
    # define start and end time of the next dataset which will be pulled
    if len(acc_data) > 0 and not jump:
        if exchange in ['bybit','bybit-linear','okx','bitfinex']:
            latest_timestamp = int(acc_data[-1][0])
            start = latest_timestamp
            print(datetime.fromtimestamp(latest_timestamp/1000))
        elif exchange == "bitstamp":
            latest_timestamp = int(acc_data[-1]["timestamp"])
            start = latest_timestamp
            print(datetime.fromtimestamp(latest_timestamp))
        elif exchange in ['kucoin-spot', 'kucoin-futures']:
            latest_timestamp = int(acc_data[-1][0])
            start = latest_timestamp
            print(datetime.fromtimestamp(latest_timestamp))
        else:
            print("Could not update the latest timestamp.")
            break

    # check if we reached present time
    if is_future_time(start, milli):
        print("All price data pulled. Good luck!")
        break

    end = start + limit * 60 * 1000 if milli else start + limit * 60
    if jump:
        print("Seems like there is no data available for this period. Trying to jump.")
        start = end
        end = start + limit * 60 * 1000 if milli else start + limit * 60
        jump = False

    # construct final url
    if exchange in ['kucoin-spot', 'kucoin-futures']:
        url = urls[exchange] + "&startAt=" + str(start) + "&endAt=" + str(end)
    elif exchange == "okx":
        url = urls[exchange] + "&after=" + str(end)
    else:
        url = urls[exchange] + "&start=" + str(start) + "&end=" + str(end)
    print(url + " __ " + str(len(acc_data)))

    # send request
    r = requests.get(url=url)
    if r.status_code != 200:
        if r.status_code == 429:
            print("Too many requests. Stopping for now.")
        else:
            print("Something went wrong. I am done.")
        break

    # extract data from request in json format
    if exchange in["bybit", "bybit-linear"]:
        data = r.json()["result"]['list']
        data.reverse()
        package_complete = len(data) >= limit-1
        if len(acc_data)>0 and len(data) > 0 and data[0][0] == acc_data[-1][0]:
            print("removed duplicate timestamp: " + str(data[0][0]))
            data = data[1:]
    elif exchange == "bitstamp":
        data = r.json()["data"]["ohlc"]
        package_complete = len(data) >= limit
        if len(acc_data)>0 and len(data) > 0 and data[0]['timestamp'] == acc_data[-1]['timestamp']:
            print("removed duplicate timestamp: " + str(data[0]['timestamp']))
            data = data[1:]
    elif exchange in ['kucoin-spot', 'kucoin-futures', 'okx']:
        data = r.json()['data']
        data.reverse()
        package_complete = len(data) >= limit - 1
        if len(acc_data) > 0 and len(data) > 0 and data[0][0] == acc_data[-1][0]:
            print("removed duplicate timestamp: " + str(data[0][0]))
            data = data[1:]
    elif exchange in ['bitfinex']:
        data = r.json()
        package_complete = len(data) >= limit - 1
        if len(acc_data) > 0 and len(data) > 0 and data[0][0] == acc_data[-1][0]:
            print("removed duplicate timestamp: " + str(data[0][0]))
            data = data[1:]
    else:
        break

    # merge data
    if len(data) == 0:
        jump = True
    else:
        acc_data += data

    # write to file
    next_file = (len(acc_data) > batch_size and nmb_files == 0) or (len(acc_data) > batch_size * nmb_files and nmb_files > 0)
    if next_file or not package_complete:
        idx = nmb_files - 1
        while idx < nmb_files + 1:
            if idx >= 0:
                file_path = history_file_name(idx, exchange, symbol)
                with open(file_path, 'w') as file:
                    content = acc_data[idx * batch_size:(idx + 1) * batch_size]
                    json.dump(content, file)
                    print("wrote to file " + str(idx))
            idx += 1

    if next_file:
        nmb_files += 1

    if not package_complete:
        print('Received less data than expected: ' + str(len(data)) + ' entries')
        print("Short break. Will continue shortly after.")
        sleep(1)
