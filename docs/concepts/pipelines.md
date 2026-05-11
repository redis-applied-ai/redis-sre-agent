---
description: Knowledge ingestion: scrape, parse, chunk, embed, index.
---

# Pipelines

Pipelines turn raw Redis documentation, runbooks, and tickets into a vector
index the agent can search at triage time. They are background processes —
you usually run them once during setup and then on a schedule. If you want
to change *what* the agent knows, you do it here. For step-by-step recipes,
see [Pipelines (how-to)](../user_guide/how_to_guides/pipelines.md).

**Related:** [Source documents](../user_guide/how_to_guides/source_documents.md) ·
[REST API reference](../api/rest_api.md)

## Pipeline stages

```
SCRAPE → PARSE → CHUNK → EMBED → INDEX
```

1. **Scrape** - Fetch content from configured sources (redis.io, local docs, runbooks)
2. **Parse** - Extract text and metadata from HTML, Markdown, or PDF
3. **Chunk** - Split documents into retrieval-sized chunks with overlap
4. **Embed** - Generate vector embeddings for each chunk
5. **Index** - Store chunks and vectors in Redis for semantic search

## Data sources

- **redis.io knowledge base** - Official Redis documentation
- **Local docs** - Clone of `redis/docs` for offline access
- **Source documents** - Custom runbooks and playbooks in `source_documents/`
- **External URLs** - Any web-accessible documentation

## Running pipelines

```bash
# Scrape and prepare artifacts
uv run redis-sre-agent pipeline scrape

# Index artifacts into Redis
uv run redis-sre-agent pipeline ingest

# Full pipeline (scrape + ingest)
uv run redis-sre-agent pipeline full
```

## State machine

Each pipeline run tracks its state:

- **QUEUED** - Waiting to start
- **RUNNING** - Actively processing
- **COMPLETED** - All stages finished successfully
- **FAILED** - An error occurred; partial results may be available
- **CANCELLED** - Manually stopped

## Incremental updates

Pipelines support incremental ingestion: only new or changed documents are re-processed. Content hashing prevents duplicate chunks.
