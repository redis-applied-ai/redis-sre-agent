## Minimal Production Quickstart (Compose)

A small, production‑oriented Compose deployment using the API + Worker and monitoring.

### Outline
- Provide secrets via environment (no .env in images)
- Start only required services (avoid Redis Enterprise demo by default)
- Expose API via reverse proxy or load balancer; enable TLS
- Monitor via Prometheus/Grafana; scrape /api/v1/metrics

### Example (skeleton)
```bash
# Build images
docker compose build sre-agent sre-worker

# Run core services
docker compose up -d redis sre-agent sre-worker prometheus grafana loki promtail
```

TODO: Add a dedicated docker-compose.prod.yml and guidance for secrets, health checks, and rollout/rollback.
