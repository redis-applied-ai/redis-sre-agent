# Knowledge Pack Release Spec

Status: Accepted

Related:
- `docs/how-to/pipelines.md`
- `.github/workflows/publish-docker.yml`
- `redis_sre_agent/pipelines/orchestrator.py`
- `redis_sre_agent/pipelines/ingestion/deduplication.py`
- `redis_sre_agent/core/redis.py`
- `redis_sre_agent/evaluation/knowledge_backend.py`

## Summary

Add a release-time "knowledge pack" zip artifact that captures the SRE Agent's curated knowledge
corpus as a versioned snapshot.

The pack must include:

- the scraped/prepared artifact batch used to build the corpus
- enough metadata to prove provenance and compatibility
- a restore payload that can repopulate the Redis knowledge index without rerunning scraping,
  chunking, or embedding generation

Add a loader path so operators can bootstrap the knowledge base from the zip instead of running the
pipeline themselves. The loader should support two modes:

- `restore`: direct Redis restore from prebuilt chunk records and vectors
- `reingest`: unpack the batch artifacts and run the existing ingestion pipeline locally

`restore` is the fast path and avoids rerunning the pipeline. `reingest` is the compatibility
fallback when the runtime embedding configuration does not match the pack.

## Problem

Today every new deployment that wants a usable knowledge base must build it locally by running some
combination of:

- `pipeline scrape`
- `pipeline prepare-sources`
- `pipeline ingest`

That creates several problems:

- release consumers do not get a ready-to-load knowledge snapshot
- setup time is long, especially when scraping Redis docs and KB content from the network
- deployments without easy outbound network access have to build and curate the corpus themselves
- the release workflow publishes container images, but not the knowledge state that makes the agent
  useful on first boot
- the repo has an artifact format for scraped documents, but no durable export/import format for
  indexed chunk records

The current architecture already separates scraping from ingestion, which is useful, but it still
assumes each operator will rebuild indexable state on their own machine.

## Goals

- Publish a versioned knowledge snapshot as a `.zip` asset alongside GitHub releases.
- Make the snapshot loadable into Redis without rerunning scraping or embedding generation.
- Preserve enough raw artifact state that operators can re-ingest locally if they need a different
  embedding model or schema.
- Keep provenance explicit: release tag, repo SHA, source revisions, batch date, schema hash, and
  embedding fingerprint must be recorded.
- Avoid deleting operator-managed documents that were not loaded from the release pack.
- Reuse the existing pipeline and RedisVL index model where possible.
- Make the default local and air-gap bootstrap story simpler.

## Non-goals

- Replacing Redis as the runtime knowledge backend.
- Implementing a zip-backed in-memory search path that bypasses Redis entirely.
- Bundling private support tickets, task history, schedules, or other mutable operational data.
- Auto-refreshing the pack after release publication.
- Solving fully offline query embeddings in this change alone.
  The pack removes corpus-building work, but query-time embedding compatibility still matters.
- Shipping LLM-generated `runbook_generator` output in the default release pack.
  That source is less deterministic and should be handled separately if needed.

## Current-State Constraints

### 1. Runtime search depends on Redis indices

The query path in `redis_sre_agent/core/knowledge_helpers.py` embeds the query at runtime and
searches RedisVL-backed indices created from `SRE_KNOWLEDGE_SCHEMA` in
`redis_sre_agent/core/redis.py`.

That means a pack cannot just contain raw markdown if the goal is to avoid rerunning the full
pipeline. A fast-path loader needs prebuilt chunk records and vectors.

### 2. Existing artifact batches are raw documents, not restore bundles

`ArtifactStorage` currently writes per-document JSON files plus `batch_manifest.json` under
`artifacts/YYYY-MM-DD/`. Those artifacts are enough for ingestion, but not enough for a direct
restore because they do not contain:

- chunked record payloads
- precomputed vectors
- document/source tracking hashes
- schema and embedding compatibility metadata

### 3. Release automation does not publish knowledge assets

`.github/workflows/publish-docker.yml` publishes container images on release, but it does not build
or upload a release asset that captures the knowledge corpus.

