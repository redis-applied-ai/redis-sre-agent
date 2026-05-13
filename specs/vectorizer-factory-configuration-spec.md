# Vectorizer Factory Configuration Spec

Status: Proposed

Related:
- `redis_sre_agent/core/config.py`
- `redis_sre_agent/core/llm_helpers.py`
- `redis_sre_agent/core/redis.py`
- `docs/reference/configuration.md`
- `docs/how-to/configuration.md`

## Summary

Add a centralized `vectorizer_factory` setting so deployments can override embedding/vectorizer
construction with a dot-path import string, the same way they can already override chat-model and
AsyncOpenAI client construction.

The runtime already has two configurable LLM-construction seams:

- `llm_factory` for LangChain chat models
- `async_openai_client_factory` for OpenAI-compatible async SDK clients

The remaining hard-coded LLM-adjacent seam is embeddings. `get_vectorizer()` still directly
constructs `OpenAITextVectorizer` or `HFTextVectorizer` inside `redis_sre_agent/core/redis.py`.
That blocks deployments that need:

- Azure/OpenAI-compatible embedding clients with custom auth or transport
- alternate RedisVL-compatible vectorizer implementations
- internal wrapper factories for observability, retries, or policy enforcement
- a single configuration story for every runtime LLM factory

This spec adds `vectorizer_factory`, keeps current defaults unchanged when it is unset, and treats
runtime model/vectorizer construction as a centralized configuration concern rather than scattered
inline imports.

## Problem

Today there is an inconsistent override story:

- chat-model construction is configurable through `Settings.llm_factory`
- async OpenAI SDK client construction is configurable through
  `Settings.async_openai_client_factory`
- vectorizer construction is not configurable through an import path at all

That inconsistency matters because vectorizers are used in multiple runtime paths:

- knowledge search query embeddings
- document ingestion and deduplication
- skills search
- Q&A vector updates
- startup and health validation paths

Any deployment that must swap embedding behavior currently has to patch code or monkey-patch
`get_vectorizer()` instead of using the same settings surface that already exists for other LLM
factories.

## Goals

- Add a `vectorizer_factory` field to the centralized `Settings` model.
- Support configuration through environment variables and config files using a dot-path import
  string.
- Keep `get_vectorizer()` as the stable public entry point so callers do not need to change.
- Preserve today's default provider behavior when no custom factory is configured.
- Keep programmatic override support symmetric with existing LLM helpers.
- Make the repo's runtime LLM/vectorizer construction seams consistently configurable from one
  place.

## Non-goals

- Replacing `embedding_provider`, `embedding_model`, or `vector_dim`.
- Redesigning vectorizer usage sites to depend on a different interface.
- Making test-only direct SDK usage configurable. The scope here is runtime code under
  `redis_sre_agent/`, not live integration tests that intentionally instantiate SDK clients
  directly.
- Introducing per-call vectorizer selection or per-index vectorizer overrides.
- Migrating away from RedisVL in this change.

## Current-State Observations

### 1. Configuration centralization is already partially in place

`redis_sre_agent/core/config.py` already exposes:

- `llm_factory`
- `async_openai_client_factory`

Those fields are documented in `.env.example`, `docs/reference/configuration.md`, and
`docs/how-to/configuration.md`.

### 2. Vectorizer construction is still hard-coded

`redis_sre_agent/core/redis.py:get_vectorizer()` currently:

- builds an `EmbeddingsCache`
- branches on `settings.embedding_provider`
- directly returns `HFTextVectorizer(...)` or `OpenAITextVectorizer(...)`

There is no import-path override, no factory registration API, and no validation path parallel to
`llm_helpers.py`.

### 3. Runtime callers are already funneled through `get_vectorizer()`

The good news is the main runtime paths already converge on `get_vectorizer()`:

- `redis_sre_agent/core/knowledge_helpers.py`
- `redis_sre_agent/skills/backend.py`
- `redis_sre_agent/core/docket_tasks.py`
- `redis_sre_agent/pipelines/ingestion/*`
- Redis health / infrastructure checks

That means we can add configurability at one seam without broad call-site churn.

### 4. Existing helpers establish the desired pattern

`redis_sre_agent/core/llm_helpers.py` already provides the pattern to mirror:

- load a dot-path factory from settings on first use
- allow programmatic registration via setter functions
- fall back to a default factory when no override is configured
- raise a clear error on invalid import paths or non-callable targets

## Proposed Design

## 1. Add `vectorizer_factory` to centralized settings

Add a new optional field to `Settings`:

- `vectorizer_factory: str | None`

Environment variable:

- `VECTORIZER_FACTORY`

Config-file example:

```yaml
vectorizer_factory: mypackage.embeddings.custom_vectorizer_factory
```

Environment example:

```bash
VECTORIZER_FACTORY=mypackage.embeddings.custom_vectorizer_factory
```

Description:

- dot-path to a callable that constructs the runtime vectorizer
- if unset, the default OpenAI/local provider logic remains in effect

## 2. Introduce a vectorizer helper module with the same override model as LLM helpers

Add a new module:

```text
redis_sre_agent/core/vectorizer_helpers.py
```

Responsibilities:

- define the vectorizer factory protocol
- manage one-time loading from `settings.vectorizer_factory`
- expose programmatic registration helpers
- provide the default factory implementation that mirrors current behavior

Suggested public helpers:

- `set_vectorizer_factory(factory)`
- `get_vectorizer_factory()`
- `create_vectorizer(config: Settings | None = None)`

