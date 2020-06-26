https://twitter.com/mkuegi/status/1254494415583948801?s=20

Let's say you found a #trading strategy that works, but executing it flawlessly is challenging. So you want to build it into a bot that does all the hard work for you? Then this thread is for you.
 
Disclaimer: This is just my experience from building 100+ bots on different plattforms. But only 2 of them were profitable, so i might know nothing. This is not financial advice and not every strategy can be automized.
 
To build a bot, *everything* in your strategy needs to be defined and written down in detail. You need to be able to give it to any trader in the world and after explaining it 1 day, they would be able to execute it just like you. If you can't do that -> forget it.
 
Also you need to write code, or someone that writes code for you. Depending on how much you trust others, it might be smart to learn it yourself. What language depends on the platform you use. Writing everything from scratch in python is always an option. (i did that)
 
So you know basic coding and have your strategy defined. My first step would be to code it in some easy-to-use platform. I use TV but also heard good things bout ThinkOrSwim. This might only work for the simple parts of your sys, but you get an idea where this is heading.
 
Why start out in TV or similar? By actually trying to code it the first time, you probably find lots of flaws in your definitions and process. Might even rethink the whole sys. Better do that on a fast iteration platform than after coding for 2 months.
 
While writing the sys for the first time you will realize problems in the automation. Either because you don't know how to code it, or cause the platform is not providing it. In case 2: try to work around it. Get as much of it coded as possible.
 
Even having parts of your sys automated helps a lot. f.e. an indicator showing you possible entry-signals where you only have to apply the final filter. Or automating the exit so you don't have to think about it but just enter numbers in the trading mask.
 
Such tools may be as simple as an excel calculation (like i did for position size based on entry and SL). everything that gets more of the logic into the machine and reduces the human factor, will help. And over time you might adapt your system into full automation.
 
If you finally come to the conclusion that the simple platforms are not enough, take the next step: decide on a powerful platform (with access to your broker) and build it there. The platform decision depends 100% on the broker and the sys. so no recommendations there.
 
There are lots of pitfalls when writing a bot. I documented some of my exp in writing it in python here: https://twitter.com/mkuegi/status/1251223614424317953?s=20 Backtesting, Overoptimizing, API-troubles and the diff between papertrading/backtest and real executions fill books.
 
But if you manage to build a bot, you are free to enjoy life at its fullest while your bot executes your trading (flawlessly) 24/7. Which is the dream, right? ;)
  