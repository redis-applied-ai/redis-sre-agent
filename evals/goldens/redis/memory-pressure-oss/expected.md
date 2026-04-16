I’d start with targeted read-only evidence on the attached cache. `INFO memory` and `MEMORY STATS` show the instance is effectively at its configured ceiling with elevated fragmentation, so memory pressure is the immediate explanation for the evictions.

From there I’d explain the evidence first and only then discuss safe follow-up checks or mitigation options. I would not jump straight to `CONFIG SET` or an immediate policy change without that evidence chain.