`redis_sre_agent/core/redis.py:get_vectorizer()` should remain public and delegate to
`create_vectorizer()` so existing imports continue to work.

### Why a helper module instead of putting more logic in `core/redis.py`

`core/redis.py` already owns Redis clients, schemas, index helpers, and health checks. Import-path
resolution and factory registration fit the same category as `llm_helpers.py`, not the same
category as index schema definitions. Separating them keeps the override mechanism easy to test and
easy to reuse.

## 3. Define the vectorizer factory contract

The factory must receive enough context to reproduce the current default behavior without reaching
back into globals.

Suggested callable contract:

```python
def custom_vectorizer_factory(
    *,
    provider: str,
    model: str | None,
    config: Settings,
    cache: EmbeddingsCache | None,
    **kwargs,
) -> Any:
    ...
```

Expected behavior:

- `provider` is the normalized `embedding_provider` value such as `openai` or `local`
- `model` is the configured embedding model unless explicitly overridden later
- `config` is the effective `Settings` object used for this call
- `cache` is the prepared RedisVL `EmbeddingsCache` instance built with current TTL/Redis settings
- the return value must implement the methods the runtime already uses:
  - `aembed()`
  - `aembed_many()`
- compatibility with `embed_many()` should be preserved because current tests and some workflows
  rely on it

This contract keeps the override powerful without forcing every custom factory to reconstruct
shared cache behavior itself.

## 4. Keep the default behavior exactly as it is today

When `vectorizer_factory` is unset:

- `embedding_provider=local` returns `HFTextVectorizer(model=..., cache=...)`
- `embedding_provider=openai` returns `OpenAITextVectorizer(model=..., cache=..., api_config=...)`
- unknown providers still raise `ValueError`

This is a compatibility requirement. Adding the new setting must not change the default runtime
for existing deployments.

## 5. Align failure behavior with other configurable factories

On first vectorizer creation:

- invalid dot-paths should raise `ValueError`
- non-callable targets should raise `ValueError`
- import failures should surface clearly with the configured path in the error message

If the factory returns an object missing required methods, the helper should fail early with a
clear error rather than letting the first indexing or search call fail with an opaque attribute
error deep in the stack.

The goal is to make configuration mistakes obvious during startup checks, ingestion, or health
probes.

## 6. Treat runtime factory settings as a single centralized family

This change should also codify the design rule that runtime LLM construction seams live in
`Settings` and are configured via import-path fields.

After this change, the runtime factory family becomes:

- `llm_factory`
- `async_openai_client_factory`
- `vectorizer_factory`

No new runtime LLM/vectorizer factory override should be added later through ad hoc env lookups or
inline imports elsewhere in the codebase.

## Implementation Outline

1. Add `vectorizer_factory` to `redis_sre_agent/core/config.py`.
2. Add `VECTORIZER_FACTORY` comments to `.env.example`.
3. Add the new setting to:
   - `docs/reference/configuration.md`
   - `docs/how-to/configuration.md`
4. Add `redis_sre_agent/core/vectorizer_helpers.py` with:
   - import-path loading
   - setter/getter
   - default factory
   - optional return-shape validation
5. Refactor `redis_sre_agent/core/redis.py:get_vectorizer()` to delegate to the helper while
   preserving its public signature.
6. Optionally extract the duplicated dot-path loader logic from `llm_helpers.py` and the new
   vectorizer helper into a small shared utility if that reduces copy-paste without obscuring the
   code.

## Testing Plan

Add or update unit coverage for these cases:

- default vectorizer behavior still returns OpenAI/local RedisVL vectorizers based on
  `embedding_provider`
- `set_vectorizer_factory()` registers and clears a programmatic override
- configured `vectorizer_factory` is loaded from settings on first use
- invalid `VECTORIZER_FACTORY` path raises a clear error
- non-callable configured target raises a clear error
- custom factory receives:
  - `provider`
  - `model`
  - `config`
  - `cache`
- `get_vectorizer()` still returns a fresh instance on each call
- health / initialization paths still report vectorizer availability correctly when the custom
  factory is valid

Suggested test files:

- new: `tests/unit/core/test_vectorizer_helpers.py`
- update: `tests/unit/core/test_redis.py`

## Backward Compatibility

- Existing deployments with no `VECTORIZER_FACTORY` configured are unaffected.
- Existing callers importing `get_vectorizer()` remain unaffected.
- Existing `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, and `VECTOR_DIM` settings remain supported and
  continue to drive the default factory.

## Open Questions

### 1. Should the helper validate the full vectorizer interface?

Recommended v1 answer:

- validate the async methods actually used in runtime paths
- do not try to perfectly model every RedisVL vectorizer method in the type system

That keeps the implementation simple and catches the failures that matter.

### 2. Should we also refactor `llm_helpers.py` to use a shared import-path loader now?

Recommended v1 answer:

- only do this if the extracted utility stays tiny and obviously better than the duplicated code
- do not expand the scope of this change into a broad helper-framework refactor

The user-visible goal is vectorizer configurability, not helper architecture cleanup.

## Acceptance Criteria

- A deployment can set `VECTORIZER_FACTORY` or `vectorizer_factory` in config and override runtime
  vectorizer construction without patching code.
- `get_vectorizer()` remains the stable public API and preserves current behavior by default.
- The new setting is documented alongside the existing LLM factory settings.
- Unit tests cover both default and custom-factory paths.
