# Semantic Caching Design

## Flow of Document & Thinking

- What is stored within the cache?
- What happens on a miss?
- What happens on a hit?
- Cache invalidation strategy on knowledge base changes
- Other cache invalidation strategies
- Other next steps

---

## Backends

The cache strategy — canonical key, scope resolution, cacheability, provenance,
tombstones, invalidation — is identical regardless of backend. Only the
match-and-store transport differs, selected by `semantic_cache_backend`:

| | `redisvl` (default) | `langcache` |
|---|---|---|
| Where it runs | This service's own Redis | Managed LangCache service |
| Setup required | None | `langcache_cache_id` + `langcache_api_key` |
| Embeddings | Client-side (this process) | Server-side |
| Missing config | N/A | Degrades to no cache, with a warning |

Both are gated by `semantic_cache_enabled`, which remains **off by default**.
Enabling the cache on the `redisvl` backend needs no external provisioning, which
is what makes the feature demonstrable on a plain local stack.

One backend is active at a time. Switching backends abandons existing entries
rather than migrating them; they expire on their own TTL (≤24h).

### Divergences on the `redisvl` backend

1. **No server-side exact-match tier.** LangCache tries `exact` then `semantic`;
   redisvl is vector-only, so `search_strategy` is always reported as
   `semantic`. Behaviourally equivalent in practice — identical text yields
   distance 0, so an exact match still outranks a semantic neighbour.
2. **A miss costs an embedding round trip.** Because embeddings are computed
   client-side, a *novel* query must be embedded before the miss is known.
   Repeated queries are free (`create_vectorizer` attaches an `EmbeddingsCache`),
   but this is the main operational difference to watch: LangCache is one network
   hop, redisvl is an OpenAI hop plus a Redis hop.
3. **TTL-refresh-on-read is deliberately disabled.** `acheck()` refreshes the TTL
   of every hit it returns, which would turn our fixed store-time TTLs into a
   sliding window — a popular `latest` answer would then never expire, defeating
   the short TTL it has precisely because it tracks a moving pointer. The backend
   therefore never passes a cache-level `ttl`, and a test pins that invariant.
4. **Entry ids are deterministic.** redisvl derives an entry id from
   `hash(prompt, filters)`, so re-storing the same prompt and scope overwrites in
   place, where LangCache mints a fresh `entryId` per set.
5. **Schema changes are breaking.** Changing the filterable fields or
   `embedding_model` makes redisvl's index-schema check raise, which fail-open
   turns into a permanently dead cache behind a single warning. The index must be
   dropped for the new schema to take effect.

---

## What the Cache Contains

An answer is cacheable only when all of these hold:

- **Grounded in the knowledge index**: Only if `state["knowledge_search_results"]` is non-empty, so there's real document provenance to stamp and later invalidate against.

LangCache is a managed service — it owns embeddings, the vector index, similarity search, and scalar attribute filters. But its attributes are scalar exact-match filter fields, not a rich metadata store, and it gives us no multi-value/contains query. So anything that needs fan-out (one document → many cache entries, for invalidation) or rich structure (full provenance with titles/paths/chunks) lives in our own Redis — the same instance the agent already uses.

> 💡 This is a single global cache. The knowledge corpus is shared with every requester and has no per-user ACL, so there's no tenant/user dimension.

### The LangCache Entry

**Core fields (LangCache managed):**

| Field | Type | Notes |
|---|---|---|
| `prompt` | — | The canonical/rewritten question, the string LangCache embeds and matches on |
| `response` | text | The served payload — the answer plus its source citations (titles/paths), serialized as JSON so a hit reconstructs sources with no extra read |
| `entry_id` | — | Unique ID LangCache returns from `astore()`, our join key to the Redis-side structures |
| `ttlMillis` | — | Per-entry expiry, fixed at store time (1h for latest, 24h for pinned). No refresh-on-hit on either backend — see divergence 3 for how that is preserved on `redisvl` |

