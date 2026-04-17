---
document_hash: iterative-diagnostics-runbook
name: iterative-diagnostics-runbook
title: Iterative Diagnostics Runbook
doc_type: runbook
version: latest
summary: Inspect low-risk diagnostics in sequence before suggesting configuration changes.
source: prompt-core://documents/iterative-diagnostics-runbook
priority: high
category: prompt
---
When a Redis cache is degraded, start with low-risk inspection steps before proposing remediation.

1. Confirm the target and state the current hypothesis.
2. Inspect `INFO memory` or other read-only diagnostics to establish whether memory pressure is present.
3. Follow with a second diagnostic such as `SLOWLOG GET` or a latency-oriented check if memory is not conclusive.
4. Explain what you observed before suggesting any configuration or operational change.
5. Do not jump directly to `CONFIG SET`, eviction-policy changes, or restart advice unless diagnostics justify it.
