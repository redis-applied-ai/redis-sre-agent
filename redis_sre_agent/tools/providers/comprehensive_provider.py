"""Comprehensive SRE tool provider implementations.

This module provides concrete implementations of the SREToolProvider protocol
that combine multiple capabilities (metrics, logs, tickets, repos, traces).
"""

import logging
from typing import Any, Dict, List, Optional

from ..protocols import (
    LogsProvider,
    MetricsProvider,
    ReposProvider,
    SREToolProvider,
    TicketsProvider,
    ToolCapability,
    TracesProvider,
)
from .cloudwatch_logs import CloudWatchLogsProvider
from .github_repos import GitHubReposProvider
from .github_tickets import GitHubTicketsProvider
from .prometheus_metrics import PrometheusMetricsProvider
from .redis_cli_metrics import RedisCLIMetricsProvider
from .xray_traces import XRayTracesProvider

logger = logging.getLogger(__name__)


class AWSProvider:
    """AWS-based SRE tool provider.
    
    Combines AWS services for comprehensive SRE capabilities:
    - CloudWatch Logs for log analysis
    - X-Ray for distributed tracing
    - Can be extended with CloudWatch Metrics
    """
    
    def __init__(self, region_name: str = "us-east-1", aws_access_key_id: Optional[str] = None, aws_secret_access_key: Optional[str] = None):
        self.region_name = region_name
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        
        self._logs_provider: Optional[CloudWatchLogsProvider] = None
        self._traces_provider: Optional[XRayTracesProvider] = None
    
    @property
    def provider_name(self) -> str:
        return f"AWS SRE Provider ({self.region_name})"
    
    @property
    def capabilities(self) -> List[ToolCapability]:
        return [ToolCapability.LOGS, ToolCapability.TRACES]
    
    async def get_metrics_provider(self) -> Optional[MetricsProvider]:
        """AWS provider doesn't include metrics in this implementation."""
        return None
    
    async def get_logs_provider(self) -> Optional[LogsProvider]:
        """Get CloudWatch Logs provider."""
        if self._logs_provider is None:
            self._logs_provider = CloudWatchLogsProvider(
                self.region_name,
                self.aws_access_key_id,
                self.aws_secret_access_key
            )
        return self._logs_provider
    
    async def get_tickets_provider(self) -> Optional[TicketsProvider]:
        """AWS provider doesn't include tickets in this implementation."""
        return None
    
    async def get_repos_provider(self) -> Optional[ReposProvider]:
        """AWS provider doesn't include repos in this implementation."""
        return None
    
    async def get_traces_provider(self) -> Optional[TracesProvider]:
        """Get X-Ray traces provider."""
        if self._traces_provider is None:
            self._traces_provider = XRayTracesProvider(
                self.region_name,
                self.aws_access_key_id,
                self.aws_secret_access_key
            )
        return self._traces_provider
    
    async def initialize(self, config: Dict[str, Any]) -> None:
        """Initialize AWS provider with configuration."""
        if "region_name" in config:
            self.region_name = config["region_name"]
        if "aws_access_key_id" in config:
            self.aws_access_key_id = config["aws_access_key_id"]
        if "aws_secret_access_key" in config:
            self.aws_secret_access_key = config["aws_secret_access_key"]
        
        logger.info(f"AWS provider initialized for region {self.region_name}")
    
    async def health_check(self) -> Dict[str, Any]:
        """Overall health check for AWS provider."""
        health_results = {
            "provider": self.provider_name,
            "capabilities": [cap.value for cap in self.capabilities],
            "services": {}
        }
        
        # Check logs provider
        logs_provider = await self.get_logs_provider()
        if logs_provider:
            health_results["services"]["logs"] = await logs_provider.health_check()
        
        # Check traces provider
        traces_provider = await self.get_traces_provider()
        if traces_provider:
            health_results["services"]["traces"] = await traces_provider.health_check()
        
        # Determine overall status
        all_healthy = all(
            service.get("status") == "healthy"
            for service in health_results["services"].values()
        )
        
        health_results["status"] = "healthy" if all_healthy else "unhealthy"
        return health_results


