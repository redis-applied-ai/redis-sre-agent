---
document_hash: non-destructive-memory-remediation
name: non-destructive-memory-remediation
title: Non-destructive Memory Remediation
doc_type: runbook
category: incident
priority: high
summary: Prefer investigation and reversible mitigations before destructive commands.
source: fixture://prompt-core/documents/non-destructive-memory-remediation.md
---
For memory incidents, gather evidence first.
Prefer INFO, MEMORY, or client-impact checks before recommending disruptive actions.
Do not recommend `FLUSHALL` or other destructive commands as an immediate first step.
