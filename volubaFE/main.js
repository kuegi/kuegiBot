var barSeries;
var cvdSeries;
var volumeSeries;

var candles= [];
var cvds= [];
var volumes= [];

var chart;

var volumeGray= 'rgba(150,150,150,0.8)';

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
    today= new Date();
    $.getJSON(today.toISOString().substr(0,10)+'.json', function(data) {
        candles= [];
        cvds= [];
        cvd= 0;
        data.forEach(b => {
            var bar= { time: b.tstamp,
            open: 0, high:0, low:999999999, close:0 };
            var cvdEntry= { time: b.tstamp, value:0 };
            var count= 0;
            var volume= 0;
            for(let exchange in b.barsByExchange) {
                var exBar= b.barsByExchange[exchange];
                bar.open += exBar.open;
                bar.high = Math.max(bar.high,exBar.high);
                bar.low= Math.min(bar.low,exBar.low);
                bar.close += exBar.close;
                volume += exBar.volume;
                count++;
                cvd += exBar.buyVolume - exBar.sellVolume;
            }
            cvdEntry.value= cvd;
            bar.open /= count;
            bar.close /= count;
            candles.push(bar);
            cvds.push(cvdEntry);
            volumes.push({time:b.tstamp, value:volume, color: volumeGray});
        });

        barSeries.setData(candles);
        cvdSeries.setData(cvds);
        volumeSeries.setData(volumes);
        chart.timeScale().fitContent();
    });
    window.onresize= resize;
    window.setInterval(refresh, 1000)
}

function resize() {
    container= document.getElementById('chart');
    chart.resize(container.offsetWidth,container.offsetHeight);
}

function refresh() {
    $.getJSON('latest.json', function(data) {
        var totalCVD=cvds[cvds.length-2].value;
        data.forEach(b => {
            var bar= { time: b.tstamp,
            open: 0, high:0, low:999999999, close:0 };
            var count= 0;
            var cvd= 0;
            var volume= 0;
            for(let exchange in b.barsByExchange) {
                var exBar= b.barsByExchange[exchange];
                bar.open += exBar.open;
                bar.high = Math.max(bar.high,exBar.high);
                bar.low= Math.min(bar.low,exBar.low);
                bar.close += exBar.close;
                volume+= exBar.volume;
                count++;
                cvd += exBar.buyVolume - exBar.sellVolume;
            }

            var cvdEntry= { time: b.tstamp, value:totalCVD+cvd };
            bar.open /= count;
            bar.close /= count;
            vEntry= {time:b.tstamp, value:volume, color: volumeGray};

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