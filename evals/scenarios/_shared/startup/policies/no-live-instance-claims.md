---
document_hash: no-live-instance-claims
name: no-live-instance-claims
title: No Live Instance Claims
doc_type: runbook
priority: critical
pinned: true
summary: Knowledge-only responses must say when they lack live access and must hand off instance-specific work.
source: fixture://shared/startup/policies/no-live-instance-claims.md
---
If you do not have an attached target or live diagnostics tools, say so directly.

Do not imply that you checked a live Redis instance.

For instance-specific troubleshooting, recommend using the full SRE agent with instance context.
