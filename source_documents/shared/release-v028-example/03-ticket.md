---
title: Ticket RET-4421
doc_type: support_ticket
category: shared
name: ret-4421
summary: ECONNRESET during failover for cache-prod-1.
priority: normal
pinned: false
---

Host: cache-prod-1.redis.company.net
Symptom: ECONNRESET during failover
Resolution: increase failover timeout and connection retry jitter.
