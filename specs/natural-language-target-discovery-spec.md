# Natural-Language Target Discovery and Authenticated Tool Loading

Status: Proposed

## Summary

Design a single target-discovery mechanism that lets the agent start with zero explicit
`instance_id` or `cluster_id`, interpret natural language like "check prod checkout cache" or
"investigate the us-east enterprise cluster", discover one or more matching Redis targets from
stored metadata, and dynamically attach authenticated tooling for those targets without exposing
connection strings, credentials, or API keys to the LLM.

At the same time, collapse the current three-agent split:

- keep `chat`
- keep `deep triage`
- remove the separate `knowledge-only` agent

The `chat` agent becomes the default general-purpose agent. It always has knowledge tools and
target-discovery tools. When no target is resolved, it behaves like today's knowledge agent.
When one or more targets are resolved, it dynamically gains target-scoped tools.

## Problem

Today the system has three different ways to get scope:

1. The caller passes `instance_id`
2. The caller passes `cluster_id`
3. The system extracts a raw `redis://...` URL from the message and creates an instance

That leaves several gaps:

- There is no metadata-based natural-language search across instances and clusters.
- The agent cannot start from "prod cache in us-east" and resolve scope on its own.
- The knowledge agent and chat agent are split even though both should be able to begin without
  target information.
- Tool loading happens up front; the toolset cannot expand naturally after a target is discovered.
- Current instance and cluster search only supports narrow filtering plus name wildcard matching.
- The desired authenticated clients exist only after a target is chosen, but the current design
  does not model "discover now, attach tools later" as a first-class flow.

## Goals

- Allow `chat` and `deep triage` to begin with no explicit target identifiers.
- Resolve instances, clusters, or multiple targets from natural language plus stored metadata.
- Keep authentication details out of LLM prompts, tool schemas, tool results, traces, and thread
  metadata.
- Support dynamic loading of authenticated tools after target discovery.
- Support multiple simultaneous target bindings in one conversation or triage run.
- Preserve the current distinction between instance-scoped tooling and cluster-scoped tooling.
- Reuse stored `RedisInstance` and `RedisCluster` records as the source of truth for credentials
  and other private connection data.

## Non-goals

- Replacing the current `RedisInstance` / `RedisCluster` storage models.
- Designing a full semantic vector search experience for targets in v1.
- Accepting raw credentials from natural language as the primary happy path.
  If a user pastes secrets into chat, that remains a separate sanitization problem.
- Redesigning provider internals beyond what is needed for dynamic target attachment.

## Current-State Observations

- `process_agent_turn()` currently prefers explicit `instance_id` / `cluster_id`, then thread
  context, then `_extract_instance_details_from_message()` if the prompt contains a raw Redis URL.
- `route_to_appropriate_agent()` still routes to `knowledge_only` when no target scope exists.
- `ChatAgent` and `KnowledgeOnlyAgent` both use `ToolManager`, but only `ChatAgent` can load
  instance-scoped or cluster-scoped providers.
- `ToolManager` can load providers for a `RedisInstance` or `RedisCluster`, but only at agent
  construction time.
- `query_instances()` and `query_clusters()` only support tag filters plus wildcard matching on
  `name`, which is too weak for natural-language resolution.

## Proposed Design

## 1. Two-agent model only

Replace the current routing model with two agents:

- `chat`
- `deep triage`

`chat` becomes the default entry point for:

- general Redis knowledge questions
- natural-language target discovery
- quick diagnostics
- follow-up investigation on one or more attached targets

`deep triage` remains the heavier orchestration path for comprehensive analysis, but it uses the
same target-discovery mechanism before it begins planning tool work.

### Routing rule

- If the request explicitly asks for deep or exhaustive analysis, route to `deep triage`.
- Otherwise route to `chat`.
- Do not route to a separate `knowledge-only` agent.

If no target is resolved, `chat` simply uses knowledge tools and answers as a general Redis/SRE
assistant.

## 2. Introduce a unified target catalog

Add a new denormalized search index for discovery:

- `sre_targets`

Each document represents either:

