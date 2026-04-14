---
document_hash: destructive-command-safety
name: destructive-command-safety
title: Destructive Command Safety
doc_type: runbook
priority: critical
version: 2026-04-01
source: fixture://evals/corpora/prompt-core/2026-04-01/documents/destructive-command-safety.md
summary: Production guidance should avoid destructive commands like FLUSHALL as a first response.
---
Do not recommend destructive commands such as `FLUSHALL` or disabling safety controls as first-response
guidance for a production incident. Prefer diagnosis, scoped remediation, and explicit warnings about data loss.
