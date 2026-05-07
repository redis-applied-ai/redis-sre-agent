Treat the `clients.normal` figure as a memory-accounting signal, not as a live client count.

`INFO clients` is the canonical source for the current connection count here, and it reports **19 connected clients**, not 72k. `MEMORY STATS` is telling you about client-related overhead, so I would not report `clients.normal=72696` as a connection spike.

If we wanted the definitive inventory beyond that summary, the next validating step would be `CLIENT LIST`, because `INFO clients` and `CLIENT LIST` are the sources that should drive connection-count claims.
