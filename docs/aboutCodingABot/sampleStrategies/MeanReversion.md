Time for a sample strat. This time: Mean reversion. As always when you code a strategy we have 3 questions:
- when to enter
- when to exit
- what size
size will be based on the initial stopdiff again. Since we base this strat on mean reversion, lets first explain that.

Every random list of numbers (like a price), has a mean and standard deviation: how much the numbers usually strive away from the mean. The mean might shift over time. But when the price moves far away from it, it might be likely to revert back. Or at least torward it.

Based on this simple idea, we build our strat: If the price moves away from the mean by a certain level (multiple of the std-dev) we expect it to return by a certain degree. lets say to a smaller multiple of the std-dev

in numbers: 68% of the values should be within +-1 std-dev. lets put a limit entry on that level, and if it triggers, we set the TP at 0.5 std-dev, and the stop at 2 std-dev (95% stay within that). The numbers will be parameters of course.

This strat works best on a "random" series. So i would go for LTF (M2 in our case) since its a lot of "noise" there (aka: random moves up and down) which is exactly what we want. So our parameters are: 
* entry-factor
* tp-factor
* sl-factor
* lookback for the mean

Now comes the coding. To have it seperated, lets make an indicator that gives us the mean and the std-deviation. Then use this in the strat. Seems like this again will be a pretty simple one.

So far so good. First test: entry at stdDev, TP at 0.5 stdDev, SL at 2 stdDev looks kinda disapointing thou. lets look at the chart. maybe we can spot something that can be improved.
 
 What jumps out is this pattern. blue line is the mean, orange, the stdDev. green lines are long positions, red lines are shorts. Now why is this big long happening? happy to hear your explanation for it.

Ok, so maybe the numbers are wrong? running a quick scan shows that basically nothing works. So are the assumptions wrong? are prices not normally distributed? Not necessarily. It only means that our way of trying to benefit from it didn't work yet.

The problem is that the mean is shifting. So the price is certainly reverting back to the mean. Just that the mean is now different than before which means our position is not reaching the target (which is relative to the old mean).

Generally thats the main problem with mean reversion systems: It most certainly reverts back to the mean, but the mean might have shifted by a lot in the meantime. How to deal with that? we could only enter in the direction of the trend (so a mean shift works in our favor)

or we could get out of the trade at the next close (so don't even give the mean time to shift). Either way: to make a mean-reversion work, you need a good filter that prevents you from getting trapped by a shifting mean. If you got that, it can work really well.
