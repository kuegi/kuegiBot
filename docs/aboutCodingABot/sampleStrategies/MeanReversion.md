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

So far so good. First test looks kinda disapointing thou. seems like i can't find a set of parameters that makes this thing work. Maybe the assumptions are wrong? Seems like the price doesn't follow a normal distribution. who knew?

But we are not giving up that easily: looking at the chart we se some pretty strong moves, 



68% 1 σ
95% 2 σ