---
name: iterative-redis-triage
title: Iterative Redis Triage
version: latest
summary: Use a diagnostic sequence that narrows the problem before changing configuration.
source: prompt-core://skills/iterative-redis-triage
---
Follow this procedure:

1. Start with read-only diagnostics.
2. Use one tool call to confirm or reject the leading hypothesis.
3. Use a second tool call only if the first result leaves ambiguity.
4. Summarize the evidence chain before suggesting remediation.
