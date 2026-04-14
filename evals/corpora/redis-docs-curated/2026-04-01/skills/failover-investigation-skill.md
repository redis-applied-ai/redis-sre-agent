---
document_hash: failover-investigation-skill
name: failover-investigation-skill
title: Failover Investigation Skill
doc_type: skill
priority: high
source: fixture://corpora/redis-docs-curated/2026-04-01/skills/failover-investigation-skill.md
summary: Verify replica posture and maintenance state before changing cluster operations after failover churn.
---
When a Redis Enterprise cluster sees failover churn:

1. Check cluster-admin health and maintenance state first.
2. Verify replica sync and failover posture before changing maintenance state.
3. Consult prior incidents for known maintenance-window failure patterns.
4. Avoid generic restart or configuration advice until the evidence is specific.