### 4. Pack-managed content must not wipe local operator content

The current knowledge index can contain:

- release-curated docs
- repo `source_documents/`
- later operator-added source documents
- future local re-ingestion results

A pack loader must replace only the previous pack-managed keys, not every `sre_knowledge:*` key in
Redis.

### 5. Embedding compatibility must be explicit

The stored vectors are only valid for query-time retrieval when the runtime embedding configuration
is compatible with the pack. At minimum this means:

- matching vector dimensions
- matching embedding model family
- no silent mismatch between query encoder and stored vectors

## Proposed Design

### 1. Introduce a versioned knowledge-pack format

Add a new zip-based export format for release snapshots.

Suggested layout:

```text
redis-sre-agent-knowledge-pack-v0.4.1.zip
├── manifest.json
├── checksums.txt
├── artifacts/
│   └── 2026-05-12/
│       ├── batch_manifest.json
│       ├── oss/
│       ├── enterprise/
│       └── shared/
└── restore/
    ├── knowledge_chunks.ndjson
    ├── knowledge_document_meta.ndjson
    ├── knowledge_source_meta.ndjson
    └── active_pack_registry.json
```

`manifest.json` should include:

- `pack_format_version`
- `pack_id`
- `release_tag`
- `repo_sha`
- `created_at`
- `batch_date`
- `included_corpora`
- `schema_hash`
- `embedding_provider`
- `embedding_model`
- `vector_dim`
- `scrapers_run`
- `source_documents_git_sha`
- `source_revisions`
  - e.g. `redis_docs_commit`, `redis_kb_scrape_started_at`, `redis_cloud_api_source`
- `record_counts`
  - artifact documents, chunk records, tracked source documents

`checksums.txt` should include sha256 checksums for every top-level exported file so operators can
validate the asset before loading it.

### 2. Export both raw artifacts and restore-ready records

The pack should contain two layers of data:

1. Raw artifacts
   - exact `artifacts/<batch_date>/...` output
   - used for provenance, inspection, and local re-ingest fallback

2. Restore records
   - chunk records equivalent to what `DocumentDeduplicator.replace_document_chunks()` writes
   - document tracking hashes equivalent to `update_document_metadata()`
   - source tracking hashes equivalent to `update_source_document_tracking()`

This dual-format design gives us:

- a fast path that avoids the pipeline entirely
- a safe fallback when runtime compatibility checks fail
- one canonical release asset instead of separate "cache" and "restore" files

### 3. Scope the MVP to the release-curated knowledge corpus

The first version of the pack should cover the release-managed `knowledge` corpus only.

Included sources:

- `redis_docs_local` output from a pinned `redis/docs` checkout
- `redis_kb`
- `redis_cloud_api`
- prepared repo `source_documents/`

Excluded from MVP:

- support tickets
- mutable user-local documents outside the release repo
- external Agent Skills packages that are not part of the release-managed corpus

The format should keep `included_corpora` extensible so a later version can add `skills` or other
indices.

### 4. Add a dedicated builder

Add a new CLI group:

```bash
uv run redis-sre-agent knowledge-pack build ...
uv run redis-sre-agent knowledge-pack load ...
uv run redis-sre-agent knowledge-pack inspect ...
```

`knowledge-pack build` should:

1. Require a batch date and output path.
2. Read the raw artifact batch from `artifacts/<batch_date>/`.
3. Export restore records from the live `sre_knowledge` index and its tracking hashes.
4. Write `manifest.json` and checksums.
5. Zip the result.

Suggested command:

```bash
uv run redis-sre-agent knowledge-pack build \
  --batch-date 2026-05-12 \
  --artifacts-path ./artifacts \
  --output ./dist/redis-sre-agent-knowledge-pack-v0.4.1.zip
```

Implementation note:

The builder should export deterministic chunk keys already used by the deduplication layer:

- `sre_knowledge:<document_hash>:chunk:<chunk_index>`
- `sre_knowledge_meta:<document_hash>`
- `sre_knowledge_meta:source:<path_hash>`

That lets the loader restore exact runtime keys instead of inventing a second key scheme.

