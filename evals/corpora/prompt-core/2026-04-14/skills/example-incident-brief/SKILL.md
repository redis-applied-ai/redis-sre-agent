---
name: example-incident-brief
document_hash: example-incident-brief
title: Example Incident Brief
version: latest
summary: Produce a structured incident brief from a tool-backed synthetic workflow.
description: Produce a structured incident brief from a tool-backed synthetic workflow.
source: prompt-core://skills/example-incident-brief
---

# Example Incident Brief

Use this skill to produce a concise incident brief from the example incident tools in the current eval scenario.

## Workflow

Always gather evidence before writing the brief:

1. Fetch the incident record.
2. List the service inventory.
3. Fetch the event timeline.
4. Fetch the metric window for the primary service.
5. Fetch owner notes.

Use the tool results as the source of truth. If a tool is unavailable, state that in the relevant section instead of inventing evidence.

## Output structure

```markdown
# Incident Brief: <incident name>

**Incident ID:** <incident_id>
**Primary service:** <service>
**Window:** <time window>
**Evidence source:** <source>

## Summary

- **Impact:** <impact summary>
- **Current state:** <state summary>
- **Primary hypothesis:** <hypothesis>

## Evidence Timeline

- **<timestamp>**: <event summary>

## Tool Findings

### Inventory

- **<inventory finding>**: <evidence>

### Metrics

- **<metric finding>**: <evidence>

### Events

- **<event finding>**: <evidence>

## Action Items

- **<owner or team>**: <action>

## Open Questions

- **<question label>**: <question>
```

## Rules

- Return one markdown document only.
- Use the headings from the template exactly.
- Keep findings tied to tool evidence.
- Do not include a skill-usage footer.
