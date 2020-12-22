# Kuegi Bot

a simple tradingbot for BTCUSD with connectors for [bybit](https://bit.ly/2rxuv8l "Bybit Homepage"), [bitmex](https://bit.ly/2G4gSB2 "Bitmex Homepage"), [binance futures](https://www.binance.com/en/futures/ref/kuegi) and [phemex](https://phemex.com/register?referralCode=F6YFL).
It just implements my manual tradingstrategy and therefore helps me to stick to the system. 
No financial advice. Don't use it if you don't understand what it does. You probably will loose money.

I only use the bybit connector myself right now. The other connectors are still there, but might have problems due to API changes in the last months which i am not aware of yet. Feel free to make a Pull Request if you find any.

## ref links

if you like it and wanna start a trading account, feel free to use the ref links:

[bybit](https://www.bybit.com/en/register?affiliate_id=4555&language=en&group_id=0&group_type=1)

[binance (saves you 10% of fees)](https://www.binance.com/en/register?ref=NV9XQ2JE)

[binance futures (saves you 10% of fees)](https://www.binance.com/en/futures/ref/kuegi)

## disclaimer

right now this is a pure expert tool for my personal use. if you find the code useful thats nice, but don't expect it to be easy to understand or work with it.
It also comes with no warranty whatsoever and is for educational purposes only!

## roots

started with code from https://github.com/BitMEX/sample-market-maker (connector to bitmex mainly but got to change a lot)

## donations

if this helps you in any way, donations are welcome: 

BTC: bc1qfdm2z0xpe7lg70try8x3n3qytrjqzq5y2v6d5n

## story time

i write twitter threads about my journey and the bot. you can either follow me there @mkuegi or read them [here](docs/aboutCodingABot/readme.md)

# Getting started

This section describes how to get the environment (i highly recommend virtual environments) set up to run the bot (backtest and trading). As mentioned before, this is highly experimental and use of the bot on real money is not recommended unless you *really* know what you are doing.

## needed modules
first install the needed packages via pip. They are listed in requirements.txt and can be installed via the standard steps

## execution

currently the only way to  execute the bot is by running the included scripts. 

# bot and strategies

Currently there are specific bots for the kuegi-strategy and a simpler SFP strategy.
Since those two work nicely together, i also created a MultiStrategyBot which can execute multiple strategies within one account and exchange.

## Kuegi Strategy
Here i will explain my strategy once i find the time

## SFP
a simple swing-failure pattern strategy. I will provide more information when the time is right.

# backtest

## crawling history
To run backtests you first have to collect data history from the exchange.
For the known exchanges i created the history_crawler script. 
make sure that a folder "history" is existing in the main directory (next to the script) and run
```
python3 history_crawler.py bybit
```
if you want to crawl bitmex, you have to replace `bybit` with `bitmex`

for future calls adapt  the known_history_files in utils/helper to the highest existing index of the M1 files.

The crawler loads M1 data from the exchange in max batchsize and aggregates it in a way to be easily reused from the backtest afterwards. The download can take a long time since its lots of data to fetch.

If you use another exchange or existing data, you need to make sure that the history data is saved in the same structure as the crawler does it.

## running the backtest

in backtest.py you find a collection of code snippets and functions for backtesting. they are mostly commented out to be used in the python console.

run
```
python3 -i backtest.py
```
to execute the script with interactive console afterwards. there you can for 

load bars from the history:
```
bars = load_bars(<daysInHistory>,<timeFrameInMinutes>,<barOffset>,<exchange>)
```

where `daysInHistory` and `timeFrameInMinutes` should be obvious.
`barOffset` is an option to shift bars. f.e. when the default first H4 bar starts at 00:00, with this parameter you can make him start at 01:00 etc. 
This is pretty useful to test for stability of the bot. small changes in input (like shifting the bars) shouldn't result in big changes of the performance.

those loaded bars you can then use for backtests. create a tradingBot (a class derived from TradingBot in kuegibot/bots/trading_bot.py). I would recommend using `MultiStrategyBot` since thats the one i am using in production too.

There are multiple samples in the file how to create a bot and add strategies (for MultiStrategyBot).

Once the bot is created and set up, call
```b= BackTest(bot,bars).run()```
this runs the backtest and prints some performance numbers into the logs. 

i mainly use the "rel:" number which is the relation between profit (per year) and the maxDD.
i consider a relation of greater than 4 a good performance. but you need to decide for yourself

after the run you can call
```bot.create_performance_plot().show()```
to create a chart with more detailed performance analysis

or
```b.prepare_plot().show()```
to create a chart with the historic bar data and the positions plotted for detailed analysis.

# production

## disclaimer
As stated before: i *DO NOT RECOMMEND* to run this bot on your own money out of the box. If you understand what it does, checked the code and are confident that it does what you want, feel free to run it.
I am running it on my own money, but i also know every line of the code and did extensive tests over 5 months before scaling up to serious position sizes.

so seriously: don't run it. You risk losing all your money!

## settings
all settings should be placed within the settings folder.

When started via the cryptobot script, it first reads default settings from `settings/default.json`.
If a path argument is provided, the first one should be a path to the full settings file with all data needed for the bot.

see a sample file in `settings/sample.json`. 

The settings needs to contain one "bot" directory per exchange. The minimum required changes in the sample file are 
- the `API_KEY` and `API_SECRET` set to your key and secret.
- `KB_RISK_FACTOR` set to the (average) amount of btc to be risked per trade.
 *WARNING*: depending on the strategy this might not be the actual max-risked amount but a target for the average. Also a trade might loose more than this amount because of slipage and execution problems on the exchange.
- If you **really** want to run it on a live exchange, also set `IS_TEST` to false. Do this at your own risk!

## realtime usage
if running the bot on a real exchange you need to run it 24/7. For this i recommend getting a server and set the bot up as a daemon that is restarted on any failure.
The bot generally is prepared for this usage. Open Positions are stored on the disk to easy pick up after a restart.

The bot also has some security measures to prevent uncovered positions. If he finds an open position on the exchange without a matching position on file and specially without a stoploss,
 it closes this position. This also means that you must not trade other positions with the account of the bot. otherwise it will close them instantly and you loose money.