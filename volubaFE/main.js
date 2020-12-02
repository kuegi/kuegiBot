var barSeries;
var cvdSeries;
var volumeSeries;
var volDeltaSeries;
var exchangeSeries= {};

var m1Data;

var chart;

var volumeGray= 'rgba(150,150,150,0.8)';
var volumeBuy= 'rgb(50,200,50)';
var volumeSell= 'rgb(250,50,50)';

var targetTF= 5;
var wantedExchanges;

function aggregateM1Data() {
    var result= [];
    var lastTstamp = 0;
    m1Data.forEach(b => {
        var bar;
        var barTstamp= Math.floor(b.tstamp /(60*targetTF))*(60*targetTF);
        var bar= { tstamp: barTstamp,
        open: 0, high:0, low:999999999, close:0, buyVolume:0, sellVolume:0, volume:0 };
        var count= 0;
        bar.cvdByExchange= {};
        for(let exchange in b.barsByExchange) {
            var exBar= b.barsByExchange[exchange];
            if(wantedExchanges.has(exchange)) {
                bar.open += exBar.open;
                bar.high = Math.max(bar.high,exBar.high);
                bar.low= Math.min(bar.low,exBar.low);
                bar.close += exBar.close;
                bar.volume += exBar.volume;
                bar.buyVolume += exBar.buyVolume;
                bar.sellVolume += exBar.sellVolume;
                count++;
            }
            bar.cvdByExchange[exchange]= exBar.buyVolume-exBar.sellVolume;
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
            existing.cvdByExchange = bar.cvdByExchange;
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
                priceLineVisible:false
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
    window.setInterval(refresh, 15000)
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
    colors= [
    "Navy",
    "Aqua",
    "Fuchsia",
    "Lime",
    "Orange",
    "Maroon",
    "Purple",
    "Blue",
    "Teal",
    "Green",
    "Yellow",
    "Olive",
    "Red"
    ];
    var colorIdx= 0;
    var exchanges= document.getElementById("exchanges");
    exchanges.innerHTML= "";
    possibleExchanges.forEach(exchange => {
        var hue= Math.round(Math.random()*360);
        var color= colors[(colorIdx++) % colors.length];
        var label = document.createElement("label");
        var input= document.createElement("input");
        var rect= document.createElement("div");
        input.type= "checkbox";
        input.value= exchange;
        input.name= "exchange";
        input.id= exchange;
        input.checked= true;
        input.onchange= reinitData;
        label.innerHTML = exchange;
        label.htmlFor= exchange;
        rect.style.background= color;
        rect.className="exchangeColor";
        exchanges.appendChild(input);
        exchanges.appendChild(label);
        label.appendChild(rect);


        exchangeSeries[exchange]= chart.addLineSeries({ priceScaleId: exchange+"cvds" ,
                priceLineVisible:false,
                lastValueVisible: false,
                color:rect.style.background,
                lineWidth:1

            });
    });
}

function checkWantedExchanges() {
    wantedExchanges= new Set();
    document.getElementsByName("exchange").forEach(input => {
        if(input.checked) {
            wantedExchanges.add(input.value);
            exchangeSeries[input.value].applyOptions({visible:true});
        } else {
            exchangeSeries[input.value].applyOptions({visible:false});
        }
    });
}

function reinitData() {
    targetTF= Number($("#tf").get(0).value);
    checkWantedExchanges();
    fillSeries();
}

function initData() {
    today= new Date();
    yesterday= new Date();
    yesterday.setDate(today.getDate()-1);
    $.getJSON(yesterday.toISOString().substr(0,10)+'.json', function(data) {
        m1Data= data;
        m1Data.sort((a,b) => {
            return a.tstamp - b.tstamp;
        });

        $.getJSON(today.toISOString().substr(0,10)+'.json', function(data) {
            integrateNewM1Data(data);
            refreshExchanges(data);
            reinitData();
            chart.timeScale().fitContent();
        });
    });
}

function fillSeries() {
    var candles= [];
    var cvds= [];
    var volumes= [];
    var volumeDeltas= [];
    var exchangeCvdsData= {};
    var cvd= 0;
    element= document.getElementById("showPrice");
    barSeries.applyOptions({visible:element.checked});

    element= document.getElementById("exchangeCvds");
    wantedExchanges.forEach(exchange => {
            exchangeSeries[exchange].applyOptions({visible:element.checked});
    })
    aggregateM1Data(m1Data).forEach(b => {
        var bar= { time: b.tstamp,
        open: b.open, high:b.high, low:b.low, close:b.close };
        cvd += b.buyVolume-b.sellVolume
        candles.push(bar);
        cvds.push( { time: b.tstamp, value: cvd });

        for(let exchange in b.cvdByExchange) {
            if(!(exchange in exchangeCvdsData)) {
                exchangeCvdsData[exchange]= {cvd:0,series:[]};
            }
            exchangeCvdsData[exchange].cvd += b.cvdByExchange[exchange];
            exchangeCvdsData[exchange].series.push( { time: b.tstamp,
                                                      value: exchangeCvdsData[exchange].cvd });
        }
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

    wantedExchanges.forEach(exchange =>{
        exchangeSeries[exchange].setData(exchangeCvdsData[exchange].series);
    });
}

function integrateNewM1Data(newData) {
    newData.sort((a,b) => {
        return a.tstamp - b.tstamp;
    });
    var lastTstamp = m1Data[m1Data.length-1].tstamp;
    newData.forEach(bar => {
        if(lastTstamp == bar.tstamp) {
            m1Data[m1Data.length-1]= bar;
            lastTstamp= bar.tstamp;
        }
        if(lastTstamp < bar.tstamp) {
            m1Data.push(bar);
            lastTstamp= bar.tstamp;
        }
    });
}

function refresh() {
    $.getJSON('latest.json', function(data) {
        integrateNewM1Data(data);
        fillSeries();
    });
}