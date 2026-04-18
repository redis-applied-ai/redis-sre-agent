---
name: target-discovery-before-live-access
title: Target Discovery Before Live Access
doc_type: runbook
category: policy
priority: critical
summary: Resolve a natural-language Redis target and attach tools before making live-state claims.
source: fixture://shared/startup/policies/target-discovery-before-live-access.md
---
When the user refers to a Redis deployment, instance, database, or cluster without an explicit
`instance_id` or `cluster_id`, call `resolve_redis_targets` with the user's description before
answering with current live state.

If the resolver returns one clear match and attaches tools, continue with the newly attached
target-scoped diagnostics or admin tools in the same turn.

If the resolver returns `clarification_required`, ask the user to disambiguate and do not claim
current live Redis state yet.

If the user asks what Redis targets you know about in the current session, enumerate the safe
target inventory you can access from your own target catalog by calling
`list_known_redis_targets` instead of claiming that the catalog cannot be listed.

If the user asks to compare multiple Redis targets, call `resolve_redis_targets` with
`allow_multiple=true`, keep the attached target set, gather evidence per target, and then answer
with an explicit comparison instead of collapsing scope to a single target.

If the user asks both what targets you know about and to drill into one target in the same turn,
list the safe target inventory first, then resolve the selected target and continue with the
attached live tools.
