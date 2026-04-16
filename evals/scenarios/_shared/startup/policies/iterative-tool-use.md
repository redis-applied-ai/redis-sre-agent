---
document_hash: iterative-tool-use-policy
name: iterative-tool-use-policy
title: Iterative Tool Use Policy
doc_type: runbook
priority: critical
pinned: true
summary: Start with a few targeted checks, analyze the results, then widen the search only if needed.
source: fixture://shared/startup/policies/iterative-tool-use.md
---
Start with two to four targeted checks.

Analyze the results before making more calls.

Do not fan out into broad metric sweeps, large file fetches, or whole-keyspace inspection unless the earlier evidence justifies it.
