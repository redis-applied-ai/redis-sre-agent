"""Provider configuration models.

These models define the configuration for each provider type at deployment level.
Providers are configured once per deployment, not per target.
"""

from typing import Optional

from pydantic import BaseModel, Field, validator


class ProviderConfig(BaseModel):
    """Base configuration for all providers."""

    enabled: bool = True

    class Config:
        """Pydantic configuration."""

        extra = "forbid"  # Prevent typos in config


class PrometheusConfig(ProviderConfig):
    """Configuration for Prometheus metrics provider."""

    prometheus_url: str = Field(
        ...,
        description="Prometheus server URL (e.g., 'http://prometheus:9090')",
    )
    timeout: int = Field(
        default=30,
        description="Request timeout in seconds",
        ge=1,
        le=300,
    )

    @validator("prometheus_url")
    def validate_url(cls, v):  # noqa: N805
        """Validate Prometheus URL format."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("Prometheus URL must start with http:// or https://")
        return v.rstrip("/")


class CloudWatchLogsConfig(ProviderConfig):
    """Configuration for AWS CloudWatch Logs provider."""

    region: str = Field(
        ...,
        description="AWS region (e.g., 'us-east-1')",
    )
    log_group_prefix: Optional[str] = Field(
        default=None,
        description="Optional prefix to filter log groups",
    )
    access_key_id: Optional[str] = Field(
        default=None,
        description="AWS access key ID (if not using IAM role)",
    )
    secret_access_key: Optional[str] = Field(
        default=None,
        description="AWS secret access key (if not using IAM role)",
    )


class GitHubConfig(ProviderConfig):
    """Configuration for GitHub provider (tickets and repos)."""

    token: str = Field(
        ...,
        description="GitHub personal access token",
    )
    organization: Optional[str] = Field(
        default=None,
        description="GitHub organization name (if applicable)",
    )
    api_url: str = Field(
        default="https://api.github.com",
        description="GitHub API URL (use for GitHub Enterprise)",
    )

    @validator("api_url")
    def validate_api_url(cls, v):  # noqa: N805
        """Validate GitHub API URL format."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("GitHub API URL must start with http:// or https://")
        return v.rstrip("/")


class RedisDirectMetricsConfig(ProviderConfig):
    """Configuration for Redis direct metrics provider.

    This provider connects directly to Redis instances via Redis protocol.
    No deployment-level configuration needed - uses target's redis_url.
    """

    connection_timeout: int = Field(
        default=5,
        description="Connection timeout in seconds",
        ge=1,
        le=60,
    )
    socket_timeout: int = Field(
        default=10,
        description="Socket timeout in seconds",
        ge=1,
        le=60,
    )


class RedisDirectDiagnosticsConfig(ProviderConfig):
    """Configuration for Redis direct diagnostics provider.

    This provider connects directly to Redis instances for diagnostics.
    No deployment-level configuration needed - uses target's redis_url.
    """

    connection_timeout: int = Field(
        default=5,
        description="Connection timeout in seconds",
        ge=1,
        le=60,
    )
    socket_timeout: int = Field(
        default=10,
        description="Socket timeout in seconds",
        ge=1,
        le=60,
    )
    max_slowlog_entries: int = Field(
        default=128,
        description="Maximum slowlog entries to retrieve",
        ge=1,
        le=1000,
    )


class RedisEnterpriseConfig(ProviderConfig):
    """Configuration for Redis Enterprise provider.

    Supports both Docker-based (rladmin) and REST API access.
    """

    # Docker-based access
    container_name: Optional[str] = Field(
        default="redis-enterprise-node1",
        description="Docker container name for rladmin commands",
    )

    # REST API access
    api_url: Optional[str] = Field(
        default=None,
        description="Redis Enterprise REST API URL",
    )
    api_username: Optional[str] = Field(
        default=None,
        description="Redis Enterprise API username",
    )
    api_password: Optional[str] = Field(
        default=None,
        description="Redis Enterprise API password",
    )

    @validator("api_url")
    def validate_api_url(cls, v):  # noqa: N805
        """Validate API URL format."""
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("API URL must start with http:// or https://")
        return v.rstrip("/") if v else None

    @validator("api_username")
    def validate_api_credentials(cls, v, values):  # noqa: N805
        """Ensure API credentials are complete if provided."""
        if values.get("api_url") and not v:
            raise ValueError("api_username required when api_url is provided")
        return v


