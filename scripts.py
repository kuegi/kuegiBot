import csv
import json
from datetime import datetime

bars= []
for i in range(56):
    with open("history/bitstamp/btceur_M1_"+str(i)+".json") as f:
        bars += json.load(f)


def eurAt(wanted):
    dt = datetime.strptime(wanted, "%d-%m-%y %H:%M:%S")
    wantedstamp= dt.timestamp()
    for bar in bars:
        tstamp= int(bar['timestamp'])
        if tstamp <= wantedstamp <= tstamp + 60:
            return bar['close']

eurAt("30-05-19 17:08:40")


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