- an instance-backed target
- a cluster-backed target

Suggested document shape:

- `target_id`
- `target_kind`: `instance | cluster`
- `resource_id`: underlying `RedisInstance.id` or `RedisCluster.id`
- `display_name`
- `name`
- `environment`
- `status`
- `instance_type` or `cluster_type`
- `usage`
- `description`
- `notes`
- `repo_url`
- `monitoring_identifier`
- `logging_identifier`
- `cluster_id`
- `redis_cloud_subscription_id`
- `redis_cloud_database_id`
- `redis_cloud_database_name`
- `search_text`
- `search_aliases`
- `capabilities`
- `updated_at`

### Searchable content

`search_text` should be built only from safe metadata, for example:

- instance name
- cluster name
- environment
- usage
- description
- notes
- repo URL host/repo slug
- monitoring identifier
- logging identifier
- Redis Cloud database name
- known aliases stored in extension metadata

No secrets belong in this index. Specifically exclude:

- `connection_url`
- `admin_url`
- usernames
- passwords
- API keys
- secret extension data

### Why a new index instead of reusing `sre_instances` and `sre_clusters`

The unified index simplifies:

- cross-kind search in one query
- consistent ranking
- capability-aware filtering
- future support for richer aliases and relevance tuning

The existing instance and cluster indices remain authoritative for CRUD and direct lookups.

## 3. Add an always-on target discovery tool

Add a new always-on provider, loaded alongside knowledge and utilities:

- `TargetDiscoveryToolProvider`

### Primary v1 tool

Expose one primary tool:

- `resolve_redis_targets`

Suggested contract:

```json
{
  "query": "prod checkout cache in us-east",
  "allow_multiple": true,
  "max_results": 5,
  "attach_tools": true,
  "preferred_capabilities": ["diagnostics", "admin", "cloud"]
}
```

Suggested result shape:

```json
{
  "status": "resolved",
  "clarification_required": false,
  "matches": [
    {
      "target_handle": "tgt_01H...",
      "target_kind": "instance",
      "resource_id": "redis-prod-checkout-cache",
      "display_name": "checkout-cache-prod",
      "environment": "production",
      "target_type": "oss_single",
      "capabilities": ["redis", "metrics", "logs"],
      "confidence": 0.94,
      "match_reasons": [
        "matched environment=production",
        "matched usage=cache",
        "matched alias=checkout"
      ]
    }
  ],
  "attached_target_handles": ["tgt_01H..."],
  "toolset_generation": 4
}
```

### Important behavior

The tool does two things:

1. searches and ranks candidate targets
2. optionally attaches authenticated target handles to the current session

The LLM sees only safe metadata and opaque handles. The actual credentials never appear in the
tool output.

### Ambiguity policy

- If there is one high-confidence match, auto-attach it.
- If there are several plausible matches and the user asked for multiple targets, attach the top
  bounded set and explain what was attached.
- If there are several plausible matches and the user appears to want one target, return
  `clarification_required=true` and ask the agent to clarify before using live tools.

## 4. Use opaque target handles, not secrets

Resolved targets should be represented in agent state by opaque handles:

- `tgt_<opaque_id>`

Each handle maps server-side to safe binding metadata:

- `target_handle`
- `target_kind`
- `resource_id`
- `capabilities`
- `thread_id`
- `task_id`
- `created_at`
- `expires_at`

This binding can live in Redis as ephemeral session state. It does not need to store secrets.
Because the underlying `RedisInstance` and `RedisCluster` records already store encrypted secrets,
the binding only needs to remember which resource was chosen.

### Secret-safe resolution path

1. `resolve_redis_targets` returns safe match metadata plus target handles.
2. The agent records attached handles in thread/task context.
3. `ToolManager` uses the handle to fetch the underlying instance or cluster by ID.
4. Provider initialization decrypts secrets server-side only when constructing clients.
5. Tool schemas and tool results reference handles and display names, not credentials.

## 5. Add dynamic authenticated tool loading

Extend `ToolManager` into a target-aware manager that can load tools in phases:

