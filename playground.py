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







