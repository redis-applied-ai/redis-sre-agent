"""Redis Enterprise provider implementation.

This provider integrates Redis Enterprise cluster management capabilities
into the SRE tool provider system. It supports both Docker-based and
REST API-based access to Redis Enterprise clusters.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..protocols import MetricDefinition, MetricValue, ToolCapability

logger = logging.getLogger(__name__)


class RedisEnterpriseProvider:
    """Redis Enterprise cluster management provider.

    This provider gives the agent access to Redis Enterprise cluster operations
    including node status, database management, and cluster health checks.

    Supports two access methods:
    1. Docker exec (for local development/testing)
    2. REST API (for production deployments)
    """

    def __init__(
        self,
        container_name: Optional[str] = None,
        api_url: Optional[str] = None,
        api_username: Optional[str] = None,
        api_password: Optional[str] = None,
    ):
        """Initialize Redis Enterprise provider.

        Args:
            container_name: Docker container name for rladmin access
            api_url: Redis Enterprise REST API URL (e.g., https://localhost:9443)
            api_username: API username (e.g., admin@redis.com)
            api_password: API password
        """
        self.container_name = container_name or "redis-enterprise-node1"
        self.api_url = api_url
        self.api_username = api_username
        self.api_password = api_password

        # Determine access method
        self.use_docker = container_name is not None
        self.use_api = api_url is not None

        if not self.use_docker and not self.use_api:
            logger.warning(
                "No access method configured for Redis Enterprise provider. "
                "Provide either container_name or api_url."
            )

    @property
    def provider_name(self) -> str:
        if self.use_docker:
            return f"Redis Enterprise (Docker: {self.container_name})"
        elif self.use_api:
            return f"Redis Enterprise (API: {self.api_url})"
        else:
            return "Redis Enterprise (unconfigured)"

    @property
    def capabilities(self) -> List[ToolCapability]:
        # Redis Enterprise provider provides metrics through cluster status
        return [ToolCapability.METRICS]

    async def get_metrics_provider(self):
        """Get metrics provider for Redis Enterprise.

        Returns self since this provider implements metrics capabilities.
        """
        return self

    async def get_logs_provider(self):
        """Redis Enterprise provider doesn't provide logs."""
        return None

    async def get_tickets_provider(self):
        """Redis Enterprise provider doesn't provide tickets."""
        return None

    async def get_repos_provider(self):
        """Redis Enterprise provider doesn't provide repos."""
        return None

    async def get_traces_provider(self):
        """Redis Enterprise provider doesn't provide traces."""
        return None

    # Metrics Provider Protocol Implementation

    @property
    def supports_time_queries(self) -> bool:
        """Redis Enterprise provider only supports current values via rladmin."""
        return False

    async def list_metrics(self) -> List[MetricDefinition]:
        """List available Redis Enterprise metrics."""
        return [
            MetricDefinition(
                name="cluster_status",
                description="Overall cluster health status",
                unit="status",
                metric_type="gauge",
            ),
            MetricDefinition(
                name="node_count",
                description="Number of nodes in cluster",
                unit="count",
                metric_type="gauge",
            ),
            MetricDefinition(
                name="database_count",
                description="Number of databases in cluster",
                unit="count",
                metric_type="gauge",
            ),
            MetricDefinition(
                name="nodes_in_maintenance",
                description="Number of nodes in maintenance mode",
                unit="count",
                metric_type="gauge",
            ),
        ]

    async def get_current_value(
        self, metric_name: str, labels: Optional[Dict[str, str]] = None
    ) -> Optional[MetricValue]:
        """Get current value of a Redis Enterprise metric.

        Args:
            metric_name: Name of the metric (e.g., 'cluster_status', 'node_count')
            labels: Optional label filters (not used for Redis Enterprise)

        Returns:
            Current metric value or None if not found
        """
        try:
            # Get cluster status to extract metrics
            cluster_status = await self.get_cluster_status()

            if not cluster_status.get("success"):
                logger.error(f"Failed to get cluster status: {cluster_status.get('error')}")
                return None

            summary = cluster_status.get("summary", {})

            # Map metric names to values
            metric_map = {
                "cluster_status": 1 if summary.get("cluster_ok") else 0,
                "node_count": summary.get("node_count", 0),
                "database_count": summary.get("database_count", 0),
            }

            # Get node status for maintenance mode count
            if metric_name == "nodes_in_maintenance":
                node_status = await self.get_node_status()
                if node_status.get("success"):
                    node_summary = node_status.get("summary", {})
                    maintenance_count = len(node_summary.get("maintenance_mode_nodes", []))
                    return MetricValue(value=maintenance_count, timestamp=datetime.now())

            if metric_name in metric_map:
                return MetricValue(value=metric_map[metric_name], timestamp=datetime.now())

            return None

        except Exception as e:
            logger.error(f"Error getting Redis Enterprise metric {metric_name}: {e}")
            return None

    async def query_time_range(
        self,
        metric_name: str,
        time_range,
        labels: Optional[Dict[str, str]] = None,
        step: Optional[str] = None,
    ) -> List[MetricValue]:
        """Redis Enterprise provider doesn't support time-range queries."""
        raise NotImplementedError(
            "Redis Enterprise provider only supports current values via rladmin"
        )

    async def health_check(self) -> Dict[str, Any]:
        """Check if Redis Enterprise cluster is accessible."""
        try:
            result = await self.get_cluster_status()

            if result.get("success"):
                return {
                    "status": "healthy",
                    "provider": self.provider_name,
                    "cluster_ok": result.get("summary", {}).get("cluster_ok", False),
                }
            else:
                return {
                    "status": "unhealthy",
                    "provider": self.provider_name,
                    "error": result.get("error", "Unknown error"),
                }

        except Exception as e:
            return {"status": "unhealthy", "provider": self.provider_name, "error": str(e)}

    # Redis Enterprise Specific Methods

    async def get_cluster_status(self) -> Dict[str, Any]:
        """Get Redis Enterprise cluster status.

        Returns:
            Dict with cluster status information
        """
        if self.use_docker:
            return await self._get_cluster_status_docker()
        elif self.use_api:
            return await self._get_cluster_status_api()
        else:
            return {"success": False, "error": "No access method configured"}

    async def get_node_status(self, node_id: Optional[int] = None) -> Dict[str, Any]:
        """Get Redis Enterprise node status.

        Args:
            node_id: Optional specific node ID to query

        Returns:
            Dict with node status information
        """
        if self.use_docker:
            return await self._get_node_status_docker(node_id)
        elif self.use_api:
            return await self._get_node_status_api(node_id)
        else:
            return {"success": False, "error": "No access method configured"}

    async def get_database_status(self, database_name: Optional[str] = None) -> Dict[str, Any]:
        """Get Redis Enterprise database status.

        Args:
            database_name: Optional specific database name to query

        Returns:
            Dict with database status information
        """
        if self.use_docker:
            return await self._get_database_status_docker(database_name)
        elif self.use_api:
            return await self._get_database_status_api(database_name)
        else:
            return {"success": False, "error": "No access method configured"}

    # Docker-based implementation (using existing redis_enterprise_tools.py functions)

    async def _get_cluster_status_docker(self) -> Dict[str, Any]:
        """Get cluster status via Docker exec."""
        from ..redis_enterprise_tools import get_redis_enterprise_cluster_status

        return await get_redis_enterprise_cluster_status(self.container_name)

    async def _get_node_status_docker(self, node_id: Optional[int] = None) -> Dict[str, Any]:
        """Get node status via Docker exec."""
        from ..redis_enterprise_tools import get_redis_enterprise_node_status

        return await get_redis_enterprise_node_status(self.container_name, node_id)

    async def _get_database_status_docker(
        self, database_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get database status via Docker exec."""
        from ..redis_enterprise_tools import get_redis_enterprise_database_status

        return await get_redis_enterprise_database_status(self.container_name, database_name)

    # REST API-based implementation (placeholder for future)

    async def _get_cluster_status_api(self) -> Dict[str, Any]:
        """Get cluster status via REST API."""
        # TODO: Implement REST API access
        return {
            "success": False,
            "error": "REST API access not yet implemented. Use Docker access method.",
        }

    async def _get_node_status_api(self, node_id: Optional[int] = None) -> Dict[str, Any]:
        """Get node status via REST API."""
        # TODO: Implement REST API access
        return {
            "success": False,
            "error": "REST API access not yet implemented. Use Docker access method.",
        }

    async def _get_database_status_api(self, database_name: Optional[str] = None) -> Dict[str, Any]:
        """Get database status via REST API."""
        # TODO: Implement REST API access
        return {
            "success": False,
            "error": "REST API access not yet implemented. Use Docker access method.",
        }


# Factory function
def create_redis_enterprise_provider(
    container_name: Optional[str] = None,
    api_url: Optional[str] = None,
    api_username: Optional[str] = None,
    api_password: Optional[str] = None,
) -> RedisEnterpriseProvider:
    """Create a Redis Enterprise provider instance.

    Args:
        container_name: Docker container name for rladmin access
        api_url: Redis Enterprise REST API URL
        api_username: API username
        api_password: API password

    Returns:
        RedisEnterpriseProvider instance
    """
    return RedisEnterpriseProvider(container_name, api_url, api_username, api_password)