### 5. Add a loader with `restore`, `reingest`, and `auto` modes

`knowledge-pack load` should accept:

- `--pack <path>`
- `--mode restore|reingest|auto`
- `--artifacts-path <path>`
- `--replace-existing`
- `--skip-checksums`

Suggested behavior:

- `restore`
  - verify checksums
  - validate `schema_hash`, `vector_dim`, and embedding fingerprint
  - create the `sre_knowledge` index if missing
  - delete only the keys recorded for the previously active pack
  - bulk load the new chunk records and tracking hashes
  - write an "active pack" registry key in Redis

- `reingest`
  - unzip `artifacts/<batch_date>/...` to disk
  - run the existing ingestion pipeline against that batch
  - do not scrape any sources

- `auto`
  - use `restore` when compatibility checks pass
  - otherwise fall back to `reingest`

This satisfies the user requirement: operators can load from the zip instead of running the
pipeline, while still having a safe path when the release pack does not match their runtime
embedding configuration.

### 6. Track pack-managed keys explicitly

Add a small registry record for the active release pack, stored in Redis under a dedicated key such
as:

- `sre:knowledge_pack:active`

Suggested registry fields:

- `pack_id`
- `release_tag`
- `loaded_at`
- `chunk_keys`
- `document_meta_keys`
- `source_meta_keys`
- `schema_hash`
- `embedding_fingerprint`

On load:

1. Read the previous registry, if any.
2. Delete only those keys.
3. Load the new pack.
4. Replace the registry.

This avoids wiping user-managed documents that happen to live in the same index.

### 7. Add startup/bootstrap integration

Add configuration for pack-aware bootstrap:

- `knowledge_pack_path: Optional[Path] = None`
- `knowledge_pack_load_mode: Literal["auto", "restore", "reingest"] = "auto"`
- `knowledge_pack_auto_load: bool = False`

Behavior:

- If `knowledge_pack_auto_load=false`, nothing changes.
- If `knowledge_pack_auto_load=true` and the target knowledge index is empty, startup should load
  the configured pack before serving traffic.
- If the index is already populated, startup should log and skip automatic loading unless an
  explicit replace flag is provided elsewhere.

This keeps automatic bootstrap safe and idempotent.

Recommended entry points:

- CLI command for explicit operators
- deployment script integration for Docker and VM flows
- optional startup hook used by air-gap deployments

MVP does not need a public REST endpoint.

### 8. Build the pack during release publication

Extend release automation so a published GitHub release also uploads a zip asset.

Recommended release pipeline:

1. Check out repo at the release tag.
2. Fetch a pinned `redis/docs` clone.
3. Start an ephemeral Redis 8 service.
4. Run:
   - `pipeline scrape --scrapers redis_docs_local,redis_kb,redis_cloud_api --latest-only`
   - `pipeline prepare-sources --source-dir ./source_documents --prepare-only`
   - `pipeline ingest --batch-date <same batch>`
5. Run `knowledge-pack build`.
6. Upload:
   - `redis-sre-agent-knowledge-pack-<tag>.zip`
   - `redis-sre-agent-knowledge-pack-<tag>.sha256`

Why this flow:

- it reuses the current scraping and ingestion code instead of adding a second content builder
- it makes the release asset match the live index format exactly
- it gives one release-time snapshot with stable provenance

### 9. Record compatibility explicitly

Add a derived manifest field:

- `embedding_fingerprint`

Suggested fingerprint inputs:

- `embedding_provider`
- `embedding_model`
- `vector_dim`
- `schema_hash`
- pack format version

On `restore`, the loader should fail closed if the fingerprint does not match the runtime unless
the operator explicitly chooses `reingest`.

That protects against subtle search corruption from incompatible vectors.

## CLI and Module Changes

### New modules

- `redis_sre_agent/knowledge_pack/models.py`
- `redis_sre_agent/knowledge_pack/builder.py`
- `redis_sre_agent/knowledge_pack/loader.py`
- `redis_sre_agent/knowledge_pack/checksums.py`

### CLI wiring

