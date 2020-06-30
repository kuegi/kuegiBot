https://twitter.com/mkuegi/status/1278057717643517952?s=20

"How to automate a strategy?" glad you asked, lets go throu the process with a simple sample strategy. If ppl like it, i will make it a series with other strats too. Let's start with the classic: crossing SMAs.
 This strat might not work and this is not financial advice! :thread:

When you want to automate a system you need the 3 basic questions answered in an unambiguous, complete way:
- when to enter? 
- when to exit?
- what position size to use?
In our case: entry will be on fastMA crossing over the slowMA. (long on cross up, short on down)

For the exit its a bit harder to decide. A MACross strat usually is a trend follower, so lets make it one. Trendfollowing means you let winners run free and only trail the stop, but how? Until the trend is broken of course. But how do we know?

A break of the (up)trend is often defined as "when the price makes lower lows". So let's go with that (keep it simple): Trail the stop to the last swing low. for me this means a low where X bars before and Y bars afterwards have higher lows. 

Last question: position size? i usually start with risking 1% per trade to keep things simple. Its always easy to get more complex later on. How do you know what you are risking? The initial StopLoss is at the last swingLow, so the diff defines our risk.

When you come up with a strat like that, you usually found it while analysing the markets. So you would/should have an idea what parameters to use (period of MAs, how much before/after the swings need). I made this all up as i write, so i also made up the params.

So far, so easy. Now comes the coding. I am using my own bot-framework to keep things simple (i really like it simple), if you have questions about it: ask. 
First i implement the needed "indicators": MA and the swings. Both are pretty straight forward.

The strat itself is also pretty easy: If MA crossed (last-bar fastMA<=slowMA && this-bar fastMA > slowMA) -> buy on close of this-bar. Buying on the close is hard, cause once its closed, the next bar is already there. its easier to execute on the first tick of the next. 

For the initialSL we only need the swing-indicator directly. Same for the trailing. So the strat has 4 parameters: periods of fast and slow MA, and the barcount before and after to identify a swing. So a few lines of code later we are ready to test it. Now the real fun starts.
 
 I am testing on bybit-data using the last 12 months, keeping 6 for out of sample (oos) tests. This concept is really important: only optimize on a subset. so when you are done and think you got it, you let it run on th oos and see how the system reacts to completly new data.

Now i was prepared to write now that the first results are negative, and start to analyze how this can be improved etc. but well the random guessing wasn't that bad: strat made 19% in the last 12 months on a 5% maxDD. max days underwater is 36... so thats pretty nice.

anyway lets still analyze it and see what we can improve. setting is fastMA:5, slowMA:34, before:3, after:2. its the typical trendfollower: long flat/down periods with some huge wins that produces the main performance. lets analyze the parts where it looses: f.e. before march

What we see are some clear false signals (yellow). can't fight them in a trendfollower. But there are also some that went into a good direction but then lost it all (black circles). I don't like that, so lets see if a BreakEven logic helps.

Lucky me, i already made the whole thing modularized with a generic BE-Module in place, so adding it is only one line. And the results are amazing: trailing to 0.1R once we are 0.5R in front, shoots us up to 27% profit on 2.4% maxDD. winrate 70%. i like it! 

But how is the OOS going? only on the 6 month we got -7% and a maxDD of -12%... not so good. maybe the system needs more work after all. if we use 8/34 instead of 5/34, we loose overall profit but have a stable performance. small changes->big impact->not good.

I hope you got an idea of the process of automation and optimizing. Let it be a warning to not trust any random system with nice numbers. You need to know and understand it. If you wanna play with this system: feel free. maybe you make it into a solid performer.