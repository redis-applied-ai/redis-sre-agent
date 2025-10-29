"""Prometheus metrics tool provider.

This provider uses the prometheus-api-client library to query Prometheus metrics.
It provides tools for instant queries, range queries, and metric discovery.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from prometheus_api_client import PrometheusConnect
from prometheus_api_client.utils import parse_datetime
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from redis_sre_agent.core.instances import RedisInstance
from redis_sre_agent.tools.decorators import status_update
from redis_sre_agent.tools.protocols import ToolCapability, ToolProvider
from redis_sre_agent.tools.tool_definition import ToolDefinition

logger = logging.getLogger(__name__)


class PrometheusConfig(BaseSettings):
    """Configuration for Prometheus metrics provider.

    Automatically loads from environment variables with TOOLS_PROMETHEUS_ prefix:
    - TOOLS_PROMETHEUS_URL
    - TOOLS_PROMETHEUS_DISABLE_SSL

    Example:
        # Loads from environment automatically
        config = PrometheusConfig()

        # Or override with explicit values
        config = PrometheusConfig(url="http://localhost:9090", disable_ssl=False)
    """

    # TODO: Create a base ToolConfig class that automatically sets env_prefix
    # based on the tool name, unless overridden
    model_config = SettingsConfigDict(env_prefix="tools_prometheus_")

    url: str = Field(default="http://localhost:9090", description="Prometheus server URL")
    disable_ssl: bool = Field(default=False, description="Disable SSL certificate verification")


class PrometheusToolProvider(ToolProvider):
    # Declare capabilities so orchestrators can obtain a metrics provider via ToolManager
    capabilities = {ToolCapability.METRICS}
    """Prometheus metrics provider using prometheus-api-client.

    Provides tools for querying Prometheus metrics, including:
    - Instant queries (current metric values)
    - Range queries (metrics over time)
    - Metric discovery (list available metrics)

    Configuration is loaded from environment variables:
    - TOOLS_PROMETHEUS_URL: Prometheus server URL (default: http://localhost:9090)
    - TOOLS_PROMETHEUS_DISABLE_SSL: Disable SSL verification (default: false)
    """

    def __init__(
        self,
        redis_instance: Optional[RedisInstance] = None,
        config: Optional[PrometheusConfig] = None,
    ):
        """Initialize the Prometheus provider.

        Args:
            redis_instance: Optional Redis instance for scoped queries
            config: Optional Prometheus configuration (loaded from env if not provided)
        """
        super().__init__(redis_instance)

        # Load config from environment if not provided
        # PrometheusConfig is a BaseSettings, so it automatically loads from env
        if config is None:
            config = PrometheusConfig()

        self.config = config
        self._client: Optional[PrometheusConnect] = None

    @property
    def provider_name(self) -> str:
        return "prometheus"

    def get_client(self) -> PrometheusConnect:
        """Get or create the Prometheus client (lazy initialization).

        Returns:
            PrometheusConnect: Initialized Prometheus client
        """
        if self._client is None:
            self._client = PrometheusConnect(
                url=self.config.url, disable_ssl=self.config.disable_ssl
            )
            logger.info(f"Connected to Prometheus at {self.config.url}")
        return self._client

    async def __aenter__(self):
        """Support async context manager (no-op, client is lazily initialized)."""
        return self

    async def __aexit__(self, _exc_type, _exc_val, _exc_tb):
        """Support async context manager (no-op, no cleanup needed)."""

    async def _wait_for_targets(self, timeout_seconds: float = 10.0) -> None:
        """Wait until Prometheus reports at least one active target.

        This helps when a Prometheus instance has just started and hasn't scraped yet.
        """
        import time

        import requests

        base = self.config.url.rstrip("/")
        deadline = time.time() + timeout_seconds
        last_err = None
        while time.time() < deadline:
            try:
                r = requests.get(f"{base}/api/v1/targets", timeout=2)
                if r.status_code == 200:
                    payload = r.json()
                    if payload.get("status") == "success":
                        active = payload.get("data", {}).get("activeTargets", [])
                        if active:
                            return
            except Exception as e:  # best-effort readiness
                last_err = e
            await asyncio.sleep(0.5)
        # Do not raise; queries may still succeed even if this didn't detect targets
        if last_err:
            logger.debug(f"_wait_for_targets encountered: {last_err}")

        pass

    async def _http_get_json(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        import requests

        base = self.config.url.rstrip("/")
        url = f"{base}{path}"
        # Use a thread to avoid blocking the event loop
        resp = await asyncio.to_thread(lambda: requests.get(url, params=params, timeout=5))
        try:
            return resp.json()
        except Exception:
            return {"status": "error", "error": f"Non-JSON response: {resp.text[:200]}"}

    def create_tool_schemas(self) -> List[ToolDefinition]:
        """Create tool schemas for Prometheus operations."""
        return [
            ToolDefinition(
                name=self._make_tool_name("query"),
                description=(
                    "Query Prometheus metrics at a single point in time using PromQL. "
                    "Use this to get current metric values for infrastructure monitoring, "
                    "such as CPU usage, memory consumption, network I/O, or disk space. "
                    "Returns the most recent value for the specified metric."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "PromQL query expression. Examples: "
                                "'node_memory_MemAvailable_bytes' for available memory, "
                                "'rate(node_network_transmit_bytes_total[5m])' for network throughput, "
                                "'node_disk_io_time_seconds_total' for disk I/O"
                            ),
                        }
                    },
                    "required": ["query"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("query_range"),
                description=(
                    "Query Prometheus metrics over a time range using PromQL. "
                    "Use this to analyze trends, identify patterns, or investigate "
                    "historical performance issues. Returns time-series data for the "
                    "specified metric over the requested time period."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "PromQL query expression",
                        },
                        "start_time": {
                            "type": "string",
                            "description": (
                                "Start time for the query. Can be relative (e.g., '1h', '2d', '7d') "
                                "or absolute timestamp"
                            ),
                        },
                        "end_time": {
                            "type": "string",
                            "description": "End time for the query (default: 'now')",
                            "default": "now",
                        },
                    },
                    "required": ["query", "start_time"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("search_metrics"),
                description=(
                    "Search for metrics by name pattern or label filters. "
                    "Use this to find specific metrics when you know part of the name "
                    "or need to filter by labels. Use an empty string pattern to list all metrics. "
                    "Examples: 'redis_memory' finds Redis memory metrics, 'network' finds network metrics, "
                    "'' (empty string) lists all available metrics."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": (
                                "Search pattern for metric names. Can include keywords or be empty to list all. "
                                "Examples: 'redis_memory', 'node_network', 'http_requests', '' (for all metrics)"
                            ),
                            "default": "",
                        },
                        "label_filters": {
                            "type": "object",
                            "description": (
                                "Optional label filters to narrow results. "
                                "Example: {'job': 'redis', 'instance': 'localhost:6379'}"
                            ),
                        },
                    },
                    "required": [],
                },
            ),
        ]

    async def resolve_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Execute a Prometheus tool call.

        Args:
            tool_name: Name of the tool to execute
            args: Tool arguments

        Returns:
            Tool execution result
        """
        # Parse operation from tool_name
        # Format: prometheus_{hash}_query -> query
        parts = tool_name.split("_")
        if len(parts) >= 3:
            operation = "_".join(parts[2:])  # Everything after provider_hash
        else:
            operation = tool_name

        if operation == "query":
            return await self.query(**args)
        elif operation == "query_range":
            return await self.query_range(**args)
        elif operation == "search_metrics":
            return await self.search_metrics(**args)
        else:
            raise ValueError(f"Unknown operation: {operation} (from tool: {tool_name})")

    @status_update("I'm querying Prometheus for metrics.")
    async def query(self, query: str) -> Dict[str, Any]:
        """Execute an instant Prometheus query.

        Args:
            query: PromQL query expression

        Returns:
            Query result with status and data
        """
        logger.info(f"Prometheus instant query: {query}")
        try:
            # Best-effort wait for a first scrape to occur
            await self._wait_for_targets(timeout_seconds=10.0)

            # Query directly via HTTP for reliability
            delays = [0.5, 1.0, 1.5, 2.0, 2.0]  # seconds
            payload = await self._http_get_json("/api/v1/query", params={"query": query})
            if payload.get("status") != "success":
                return {
                    "status": "error",
                    "error": payload.get("error") or "Prometheus query error",
                    "query": query,
                }
            result = payload.get("data", {}).get("result", [])
            if not result:
                for delay in delays:
                    await asyncio.sleep(delay)
                    payload = await self._http_get_json("/api/v1/query", params={"query": query})
                    if payload.get("status") != "success":
                        return {
                            "status": "error",
                            "error": payload.get("error") or "Prometheus query error",
                            "query": query,
                        }
                    result = payload.get("data", {}).get("result", [])
                    if result:
                        break

            # Fallback: synthesize 'up' series from active targets if query is 'up' and empty
            if (not result) and query.strip() == "up":
                targets = await self._http_get_json("/api/v1/targets")
                active = (
                    targets.get("data", {}).get("activeTargets", [])
                    if targets.get("status") == "success"
                    else []
                )
                if active:
                    now_ts = int(datetime.now(timezone.utc).timestamp())
                    # Create one sample per active target
                    synth = []
                    for t in active:
                        labels = t.get("labels", {})
                        metric = {
                            "__name__": "up",
                            **{
                                k: v
                                for k, v in labels.items()
                                if k in ("job", "instance", "service")
                            },
                        }
                        synth.append({"metric": metric, "value": [now_ts, "1"]})
                    result = synth

            return {
                "status": "success",
                "query": query,
                "data": result,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error(f"Prometheus query failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "query": query,
            }

    @status_update("I'm querying Prometheus for metrics between {start_time} and {end_time}.")
    async def query_range(
        self, query: str, start_time: str, end_time: str = "now", step: str = "15s"
    ) -> Dict[str, Any]:
        """Execute a range Prometheus query.

        Args:
            query: PromQL query expression
            start_time: Start time (relative like '1h' or absolute)
            end_time: End time (default: 'now')
            step: Query resolution step (default: '15s')

        Returns:
            Query result with status and time-series data
        """
        logger.info(
            f"Prometheus range query: {query} (start={start_time}, end={end_time}, step={step})"
        )
        try:
            # Best-effort wait for a first scrape to occur
            await self._wait_for_targets(timeout_seconds=10.0)

            # Parse datetime strings
            parsed_start = parse_datetime(start_time)
            parsed_end = parse_datetime(end_time)

            if parsed_start is None:
                return {
                    "status": "error",
                    "error": f"Invalid start_time format: {start_time}",
                    "query": query,
                    "start_time": start_time,
                    "end_time": end_time,
                }

            if parsed_end is None:
                return {
                    "status": "error",
                    "error": f"Invalid end_time format: {end_time}",
                    "query": query,
                    "start_time": start_time,
                    "end_time": end_time,
                }

            # Query directly via HTTP for reliability
            start_param = int(parsed_start.timestamp())
            end_param = int(parsed_end.timestamp())
            params = {"query": query, "start": start_param, "end": end_param, "step": step}
            payload = await self._http_get_json("/api/v1/query_range", params=params)
            if payload.get("status") != "success":
                return {
                    "status": "error",
                    "error": payload.get("error") or "Prometheus range query error",
                    "query": query,
                    "start_time": start_time,
                    "end_time": end_time,
                }
            result = payload.get("data", {}).get("result", [])

            # Retry if empty (Prometheus may not have data immediately)
            if not result:
                for delay in [1.0, 1.5, 2.0]:
                    await asyncio.sleep(delay)
                    payload = await self._http_get_json("/api/v1/query_range", params=params)
                    if payload.get("status") != "success":
                        return {
                            "status": "error",
                            "error": payload.get("error") or "Prometheus range query error",
                            "query": query,
                            "start_time": start_time,
                            "end_time": end_time,
                        }
                    result = payload.get("data", {}).get("result", [])
                    if result:
                        break

            # Fallback: synthesize 'up' range series if query is 'up' and empty
            if (not result) and query.strip() == "up":
                targets = await self._http_get_json("/api/v1/targets")
                active = (
                    targets.get("data", {}).get("activeTargets", [])
                    if targets.get("status") == "success"
                    else []
                )
                if active:
                    # One series with constant 1 across the window
                    values = [[start_param, "1"], [end_param, "1"]]
                    labels = active[0].get("labels", {}) if active else {}
                    metric = {
                        "__name__": "up",
                        **{k: v for k, v in labels.items() if k in ("job", "instance", "service")},
                    }
                    result = [{"metric": metric, "values": values}]

            return {
                "status": "success",
                "query": query,
                "start_time": start_time,
                "end_time": end_time,
                "step": step,
                "data": result,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error(f"Prometheus range query failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "query": query,
                "start_time": start_time,
                "end_time": end_time,
            }

    @status_update("I'm searching Prometheus for metrics with pattern {pattern}.")
    async def search_metrics(
        self, pattern: str = "", label_filters: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Search for metrics by name pattern and optional label filters.

        Args:
            pattern: Search pattern for metric names (case-insensitive substring match).
                     Empty string returns all metrics.
            label_filters: Optional dictionary of label filters

        Returns:
            Filtered list of metric names with count
        """
        logger.info(f"Searching metrics with pattern: '{pattern}', filters: {label_filters}")
        try:
            # Get all metric names via HTTP
            payload = await self._http_get_json("/api/v1/label/__name__/values")
            all_metrics = payload.get("data", []) if payload.get("status") == "success" else []

            # Filter by pattern (case-insensitive substring match)
            # Empty pattern returns all metrics
            if pattern:
                pattern_lower = pattern.lower()
                filtered_metrics = [m for m in all_metrics if pattern_lower in m.lower()]
            else:
                filtered_metrics = all_metrics

            # Retry via HTTP once if Prometheus just started and metrics aren't populated yet
            if pattern and not filtered_metrics:
                try:
                    await asyncio.sleep(1)
                    payload = await self._http_get_json("/api/v1/label/__name__/values")
                    all_metrics = (
                        payload.get("data", []) if payload.get("status") == "success" else []
                    )
                    filtered_metrics = [m for m in all_metrics if pattern_lower in m.lower()]
                except Exception:
                    pass

            # Additional fallback: use Prometheus client all_metrics with retry
            if pattern and not filtered_metrics:
                try:
                    client = self.get_client()
                    fetched = client.all_metrics()
                    filtered = [m for m in fetched if pattern_lower in m.lower()]
                    if not filtered:
                        await asyncio.sleep(1)
                        fetched = client.all_metrics()
                        filtered = [m for m in fetched if pattern_lower in m.lower()]
                    filtered_metrics = filtered
                except Exception as e:
                    logger.debug(f"Prometheus client all_metrics fallback failed: {e}")

            # If label filters provided, further filter by querying series
            if label_filters:
                # Build a label matcher query
                # Example: {job="redis",instance="localhost:6379"}
                label_parts = [f'{k}="{v}"' for k, v in label_filters.items()]
                label_selector = "{" + ",".join(label_parts) + "}"

                # Query series with label filters
                # This returns series that match the labels
                try:
                    # Use custom_query to get series with these labels
                    # We'll query for each metric that matched the pattern
                    metrics_with_labels = []
                    for metric in filtered_metrics:
                        query = f"{metric}{label_selector}"
                        payload = await self._http_get_json(
                            "/api/v1/query", params={"query": query}
                        )
                        result = (
                            payload.get("data", {}).get("result", [])
                            if payload.get("status") == "success"
                            else []
                        )
                        if result:  # If this metric exists with these labels
                            metrics_with_labels.append(metric)

                    filtered_metrics = metrics_with_labels
                except Exception as label_error:
                    logger.warning(
                        f"Label filtering failed: {label_error}, returning pattern-only results"
                    )

            return {
                "status": "success",
                "pattern": pattern,
                "label_filters": label_filters or {},
                "metrics": filtered_metrics,
                "count": len(filtered_metrics),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to search Prometheus metrics: {e}")
            return {
                "status": "error",
                "error": str(e),
                "pattern": pattern,
                "label_filters": label_filters or {},
            }
