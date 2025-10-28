"""Provider configuration models for deployment-level integrations."""

from __future__ import annotations

import os
from typing import List, Optional

from pydantic import BaseModel, field_validator


class ProviderConfig(BaseModel):
    """Base model for provider configuration.

    Extra fields are forbidden to keep configs strict.
    """

    model_config = {
        "extra": "forbid",
    }


class PrometheusConfig(ProviderConfig):
    prometheus_url: str
    timeout: int = 30
    enabled: bool = True

    @field_validator("prometheus_url")
    @classmethod
    def validate_prom_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("must start with http:// or https://")
        # Strip trailing slash for consistency
        if v.endswith("/"):
            v = v[:-1]
        return v


class CloudWatchLogsConfig(ProviderConfig):
    region: str
    log_group_prefix: Optional[str] = None
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    enabled: bool = True


class GitHubConfig(ProviderConfig):
    token: str
    organization: Optional[str] = None
    api_url: str = "https://api.github.com"
    enabled: bool = True


class RedisDirectMetricsConfig(ProviderConfig):
    connection_timeout: int = 5
    socket_timeout: int = 10
    enabled: bool = True


class RedisDirectDiagnosticsConfig(ProviderConfig):
    connection_timeout: int = 5
    socket_timeout: int = 10
    max_slowlog_entries: int = 128
    enabled: bool = True


class RedisEnterpriseConfig(ProviderConfig):
    # Either container_name (Docker) or API connection details
    container_name: Optional[str] = None
    api_url: Optional[str] = None
    api_username: Optional[str] = None
    api_password: Optional[str] = None
    enabled: bool = True


class XRayTracesConfig(ProviderConfig):
    region: Optional[str] = None
    enabled: bool = False


class DeploymentProvidersConfig(ProviderConfig):
    prometheus: Optional[PrometheusConfig] = None
    cloudwatch_logs: Optional[CloudWatchLogsConfig] = None
    github: Optional[GitHubConfig] = None
    redis_direct_metrics: Optional[RedisDirectMetricsConfig] = None
    redis_direct_diagnostics: Optional[RedisDirectDiagnosticsConfig] = None
    redis_enterprise: Optional[RedisEnterpriseConfig] = None
    xray_traces: Optional[XRayTracesConfig] = None

    def get_enabled_providers(self) -> List[str]:
        """Return list of provider names that are configured and enabled."""
        enabled = []
        for name, value in self.__dict__.items():
            if value is None:
                continue
            # Provider models have an `enabled` flag; default True when present
            if getattr(value, "enabled", True):
                enabled.append(name)
        return enabled

    @classmethod
    def from_env(cls) -> "DeploymentProvidersConfig":
        """Create providers config from environment variables.

        Minimal behavior expected by tests:
        - Create PrometheusConfig if PROMETHEUS_URL is set
        - Apply PROMETHEUS_TIMEOUT if provided
        - Create GitHubConfig if GITHUB_TOKEN is set; include organization/api_url if provided
        - Create CloudWatchLogsConfig if CLOUDWATCH_REGION is set
        - Always create RedisDirect providers (metrics + diagnostics)
        """
        prometheus = None
        if url := os.environ.get("PROMETHEUS_URL"):
            timeout = int(os.environ.get("PROMETHEUS_TIMEOUT", "30"))
            prometheus = PrometheusConfig(prometheus_url=url, timeout=timeout)

        github = None
        if token := os.environ.get("GITHUB_TOKEN"):
            organization = os.environ.get("GITHUB_ORGANIZATION")
            api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com")
            github = GitHubConfig(token=token, organization=organization, api_url=api_url)

        cloudwatch = None
        if region := os.environ.get("CLOUDWATCH_REGION"):
            cloudwatch = CloudWatchLogsConfig(
                region=region,
                log_group_prefix=os.environ.get("CLOUDWATCH_LOG_GROUP_PREFIX"),
                access_key_id=os.environ.get("CLOUDWATCH_ACCESS_KEY_ID"),
                secret_access_key=os.environ.get("CLOUDWATCH_SECRET_ACCESS_KEY"),
            )

        # Always provide Redis direct configs by default
        redis_direct_metrics = RedisDirectMetricsConfig()
        redis_direct_diagnostics = RedisDirectDiagnosticsConfig()

        redis_enterprise = None
        if (api := os.environ.get("REDIS_ENTERPRISE_API_URL")) or (
            container := os.environ.get("REDIS_ENTERPRISE_CONTAINER")
        ):
            redis_enterprise = RedisEnterpriseConfig(
                api_url=api,
                container_name=container,
                api_username=os.environ.get("REDIS_ENTERPRISE_API_USERNAME"),
                api_password=os.environ.get("REDIS_ENTERPRISE_API_PASSWORD"),
            )

        xray = None
        if xr := os.environ.get("XRAY_REGION"):
            xray = XRayTracesConfig(region=xr, enabled=True)

        return cls(
            prometheus=prometheus,
            cloudwatch_logs=cloudwatch,
            github=github,
            redis_direct_metrics=redis_direct_metrics,
            redis_direct_diagnostics=redis_direct_diagnostics,
            redis_enterprise=redis_enterprise,
            xray_traces=xray,
        )
