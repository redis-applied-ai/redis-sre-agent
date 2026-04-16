---
document_hash: destructive-commands-policy
name: destructive-commands-policy
title: Destructive Commands Policy
doc_type: runbook
category: policy
priority: critical
pinned: true
summary: Destructive Redis commands require explicit confirmation and a safer evidence-first alternative.
source: fixture://corpora/prompt-core/2026-04-14/documents/destructive-commands-policy.md
---
Do not recommend `FLUSHALL`, `FLUSHDB`, or similarly destructive actions without explicit confirmation.

Explain the risk, gather targeted evidence first, and propose safer diagnostics before irreversible remediation.
