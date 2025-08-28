"""Configuration management using Pydantic Settings."""

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load environment variables from .env file
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # dotenv not installed


class Settings(BaseSettings):
    """Application configuration."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_name: str = "Redis SRE Agent"
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Logging level")

    # Server
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")
    redis_password: Optional[str] = Field(default=None, description="Redis password")

    # OpenAI
    openai_api_key: str = Field(description="OpenAI API key")
    openai_model: str = Field(default="o4-mini", description="OpenAI model for agent reasoning")
    openai_model_mini: str = Field(default="o4-mini", description="OpenAI model for tools")

    # Vector Search
    embedding_model: str = Field(
        default="text-embedding-3-small", description="OpenAI embedding model"
    )
    vector_dim: int = Field(default=1536, description="Vector dimensions")

    # Docket Task Queue
    task_queue_name: str = Field(default="sre_agent_tasks", description="Task queue name")
    max_task_retries: int = Field(default=3, description="Maximum task retries")
    task_timeout: int = Field(default=300, description="Task timeout in seconds")

    # Agent
    max_iterations: int = Field(default=10, description="Maximum agent iterations")
    tool_timeout: int = Field(default=60, description="Tool execution timeout")

    # LLM Retry Configuration
    llm_max_retries: int = Field(default=3, description="Maximum retries for LLM calls")
    llm_initial_delay: float = Field(
        default=1.0, description="Initial delay for LLM retries (seconds)"
    )
    llm_backoff_factor: float = Field(default=2.0, description="Backoff factor for LLM retries")

    # Monitoring Integration (optional)
    prometheus_url: Optional[str] = Field(default=None, description="Prometheus server URL")
    grafana_url: Optional[str] = Field(default=None, description="Grafana server URL")
    grafana_api_key: Optional[str] = Field(default=None, description="Grafana API key")

    # Security
    api_key: Optional[str] = Field(default=None, description="API authentication key")
    allowed_hosts: list[str] = Field(default=["*"], description="Allowed hosts for CORS")


# Global settings instance
settings = Settings()