- base tools
  - knowledge
  - utilities
  - target discovery
  - MCP tools that do not require target scope
- target-scoped tools
  - loaded after one or more target handles are attached

### Required capability

The manager must support:

- initial load with no target
- attaching one target
- attaching multiple targets
- rebuilding the bound tool list when the target set changes

### Tool loading rules

For an attached instance handle:

- load Redis command diagnostics
- load metrics/logs/host telemetry providers as appropriate
- load Redis Cloud provider when the instance represents a Redis Cloud database and credentials
  are available through a secret-safe auth source

For an attached cluster handle:

- load Redis Enterprise admin provider when cluster type is `redis_enterprise`
- load Redis Cloud subscription-level provider when cluster type is `redis_cloud` and a cloud auth
  source exists
- optionally expose cluster-linked instance tools when the agent explicitly expands into database
  diagnostics

### Multi-target naming

Tool names must be target-scoped and secret-safe. They should include the opaque handle or another
stable safe suffix, never a host or credential-bearing URL.

Example shape:

- `redis_diag_tgt_a1b2_info`
- `re_admin_tgt_c3d4_list_bdbs`
- `redis_cloud_tgt_e5f6_get_database`

The display label shown to the LLM can still mention the safe display name:

- "Redis diagnostics for checkout-cache-prod"

## 6. Search and ranking strategy

The resolver should be deterministic and metadata-first, not LLM-only.

### Proposed pipeline

1. Parse lightweight intent from the query
   - environment terms: `prod`, `staging`, `dev`
   - kind hints: `cluster`, `instance`, `database`
   - topology hints: `enterprise`, `cloud`, `oss`
   - usage hints: `cache`, `queue`, `session`, `analytics`
   - entity tokens: names, aliases, repo names, cloud database names
2. Search `sre_targets` with:
   - exact tag matches where possible
   - wildcard / full-text search on safe text fields
3. Score matches using weighted metadata evidence
4. Return ranked candidates plus an attach decision

### Ranking inputs

- exact name or alias match
- environment match
- usage match
- target kind match
- instance or cluster type match
- monitoring/logging identifier match
- cloud database name match
- recency / status as tie-breakers

### Why not pure LLM selection

The LLM should choose whether to call the resolver, not perform secret-bearing lookup logic. The
resolver must remain deterministic, inspectable, testable, and independent from model variance.

## 7. Session and thread state

Thread context should evolve from a single active ID to a target set:

- `attached_target_handles: List[str]`
- `active_target_handle: Optional[str]`
- `target_toolset_generation: int`

Retain compatibility fields during migration:

- `instance_id`
- `cluster_id`

### Session semantics

- A new session starts with no attached targets.
- `resolve_redis_targets(..., attach_tools=true)` adds or replaces attached handles depending on
  agent intent.
- Follow-up turns reuse attached handles unless the user changes scope.
- `deep triage` persists the same safe handle set on the task/thread so later follow-ups can
  continue without rediscovery.

## 8. Agent behavior

## Chat

`chat` should follow this pattern:

1. start with base tools only
2. if the user intent needs live Redis scope, call `resolve_redis_targets`
3. if targets are attached, refresh the toolset
4. continue the same turn using the newly loaded target-scoped tools
5. if no target is resolved, continue as a knowledge-oriented chat

This replaces today's split between `ChatAgent` and `KnowledgeOnlyAgent`.

## Deep triage

`deep triage` should use the same resolver first, then decide the work plan:

- single instance target: standard instance triage
- single cluster target: cluster triage, with optional expansion into linked instances
- multiple targets: bounded fan-out with per-target evidence and aggregated synthesis

The deep triage planner should be able to request additional target expansion if it starts with a
cluster and later determines that per-database diagnostics are required.

## 9. Authentication model

The design should support three authenticated client families:

- Redis client
- Redis Enterprise Admin API client
- Redis Cloud API client

### Credential sources

The LLM never receives these values directly. The runtime resolves them from stored records and
secret sources:

