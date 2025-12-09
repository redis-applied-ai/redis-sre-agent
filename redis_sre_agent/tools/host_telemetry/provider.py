"""Host Telemetry tool provider.

Minimal provider that orchestrates host-level metrics and logs using
existing metrics/logs/diagnostics providers via ToolManager capability lookup.

Defaults target Prometheus (metrics) and Loki (logs). Users supply hostnames
(or label values) explicitly or let us derive them from diagnostics if available.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from redis_sre_agent.tools.models import ToolCapability, ToolDefinition
from redis_sre_agent.tools.protocols import (
    DiagnosticsProviderProtocol,
    LogsProviderProtocol,
    MetricsProviderProtocol,
    ToolProvider,
)

logger = logging.getLogger(__name__)


# ------------------------------- Config models -------------------------------


class HostTelemetryPromConfig(BaseModel):
    metric_aliases: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of logical metric keys to PromQL templates containing {host}",
    )
    default_step: str = Field(default="30s")


class HostTelemetryLokiConfig(BaseModel):
    stream_selector_template: str = Field(
        default='{job="syslog", host="{host}"}',
        description="Loki stream selector template containing {host}",
    )
    direction: str = Field(default="backward")
    limit: int = Field(default=1000)


class HostTelemetryConfig(BaseModel):
    hosts: Optional[List[str]] = None
    metrics: HostTelemetryPromConfig = Field(default_factory=HostTelemetryPromConfig)
    logs: HostTelemetryLokiConfig = Field(default_factory=HostTelemetryLokiConfig)


# ------------------------------- Provider class ------------------------------


class HostTelemetryToolProvider(ToolProvider):
    """Backend-agnostic host telemetry tools built on provider Protocols."""

    instance_config_model = HostTelemetryConfig
    extension_namespace = "host_telemetry"

    @property
    def provider_name(self) -> str:
        return "host_telemetry"

    @property
    def _metrics_providers(self) -> List[MetricsProviderProtocol]:
        mgr = self._manager
        if not mgr:
            return []
        return mgr.get_providers_for_capability(ToolCapability.METRICS)  # type: ignore[return-value]

    @property
    def _logs_providers(self) -> List[LogsProviderProtocol]:
        mgr = self._manager
        if not mgr:
            return []
        return mgr.get_providers_for_capability(ToolCapability.LOGS)  # type: ignore[return-value]

    @property
    def _diag_providers(self) -> List[DiagnosticsProviderProtocol]:
        mgr = self._manager
        if not mgr:
            return []
        return mgr.get_providers_for_capability(ToolCapability.DIAGNOSTICS)  # type: ignore[return-value]

    def create_tool_schemas(self) -> List[ToolDefinition]:
        """Create tool schemas for host telemetry operations.

        These tools orchestrate calls to metrics/logs/diagnostics providers and
        are treated as DIAGNOSTICS capability tools by the manager.
        """

        return [
            ToolDefinition(
                name=self._make_tool_name("list_hosts"),
                description=(
                    "List hosts to use with metrics/logs providers. Uses instance config hosts when provided, "
                    "otherwise attempts discovery from diagnostics via the system_hosts protocol."
                ),
                capability=ToolCapability.DIAGNOSTICS,
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            ToolDefinition(
                name=self._make_tool_name("get_host_metrics"),
                description=(
                    "Query host metrics for one or more hosts using configured metric aliases. "
                    "Each alias is a PromQL template that includes {host}. Queries all available metrics providers."
                ),
                capability=ToolCapability.DIAGNOSTICS,
                parameters={
                    "type": "object",
                    "properties": {
                        "hosts": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Host identifiers expected by metrics system (e.g., instance label value)",
                        },
                        "metric_keys": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Keys defined in host_telemetry.metrics.metric_aliases",
                        },
                        "start_time": {
                            "type": "string",
                            "description": "Start (e.g., 1h, 2025-01-01T00:00:00Z)",
                        },
                        "end_time": {
                            "type": "string",
                            "description": "End (default: now)",
                            "default": "now",
                        },
                        "step": {
                            "type": "string",
                            "description": "Resolution step (default from config)",
                        },
                    },
                    "required": ["hosts", "metric_keys", "start_time"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("get_host_logs"),
                description=(
                    "Query host logs for one or more hosts. Builds provider-specific selectors from config and "
                    "combines keywords into a single safe regex. Queries all available log providers."
                ),
                capability=ToolCapability.DIAGNOSTICS,
                parameters={
                    "type": "object",
                    "properties": {
                        "hosts": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Host identifiers expected by logs system",
                        },
                        "start": {"type": "string", "description": "Start time"},
                        "end": {"type": "string", "description": "End time"},
                        "keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Keywords to OR-combine into a regex",
                        },
                        "direction": {"type": "string", "description": "forward|backward"},
                        "limit": {"type": "integer", "description": "Max entries per provider"},
                    },
                    "required": ["hosts", "start", "end"],
                },
            ),
        ]

    # --------------------------------- Helpers ---------------------------------

    async def _discover_hosts_via_diagnostics(self) -> List[str]:
        hosts: set[str] = set()
        for diag in self._diag_providers:
            # Only use providers that implement the full DiagnosticsProviderProtocol
            if not isinstance(diag, DiagnosticsProviderProtocol):
                continue
            try:
                items = await diag.system_hosts()
            except Exception:
                continue
            if not items:
                continue
            for item in items:
                try:
                    if isinstance(item, dict):
                        h = item.get("host")
                    else:
                        h = item.host
                    if isinstance(h, str) and h:
                        hosts.add(h)
                except Exception:
                    continue
        return list(hosts)

    def _build_loki_query(self, host: str, keywords: Optional[List[str]]) -> str:
        cfg: HostTelemetryConfig = self.instance_config or HostTelemetryConfig()
        tmpl = cfg.logs.stream_selector_template or ""
        selector = tmpl.replace("{host}", host)
        if keywords:
            # Combine into single OR regex and escape quotes minimally
            safe = [k.replace('"', "'") for k in keywords if isinstance(k, str) and k]
            if safe:
                regex = "|".join([f"{s}" for s in safe])
                return f'{selector} |~ "({regex})"'
        return selector

    # --------------------------------- Tools -----------------------------------

    async def list_hosts(self) -> Dict[str, Any]:
        cfg: HostTelemetryConfig = self.instance_config or HostTelemetryConfig()
        hosts: List[str] = []
        source_notes: List[str] = []
        host_details: List[Dict[str, Any]] = []

        # Config-provided hosts
        if cfg.hosts:
            for h in cfg.hosts:
                if isinstance(h, str) and h:
                    hosts.append(h)
                    # Record minimal details with source label for transparency
                    host_details.append(
                        {"host": h, "port": None, "role": None, "labels": {"source": "config"}}
                    )
            source_notes.append("config")

        # Diagnostics discovery via explicit system_hosts() API
        discovered_any = False
        for diag in self._diag_providers:
            # Only use providers that implement the full DiagnosticsProviderProtocol
            if not isinstance(diag, DiagnosticsProviderProtocol):
                continue
            try:
                items = await diag.system_hosts()
            except Exception:
                continue
            if not items:
                continue
            discovered_any = True
            for item in items:
                try:
                    if isinstance(item, dict):
                        host = item.get("host")
                        port = item.get("port")
                        role = item.get("role")
                        labels = item.get("labels") or {}
                    else:
                        host = item.host
                        port = item.port
                        role = item.role
                        labels = item.labels or {}
                    if isinstance(host, str) and host:
                        if host not in hosts:
                            hosts.append(host)
                        host_details.append(
                            {"host": host, "port": port, "role": role, "labels": labels}
                        )
                except Exception:
                    continue
        if discovered_any:
            source_notes.append("diagnostics")

        return {
            "status": "success",
            "hosts": hosts,
            "sources": source_notes,
            "host_details": host_details,
        }

    async def get_host_metrics(
        self,
        hosts: List[str],
        metric_keys: List[str],
        start_time: str,
        end_time: str = "now",
        step: Optional[str] = None,
    ) -> Dict[str, Any]:
        cfg: HostTelemetryConfig = self.instance_config or HostTelemetryConfig()
        aliases = cfg.metrics.metric_aliases or {}
        if not aliases:
            return {
                "status": "error",
                "error": "No metric_aliases configured in host_telemetry.metrics",
            }
        missing = [k for k in (metric_keys or []) if k not in aliases]
        if missing:
            return {
                "status": "error",
                "error": f"Unknown metric_keys: {missing}",
                "available_keys": list(aliases.keys()),
            }

        providers = self._metrics_providers
        if not providers:
            return {"status": "error", "error": "No metrics providers available"}

        step_val = step or (cfg.metrics.default_step or "30s")

        async def run_query(provider: MetricsProviderProtocol, host: str, key: str):
            tmpl = aliases[key] or ""
            # Avoid Python format() clashing with PromQL braces; only replace our token
            q = tmpl.replace("{host}", host)
            try:
                res = await provider.query_range(
                    query=q, start_time=start_time, end_time=end_time, step=step_val
                )
                return {
                    "provider": provider.provider_name,
                    "host": host,
                    "key": key,
                    "query": q,
                    "result": res,
                }
            except Exception as e:
                return {
                    "provider": provider.provider_name,
                    "host": host,
                    "key": key,
                    "query": q,
                    "error": str(e),
                }

        tasks = [run_query(p, h, k) for p in providers for h in hosts for k in metric_keys]
        results = await asyncio.gather(*tasks)
        return {
            "status": "success",
            "start_time": start_time,
            "end_time": end_time,
            "step": step_val,
            "results": results,
        }

    async def get_host_logs(
        self,
        hosts: List[str],
        start: str,
        end: str,
        keywords: Optional[List[str]] = None,
        direction: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        cfg: HostTelemetryConfig = self.instance_config or HostTelemetryConfig()
        providers = self._logs_providers
        if not providers:
            return {"status": "error", "error": "No logs providers available"}

        direction = direction or cfg.logs.direction
        limit = limit or cfg.logs.limit

        async def run_query(provider: LogsProviderProtocol, host: str):
            q = self._build_loki_query(host, keywords)
            try:
                res = await provider.query_range(
                    query=q, start=start, end=end, direction=direction, limit=limit
                )
                return {
                    "provider": provider.provider_name,
                    "host": host,
                    "query": q,
                    "result": res,
                }
            except Exception as e:
                return {
                    "provider": provider.provider_name,
                    "host": host,
                    "query": q,
                    "error": str(e),
                }

        tasks = [run_query(p, h) for p in providers for h in hosts]
        results = await asyncio.gather(*tasks)
        return {"status": "success", "start": start, "end": end, "results": results}
