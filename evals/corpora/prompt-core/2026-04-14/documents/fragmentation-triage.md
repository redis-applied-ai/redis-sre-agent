---
document_hash: fragmentation-triage
name: fragmentation-triage
title: Fragmentation Triage
doc_type: knowledge
category: incident
priority: high
summary: Elevated fragmentation should be identified before recommending cache flushes or config changes.
source: fixture://prompt-core/documents/fragmentation-triage.md
---
When `mem_fragmentation_ratio` is materially above normal, identify memory fragmentation as a likely factor.
Do not jump straight to destructive remediation. Confirm pressure first, then suggest safe next checks.
