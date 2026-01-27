"""Configuration management using Pydantic Settings."""

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Type, Union

from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from redis_sre_agent.tools.models import ToolCapability

if TYPE_CHECKING:
    pass


class MCPToolConfig(BaseModel):
    """Configuration for a specific tool exposed by an MCP server.

    This allows overriding or constraining how the agent sees and uses
    a specific MCP tool.

    Example:
        MCPToolConfig(
            capability=ToolCapability.LOGS,
            description="Use this tool when searching for memories..."
        )
    """

    capability: Optional[ToolCapability] = Field(
        default=None,
        description="The capability category for this tool (e.g., LOGS, METRICS). "
        "If not specified, defaults to UTILITIES.",
    )
    description: Optional[str] = Field(
        default=None,
        description="Alternative description for this tool. "
        "If provided, the agent sees this instead of the MCP server's description.",
    )


class MCPServerConfig(BaseModel):
    """Configuration for an MCP server.

    This follows the standard MCP configuration format used by Claude, VS Code,
    and other tools, with additional fields for tool constraints.

    Example:
        MCPServerConfig(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-memory"],
            tools={
                "search_memories": MCPToolConfig(capability=ToolCapability.LOGS),
                "create_memories": MCPToolConfig(description="Use this tool when..."),
            }
        )
    """

    # Standard MCP configuration fields
    command: Optional[str] = Field(
        default=None,
        description="Command to launch the MCP server (for stdio transport).",
    )
    args: Optional[List[str]] = Field(
        default=None,
        description="Arguments to pass to the MCP server command.",
    )
    env: Optional[Dict[str, str]] = Field(
        default=None,
        description="Environment variables to set when launching the server.",
    )

    # URL-based transport (alternative to command-based)
    url: Optional[str] = Field(
        default=None,
        description="URL for SSE or HTTP-based MCP transport.",
    )

    # Headers for HTTP/SSE transport (e.g., Authorization)
    headers: Optional[Dict[str, str]] = Field(
        default=None,
        description="Headers to send with HTTP/SSE requests (e.g., Authorization).",
    )

    # Transport type for URL-based connections
    transport: Optional[str] = Field(
        default=None,
        description="Transport type for URL-based connections: 'sse' for Server-Sent Events "
        "(legacy), 'streamable_http' for Streamable HTTP (recommended for modern servers like "
        "GitHub's remote MCP). If not specified, defaults to 'streamable_http' for better "
        "compatibility with modern MCP servers.",
    )

    # Tool constraints - if provided, only these tools are exposed to the agent
    tools: Optional[Dict[str, MCPToolConfig]] = Field(
        default=None,
        description="Optional mapping of tool names to their configurations. "
        "If provided, only these tools are exposed to the agent from the MCP server. "
        "Each tool can have a custom capability and/or description override.",
    )


# Load environment variables from .env file if it exists
# In Docker/production, environment variables are set directly
ENV_FILE_OPT: str | None = None
TWENTY_MINUTES_IN_SECONDS = 1200

# Only load .env if it exists (for local development)
# In Docker/production, environment variables are set directly.
# We check existence before calling load_dotenv to avoid FileNotFoundError.
_env_path = Path(".env")
try:
    if _env_path.is_file():
        load_dotenv(dotenv_path=_env_path)
        ENV_FILE_OPT = str(_env_path)
    else:
        # Try loading from default locations without erroring if not found
        load_dotenv()
except (FileNotFoundError, OSError):
    # File may have been removed after is_file() check, or mount issues in Docker
    pass


# Default config file paths (checked in order)
# SRE_AGENT_CONFIG environment variable takes precedence if set
DEFAULT_CONFIG_PATHS = [
    "config.yaml",
    "config.yml",
    "sre_agent_config.yaml",
    "sre_agent_config.yml",
]


def _get_yaml_config_path() -> str | list[str] | None:
    """Get the YAML config file path to use.

    Returns:
        - The path from SRE_AGENT_CONFIG env var if set
        - Or the list of default paths to check
        - Or None if SRE_AGENT_CONFIG is set to a nonexistent file
    """
    config_path = os.environ.get("SRE_AGENT_CONFIG")

    if config_path:
        # If explicitly specified, use it (pydantic will handle missing files)
        return config_path

    # Return list of default paths - pydantic-settings will check each in order
    return DEFAULT_CONFIG_PATHS