**Attributes (declared at cache creation, immutable, scalar, exact-equality filters):**

| Attribute | Example | Purpose |
|---|---|---|
| `version` | `latest` / `7.8` / `7.4` | Lookup filter — never serve latest to a 7.2 query |
| `cache_origin` | `dynamic` / `curated` | Distinguishes generated vs. pre-warmed (for warming) |
| `entity_id` | `RET-4421` or `_none` | Exact identifier gate; pre-filters before similarity so `RET-4422` can't match `RET-4421`. **Always written**, using the `_none` sentinel when a query names no ticket — a tag filter cannot express "field absent", and an empty tag value compiles to `*` (match *everything*), so omitting it would let a general query match ticket-scoped entries. Collision-free: real ids must match `[A-Z]{2,}-\d+` |

> **Note:** Attributes are a 1:1 relationship in LangCache. They are scalar exact-match filter fields, so any query with multiple attribute matches is skipped for now and scoped for a future iteration.

### Our Redis: Reverse Index (Provenance & Bookkeeping for Invalidation & Debugging)

```
cache_prov:{path_hash}  →  SET { entry_id_a, entry_id_b, … }
```

- **Type**: Redis Set, one per cited document. `path_hash = sha256(source_document_path)[:16]`, the same hash used by ingestion for `sre_knowledge_meta:source:{path_hash}`. For each document an answer cited, we `SADD` the entry_id here. This is what lets us surgically invalidate: a changed doc → look up its `cache_prov` set → delete exactly those LangCache entries. It's how we get fan-out (one doc → many entries) without needing LangCache multi-value attributes.
- **Written at store time**: for each document the answer cited, `SADD cache_prov:{path_hash} {entry_id}`.
- **Read at invalidation**: ingestion emits a changed `path_hash` → `SMEMBERS cache_prov:{path_hash}` → `delete_entry` each → clear the links for the entries confirmed deleted (a failed delete keeps its link for a later retry).
- This is the structure that makes surgical, per-document invalidation possible without LangCache multi-value support. We keep the fan-out ourselves.

### Our Redis: Write-vs-Invalidate Tombstone

```
cache_inval:{path_hash} → short-TTL string ("1", TTL = semantic_cache_inval_tombstone_ttl_seconds, default 120s)
```

- Written by invalidation **first** (before deleting entries) to mark "this path just changed."
- The async store checks it before writing (skip if a cited path has a fresh tombstone) and rechecks after `SADD` (undo the just-written entry if a tombstone appeared during the write window). This closes the race the fire-and-forget write would otherwise open; the fixed TTL bounds any residual exposure.

### Our Redis: Side Metadata

```
cache_meta:{entry_id} → JSON
```

Holds the rich provenance and audit data that don't fit in scalar attributes and aren't needed on the hot serve path. Used for debugging ("why did this get cached / why didn't it invalidate?") and observability. Not on the serve path — sources for serving ride inside the LangCache response.

```json
{
  "provenance": [
    {
      "source_document_path": "operate/rs/7.8/clustering",
      "path_hash": "a1b2c3d4e5f6a7b8",
      "index_type": "knowledge",
      "title": "Redis Enterprise Clustering",
      "doc_version": "7.8",
      "document_hash": "9f8e…"
    }
  ],
  "original_question": "what about for 7.2?",
  "rewritten_question": "How do I configure clustering in Redis Enterprise 7.2?",
  "version": "7.2",
  "num_sources": 1,
  "entity_id": null
}
```

### How the Layers Connect

The cache wrapper builds one `provenance[]` entry per cited document from the turn's `search_results` (the citations on the returned `AgentResponse`, which already carry `source_document_path`, `document_hash`, `title`, `version`, `index_type`).

The LangCache attributes are resolved independently from the canonical key, not projected from provenance.

