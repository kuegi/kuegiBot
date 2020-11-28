var barSeries;
var cvdSeries;
var volumeSeries;

var candles= [];
var cvds= [];
var volumes= [];

var chart;

var volumeGray= 'rgba(150,150,150,0.8)';
var targetTF= 5;

function aggregateM1Data(m1Data) {
    var result= [];
    m1Data.sort((a,b) => {
        return a.tstamp - b.tstamp;
    });
    var lastTstamp = 0;
    m1Data.forEach(b => {
        var bar;
        var barTstamp= Math.floor(b.tstamp /(60*targetTF))*(60*targetTF);
        var bar= { tstamp: barTstamp,
        open: 0, high:0, low:999999999, close:0, buyVolume:0, sellVolume:0, volume:0 };
        var count= 0;
        for(let exchange in b.barsByExchange) {
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
        bar.open /= count;
        bar.close /= count;

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
        timeScale: {
            visible: true,
            timeVisible: true
        }
    });
    cvdSeries = chart.addLineSeries({ priceScaleId: 'left'});
    barSeries= chart.addCandlestickSeries({ priceScaleId: 'right'});
    volumeSeries = chart.addHistogramSeries({
        priceFormat: {
            type: 'volume',
        },
        priceScaleId: '',
        scaleMargins: {
            top: 0.8,
            bottom: 0,
        },
    });
    initData();
    window.onresize= resize;
    window.setInterval(refresh, 1000)
}

function resize() {
    container= document.getElementById('chart');
    chart.resize(container.offsetWidth,container.offsetHeight);
}

function initData() {
    var targetTF= Number($("#tf").get(0).value);
    today= new Date();
    $.getJSON(today.toISOString().substr(0,10)+'.json', function(data) {
        candles= [];
        cvds= [];
        volumes= [];
        cvd= 0;
        aggregateM1Data(data).forEach(b => {
            var bar= { time: b.tstamp,
            open: b.open, high:b.high, low:b.low, close:b.close };
            cvd += b.buyVolume-b.sellVolume
            var cvdEntry= { time: b.tstamp, value: cvd };
            candles.push(bar);
            cvds.push(cvdEntry);
            volumes.push({time:b.tstamp, value:b.volume, color: volumeGray});
        });

        barSeries.setData(candles);
        cvdSeries.setData(cvds);
        volumeSeries.setData(volumes);
        chart.timeScale().fitContent();
    });
}

function refresh() {
    $.getJSON('latest.json', function(data) {
        var totalCVD=cvds[cvds.length-2].value;

        aggregateM1Data(data).forEach(b => {
            var bar= { time: b.tstamp,
            open: b.open, high:b.high, low:b.low, close:b.close };
            var cvd= b.buyVolume-b.sellVolume;
            var cvdEntry= { time: b.tstamp, value:totalCVD+cvd };
            vEntry= {time:b.tstamp, value:b.volume, color: volumeGray};

            if(candles[candles.length-1].time == b.tstamp) {
                candles[candles.length-1]= bar;
            }
            if(candles[candles.length-1].time < b.tstamp) {
                candles.push(bar);
            }
            if(volumes[volumes.length-1].time == b.tstamp) {
                volumes[volumes.length-1]= vEntry;
            }
            if(volumes[volumes.length-1].time < b.tstamp) {
                volumes.push(vEntry);
            }
            if(cvds[cvds.length-1].time == b.tstamp) {
                cvds[cvds.length-1]= cvdEntry;
                totalCVD += cvd;
            }
            if(cvds[cvds.length-1].time < b.tstamp) {
                cvds.push(cvdEntry);
                totalCVD += cvd;
            }
        });
        barSeries.setData(candles);
        cvdSeries.setData(cvds);
        volumeSeries.setData(volumes);
    });
}