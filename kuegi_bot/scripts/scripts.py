import csv
import json
from datetime import datetime

from kuegi_bot.utils.helper import known_history_files
from kuegi_bot.utils.trading_classes import parse_utc_timestamp

#'''

def read_ref_bars(coin):
    bars= []
    end = known_history_files["bitstamp_" +coin.lower()+"eur"]
    for i in range(end-20,end):
        with open("history/bitstamp/"+coin.lower()+"eur_M1_"+str(i)+".json") as f:
            bars += json.load(f)
    return bars

def eurAt(bars, wantedtstamp):
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


def eurAtArray(bars,format,wantedArray):
    result= []
    for wanted in wantedArray:
        dt= None
        try:
            dt = datetime.strptime(wanted, format)
        except Exception as e:
            print(e)
            pass
        result.append(eurAt(bars,dt.timestamp() if dt is not None else None))
    return result

bars= read_ref_bars("btc")

res= eurAtArray(bars, "%d.%m.%Y %H:%M", [
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

import csv

walletData= get_wallet_records()


coin= "xrp"

bars= read_ref_bars(coin)

with open("bybitHistory"+coin+".csv", 'w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(["type","time", "amount", "balance","eurValueOfCoin"])
    for entry in reversed(walletData):
        if entry['coin'] == coin.upper():
            writer.writerow([entry['type'],
                             entry['exec_time'],
                             entry['amount'],
                             entry['wallet_balance'],
                             eurAt(bars,datetime.strptime(entry['exec_time'],"%Y-%m-%dT%H:%M:%S.%fZ").timestamp())])


print("done writing wallet history to file bybitHistory.csv")


#'''