class Settings(BaseSettings):
    """Application configuration.

    Loads settings from environment variables. In local development, these can be
    provided via a .env file. In Docker/production, they should be set directly.

    Configuration can also be loaded from YAML files. The following paths are checked
    (first match wins):
    - Path specified in SRE_AGENT_CONFIG environment variable
    - config.yaml, config.yml, sre_agent_config.yaml, sre_agent_config.yml

    Priority (highest to lowest):
    1. Values passed to Settings() constructor
    2. Environment variables
    3. .env file
    4. YAML config file
    5. Default values
    """

    model_config = SettingsConfigDict(
        # Only hint an env file to pydantic if it actually exists
        env_file=ENV_FILE_OPT,
        env_file_encoding="utf-8",
        extra="ignore",
        # Don't error if .env file is missing (Docker/production use env vars directly)
        env_ignore_empty=True,
        # Note: yaml_file is set dynamically in settings_customise_sources
        # to support SRE_AGENT_CONFIG env var being set after module import
    )

    # Application
    app_name: str = "Redis SRE Agent"
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Logging level")

    # Server
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")

    # Redis
    redis_url: SecretStr = Field(
        default=SecretStr("redis://localhost:7843/0"), description="Redis connection URL"
    )
    redis_password: Optional[SecretStr] = Field(default=None, description="Redis password")

    # OpenAI (optional at import time to allow CLI/docs to load without secrets)
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    openai_base_url: Optional[str] = Field(
        default=None,
        description="OpenAI API base URL (optional, for using LLM proxy or alternative endpoints)",
    )
    openai_model: str = Field(default="gpt-5", description="OpenAI model for agent reasoning")
    openai_model_mini: str = Field(
        default="gpt-5-mini", description="OpenAI model for knowledge/search and utility tasks"
    )
    openai_model_nano: str = Field(
        default="gpt-5-nano", description="OpenAI model for very simple classification/triage"
    )

    # Vector Search / Embeddings
    embedding_provider: str = Field(
        default="openai",
        description=(
            "Embedding provider: 'openai' for OpenAI API (requires OPENAI_API_KEY), "
            "'local' for local HuggingFace sentence-transformers (no API needed, air-gap compatible)"
        ),
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description=(
            "Embedding model name. For 'openai' provider: 'text-embedding-3-small', "
            "'text-embedding-3-large', etc. For 'local' provider: any sentence-transformers "
            "model like 'sentence-transformers/all-MiniLM-L6-v2' (384 dims) or "
            "'sentence-transformers/all-mpnet-base-v2' (768 dims)"
        ),
    )
    vector_dim: int = Field(
        default=1536,
        description=(
            "Vector dimensions. Must match the embedding model: "
            "OpenAI text-embedding-3-small=1536, all-MiniLM-L6-v2=384, all-mpnet-base-v2=768"
        ),
    )
    embeddings_cache_ttl: Optional[int] = Field(
        default=86400 * 7,  # 7 days
        description="TTL in seconds for cached embeddings. None means no expiration.",
    )

    # Docket Task Queue
    task_queue_name: str = Field(default="sre_agent_tasks", description="Task queue name")
    max_task_retries: int = Field(default=3, description="Maximum task retries")
    task_timeout: int = Field(
        default=TWENTY_MINUTES_IN_SECONDS, description="Task timeout in seconds"
    )

    # Agent
    max_iterations: int = Field(
        default=50,
        description="Maximum reasoning iterations (LLM message cycles) for the main agent",
    )
    # A tighter default is helpful for the knowledge-only agent to avoid loops
    knowledge_max_iterations: int = Field(
        default=8,
        description="Maximum iterations specifically for the knowledge-only agent",
    )
    max_tool_calls_per_stage: int = Field(
        default=3,
        description="Maximum knowledge/tool calls per subgraph stage (e.g., per-topic research budget)",
    )
    max_recommendation_topics: int = Field(
        default=3,
        description="Maximum number of topics to run recommendation workers for",
    )
    max_rejections: int = Field(
        default=1,
        description="Maximum number of correction attempts triggered by safety or fact-checking per query",
    )
    recursion_limit: int = Field(
        default=100, description="LangGraph recursion limit for complex workflows"
    )
    tool_timeout: int = Field(default=60, description="Tool execution timeout")

    # Tool Caching
    tool_cache_enabled: bool = Field(
        default=True,
        description="Enable Redis-backed caching of tool outputs across runs",
    )
    tool_cache_default_ttl: int = Field(
        default=60,
        description="Default TTL in seconds for cached tool outputs",
    )
    tool_cache_ttl_overrides: Dict[str, int] = Field(
        default_factory=dict,
        description="Per-tool TTL overrides in seconds. Keys are matched against tool names. "
        "Example: {'info': 120, 'slowlog': 30}. "
        "Set via env var as JSON: TOOL_CACHE_TTL_OVERRIDES='{\"info\": 120}'",
    )

    # LLM Retry Configuration
    llm_max_retries: int = Field(default=3, description="Maximum retries for LLM calls")
    llm_initial_delay: float = Field(
        default=1.0, description="Initial delay for LLM retries (seconds)"
    )
    llm_backoff_factor: float = Field(default=2.0, description="Backoff factor for LLM retries")

    # LLM Request Timeout (seconds)
    llm_timeout: float = Field(default=180.0, description="HTTP timeout for LLM requests (seconds)")

    # Monitoring Integration (optional)
    prometheus_url: Optional[str] = Field(default=None, description="Prometheus server URL")
    grafana_url: Optional[str] = Field(default=None, description="Grafana server URL")
    grafana_api_key: Optional[str] = Field(default=None, description="Grafana API key")

    # Security
    api_key: Optional[str] = Field(default=None, description="API authentication key")
    allowed_hosts: list[str] = Field(default=["*"], description="Allowed hosts for CORS")

    # Support Package Configuration
    support_package_artifacts_dir: Path = Field(
        default=Path("/tmp/sre_agent/support_packages"),
        description="Directory where support packages are extracted and stored",
    )
    support_package_storage_type: str = Field(
        default="local",
        description="Storage backend type: 'local' or 's3'",
    )
    support_package_s3_bucket: Optional[str] = Field(
        default=None,
        description="S3 bucket name for support package storage (when storage_type='s3')",
    )
    support_package_s3_prefix: str = Field(
        default="support-packages/",
        description="S3 key prefix for support packages",
    )
    support_package_s3_region: Optional[str] = Field(
        default=None,
        description="AWS region for S3 bucket (optional, uses default if not set)",
    )
    support_package_s3_endpoint: Optional[str] = Field(
        default=None,
        description="Custom S3 endpoint URL (for S3-compatible storage like MinIO)",
    )

    # Tool Provider Configuration
    tool_providers: List[str] = Field(
        default_factory=lambda: [
            "redis_sre_agent.tools.metrics.prometheus.provider.PrometheusToolProvider",
            "redis_sre_agent.tools.diagnostics.redis_command.provider.RedisCommandToolProvider",
            "redis_sre_agent.tools.logs.loki.provider.LokiToolProvider",
            "redis_sre_agent.tools.host_telemetry.provider.HostTelemetryToolProvider",
        ],
        description="Enabled tool providers (fully qualified class paths). "
        "Example: redis_sre_agent.tools.metrics.prometheus.PrometheusToolProvider",
    )

    # MCP Server Configuration
    # Uses "uv tool run" (equivalent to uvx) to auto-install the package from PyPI.
    # Override via MCP_SERVERS environment variable (JSON) if needed.
    mcp_servers: Dict[str, Union[MCPServerConfig, Dict[str, Any]]] = Field(
        default_factory=lambda: {
            "redis-memory-server": {
                "command": "uv",
                "args": [
                    "tool",
                    "run",
                    "--from",
                    "agent-memory-server",
                    "agent-memory",
                    "mcp",
                ],
                "env": {"REDIS_URL": "${REDIS_URL}"},
                # Only include specific tools, with context-aware descriptions.
                # Use {original} to include the tool's original description.
                "tools": {
                    "get_current_datetime": {
                        "description": (
                            "Get the current date and time. Use this when you need to "
                            "record timestamps for Redis instance events or incidents.\n\n"
                            "{original}"
                        ),
                    },
                    "create_long_term_memories": {
                        "description": (
                            "Save long-term memories about Redis instances. Use this to "
                            "record: past incidents and their resolutions, configuration "
                            "changes, performance baselines, known issues, maintenance "
                            "history, and lessons learned. Always include the instance_id "
                            "in the memory text for future retrieval.\n\n{original}"
                        ),
                    },
                    "search_long_term_memory": {
                        "description": (
                            "Search saved memories about Redis instances. ALWAYS use this "
                            "before troubleshooting a Redis instance to recall past issues, "
                            "solutions, and context. Search by instance_id, error patterns, "
                            "or symptoms.\n\n{original}"
                        ),
                    },
                    "get_long_term_memory": {
                        "description": (
                            "Retrieve a specific memory by ID. Use this to get full details "
                            "of a memory found via search.\n\n{original}"
                        ),
                    },
                    "edit_long_term_memory": {
                        "description": (
                            "Update an existing memory. Use this to add new information to "
                            "a past incident record, update resolution status, or correct "
                            "outdated information.\n\n{original}"
                        ),
                    },
                    "delete_long_term_memories": {
                        "description": (
                            "Delete memories that are no longer relevant. Use sparingly - "
                            "prefer editing to add context rather than deleting.\n\n{original}"
                        ),
                    },
                },
            }
        },
        description="MCP (Model Context Protocol) servers to connect to. "
        "Each key is the server name, and the value is the server configuration. "
        "Example: {'memory': {'command': 'npx', 'args': ['-y', '@modelcontextprotocol/server-memory'], "
        "'tools': {'search_memories': {'capability': 'logs'}}}}",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        """Customize settings sources to include YAML config file.

        Priority (highest to lowest):
        1. init_settings (passed to Settings())
        2. env_settings (environment variables)
        3. dotenv_settings (.env file)
        4. yaml_settings (config.yaml file)
        5. file_secret_settings (Docker secrets)
        """
        # Use the built-in YamlConfigSettingsSource from pydantic-settings
        # Get the yaml_file path dynamically to respect SRE_AGENT_CONFIG env var
        # set after module import
        yaml_file = _get_yaml_config_path()
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file=yaml_file),
            file_secret_settings,
        )


# Global settings instance
settings = Settings()
