---
title: Finding Voice and Style
description: Tone and phrasing rules for TAM-facing cluster health check findings.
---

# Finding Voice and Style

Use a TAM voice: direct, specific, quantified, and restrained.

## Core rules

- Name entities the way the customer recognizes them. Use database names with ids in parentheses.
- Quantify every finding with the actual Analyzer value.
- Lead with the observation and follow with the recommendation.
- Hedge only when customer intent is unknowable, not when the Analyzer data is clear.
- Use imperative recommendations, not tentative language.

## Useful patterns

### Numeric threshold finding

`Database <name> (<id>) <metric> is <value>. <Impact>. <Imperative recommendation>.`

Example:

`Database q-aperture-redis-oculus (14) average key size is 31.51MB. Large keys increase replication and full-key access cost. Identify big keys and work with application owners to split them up.`

### Configuration finding where intent matters

`<Observation>. <Recommendation>. <Question about intent>?`

Example:

`Persistence is disabled on database q-rdc-reg (5). Review whether that matches the workload's durability needs. Intentional?`

### Critical finding

`<Direct statement of problem>. <Why it matters>. <Action>.`

Example:

`Database q-cmt-redis-crdb-dwhservice (11) has 77% shard size deviation. This is well above the warning threshold and indicates significant data skew. Investigate hash-tag usage and large-key concentration immediately.`

## Avoid

- `It appears that`
- `It seems`
- `might want to consider`
- unexplained references to internal check names
- unquantified claims such as `slowlog has entries`
- combining unrelated issues into one bullet

## Ordering guidance

Within one database:

1. Critical findings
2. Memory and sizing findings
3. Configuration issues
4. Slowlog findings
5. Key-size and distribution findings
6. Placement findings
7. Transient status findings

Across the report:

1. Cluster-level findings
2. Node-level findings
3. Database-level findings

## No-findings language

If the package is clean, say so plainly:

`Analyzer returned no non-OK health checks. No automated findings to report. See the manual-review section for items that still require TAM validation.`
