"""Configuration models for tool providers.

Each tool provider can have its own configuration model that defines
the settings it needs (API keys, URLs, etc.).
"""

from typing import Optional

from pydantic import BaseModel, Field, SecretStr, validator


class PrometheusToolProviderSettings(BaseModel):
    """Configuration for Prometheus tool provider."""

    prometheus_url: str = Field(
        ..., description="Prometheus server URL (e.g., 'http://prometheus:9090')"
    )
    timeout: int = Field(default=30, ge=1, le=300)

    @validator("prometheus_url")
    def validate_url(cls, v):  # noqa: N805
        if not v.startswith(("http://", "https://")):
            raise ValueError("Prometheus URL must start with http:// or https://")
        return v.rstrip("/")


class GitHubToolProviderSettings(BaseModel):
    """Configuration for GitHub tool provider."""

    token: SecretStr = Field(..., description="GitHub personal access token")
    organization: Optional[str] = Field(default=None)
    api_url: str = Field(default="https://api.github.com")

    @validator("api_url")
    def validate_api_url(cls, v):  # noqa: N805
        if not v.startswith(("http://", "https://")):
            raise ValueError("GitHub API URL must start with http:// or https://")
        return v.rstrip("/")


class CloudWatchToolProviderSettings(BaseModel):
    """Configuration for CloudWatch Logs tool provider."""

    region: str = Field(..., description="AWS region (e.g., 'us-east-1')")
    log_group_prefix: Optional[str] = None
    access_key_id: Optional[SecretStr] = None
    secret_access_key: Optional[SecretStr] = None


class RedisEnterpriseToolProviderSettings(BaseModel):
    """Configuration for Redis Enterprise tool provider."""

    container_name: Optional[str] = Field(default="redis-enterprise-node1")
    api_url: Optional[str] = None
    api_username: Optional[str] = None
    api_password: Optional[SecretStr] = None

    @validator("api_url")
    def validate_api_url(cls, v):  # noqa: N805
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("API URL must start with http:// or https://")
        return v.rstrip("/") if v else None
