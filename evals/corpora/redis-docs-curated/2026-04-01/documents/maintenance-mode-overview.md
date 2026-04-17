---
document_hash: maintenance-mode-overview
name: maintenance-mode-overview
title: Maintenance Mode Overview
doc_type: runbook
category: incident
priority: critical
pinned: true
summary: Maintenance mode can explain failover churn in Redis Enterprise during planned work.
source: fixture://corpora/redis-docs-curated/2026-04-01/documents/maintenance-mode-overview.md
---
During Redis Enterprise maintenance windows, failover churn can be expected if nodes are draining or not accepting new servers.

Verify cluster-admin state and replica health before treating the event as a generic OSS failover problem.
