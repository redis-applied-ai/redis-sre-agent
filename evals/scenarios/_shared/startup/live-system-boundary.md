---
name: live-system-boundary
title: Live System Boundary Policy
doc_type: runbook
category: policy
priority: critical
summary: Do not claim live system access without target scope and tool evidence.
source: fixture://shared/startup/live-system-boundary.md
---
Only describe live Redis state when the conversation has an attached target and the claim is
grounded in tool output from this turn. If there is no bound target or no live evidence, say so
explicitly and switch to documented guidance, safe next steps, and source-backed recommendations.
