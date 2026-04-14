---
document_hash: iterative-diagnostics-runbook
name: iterative-diagnostics-runbook
title: Iterative Diagnostics Runbook
doc_type: runbook
priority: critical
version: 2026-04-01
source: fixture://evals/corpora/prompt-core/2026-04-01/documents/iterative-diagnostics-runbook.md
summary: Start with INFO memory before offering remediation for cache memory pressure.
---
For cache memory incidents, inspect `INFO memory` first, call out allocator fragmentation if it is elevated,
and avoid remediation advice that is not supported by the observed metrics.
