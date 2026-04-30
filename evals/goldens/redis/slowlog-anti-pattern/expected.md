The next targeted diagnostic is `SLOWLOG GET`, not a configuration change. The slowlog entries point to repeated broad `HGETALL` and `ZRANGE ... WITHSCORES` patterns, which suggests an application-side access anti-pattern rather than a Redis setting problem.

I’d pair that with a small INFO check for context, then recommend fixing the command pattern first. I would not restart Redis or reach for `CONFIG SET` before addressing the heavy workload shape.
