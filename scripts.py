import csv
import json
from datetime import datetime

from kuegi_bot.utils.trading_classes import parse_utc_timestamp

#'''
bars= []
for i in range(85,97):
    with open("history/bitstamp/btceur_M1_"+str(i)+".json") as f:
        bars += json.load(f)


def eurAt(wantedtstamp):
    if wantedtstamp is None:
        return None
    start= int(bars[0]['timestamp'])
    end= int(bars[-1]['timestamp'])
    idx= int(len(bars)*(wantedtstamp-start)/(end-start))
    for bar in bars[max(0,idx-2):min(len(bars)-1,idx+2)]:
        tstamp= int(bar['timestamp'])
        if tstamp <= wantedtstamp <= tstamp + 60:
            return float(bar['close'])
    return None


def eurAtArray(format,wantedArray):
    result= []
    for wanted in wantedArray:
        dt= None
        try:
            dt = datetime.strptime(wanted, format)
        except Exception as e:
            print(e)
            pass
        result.append(eurAt(dt.timestamp() if dt is not None else None))
    return result


res= eurAtArray( "%d.%m.%Y %H:%M", [
])

#'''

'''
funding = dict()
with open("history/bybit/BTCUSD_fundraw.json") as f:
    fund= json.load(f)
    for key, value in fund.items():
        tstamp = parse_utc_timestamp(key)
        funding[int(tstamp)]= value

with open("history/bybit/BTCUSD_funding.json","w") as f:
    json.dump(funding,f)
#'''

'''
with open("btceur.csv", 'w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(["time", "open", "high", "low", "close"])
    for bar in reversed(bars):
        writer.writerow([datetime.fromtimestamp(int(bar['timestamp'])).isoformat(),
                         bar['open'],
                         bar['high'],
                         bar['low'],
                         bar['close']])

# account history from bybit (execute in exchange_test)

result = []
gotone = True
page = 1
while gotone:
    data = b.Wallet.Wallet_getRecords(start_date="2019-01-01", end_date="2020-01-01", limit="50",
                                      page=str(page)).response().result['result']['data']
    gotone = len(data) > 0
    result = result + data
    page = page + 1

with open("bybitHistory.csv", 'w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(["time", "amount", "balance"])
    for entry in reversed(result):
        if entry['type'] != "Deposit":
            writer.writerow([entry['exec_time'],
                             entry['amount'],
                             entry['wallet_balance']])

#'''
