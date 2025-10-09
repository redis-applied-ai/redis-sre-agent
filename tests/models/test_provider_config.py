"""Tests for provider configuration models."""

import os

import pytest
from pydantic import ValidationError

from redis_sre_agent.models.provider_config import (
    CloudWatchLogsConfig,
    DeploymentProvidersConfig,
    GitHubConfig,
    PrometheusConfig,
    RedisDirectDiagnosticsConfig,
    RedisDirectMetricsConfig,
    RedisEnterpriseConfig,
)


def test_prometheus_config_valid():
    """Test valid Prometheus configuration."""
    config = PrometheusConfig(prometheus_url="http://prometheus:9090")
    assert config.prometheus_url == "http://prometheus:9090"
    assert config.timeout == 30
    assert config.enabled is True


def test_prometheus_config_invalid_url():
    """Test Prometheus configuration with invalid URL."""
    with pytest.raises(ValidationError) as exc_info:
        PrometheusConfig(prometheus_url="invalid-url")

    assert "must start with http:// or https://" in str(exc_info.value)


def test_prometheus_config_strips_trailing_slash():
    """Test that trailing slash is stripped from URL."""
    config = PrometheusConfig(prometheus_url="http://prometheus:9090/")
    assert config.prometheus_url == "http://prometheus:9090"


def test_cloudwatch_logs_config():
    """Test CloudWatch Logs configuration."""
    config = CloudWatchLogsConfig(
        region="us-east-1",
        log_group_prefix="/aws/redis",
        access_key_id="AKIAIOSFODNN7EXAMPLE",
        secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    )
    assert config.region == "us-east-1"
    assert config.log_group_prefix == "/aws/redis"
    assert config.enabled is True


def test_github_config():
    """Test GitHub configuration."""
    config = GitHubConfig(
        token="ghp_1234567890",
        organization="redis-applied-ai",
    )
    assert config.token == "ghp_1234567890"
    assert config.organization == "redis-applied-ai"
    assert config.api_url == "https://api.github.com"


def test_github_config_enterprise():
    """Test GitHub Enterprise configuration."""
    config = GitHubConfig(
        token="ghp_1234567890",
        api_url="https://github.company.com/api/v3",
    )
    assert config.api_url == "https://github.company.com/api/v3"


def test_redis_direct_metrics_config():
    """Test Redis direct metrics configuration."""
    config = RedisDirectMetricsConfig()
    assert config.connection_timeout == 5
    assert config.socket_timeout == 10
    assert config.enabled is True


def test_redis_direct_diagnostics_config():
    """Test Redis direct diagnostics configuration."""
    config = RedisDirectDiagnosticsConfig()
    assert config.connection_timeout == 5
    assert config.socket_timeout == 10
    assert config.max_slowlog_entries == 128


def test_redis_enterprise_config_docker():
    """Test Redis Enterprise configuration with Docker."""
    config = RedisEnterpriseConfig(container_name="redis-enterprise-node1")
    assert config.container_name == "redis-enterprise-node1"
    assert config.api_url is None


def test_redis_enterprise_config_api():
    """Test Redis Enterprise configuration with REST API."""
    config = RedisEnterpriseConfig(
        api_url="https://redis-enterprise:9443",
        api_username="admin",
        api_password="password",
    )
    assert config.api_url == "https://redis-enterprise:9443"
    assert config.api_username == "admin"
    assert config.api_password == "password"


def test_deployment_providers_config_empty():
    """Test empty deployment providers configuration."""
    config = DeploymentProvidersConfig()
    assert config.prometheus is None
    assert config.cloudwatch_logs is None
    assert config.github is None
    assert config.get_enabled_providers() == []


def test_deployment_providers_config_with_providers():
    """Test deployment providers configuration with multiple providers."""
    config = DeploymentProvidersConfig(
        prometheus=PrometheusConfig(prometheus_url="http://prometheus:9090"),
        redis_direct_metrics=RedisDirectMetricsConfig(),
        github=GitHubConfig(token="ghp_1234567890"),
    )

    assert config.prometheus is not None
    assert config.redis_direct_metrics is not None
    assert config.github is not None

    enabled = config.get_enabled_providers()
    assert "prometheus" in enabled
    assert "redis_direct_metrics" in enabled
    assert "github" in enabled


def test_deployment_providers_config_from_env(monkeypatch):
    """Test creating deployment providers config from environment variables."""
    # Set environment variables
    monkeypatch.setenv("PROMETHEUS_URL", "http://prometheus:9090")
    monkeypatch.setenv("PROMETHEUS_TIMEOUT", "60")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    monkeypatch.setenv("GITHUB_ORGANIZATION", "test-org")
    monkeypatch.setenv("CLOUDWATCH_REGION", "us-west-2")

    config = DeploymentProvidersConfig.from_env()

    # Check Prometheus
    assert config.prometheus is not None
    assert config.prometheus.prometheus_url == "http://prometheus:9090"
    assert config.prometheus.timeout == 60

    # Check GitHub
    assert config.github is not None
    assert config.github.token == "ghp_test_token"
    assert config.github.organization == "test-org"

    # Check CloudWatch
    assert config.cloudwatch_logs is not None
    assert config.cloudwatch_logs.region == "us-west-2"

    # Check Redis Direct (always enabled by default)
    assert config.redis_direct_metrics is not None
    assert config.redis_direct_diagnostics is not None


def test_deployment_providers_config_from_env_minimal(monkeypatch):
    """Test creating deployment providers config with minimal environment variables."""
    # Clear all provider-related env vars
    for key in list(os.environ.keys()):
        if any(
            prefix in key
            for prefix in [
                "PROMETHEUS",
                "GITHUB",
                "CLOUDWATCH",
                "REDIS_ENTERPRISE",
                "XRAY",
            ]
        ):
            monkeypatch.delenv(key, raising=False)

    config = DeploymentProvidersConfig.from_env()

    # Only Redis Direct providers should be enabled by default
    assert config.prometheus is None
    assert config.github is None
    assert config.cloudwatch_logs is None
    assert config.redis_direct_metrics is not None
    assert config.redis_direct_diagnostics is not None


def test_provider_config_extra_fields_forbidden():
    """Test that extra fields are forbidden in provider configs."""
    with pytest.raises(ValidationError) as exc_info:
        PrometheusConfig(
            prometheus_url="http://prometheus:9090",
            invalid_field="should_fail",  # This should raise an error
        )

    assert "extra" in str(exc_info.value).lower() or "unexpected" in str(exc_info.value).lower()


def test_deployment_providers_config_disabled_provider():
    """Test deployment providers config with disabled provider."""
    config = DeploymentProvidersConfig(
        prometheus=PrometheusConfig(
            prometheus_url="http://prometheus:9090",
            enabled=False,  # Disabled
        ),
        redis_direct_metrics=RedisDirectMetricsConfig(),
    )

    enabled = config.get_enabled_providers()
    assert "prometheus" not in enabled  # Should not be in enabled list
    assert "redis_direct_metrics" in enabled
