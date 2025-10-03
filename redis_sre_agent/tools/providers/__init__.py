"""SRE tool providers package.

This package contains concrete implementations of the SRE tool protocols.
Users can import and use these providers or create their own implementations.
"""

from .cloudwatch_logs import CloudWatchLogsProvider, create_cloudwatch_logs_provider
from .comprehensive_provider import (
    AWSProvider,
    GitHubProvider,
    RedisProvider,
    create_aws_provider,
    create_github_provider,
    create_redis_provider,
)
from .github_repos import GitHubReposProvider, create_github_repos_provider
from .github_tickets import GitHubTicketsProvider, create_github_tickets_provider
from .prometheus_metrics import PrometheusMetricsProvider, create_prometheus_provider
from .redis_command_metrics import RedisCommandMetricsProvider, create_redis_command_provider
from .xray_traces import XRayTracesProvider, create_xray_traces_provider

__all__ = [
    # Individual providers
    "RedisCommandMetricsProvider",
    "PrometheusMetricsProvider",
    "CloudWatchLogsProvider",
    "GitHubTicketsProvider",
    "GitHubReposProvider",
    "XRayTracesProvider",
    # Comprehensive providers
    "AWSProvider",
    "GitHubProvider",
    "RedisProvider",
    # Factory functions
    "create_redis_command_provider",
    "create_prometheus_provider",
    "create_cloudwatch_logs_provider",
    "create_github_tickets_provider",
    "create_github_repos_provider",
    "create_xray_traces_provider",
    "create_aws_provider",
    "create_github_provider",
    "create_redis_provider",
]