- `RedisInstance.connection_url`
- `RedisCluster.admin_url`, `admin_username`, `admin_password`
- Redis Cloud credentials from a secret-safe auth source
  - environment-backed in v1 is acceptable
  - later this can expand to cluster or extension-backed secrets

### Client factories

Introduce a small internal abstraction:

- `AuthenticatedTargetContext`

It exposes safe runtime factories such as:

- `get_redis_client()`
- `get_enterprise_client()`
- `get_cloud_client()`

These factories live below the LLM boundary. Providers may use them directly, or the tool manager
may continue constructing providers from `RedisInstance` / `RedisCluster` models as long as the
credential resolution stays server-side.

## 10. API and MCP surface

Target state should be discoverable through the main task-based chat and triage flows, not just
through low-level list/get tools.

### Public direction

Move the product surface toward:

- `redis_sre_chat`
- `redis_sre_deep_triage`

Compatibility wrappers can remain for:

- `redis_sre_general_chat`
- `redis_sre_database_chat`
- `redis_sre_knowledge_query`

But internally they should map onto the new two-agent design.

### Optional helper tools

The primary v1 feature only requires `resolve_redis_targets`, but these may be useful:

- `list_attached_redis_targets`
- `detach_redis_targets`
- `expand_cluster_targets_to_instances`

Those helpers are optional follow-ons, not prerequisites.

## 11. Implementation sketch

## Phase 1: Search foundation

- Add `sre_targets` index and builder.
- Backfill target documents from existing instances and clusters.
- Add alias support from safe extension metadata.
- Implement deterministic resolver service with ranking and ambiguity thresholds.

## Phase 2: Tool provider

- Add `TargetDiscoveryToolProvider`.
- Expose `resolve_redis_targets`.
- Persist safe target bindings in thread/task/session state.

## Phase 3: Dynamic tool manager

- Extend `ToolManager` to attach multiple targets and rebuild tool definitions.
- Add target-scoped tool naming.
- Ensure result envelopes and traces remain secret-safe.

## Phase 4: Agent unification

- Merge knowledge-only behavior into `chat`.
- Remove `knowledge_only` from router decisions.
- Update `process_agent_turn()` to use target handles instead of only `instance_id` /
  `cluster_id`.

## Phase 5: Deep triage integration

- Resolve targets before triage planning.
- Support bounded multi-target fan-out.
- Support cluster-to-instance expansion where needed.

## 12. Testing requirements

Add tests for:

- target catalog indexing from instances and clusters
- resolver ranking and ambiguity handling
- secret-safe tool output
- dynamic toolset refresh after resolution
- chat with zero initial scope resolving a target mid-turn
- chat with no live target staying in knowledge mode
- deep triage resolving one target from natural language
- deep triage resolving multiple targets from natural language
- cluster resolution followed by instance expansion

Add regression coverage that ensures:

- secrets never appear in resolver tool results
- secrets never appear in stored traces or thread metadata
- current explicit `instance_id` / `cluster_id` paths still work during migration

## 13. Risks and tradeoffs

- Dynamic tool rebinding adds complexity to the LangGraph loop.
- Multi-target tool naming can increase prompt/toolset size if not bounded carefully.
- Redis Cloud auth is less mature than instance and enterprise cluster auth today, so the first
  implementation may need to keep cloud attachment behind capability checks.
- A unified target catalog introduces denormalization; it must be kept in sync whenever instances
  or clusters change.

## 14. Recommended v1 decisions

- Build `sre_targets` as a new unified metadata index.
- Add exactly one primary tool: `resolve_redis_targets`.
- Keep handles opaque and secret-free.
- Merge `knowledge-only` behavior into `chat`.
- Make routing binary: `chat` vs `deep triage`.
- Use deterministic metadata search and scoring in v1.
- Bound auto-attached targets to a small maximum, for example 3.

## Open Questions

- Should cluster selection automatically attach linked instances, or should that remain an
  explicit expansion step?
- Should Redis Cloud credentials remain environment-scoped in v1, or should this work also define
  cluster-backed cloud secrets?
- Should attached target handles live only for a thread, or also be shareable across threads in a
  user session?
