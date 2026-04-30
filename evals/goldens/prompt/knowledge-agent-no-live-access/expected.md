I do not have access to your live Redis instance or its current metrics from the knowledge-only lane.

Use the full SRE agent with instance context if you need a live check right now.

Before handing this to the on-call, read the knowledge-only boundary guidance and the prior checkout-cache memory-pressure case, then verify the incident with `INFO memory` and `MEMORY STATS` once you are in a live diagnostics workflow.
