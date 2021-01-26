import csv
import json
from datetime import datetime

from kuegi_bot.exchanges.bybit.bybit_interface import ByBitInterface
from kuegi_bot.utils import log
from kuegi_bot.utils.helper import known_history_files, load_settings_from_args
from kuegi_bot.utils.trading_classes import parse_utc_timestamp

#'''

def read_ref_bars(coin):
    bars= []
    end = known_history_files["bitstamp_" +coin.lower()+"eur"]
    for i in range(end-20,end+1):
        with open("history/bitstamp/"+coin.lower()+"eur_M1_"+str(i)+".json") as f:
            bars += json.load(f)
    return bars

def eurAt(bars, wantedtstamp):
    if wantedtstamp is None:
        return None
    start= int(bars[0]['timestamp'])
    end= int(bars[-1]['timestamp'])
    idx= int(len(bars)*(wantedtstamp-start)/(end-start))

    tstamp = int(bars[idx]['timestamp'])
    result= float(bars[idx]['open'])
    delta= 1 if tstamp < wantedtstamp else -1
    while (tstamp - wantedtstamp)*delta < 0 and len(bars) > idx >= 0:
        tstamp = int(bars[idx]['timestamp'])
        result= float(bars[idx]['open'])
        idx += delta
    if abs(tstamp-wantedtstamp) > 60:
        print("got big difference in eurAt. deltasec: %d" %(tstamp-wantedtstamp))
    return result


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

'''
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

'''

'''
# getting account history, helpful for taxreports
settings= load_settings_from_args()

logger = log.setup_custom_logger("cryptobot",
                                 log_level=settings.LOG_LEVEL,
                                 logToConsole=True,
                                 logToFile= False)


def onTick(fromAccountAction):
    logger.info("got Tick "+str(fromAccountAction))



interface= ByBitInterface(settings= settings,logger= logger,on_tick_callback=onTick)
b= interface.bybit

walletData = []
gotone = True
page = 1
while gotone:
    data = b.Wallet.Wallet_getRecords(start_date="2020-01-01", end_date="2021-01-01", limit="50",
                                      page=str(page)).response().result['result']['data']
    gotone = len(data) > 0
    walletData = walletData + data
    page = page + 1


import csv


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


print("done writing wallet history to file bybitHistory"+coin+".csv")


#'''

#'''

bars = []
end = known_history_files["bitstamp_eurusd"]
for i in range(end - 20, end + 1):
    with open("history/bitstamp/eurusd_M1_" + str(i) + ".json") as f:
        bars += json.load(f)

# Date,Operation,Amount,Cryptocurrency,FIAT value,FIAT currency,Transaction ID,Withdrawal address,Reference
with open("cakeHistory.csv", 'r', newline='') as file:
    reader = csv.reader(file)
    with open("cakeHistoryWithEur.csv", 'w', newline='') as output:
        writer = csv.writer(output)
        for row in reader:
            date = row[0]
            if date != "Date":
                row.append(eurAt(bars, datetime.strptime(date, "%Y-%m-%dT%H:%M:%S%z").timestamp()))
            else:
                row.append("eurusd")
            writer.writerow(row)


#'''
