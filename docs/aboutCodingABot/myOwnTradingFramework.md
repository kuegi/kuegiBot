https://twitter.com/mkuegi/status/1251223614424317953?s=20

After realising that my edge is fully automizable, i implemented it in python. But since i have to trust that bot with a lot of money (at least i plan to) i really need to know what its doing. so i decided to write the whole thing from scratch: a thread. 1/14

Disclaimer: This is how i did it based on my own exp and knowledge. Doesn't mean its smart to do it that way. Probably introduced lots of bugs, but so far its executing pretty good. And yes will open source it if ppl are interested. 2/14

The whole thing consists of 4 parts:
- bot itself, capsulated to easily add new bots
- backtest module: executing a bot on historic data
- livetrading module: using exchange APIs to execute bots
- Exchange APIs. abstracted such that i can easily add new exchanges
3/14

To be flexible for multiple exchanges and bots, i decided to roll my own datastructures (Bars, Orders, Positions, AccountData etc.). Means i have to convert data from the exchange APIs to my own structures, but that way the rest of the code is independent. 4/14

For backtests i crawled M1 data from the exchange and saved it locally (performance) in my own format. During a backtest i then load each M1 Bar and add them to the real TF i work on (my case H4). The bot always gets the current bars (including the unfinished one)... 5/14

and the account information(with open orders and position size) on every tick. In backtest i simulate to have one tick each minute (enough for an H4 system). So the backtestmodule only needs to provide the orderinterface (send, update, cancel), and simulate executions. 6/14

For the executions to be realistic i added assumed slippage (depending on the ordertype and the M1 bar that triggered the order). And performance tracking also includes fees cause you want it to be as realistic as possible. 7/14

The livetrading module is even simpler. Just take the callback from the api on each tick, forward all data to the bot. done. similar is the bot itself (in terms of me not writing more about it here;): first handle the open orders/positions, then check for opening new ones. 8/14

The APIs are a different beast. Inconsistent datatypes between REST and realtime, inconsistent updates throu realtime, huge lags in updates (a second between execution event and account update)... But you only realise those problems once you are in production. 9/14

So all set and done, backtest ran throu, optimization tells me lambo soon. How to put it into production and let it make money? glad you asked: get a simple server with linux, put the bot in a systemd/unit and you are good to go. 10/14

During live execution you will face completely new challenges: Specially problems with connections and exchanges. I decided to restart the bot in such a case. Drastic i know, but better safe than sorry/inconsistent/undefined. Also the position sync is/was a big topic: 11/14

You need to prepare for the case that your bot thinks it has positions open, but the actual data in the account is different. Then you need to recover. Either open orders that are missing, asume a position got closed without you noticing, or other way round. etc. 12/14

My main concept behind everything: better miss a position than do more harm. So if the bot is in doubt he better cancels the assumed position, than increase exposure in the market etc. maybe not the smartest way but makes me sleep easier at night. 13/14


