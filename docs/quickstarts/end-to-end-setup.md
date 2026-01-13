# Getting started with the SRE agent

## Prerequisites
- Docker
- Docker compose
- OpenAI API key
- Python >= 3.12
- uv package manager

## Env

Copy the example env
```bash
cp .env.example .env
```

Update the env to include your openai key
```bash
OPENAI_API_KEY=your_key
```

Generate a master key
```bash
python -c 'import os, base64; print(base64.b64encode(os.urandom(32)).decode())'
```

Update the env to include the master key
```bash
REDIS_SRE_MASTER_KEY=your_key
```

Note: The env example will set the default models. If you are using newer models confirm that they are available in the litellm config: /monitoring/litellm/config.yaml.

## Docker compose

Start the following services using docker compose
```bash
docker compose up -d \
  redis redis-demo \
  sre-agent sre-worker \
  prometheus grafana \
  loki promtail
```

A breakdown of what each of these services are:

- redis: the redis instance used by the sre-agent and sre-worker.
- redis-demo: the redis instance that the sre-agent will monitor.
- sre-agent: the sre agent api
- sre-worker: the sre agent worker
- prometheus: prometheus instance
- grafana: grafana instance
- loki: loki instance
- promtail: promtail instance

**Note**: there are **two** redis instances. One is used by the application itself and the other is the redis instance that the sre-agent will monitor.

### Status checks

#### API
```bash
# Root health (fast)
# Use port 8080 for Docker Compose, port 8000 for local uvicorn
curl -fsS http://localhost:8080/

# Detailed health (Redis, vector index, workers)
curl -fsS http://localhost:8080/api/v1/health | jq

# Prometheus metrics (scrape this)
curl -fsS http://localhost:8080/api/v1/metrics | head -n 20
```

#### Docker ps
```bash
docker ps
```

![alt text](./resources/docker.png)

#### Redis

Use redis insight or redis_cli to confirm that both redis instances are up and running. By default the internal sre redis should be available at redis://localhost:7843 and the redis-demo at redis://localhost:7844. The internal instance 7843 will have docket workers and some additional keys related to the sre-agent. The redis-demo instance will be empty.

## Populating the knowledge base and running the UI

Populate the index locally (this will take a second to do the embeddings)
```bash
uv run ./scripts/setup_redis_docs_local.sh

uv run redis-sre-agent pipeline ingest
```

![scrape](./resources/scrape.png)

Now check the index to make sure documents were loaded.

![data](./resources/data-proc.png)

### Run the sre-ui
```bash
docker compose up -d sre-ui
```

The ui should be available at http://localhost:3002 and look something like the following.

![ui](./resources/ui.png)

Note: if you see connection issue open the dev console and check that connection are attempting to be made to the correct ports. If you see that it is attempting to connect at the wrong port update ui/.env to include the correct port. For example:
```bash
# in ui/.env not root level .env
VITE_API_URL=http://localhost:8080/api/v1
```

## Adding an instance

Create the instance the agent will triage, then verify a connection.
```bash
# Create instance
curl -fsS -X POST http://localhost:8080/api/v1/instances \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "local-dev",
    "connection_url": "redis://redis-demo:6379/0",
    "environment": "dev",
    "usage": "cache",
    "description": "Primary Redis"
  }' | jq
```


# Review

Now you should have a basic running version of the redis sre agent! You can try asking it questions about redis in the UI or via the API. You can also try running the agent with different configurations and settings.
