---
document_hash: client-count-source-discipline
name: client-count-source-discipline
title: Client count source discipline
doc_type: runbook
version: latest
summary: Use INFO clients or CLIENT LIST for connection counts; do not infer them from MEMORY STATS.
source: redis-docs-curated://documents/client-count-source-discipline
priority: high
category: redis
---
When you need to answer "how many clients are connected right now?", use `INFO clients` or `CLIENT LIST`.

`MEMORY STATS` is a memory-accounting command. Fields such as `clients.normal` and `clients.slaves` describe client-related overhead and are not authoritative connection counters.

If `MEMORY STATS` seems to disagree with `INFO clients`, trust `INFO clients` and `CLIENT LIST` for live connection counts, and explain the distinction instead of collapsing the metrics into one conclusion.
