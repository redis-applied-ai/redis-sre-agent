# Documentation Gaps Found While Testing v0.2.8

## Summary
- I could use most release features from docs, but several workflows required guesswork or source-code/CLI-help discovery.
- Biggest gaps: cluster-scoped diagnostics examples, outdated worker command, and unclear provenance command behavior.

## Gaps
1. Local worker startup command is outdated.
- Docs location: `how-to/cli/#1-start-services-choose-one` and `how-to/api/#1-start-services-choose-one`
- Doc command: `uv run redis-sre-agent worker --concurrency 4`
- Actual behavior: fails (`No such option: --concurrency`)
- Working command: `uv run redis-sre-agent worker start`

2. No explicit cluster-scoped query examples in CLI how-to.
- Docs location: `how-to/cli/#3-triage-with-queries`
- Missing: `query -c/--redis-cluster-id` examples and expected behavior (auto route to triage + fan-out)
- Impact: users won’t discover the primary v0.2.8 cluster diagnostic workflow.

3. API triage docs show `instance_id` context only, not `cluster_id`.
- Docs location: `how-to/api/#4-triage-with-tasks-and-threads`
- Missing: `{"context":{"cluster_id":"..."}}` task example
- Impact: release feature appears undocumented in core API workflow page.

4. MCP cluster-scoped diagnostics path is not documented end-to-end.
- Docs location: no clear page for MCP cluster workflow
- Missing: how to discover cluster IDs for MCP task calls and how `cluster_id` is expected to route
- Impact: hard to use cluster-scoped MCP diagnostics from docs alone.

5. `thread sources` behavior is unclear relative to `thread get` source messages.
- Docs location: `how-to/cli/#citations-in-thread-history`
- Docs suggest `thread sources` lists retrieved fragments by thread/turn.
- Observed: `thread get` included `Sources for previous response` system messages, but `thread sources` returned empty for support-ticket retrieval.
- Impact: unclear whether this is limitation, bug, or expected index-specific behavior.

6. Citation-trace input naming is ambiguous.
- Docs location: `how-to/cli/#citations-in-thread-history`
- Docs say use assistant `message_id` from `thread get`.
- CLI also prints `Decision trace: <id>`; this worked for `thread trace`, but docs do not explain relationship.
- Impact: users may not know which ID to pass when both are present.

7. Source-document-features page lacks a minimal copy/paste sample directory with all three doc types together.
- Docs location: `how-to/source-document-features/`
- Missing: tiny 3-file example (`pinned`, `skill`, `support_ticket`) plus expected query outputs.
- Impact: extra trial-and-error to verify feature behavior.

8. Backfill docs don’t call out completion-marker behavior.
- Docs location: `how-to/api/#notes` (mentions backfill command)
- Observed: backfill skipped due marker until `--force` was provided.
- Impact: users may think backfill is broken when testing after startup migration already ran.

9. Release/tag version mismatch not documented.
- Context: `v0.2.8` release page/tag
- Observed: `redis-sre-agent version` reports `0.2.7` on tested tag
- Impact: confusing verification signal for users validating they’re on latest release.

## Suggested Fixes
1. Update worker commands in CLI/API how-to pages to `worker start`.
2. Add cluster query examples to CLI and API core workflow pages (`-c` and `context.cluster_id`).
3. Add an MCP how-to section for cluster-scoped diagnostics including cluster ID discovery.
4. Clarify `thread trace` input (assistant message ID vs decision trace ID), with one concrete JSON example.
5. Clarify what `thread sources` includes/excludes (knowledge vs support-ticket/tool-specific provenance).
6. Add a minimal end-to-end source-document example set with expected outputs for pinned/skills/support tickets.
7. Add note that `cluster backfill-instance-links` may require `--force` after marker creation.
8. Resolve or document version output mismatch for the v0.2.8 release artifact/tag.