The only thing derived from provenance is the reverse index: one `SADD cache_prov:{path_hash}` per cited document. There are no `source_ids` / `index_origin` / `chunk_hashes` LangCache tags, and invalidation does not use a LangCache attribute query — it reads our own Redis (`SMEMBERS cache_prov`) then calls `delete_entry`.

**Four structures, four jobs:**
- LangCache = match + serve
- Reverse index = invalidate
- Tombstone = write-vs-invalidate race guard
- Side-blob = debug/audit

### Lifecycle, in One Line Each

- **Created**: on a grounded miss (async fire-and-forget) → `set_entry` → `entry_id`, then `SADD` reverse index per cited path + `SET cache_meta`. Skipped if a cited path has a fresh tombstone; rolled back (`delete_entry`) if a tombstone appears mid-write or the provenance write fails.
- **Served**: on a hit → reconstruct and return the `AgentResponse` (answer + sources) from the entry's response payload. No TTL refresh — TTL is fixed at store time.
- **Invalidated**: doc replaced/removed at ingestion → write tombstone → `SMEMBERS cache_prov` → `delete_entry` each → clear links for confirmed-deleted entries. Per-document only — no coarse `deleteQuery` and no feedback eviction in v1 (both deferred).
- **Expired**: fixed per-entry TTL backstop (short for latest, longer for pinned).

---

## Cache Flow

### Hit Flow

1. Query comes in. Any query that is instance-scoped is bypassed entirely. Only `knowledge_only` turns hit the cache.
2. Check `semantic_cache_enabled` flag. If off, straight to the agent, no cache calls.
3. Build the configured backend. If it cannot be built — `langcache` without credentials, or `redisvl` failing to construct — returns `None` and exits the cache flow.
4. Compute the canonical key on the raw query. Resolve the scope from that key:
   - **Version**: default `latest`
   - **Entity_id**: only a single support_ticket ID
   - **Multi-entity flag**: if enabled (≥ 2 tickets), treat as a miss, don't serve
5. Query the backend. If no entries come back, miss.
6. Scan the returned entries for the first one at or above the similarity threshold whose `entity_id` matches the requested scope exactly, comparing sentinel-to-sentinel in both directions. If none qualifies, miss.

   > Scanning rather than judging only the top hit is deliberate: a transport that ranks an out-of-scope near-miss first would otherwise produce a *false* miss while a valid in-scope answer sat right behind it.
7. On a hit, reconstruct the `AgentResponse` (answer + citations) from the entry's response JSON, log the hit via `exact|semantic (similarity=..)`; close the client.

> **Note:** Any errors are failed open, logged, and treated as a miss.

### Miss Flow

1. Run the real agent → `AgentResponse`. Return to the user immediately.
2. Schedule the store via an async fire-and-forget if the query is `knowledge_only` and `semantic_cache_enabled`.
3. Only cache if the answer is grounded (non-empty citations), has a non-empty answer, and doesn't reference multiple entities (multiple support tickets).
4. If any cited path has a fresh `cache_inval` tombstone, skip (that doc just changed).
5. Record provenance: `SADD cache_prov:{path_hash} entry_id` per cited doc + `SET cache_meta{entry_id}`. If links were expected but the record fails → roll back, `delete_entry`, and clean up so we never leave an un-invalidatable orphan.
6. Post-`SADD`, if a tombstone appeared during the write window, undo the entry (`delete_entry` + remove_entry).

### Invalidation Flow

1. Ingestion pipeline replaces/removes a document. `invalidate_changed_sources` runs.
2. Writes the `cache_inval` tombstone first (closes the race condition for any in-flight store flow).
3. Check for any relevant cache entries in the path_hash set: `SMEMBERS cache_prov:{path_hash}` → `delete_entry` each. Track which succeeded (and which were already deleted earlier in the same call for a doc cited by multiple paths).
4. Clear the reverse-index links only for entries confirmed gone; keep failed deletes for a later retry.
5. TTL is the passive backstop for anything push-invalidation misses (short for latest).

