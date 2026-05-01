---
name: redis-maintenance-triage
title: Redis Maintenance Triage
description: Investigate maintenance mode before taking failover or restart actions.
summary: Check maintenance state, gather evidence, and avoid disruptive actions until the owner is clear.
priority: high
version: latest
---

# Redis Maintenance Triage

Use this skill when a cluster looks unhealthy during maintenance windows, failover tests, or
operator-driven interventions.

1. Confirm whether maintenance mode is active.
2. Identify the cluster, impacted nodes, and active owner.
3. Gather evidence before recommending failover or restart actions.
4. Prefer retrieval and escalation over automation when ownership is unclear.
