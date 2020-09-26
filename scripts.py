import csv
import json
from datetime import datetime

with open("history/bitstamp/btceur_D1_0.json") as f:
    bars= json.load(f)

with open("btceur.csv",'w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(["time","open","high","low","close"])
    for bar in reversed(bars):
        writer.writerow([datetime.fromtimestamp(int(bar['timestamp'])).isoformat(),
                        bar['open'],
                        bar['high'],
                        bar['low'],
                        bar['close']])


#account history from bybit (execute in exchange_test)

result=[]
gotone=True
page=1
while gotone:
    data = b.Wallet.Wallet_getRecords(start_date="2019-01-01", end_date="2020-01-01", limit="50",
                                      page=str(page)).response().result['result']['data']
    gotone= len(data)>0
    result = result + data
    page = page+1


with open("bybitHistory.csv",'w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(["time","amount","balance"])
    for entry in reversed(result):
        if entry['type'] != "Deposit":
            writer.writerow([entry['exec_time'],
                        entry['amount'],
                        entry['wallet_balance']])
