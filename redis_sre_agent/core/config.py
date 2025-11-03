"""Configuration management using Pydantic Settings."""

from typing import TYPE_CHECKING, List, Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    pass

# Load environment variables from .env file if it exists
# In Docker/production, environment variables are set directly
from pathlib import Path

from dotenv import load_dotenv

ENV_FILE_OPT: str | None = None
TWENTY_MINUTES_IN_SECONDS = 1200

# Only load .env if it exists (for local development)
_env_path = Path(".env")
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)
    ENV_FILE_OPT = str(_env_path)


class Settings(BaseSettings):
    """Application configuration.

    Loads settings from environment variables. In local development, these can be
    provided via a .env file. In Docker/production, they should be set directly.
    """

    model_config = SettingsConfigDict(
        # Only hint an env file to pydantic if it actually exists
        env_file=ENV_FILE_OPT,
        env_file_encoding="utf-8",
        extra="ignore",
        # Don't error if .env file is missing (Docker/production use env vars directly)
        env_ignore_empty=True,
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
        default="redis://localhost:7843/0", description="Redis connection URL"
    )
    redis_password: Optional[SecretStr] = Field(default=None, description="Redis password")

    # OpenAI (optional at import time to allow CLI/docs to load without secrets)
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    openai_model: str = Field(default="gpt-5", description="OpenAI model for agent reasoning")
    openai_model_mini: str = Field(
        default="gpt-5-mini", description="OpenAI model for knowledge/search and utility tasks"
    )
    openai_model_nano: str = Field(
        default="gpt-5-nano", description="OpenAI model for very simple classification/triage"
    )

    # Vector Search
    embedding_model: str = Field(
        default="text-embedding-3-small", description="OpenAI embedding model"
    )
    vector_dim: int = Field(default=1536, description="Vector dimensions")

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


# Global settings instance
settings = Settings()