class XRayTracesConfig(ProviderConfig):
    """Configuration for AWS X-Ray traces provider."""

    region: str = Field(
        ...,
        description="AWS region (e.g., 'us-east-1')",
    )
    access_key_id: Optional[str] = Field(
        default=None,
        description="AWS access key ID (if not using IAM role)",
    )
    secret_access_key: Optional[str] = Field(
        default=None,
        description="AWS secret access key (if not using IAM role)",
    )


class DeploymentProvidersConfig(BaseModel):
    """All provider configurations for this deployment.

    Only enabled providers will be initialized and available to the agent.
    Each provider can be configured independently.
    """

    prometheus: Optional[PrometheusConfig] = Field(
        default=None,
        description="Prometheus metrics provider configuration",
    )

    cloudwatch_logs: Optional[CloudWatchLogsConfig] = Field(
        default=None,
        description="AWS CloudWatch Logs provider configuration",
    )

    github: Optional[GitHubConfig] = Field(
        default=None,
        description="GitHub provider configuration (tickets and repos)",
    )

    redis_direct_metrics: Optional[RedisDirectMetricsConfig] = Field(
        default=None,
        description="Redis direct metrics provider configuration",
    )

    redis_direct_diagnostics: Optional[RedisDirectDiagnosticsConfig] = Field(
        default=None,
        description="Redis direct diagnostics provider configuration",
    )

    redis_enterprise: Optional[RedisEnterpriseConfig] = Field(
        default=None,
        description="Redis Enterprise provider configuration",
    )

    xray_traces: Optional[XRayTracesConfig] = Field(
        default=None,
        description="AWS X-Ray traces provider configuration",
    )

    class Config:
        """Pydantic configuration."""

        extra = "forbid"  # Prevent typos in config

    def get_enabled_providers(self) -> list[str]:
        """Get list of enabled provider names."""
        enabled = []
        for field_name, field_value in self.dict().items():
            if field_value and field_value.get("enabled", True):
                enabled.append(field_name)
        return enabled

    @classmethod
    def from_env(cls) -> "DeploymentProvidersConfig":
        """Create configuration from environment variables.

        Expected environment variables:
        - PROMETHEUS_URL
        - CLOUDWATCH_REGION
        - GITHUB_TOKEN
        - etc.
        """
        import os

        config = {}

        # Prometheus
        if os.getenv("PROMETHEUS_URL"):
            config["prometheus"] = PrometheusConfig(
                prometheus_url=os.getenv("PROMETHEUS_URL"),
                timeout=int(os.getenv("PROMETHEUS_TIMEOUT", "30")),
            )

        # CloudWatch Logs
        if os.getenv("CLOUDWATCH_REGION"):
            config["cloudwatch_logs"] = CloudWatchLogsConfig(
                region=os.getenv("CLOUDWATCH_REGION"),
                log_group_prefix=os.getenv("CLOUDWATCH_LOG_GROUP_PREFIX"),
                access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            )

        # GitHub
        if os.getenv("GITHUB_TOKEN"):
            config["github"] = GitHubConfig(
                token=os.getenv("GITHUB_TOKEN"),
                organization=os.getenv("GITHUB_ORGANIZATION"),
                api_url=os.getenv("GITHUB_API_URL", "https://api.github.com"),
            )

        # Redis Direct Metrics (always enabled by default)
        config["redis_direct_metrics"] = RedisDirectMetricsConfig(
            connection_timeout=int(os.getenv("REDIS_CONNECTION_TIMEOUT", "5")),
            socket_timeout=int(os.getenv("REDIS_SOCKET_TIMEOUT", "10")),
        )

        # Redis Direct Diagnostics (always enabled by default)
        config["redis_direct_diagnostics"] = RedisDirectDiagnosticsConfig(
            connection_timeout=int(os.getenv("REDIS_CONNECTION_TIMEOUT", "5")),
            socket_timeout=int(os.getenv("REDIS_SOCKET_TIMEOUT", "10")),
        )

        # Redis Enterprise
        if os.getenv("REDIS_ENTERPRISE_CONTAINER") or os.getenv("REDIS_ENTERPRISE_API_URL"):
            config["redis_enterprise"] = RedisEnterpriseConfig(
                container_name=os.getenv("REDIS_ENTERPRISE_CONTAINER"),
                api_url=os.getenv("REDIS_ENTERPRISE_API_URL"),
                api_username=os.getenv("REDIS_ENTERPRISE_API_USERNAME"),
                api_password=os.getenv("REDIS_ENTERPRISE_API_PASSWORD"),
            )

        # X-Ray
        if os.getenv("XRAY_REGION"):
            config["xray_traces"] = XRayTracesConfig(
                region=os.getenv("XRAY_REGION"),
                access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            )

        return cls(**config)
