# importing the requests library
import requests
import json
import math
from time import sleep

# ====================================
#
# api-endpoint
URL = "https://www.bitmex.com/api/v1/trade/bucketed?binSize=1m&partial=false&symbol=XBTUSD&count=1000&reverse=false"
result= []
start= 0
while True:
    # sending get request and saving the response as response object
    url= URL+"&start="+str(start)
    url
    r = requests.get(url=url)
    # extracting data in json format
    data = r.json()
    if len(data) < 1000:
        data
        result[-1]
        sleep(3)
    else:
        result += data
        start += len(data)
    if len(result) % 15000 == 0:
        batchsize= 50000
        max= math.ceil(len(result)/batchsize)
        idx= max - 2
        while idx < math.ceil(len(result)/batchsize):
            with open('M1_'+str(idx)+'.json','w') as file:
                json.dump(result[idx*batchsize:(idx+1)*batchsize],file)
                "wrote file "+str(idx)
                idx += 1


from datetime import datetime
import json

for idx in range(43):
    with open('history/M1_'+str(idx)+'.json','r') as file:
        bars = json.load(file)

    for b in bars:
        b['tstamp'] = datetime.strptime(b['timestamp'], '%Y-%m-%dT%H:%M:%S.%fZ').timestamp()

    with open('history/M1_' + str(idx) + '.json', 'w') as file:
        json.dump(bars,file)






