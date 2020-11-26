(function() {
    $.ajaxSetup ({
        // Disable caching of AJAX responses
        cache: false
    });

    Handlebars.registerHelper('formatPrice',function(aPrice) {
        if(typeof aPrice === "number")
            return aPrice.toFixed(Math.abs(aPrice) < 10?2:1);
        else
            return "";
    });
    Handlebars.registerHelper('formatTime',function(aTime) {
        if(typeof aTime === "number" && aTime > 100000) {
            var date= new Date();
            date.setTime(aTime*1000);
            return date.toLocaleString();
        } else
            return "";
    });
    Handlebars.registerHelper('classFromPosition',function(aPos) {
        var clazz= aPos.status;
        if(aPos.amount > 0) {
            clazz +="Long";
        } else {
            clazz += "Short";
        }
        if(aPos.worstCase > 0) {
            clazz += " winning"
        } else if (aPos.worstCase < 0) {
            clazz += " losing"
        }
        return clazz;
    });
    Handlebars.registerHelper('formatResult',function(aResult) {
        if(typeof aResult === "number") {
            result= "";
            if( aResult > 0) {
                result = "+";
            }
            return result + aResult.toFixed(1)+"R";
        } else
            return "-";
    });

})();

function refresh() {
    $.getJSON('dashboard.json', function(data) {
        var template = Handlebars.templates.openPositions;
        var container= $('#positions')[0];
        container.innerHTML= '';
        bots= []
        for (let id in data) {
            var bot= data[id];
            bot.id= id;
            bot.drawdown = ((bot.max_equity - bot.equity)/bot.risk_reference).toFixed(1)+"R"
            bot.uwdays= ((Date.now()-bot.time_of_max_equity*1000)/(1000*60*60*24)).toFixed(0)
            bot.equity = bot.equity.toFixed(3)
            bot.max_equity = bot.max_equity.toFixed(3)
            var totalPos= 0;
            var totalWorstCase= 0;
            bot.positions.forEach(function(pos) {

                pos.connectedOrders.forEach(function(order) {
                    if(order.id.includes("_SL_")) {
                        pos.currentStop= order.stop_price;
                        if(Math.abs(pos.amount) > 10) {
                            pos.worstCase= (1/pos.currentStop - 1/pos.filled_entry)/(1/pos.wanted_entry-1/pos.initial_stop);
                        } else {
                            pos.worstCase= (pos.currentStop - pos.filled_entry)/(pos.wanted_entry-pos.initial_stop);
                        }
                    }
                    if(Math.abs(pos.amount) > 10) {
                        pos.initialRisk= pos.amount/pos.initial_stop - pos.amount/pos.wanted_entry;
                    } else {
                        pos.initialRisk= pos.amount*(pos.wanted_entry-pos.initial_stop);
                    }
                });
                if(pos.status == "open") {
                    totalPos += pos.amount;
                    totalWorstCase += pos.initialRisk*pos.worstCase;
                }
            });
            bot.totalWorstCase= (totalWorstCase/bot.risk_reference);
            bot.totalPos = totalPos.toFixed(Math.abs(totalPos) > 100 ? 0 : 3);
            bots.push(bot)
        }
        var div= template(bots);
        container.insertAdjacentHTML('beforeend',div);
    });
}