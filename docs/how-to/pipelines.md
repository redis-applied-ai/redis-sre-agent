## Pipelines & Ingestion

Use pipelines to ingest knowledge sources (docs, runbooks, vendor references) to power the Knowledge Agent.

- Prepare sources (configure what to ingest): `uv run redis-sre-agent pipeline prepare_sources`
- Ingest content into the knowledge base: `uv run redis-sre-agent pipeline ingest`

### Notes
- Run these from the project root (or inside the container with `docker compose exec -T sre-agent ...`).
- Configure sources and credentials via environment and provider settings.
- Start small; verify retrieval quality before scaling up.