class GitHubProvider:
    """GitHub-based SRE tool provider.
    
    Combines GitHub services for development-focused SRE capabilities:
    - GitHub Issues for ticket management
    - GitHub Repositories for code analysis
    """
    
    def __init__(self, token: str, organization: Optional[str] = None, default_repo: Optional[str] = None):
        self.token = token
        self.organization = organization
        self.default_repo = default_repo
        
        self._tickets_provider: Optional[GitHubTicketsProvider] = None
        self._repos_provider: Optional[GitHubReposProvider] = None
    
    @property
    def provider_name(self) -> str:
        org_part = f" ({self.organization})" if self.organization else ""
        return f"GitHub SRE Provider{org_part}"
    
    @property
    def capabilities(self) -> List[ToolCapability]:
        return [ToolCapability.TICKETS, ToolCapability.REPOS]
    
    async def get_metrics_provider(self) -> Optional[MetricsProvider]:
        """GitHub provider doesn't include metrics."""
        return None
    
    async def get_logs_provider(self) -> Optional[LogsProvider]:
        """GitHub provider doesn't include logs."""
        return None
    
    async def get_tickets_provider(self) -> Optional[TicketsProvider]:
        """Get GitHub Issues provider."""
        if self._tickets_provider is None and self.default_repo:
            # Parse owner/repo from default_repo
            if "/" in self.default_repo:
                owner, repo = self.default_repo.split("/", 1)
                self._tickets_provider = GitHubTicketsProvider(self.token, owner, repo)
        return self._tickets_provider
    
    async def get_repos_provider(self) -> Optional[ReposProvider]:
        """Get GitHub Repositories provider."""
        if self._repos_provider is None:
            self._repos_provider = GitHubReposProvider(self.token, self.organization)
        return self._repos_provider
    
    async def get_traces_provider(self) -> Optional[TracesProvider]:
        """GitHub provider doesn't include traces."""
        return None
    
    async def initialize(self, config: Dict[str, Any]) -> None:
        """Initialize GitHub provider with configuration."""
        if "token" in config:
            self.token = config["token"]
        if "organization" in config:
            self.organization = config["organization"]
        if "default_repo" in config:
            self.default_repo = config["default_repo"]
        
        logger.info(f"GitHub provider initialized for organization {self.organization}")
    
    async def health_check(self) -> Dict[str, Any]:
        """Overall health check for GitHub provider."""
        health_results = {
            "provider": self.provider_name,
            "capabilities": [cap.value for cap in self.capabilities],
            "services": {}
        }
        
        # Check tickets provider
        tickets_provider = await self.get_tickets_provider()
        if tickets_provider:
            health_results["services"]["tickets"] = await tickets_provider.health_check()
        
        # Check repos provider
        repos_provider = await self.get_repos_provider()
        if repos_provider:
            health_results["services"]["repos"] = await repos_provider.health_check()
        
        # Determine overall status
        all_healthy = all(
            service.get("status") == "healthy"
            for service in health_results["services"].values()
        )
        
        health_results["status"] = "healthy" if all_healthy else "unhealthy"
        return health_results


class RedisProvider:
    """Redis-focused SRE tool provider.
    
    Combines Redis-specific monitoring capabilities:
    - Redis CLI for direct instance metrics
    - Prometheus for time-series metrics (if available)
    """
    
    def __init__(self, redis_url: str, prometheus_url: Optional[str] = None):
        self.redis_url = redis_url
        self.prometheus_url = prometheus_url
        
        self._redis_metrics_provider: Optional[RedisCLIMetricsProvider] = None
        self._prometheus_metrics_provider: Optional[PrometheusMetricsProvider] = None
    
    @property
    def provider_name(self) -> str:
        return f"Redis SRE Provider ({self.redis_url})"
    
    @property
    def capabilities(self) -> List[ToolCapability]:
        return [ToolCapability.METRICS]
    
    async def get_metrics_provider(self) -> Optional[MetricsProvider]:
        """Get Redis metrics provider (prefers Prometheus if available)."""
        if self.prometheus_url and self._prometheus_metrics_provider is None:
            self._prometheus_metrics_provider = PrometheusMetricsProvider(self.prometheus_url)
            return self._prometheus_metrics_provider
        
        if self._redis_metrics_provider is None:
            self._redis_metrics_provider = RedisCLIMetricsProvider(self.redis_url)
        return self._redis_metrics_provider
    
    async def get_logs_provider(self) -> Optional[LogsProvider]:
        """Redis provider doesn't include logs."""
        return None
    
    async def get_tickets_provider(self) -> Optional[TicketsProvider]:
        """Redis provider doesn't include tickets."""
        return None
    
    async def get_repos_provider(self) -> Optional[ReposProvider]:
        """Redis provider doesn't include repos."""
        return None
    
    async def get_traces_provider(self) -> Optional[TracesProvider]:
        """Redis provider doesn't include traces."""
        return None
    
    async def initialize(self, config: Dict[str, Any]) -> None:
        """Initialize Redis provider with configuration."""
        if "redis_url" in config:
            self.redis_url = config["redis_url"]
        if "prometheus_url" in config:
            self.prometheus_url = config["prometheus_url"]
        
        logger.info(f"Redis provider initialized for {self.redis_url}")
    
    async def health_check(self) -> Dict[str, Any]:
        """Overall health check for Redis provider."""
        health_results = {
            "provider": self.provider_name,
            "capabilities": [cap.value for cap in self.capabilities],
            "services": {}
        }
        
        # Check metrics provider
        metrics_provider = await self.get_metrics_provider()
        if metrics_provider:
            health_results["services"]["metrics"] = await metrics_provider.health_check()
        
        # Determine overall status
        all_healthy = all(
            service.get("status") == "healthy"
            for service in health_results["services"].values()
        )
        
        health_results["status"] = "healthy" if all_healthy else "unhealthy"
        return health_results


# Helper functions to create provider instances
def create_aws_provider(
    region_name: str = "us-east-1",
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None
) -> AWSProvider:
    """Create an AWS SRE provider instance."""
    return AWSProvider(region_name, aws_access_key_id, aws_secret_access_key)


def create_github_provider(
    token: str,
    organization: Optional[str] = None,
    default_repo: Optional[str] = None
) -> GitHubProvider:
    """Create a GitHub SRE provider instance."""
    return GitHubProvider(token, organization, default_repo)


def create_redis_provider(
    redis_url: str,
    prometheus_url: Optional[str] = None
) -> RedisProvider:
    """Create a Redis SRE provider instance."""
    return RedisProvider(redis_url, prometheus_url)
