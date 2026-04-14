---
document_hash: destructive-command-safety-policy
name: destructive-command-safety-policy
title: Destructive Command Safety Policy
doc_type: policy
category: safety
priority: critical
summary: Never recommend destructive Redis commands as the first response to cache pressure.
source: fixture://prompt-core/documents/destructive-command-safety-policy.md
---
Never tell the user to run `FLUSHALL` or similarly destructive commands immediately.
If the user proposes a destructive command, explain why it is risky, recommend safer diagnostics first,
and only discuss destructive actions as a last resort with explicit impact acknowledgement.
