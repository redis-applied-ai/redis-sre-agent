---
document_hash: cluster-health-triage
name: cluster-health-triage
title: Cluster Health Triage
doc_type: knowledge
category: incident
priority: high
summary: Use cluster-level admin evidence before inferring Redis Enterprise health from a single database view.
source: fixture://corpora/redis-docs-curated/2026-04-01/documents/cluster-health-triage.md
---
Use cluster-admin health evidence instead of a single database `INFO` view when deciding whether a Redis Enterprise cluster is unhealthy.

One resyncing database does not necessarily mean the whole cluster is down.