- add a `knowledge-pack` click group under `redis_sre_agent/cli/`
- register it from `redis_sre_agent/cli/main.py`

### Config wiring

- add the knowledge-pack settings to `redis_sre_agent/core/config.py`

### Release workflow changes

- extend `.github/workflows/publish-docker.yml` or add a dedicated release-assets workflow
- upload the knowledge pack only on release publication by default
- optionally allow manual rebuild via workflow dispatch

## Data Contract Details

### `restore/knowledge_chunks.ndjson`

One JSON object per Redis hash record, including:

- `key`
- `payload`

`payload` should match the fields currently loaded by `AsyncSearchIndex.load()`:

- `id`
- `document_hash`
- `content_hash`
- `title`
- `content`
- `source`
- `category`
- `doc_type`
- `name`
- `summary`
- `priority`
- `pinned`
- `severity`
- `version`
- `chunk_index`
- `vector`
- `created_at`
- any optional indexed metadata fields

`vector` should be stored in a zip-safe representation such as base64-encoded bytes.

### `restore/knowledge_document_meta.ndjson`

One JSON object per tracking hash:

- `key`
- `mapping`

### `restore/knowledge_source_meta.ndjson`

One JSON object per source-tracking hash:

- `key`
- `mapping`

### `restore/active_pack_registry.json`

Registry payload persisted both in the zip and in Redis after load.

## Operator Experience

### Fast-path bootstrap

```bash
curl -L -o knowledge-pack.zip <release-asset-url>

uv run redis-sre-agent knowledge-pack load \
  --pack ./knowledge-pack.zip \
  --mode restore
```

### Compatibility fallback

```bash
uv run redis-sre-agent knowledge-pack load \
  --pack ./knowledge-pack.zip \
  --mode reingest \
  --artifacts-path ./artifacts
```

### Automatic mode

```bash
uv run redis-sre-agent knowledge-pack load \
  --pack ./knowledge-pack.zip \
  --mode auto
```

## Testing Strategy

### Unit tests

- manifest generation and checksum validation
- export/import round-tripping for chunk and metadata records
- compatibility check behavior for matching and mismatched embeddings
- registry replacement logic that deletes only previous pack-managed keys
- loader idempotency when the same pack is loaded twice

### Integration tests

- build a small artifact batch, ingest it into Redis 8, export a pack, load it into a fresh Redis,
  and verify search results
- verify `auto` falls back to `reingest` when the embedding fingerprint does not match
- verify user-added non-pack keys survive a pack replacement

### Release workflow validation

- smoke test the release job in workflow dispatch mode
- assert the release asset exists and has a checksum sidecar
- verify the pack can be loaded by a clean container using only the zip

## Risks and Mitigations

- Large release asset size.
  Mitigation: compress with zip, exclude nonessential transient files, and keep MVP to the
  release-managed corpus.

- Embedding mismatch causing poor retrieval.
  Mitigation: manifest fingerprint checks plus `auto -> reingest` fallback.

- Accidentally deleting local operator content.
  Mitigation: explicit active-pack key registry and targeted deletion only.

- Release build nondeterminism from source changes.
  Mitigation: record source revisions in the manifest and use pinned checkout inputs where
  possible.

## Rollout Plan

### Phase 1

- Add pack models, builder, and inspector.
- Add release workflow job to build and upload the zip.

### Phase 2

- Add loader with `restore` and registry-based replacement.
- Add config-driven bootstrap support.

### Phase 3

- Add `auto` fallback to `reingest`.
- Update deployment docs to prefer release-pack bootstrap over local scraping for first-time setup.

## Implementation Decisions

- Publish two release-managed pack variants:
  - `runtime`: built with the default runtime embedding settings and dimensions
  - `airgap`: built with the air-gap local embedding settings and dimensions
- Keep pack operations CLI-only for the MVP:
  - `knowledge-pack build`
  - `knowledge-pack inspect`
  - `knowledge-pack load`
- Ship the full pack in both variants:
  - raw `artifacts/` batch included
  - restore payload included
- Defer any slim restore-only variant until there is a demonstrated distribution or size problem.
