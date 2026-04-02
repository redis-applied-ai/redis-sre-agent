## Configuration Reference

Use this page as the complete reference for settings loaded by [`redis_sre_agent/core/config.py`](https://github.com/redis-applied-ai/redis-sre-agent/blob/main/redis_sre_agent/core/config.py).

For configuration precedence, `.env` behavior, config-file discovery order, and setup examples, see [Configuration How-to](../how-to/configuration.md).

### Config File Selector

| Setting | Environment Variable | Type | Default | Notes |
|---|---|---|---|---|
| Config file path | `SRE_AGENT_CONFIG` | `str` | unset | Optional path to a YAML, TOML, or JSON config file. If unset, the app checks `config.yaml`, `config.yml`, `config.toml`, `config.json`, `sre_agent_config.yaml`, `sre_agent_config.yml`, `sre_agent_config.toml`, `sre_agent_config.json`. |

### Application

| Field | Environment Variable | Type | Default | Notes |
|---|---|---|---|---|
| `app_name` | `APP_NAME` | `str` | `Redis SRE Agent` | Application name. |
| `debug` | `DEBUG` | `bool` | `false` | Debug mode toggle. |
| `log_level` | `LOG_LEVEL` | `str` | `INFO` | Logging level. |

### Server

| Field | Environment Variable | Type | Default | Notes |
|---|---|---|---|---|
| `host` | `HOST` | `str` | `0.0.0.0` | API bind host. |
| `port` | `PORT` | `int` | `8000` | API bind port. |

### Redis

| Field | Environment Variable | Type | Default | Notes |
|---|---|---|---|---|
| `redis_url` | `REDIS_URL` | `SecretStr` | `redis://localhost:7843/0` | Redis connection URL for agent data. |

### LLM / OpenAI

| Field | Environment Variable | Type | Default | Notes |
|---|---|---|---|---|
| `openai_api_key` | `OPENAI_API_KEY` | `str \| None` | `None` | OpenAI API key. |
| `openai_base_url` | `OPENAI_BASE_URL` | `str \| None` | `None` | Optional OpenAI-compatible base URL. |
| `openai_model` | `OPENAI_MODEL` | `str` | `gpt-5` | Main reasoning model. |
| `openai_model_mini` | `OPENAI_MODEL_MINI` | `str` | `gpt-5-mini` | Lightweight model for utility/search tasks. |
| `openai_model_nano` | `OPENAI_MODEL_NANO` | `str` | `gpt-5-nano` | Smallest model for simple classification/triage. |

### Embeddings / Vector Search

| Field | Environment Variable | Type | Default | Notes |
|---|---|---|---|---|
| `embedding_provider` | `EMBEDDING_PROVIDER` | `str` | `openai` | `openai` or `local`. |
| `embedding_model` | `EMBEDDING_MODEL` | `str` | `text-embedding-3-small` | Embedding model name. |
| `vector_dim` | `VECTOR_DIM` | `int` | `1536` | Must match embedding model output dimensions. |
| `embeddings_cache_ttl` | `EMBEDDINGS_CACHE_TTL` | `int \| None` | `604800` | Embedding cache TTL in seconds; `None` means no expiration. |

### Task Queue

| Field | Environment Variable | Type | Default | Notes |
|---|---|---|---|---|
| `task_queue_name` | `TASK_QUEUE_NAME` | `str` | `sre_agent_tasks` | Docket queue name. |
| `max_task_retries` | `MAX_TASK_RETRIES` | `int` | `3` | Maximum retries per task. |
| `task_timeout` | `TASK_TIMEOUT` | `int` | `1200` | Task timeout in seconds. |

### Agent Runtime

| Field | Environment Variable | Type | Default | Notes |
|---|---|---|---|---|
| `max_iterations` | `MAX_ITERATIONS` | `int` | `50` | Max iterations for the main agent. |
| `knowledge_max_iterations` | `KNOWLEDGE_MAX_ITERATIONS` | `int` | `8` | Max iterations for the knowledge-only agent. |
| `max_tool_calls_per_stage` | `MAX_TOOL_CALLS_PER_STAGE` | `int` | `3` | Max tool/knowledge calls per worker stage. |
| `max_recommendation_topics` | `MAX_RECOMMENDATION_TOPICS` | `int` | `3` | Max recommendation topics processed per request. |
| `max_rejections` | `MAX_REJECTIONS` | `int` | `1` | Max correction attempts from safety/fact-check rejections. |
| `recursion_limit` | `RECURSION_LIMIT` | `int` | `100` | LangGraph recursion limit. |
| `tool_timeout` | `TOOL_TIMEOUT` | `int` | `60` | Tool execution timeout in seconds. |

### Tool Caching

| Field | Environment Variable | Type | Default | Notes |
|---|---|---|---|---|
| `tool_cache_enabled` | `TOOL_CACHE_ENABLED` | `bool` | `true` | Enables Redis-backed tool output cache. |
| `tool_cache_default_ttl` | `TOOL_CACHE_DEFAULT_TTL` | `int` | `60` | Default tool cache TTL in seconds. |
| `tool_cache_ttl_overrides` | `TOOL_CACHE_TTL_OVERRIDES` | `dict[str, int]` | `{}` | JSON map of per-tool TTL overrides. Example: `{"info": 120}`. |

### LLM Retry / Timeout / Factories

| Field | Environment Variable | Type | Default | Notes |
|---|---|---|---|---|
| `llm_max_retries` | `LLM_MAX_RETRIES` | `int` | `3` | Retry attempts for LLM requests. |
| `llm_initial_delay` | `LLM_INITIAL_DELAY` | `float` | `1.0` | Initial retry delay (seconds). |
| `llm_backoff_factor` | `LLM_BACKOFF_FACTOR` | `float` | `2.0` | Exponential backoff multiplier. |
| `llm_timeout` | `LLM_TIMEOUT` | `float` | `180.0` | LLM HTTP timeout in seconds. |
| `llm_factory` | `LLM_FACTORY` | `str \| None` | `None` | Dot-path to custom LangChain chat model factory. |
| `async_openai_client_factory` | `ASYNC_OPENAI_CLIENT_FACTORY` | `str \| None` | `None` | Dot-path to custom AsyncOpenAI-compatible client factory. |

### Monitoring

| Field | Environment Variable | Type | Default | Notes |
|---|---|---|---|---|
| `prometheus_url` | `PROMETHEUS_URL` | `str \| None` | `None` | Optional app-level Prometheus URL. |
| `grafana_url` | `GRAFANA_URL` | `str \| None` | `None` | Optional app-level Grafana URL. |
| `grafana_api_key` | `GRAFANA_API_KEY` | `str \| None` | `None` | Optional Grafana API key. |

### Security

| Field | Environment Variable | Type | Default | Notes |
|---|---|---|---|---|
| `api_key` | `API_KEY` | `str \| None` | `None` | API authentication key. |
| `allowed_hosts` | `ALLOWED_HOSTS` | `list[str]` | `["*"]` | CORS allow-list; pass as JSON in env var. |

### Support Package Storage

| Field | Environment Variable | Type | Default | Notes |
|---|---|---|---|---|
| `support_package_artifacts_dir` | `SUPPORT_PACKAGE_ARTIFACTS_DIR` | `Path` | `/tmp/sre_agent/support_packages` | Local extraction/storage path. |
| `support_package_storage_type` | `SUPPORT_PACKAGE_STORAGE_TYPE` | `str` | `local` | Storage backend: `local` or `s3`. |
| `support_package_s3_bucket` | `SUPPORT_PACKAGE_S3_BUCKET` | `str \| None` | `None` | S3 bucket name when using `s3` storage. |
| `support_package_s3_prefix` | `SUPPORT_PACKAGE_S3_PREFIX` | `str` | `support-packages/` | S3 key prefix. |
| `support_package_s3_region` | `SUPPORT_PACKAGE_S3_REGION` | `str \| None` | `None` | Optional AWS region override. |
| `support_package_s3_endpoint` | `SUPPORT_PACKAGE_S3_ENDPOINT` | `str \| None` | `None` | Optional custom S3 endpoint (for MinIO/S3-compatible storage). |

### Tool Providers

| Field | Environment Variable | Type | Default | Notes |
|---|---|---|---|---|
| `tool_providers` | `TOOL_PROVIDERS` | `list[str]` | Built-in provider class list | JSON array of provider class paths to enable. |

### MCP Servers

| Field | Environment Variable | Type | Default | Notes |
|---|---|---|---|---|
| `mcp_servers` | `MCP_SERVERS` | `dict[str, MCPServerConfig]` | Empty dict | JSON object of MCP server definitions. No MCP integrations are enabled unless you configure them. |

`MCPServerConfig` object keys:

- `command`: command to start MCP server (stdio mode)
- `args`: command arguments
- `env`: environment variables for the server process
- `url`: URL for remote MCP server (HTTP/SSE)
- `headers`: HTTP headers for remote MCP server
- `transport`: `streamable_http` (recommended) or `sse`
- `tools`: optional map of tool names to overrides

`MCPToolConfig` object keys inside `tools`:

- `capability`: capability classification (for example `logs`, `metrics`, `tickets`, `repos`)
- `description`: replacement description shown to the agent (`{original}` keeps upstream description text)

### Environment Value Formats

For structured settings, environment variables must be JSON strings:

- `ALLOWED_HOSTS`: JSON array, e.g. `["localhost", "127.0.0.1"]`
- `TOOL_PROVIDERS`: JSON array of class paths
- `TOOL_CACHE_TTL_OVERRIDES`: JSON object of `{tool_name: ttl_seconds}`
- `MCP_SERVERS`: JSON object matching `MCPServerConfig`

### See Also

- [Configuration How-to](../how-to/configuration.md)
- [Advanced Encryption](../how-to/configuration/encryption.md)
- [Tool Providers](../how-to/tool-providers.md)
