var barSeries;
var cvdSeries;
var volumeSeries;
var volDeltaSeries;

var candles= [];
var cvds= [];
var volumeDeltas= [];
var volumes= [];

var chart;

var volumeGray= 'rgba(150,150,150,0.8)';
var volumeBuy= 'rgb(50,200,50)';
var volumeSell= 'rgb(250,50,50)';
var targetTF= 5;

function aggregateM1Data(m1Data) {
    var result= [];
    m1Data.sort((a,b) => {
        return a.tstamp - b.tstamp;
    });
    var wantedExchanges= new Set();
    document.getElementsByName("exchange").forEach(input => {
        if(input.checked) {
            wantedExchanges.add(input.value);
        }
    });
    var lastTstamp = 0;
    m1Data.forEach(b => {
        var bar;
        var barTstamp= Math.floor(b.tstamp /(60*targetTF))*(60*targetTF);
        var bar= { tstamp: barTstamp,
        open: 0, high:0, low:999999999, close:0, buyVolume:0, sellVolume:0, volume:0 };
        var count= 0;
        for(let exchange in b.barsByExchange) {
            if(wantedExchanges.has(exchange)) {
                var exBar= b.barsByExchange[exchange];
                bar.open += exBar.open;
                bar.high = Math.max(bar.high,exBar.high);
                bar.low= Math.min(bar.low,exBar.low);
                bar.close += exBar.close;
                bar.volume += exBar.volume;
                bar.buyVolume += exBar.buyVolume;
                bar.sellVolume += exBar.sellVolume;
                count++;
            }
        }
        if(count > 0) {
            bar.open /= count;
            bar.close /= count;
        } else {
            return;
        }
        if(barTstamp == lastTstamp) {
            var existing= result[result.length-1];
            existing.high= Math.max(existing.high,bar.high);
            existing.low= Math.min(existing.low,bar.low);
            existing.close= bar.close;
            existing.volume += bar.volume;
            existing.buyVolume += bar.buyVolume;
            existing.sellVolume += bar.sellVolume;
        } else {
            result.push(bar);
            lastTstamp= bar.tstamp;
        }
    });
    return result;
}


function init() {
    chart = LightweightCharts.createChart(document.getElementById('chart'),{
        rightPriceScale: {
            scaleMargins: {
              top: 0.1,
              bottom: 0.1,
            },
        },
        leftPriceScale: {
            scaleMargins: {
              top: 0.1,
              bottom: 0.1,
            },
        },
        timeScale: {
            rightOffset: 10,
            visible: true,
            timeVisible: true
        },
        crosshair: {
            horLine: {
              labelVisible: false,
            },
            mode: 0
        }
    });
    cvdSeries = chart.addLineSeries({ priceScaleId: 'left' ,
                priceLineVisible:false,
            });
    barSeries= chart.addCandlestickSeries({ priceScaleId: 'right' });
    volDeltaSeries = chart.addHistogramSeries({
        priceFormat: {type: 'volume'},
        priceScaleId: 'volume',
        scaleMargins: {
            top: 0.8,
            bottom: 0,
        },
        priceLineVisible:false,
        lastValueVisible: false
    });
    volumeSeries = chart.addHistogramSeries({
        priceFormat: {type: 'volume'},
        priceScaleId: 'volume',
        scaleMargins: {
            top: 0.8,
            bottom: 0,
        },
        priceLineVisible:false,
        lastValueVisible: false
    });
    initData(false);
    window.onresize= resize;
    window.setInterval(refresh, 1000)
}

function resize() {
    container= document.getElementById('chart');
    chart.resize(container.offsetWidth,container.offsetHeight);
}

function refreshExchanges(m1Data) {
    var possibleExchanges= new Set();
    m1Data.forEach(b => {
        for(let exchange in b.barsByExchange) {
            possibleExchanges.add(exchange);
        }
    });

    var exchanges= document.getElementById("exchanges");
    exchanges.innerHTML= "";
    possibleExchanges.forEach(exchange => {
        var label = document.createElement("label");
        var input= document.createElement("input");
        input.type= "checkbox";
        input.value= exchange;
        input.name="exchange";
        input.checked= true;
        input.onchange= reinitData;
        label.innerHTML = exchange;
        exchanges.appendChild(input);
        exchanges.appendChild(label);
    });
}

function reinitData() {
    initData(true);
}

function initData(isrefresh) {
    targetTF= Number($("#tf").get(0).value);
    today= new Date();
    $.getJSON(today.toISOString().substr(0,10)+'.json', function(data) {
        candles= [];
        cvds= [];
        volumes= [];
        volumeDeltas= [];
        cvd= 0;
        if(!isrefresh) {
            refreshExchanges(data);
        }
        aggregateM1Data(data).forEach(b => {
            var bar= { time: b.tstamp,
            open: b.open, high:b.high, low:b.low, close:b.close };
            cvd += b.buyVolume-b.sellVolume
            candles.push(bar);
            cvds.push( { time: b.tstamp, value: cvd });
            if(b.buyVolume > b.sellVolume) {
                volumeDeltas.push( { time: b.tstamp, value:b.buyVolume-b.sellVolume, color: volumeBuy });
            } else {
                volumeDeltas.push( { time: b.tstamp, value:b.sellVolume-b.buyVolume, color: volumeSell });
            }
            volumes.push({time:b.tstamp, value:b.volume, color: volumeGray});
        });

        barSeries.setData(candles);
        cvdSeries.setData(cvds);
        volumeSeries.setData(volumes);
        volDeltaSeries.setData(volumeDeltas);
        chart.timeScale().fitContent();
    });
}

function refresh() {
    $.getJSON('latest.json', function(data) {
        var totalCVD=cvds[cvds.length-2].value;

        aggregateM1Data(data).forEach(b => {
            var cvd= b.buyVolume-b.sellVolume;
            var deltaEntry;
            if(b.buyVolume > b.sellVolume) {
                deltaEntry= { time: b.tstamp, value:b.buyVolume-b.sellVolume, color: volumeBuy };
            } else {
                deltaEntry= { time: b.tstamp, value:b.sellVolume-b.buyVolume, color: volumeSell };
            }

            replaceLastOrAdd(candles,{ time: b.tstamp, open: b.open, high:b.high, low:b.low, close:b.close });
            replaceLastOrAdd(volumes,{ time: b.tstamp, value:b.volume, color: volumeGray});
            if(replaceLastOrAdd(cvds,{ time: b.tstamp, value:totalCVD+cvd })) {
                totalCVD += cvd;
            }
            replaceLastOrAdd(volumeDeltas,deltaEntry);
        });
        barSeries.setData(candles);
        cvdSeries.setData(cvds);
        volumeSeries.setData(volumes);
        volDeltaSeries.setData(volumeDeltas);
    });
}

function replaceLastOrAdd(array, entry) {
    if(array[array.length-1].time == entry.time) {
        array[array.length-1]= entry;
        return true;
    } else if(array[array.length-1].time < entry.time) {
        array.push(entry);
        return true;
    }
    return false;
}