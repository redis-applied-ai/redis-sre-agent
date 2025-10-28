"""Loki logs tool provider.

This provider exposes common Loki HTTP API operations as LLM-callable tools:
- query:        GET /loki/api/v1/query
- query_range:  GET /loki/api/v1/query_range
- labels:       GET /loki/api/v1/labels
- label_values: GET /loki/api/v1/label/<name>/values
- series:       GET/POST /loki/api/v1/series
- volume:       GET /loki/api/v1/index/volume (requires volume_enabled: true)
- patterns:     GET /loki/api/v1/patterns (requires pattern_ingester enabled)

Configuration via environment (automatically loaded):
- TOOLS_LOKI_URL (default: http://localhost:3100)
- TOOLS_LOKI_TENANT_ID (optional; sent as X-Scope-OrgID)
- TOOLS_LOKI_TIMEOUT (seconds, default: 30)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from redis_sre_agent.tools.decorators import status_update
from redis_sre_agent.tools.protocols import ToolCapability, ToolProvider
from redis_sre_agent.tools.tool_definition import ToolDefinition

logger = logging.getLogger(__name__)


class LokiConfig(BaseSettings):
    """Configuration for the Loki provider (loaded from env).

    Env prefix: TOOLS_LOKI_
    - TOOLS_LOKI_URL
    - TOOLS_LOKI_TENANT_ID
    - TOOLS_LOKI_TIMEOUT
    - TOOLS_LOKI_DEFAULT_SELECTOR
    """

    model_config = SettingsConfigDict(env_prefix="tools_loki_")

    url: str = Field(default="http://localhost:3100", description="Loki base URL")
    tenant_id: Optional[str] = Field(default=None, description="X-Scope-OrgID tenant header")
    timeout: float = Field(default=30.0, description="HTTP timeout (seconds)")
    default_selector: Optional[str] = Field(
        default=None,
        description='Default stream selector to use when query starts with {}. Example: {service=~".+"}',
    )


class LokiInstanceConfig(BaseModel):
    """Optional per-instance extension config for Loki provider.

    Sourced from RedisInstance.extension_data/extension_secrets under namespace 'loki'
    (or flat keys like 'loki.<key>'). Secrets can be SecretStr.
    """

    prefer_streams: Optional[List[Dict[str, str]]] = Field(
        default=None,
        description="Preferred stream label dicts to OR into empty selectors (e.g., [{'job':'node-exporter','instance':'demo-host'}]).",
    )
    keywords: Optional[List[str]] = Field(
        default=None, description="Preferred keywords to search for (reserved for future use)"
    )
    default_selector: Optional[str] = Field(
        default=None,
        description="Optional selector to include when query starts with {} (e.g., {service=~'.+'}).",
    )


class LokiToolProvider(ToolProvider):
    """Loki logs provider using the Loki HTTP API."""

    # Enable per-instance extension config parsing
    instance_config_model = LokiInstanceConfig
    extension_namespace = "loki"

    # Declare capabilities so orchestrators can request a logs provider via ToolManager
    capabilities = {ToolCapability.LOGS}

    def __init__(self, redis_instance=None, config: Optional[LokiConfig] = None):
        super().__init__(redis_instance)
        self.config = config or LokiConfig()

    @property
    def provider_name(self) -> str:
        return "loki"

    def _headers(self) -> Dict[str, str]:
        hdrs: Dict[str, str] = {"Accept": "application/json"}
        if self.config.tenant_id:
            hdrs["X-Scope-OrgID"] = self.config.tenant_id
        return hdrs

    # ----------------------------- Time helpers -----------------------------
    def _now_epoch_ns(self) -> str:
        return str(int(datetime.now(timezone.utc).timestamp() * 1e9))

    def _parse_time_to_epoch_ns(self, value: Optional[str]) -> Optional[str]:
        """Convert a time value to an epoch ns string acceptable by Loki.

        Accepts:
        - "now" or None -> current time
        - Relative durations like "-6h", "6h", "15m", "30s", "1d", "1w" (interpreted as now - duration)
        - Numeric epoch in s/ms/us/ns (converted to ns)
        - RFC3339 timestamps (converted to ns)
        Returns None if the value is falsy and cannot be parsed.
        """
        if not value:
            return None

        v = value.strip().lower()
        if v == "now":
            return self._now_epoch_ns()

        # Relative duration, accept optional leading '-'; treat positive as "ago"
        m = re.match(r"^-?(\d+)([smhdw])$", v)
        if m:
            amount = int(m.group(1))
            unit = m.group(2)
            seconds = amount
            if unit == "m":
                seconds *= 60
            elif unit == "h":
                seconds *= 60 * 60
            elif unit == "d":
                seconds *= 60 * 60 * 24
            elif unit == "w":
                seconds *= 60 * 60 * 24 * 7
            # now - duration
            ts = datetime.now(timezone.utc) - timedelta(seconds=seconds)
            return str(int(ts.timestamp() * 1e9))

        # Pure digits: interpret as epoch (s/ms/us/ns)

        if re.match(r"^\d+$", v):
            iv = int(v)
            # Heuristic by digits length
            if iv < 1_000_000_000_000:  # < 10^12 -> seconds
                return str(iv * 1_000_000_000)
            elif iv < 1_000_000_000_000_000:  # < 10^15 -> milliseconds
                return str(iv * 1_000_000)
            elif iv < 1_000_000_000_000_000_000:  # < 10^18 -> microseconds
                return str(iv * 1_000)
            else:
                return str(iv)

        # RFC3339-ish (accept 'Z')
        try:
            v2 = v.replace("z", "+00:00")
            dt = datetime.fromisoformat(v2)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return str(int(dt.timestamp() * 1e9))
        except Exception:
            pass

        # Fallback: if unknown, return as-is so caller error surfaces from Loki
        return v

    def create_tool_schemas(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name=self._make_tool_name("query"),
                description=(
                    "Query Loki at a single point in time using LogQL. Use this for metric-style "
                    'queries (e.g., sum(rate({job="foo"}[5m]))) or to compute values.'
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "LogQL expression"},
                        "time": {
                            "type": "string",
                            "description": "Evaluation time (RFC3339 or unix ns). Default: now",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max entries (streams)",
                            "minimum": 1,
                        },
                        "direction": {
                            "type": "string",
                            "enum": ["forward", "backward"],
                            "description": "Sort order for logs (default: backward)",
                        },
                    },
                    "required": ["query"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("query_range"),
                description=(
                    "Query Loki over a time range using LogQL. Supports both log and metric queries."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "LogQL expression"},
                        "start": {
                            "type": "string",
                            "description": "Start time (RFC3339 or unix ns)",
                        },
                        "end": {"type": "string", "description": "End time (RFC3339 or unix ns)"},
                        "step": {
                            "type": "string",
                            "description": "Step for metric queries (e.g., 30s)",
                        },
                        "limit": {"type": "integer", "description": "Max log entries"},
                        "interval": {
                            "type": "string",
                            "description": "Interval for stream responses (log queries)",
                        },
                        "direction": {
                            "type": "string",
                            "enum": ["forward", "backward"],
                            "description": "Sort order for logs (default: backward)",
                        },
                    },
                    "required": ["query", "start", "end"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("labels"),
                description="List known labels within a time span (optionally scoped by a selector)",
                parameters={
                    "type": "object",
                    "properties": {
                        "start": {"type": "string", "description": "Start time"},
                        "end": {"type": "string", "description": "End time"},
                        "since": {
                            "type": "string",
                            "description": "Duration to calculate start from end",
                        },
                        "query": {
                            "type": "string",
                            "description": "Optional selector to scope labels",
                        },
                    },
                    "required": [],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("label_values"),
                description="List known values for a label within a time span",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Label name", "minLength": 1},
                        "start": {"type": "string", "description": "Start time"},
                        "end": {"type": "string", "description": "End time"},
                        "since": {
                            "type": "string",
                            "description": "Duration to calculate start from end",
                        },
                        "query": {
                            "type": "string",
                            "description": "Optional selector to scope values",
                        },
                    },
                    "required": ["name"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("series"),
                description="List streams (unique label sets) matching selectors over a time range",
                parameters={
                    "type": "object",
                    "properties": {
                        "match": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "One or more stream selectors (match[]=...)",
                        },
                        "start": {"type": "string", "description": "Start time"},
                        "end": {"type": "string", "description": "End time"},
                    },
                    "required": ["match"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("volume"),
                description=(
                    "Query log volume (bytes/chunks) aggregated by label or series. Requires Loki volume_enabled."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Stream selector",
                            "minLength": 1,
                        },
                        "start": {"type": "string", "description": "Start time (ns or RFC3339)"},
                        "end": {"type": "string", "description": "End time (ns or RFC3339)"},
                        "limit": {"type": "integer", "description": "Max series to return"},
                        "targetLabels": {"type": "string", "description": "Comma-separated labels"},
                        "aggregateBy": {
                            "type": "string",
                            "enum": ["series", "labels"],
                            "description": "Aggregation strategy",
                        },
                    },
                    "required": ["query", "start", "end"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("patterns"),
                description=(
                    "Detect and count log patterns for a selector over time. Requires pattern_ingester enabled."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Stream selector"},
                        "start": {"type": "string", "description": "Start time"},
                        "end": {"type": "string", "description": "End time"},
                        "step": {"type": "string", "description": "Step duration (e.g., 1m)"},
                    },
                    "required": ["query", "start", "end"],
                },
            ),
        ]

    async def resolve_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Any:
        # Extract operation (everything after provider/hash)
        parts = tool_name.split("_")
        operation = "_".join(parts[2:]) if len(parts) >= 3 else tool_name
        if operation == "query":
            return await self.query(**args)
        if operation == "query_range":
            return await self.query_range(**args)
        if operation == "labels":
            return await self.labels(**args)
        if operation == "label_values":
            return await self.label_values(**args)
        if operation == "series":
            return await self.series(**args)
        if operation == "volume":
            return await self.volume(**args)
        if operation == "patterns":
            return await self.patterns(**args)
        raise ValueError(f"Unknown operation: {operation} (from tool: {tool_name})")

    async def _request(
        self, method: str, path: str, params: Dict[str, Any] | None = None, data: Any | None = None
    ) -> Dict[str, Any]:
        url = self.config.url.rstrip("/") + path
        try:
            async with httpx.AsyncClient(
                timeout=self.config.timeout, headers=self._headers()
            ) as client:
                resp = await client.request(method, url, params=params, data=data)
            if resp.headers.get("content-type", "").startswith("application/json"):
                payload = resp.json()
            else:
                payload = {"raw": resp.text}
            if resp.status_code >= 400:
                logger.error("Loki API error %s %s: %s", method, path, payload)
                return {"status": "error", "code": resp.status_code, "error": payload}
            return {"status": "success", "code": resp.status_code, "data": payload}
        except Exception as e:
            logger.exception("Loki request failed: %s %s", method, path)
            return {"status": "error", "error": str(e)}

    def _selector_from_labels(self, labels: Dict[str, str]) -> str:
        parts = []
        for k, v in (labels or {}).items():
            parts.append(f'{k}="{v}"')
        return "{" + ",".join(parts) + "}"

    # ----------------------------- Query sanitization -----------------------------
    def _fix_empty_stream_selector(self, query: str) -> str:
        """Loki requires at least one non-empty-compatible label matcher in selectors.

        If the query starts with an empty selector (e.g., "{} |= \"foo\""), rewrite the
        first selector to include a default non-empty matcher: {job=~".+"}.

        This avoids 400 errors like:
          "queries require at least one regexp or equality matcher that does not have an
           empty-compatible value... app=~\".+\" meets this requirement"
        """
        try:
            import re as _re

            m = _re.match(r"^\s*\{\s*\}(.*)$", query or "")
            if m:
                suffix = m.group(1)
                selectors: List[str] = []
                # Include per-instance preferred streams first, if provided
                try:
                    ic = getattr(self, "instance_config", None)
                    if ic and getattr(ic, "prefer_streams", None):
                        for lbls in ic.prefer_streams or []:
                            try:
                                selectors.append(self._selector_from_labels(lbls or {}))
                            except Exception:
                                continue
                    # Optional per-instance default selector
                    if ic and getattr(ic, "default_selector", None):
                        ds_inst = (ic.default_selector or "").strip()
                        if ds_inst:
                            selectors.append(ds_inst)
                except Exception:
                    pass
                # Env-configured default selector
                ds_env = (self.config.default_selector or "").strip()
                if ds_env:
                    selectors.append(ds_env)
                if selectors:
                    # Build OR-union across all selectors, applying the same suffix
                    if len(selectors) == 1:
                        return f"{selectors[0]}{suffix}"
                    union = " or ".join(f"({s}{suffix})" for s in selectors)
                    return union
                # Fallback union for common labels
                return f'({{job=~".+"}}{suffix}) or ({{service=~".+"}}{suffix})'
        except Exception:
            pass
        return query

    # ----------------------------- Operations -----------------------------

    @status_update("I'm querying Loki for logs.")
    async def query(
        self,
        query: str,
        time: Optional[str] = None,
        limit: Optional[int] = None,
        direction: Optional[str] = None,
    ) -> Dict[str, Any]:
        safe_query = self._fix_empty_stream_selector(query)
        params: Dict[str, Any] = {"query": safe_query}
        if time:
            params["time"] = time
        if limit is not None:
            params["limit"] = int(limit)
        if direction:
            params["direction"] = direction
        return await self._request("GET", "/loki/api/v1/query", params=params)

    @status_update("I'm querying Loki for logs over a time range.")
    async def query_range(
        self,
        query: str,
        start: str,
        end: str,
        step: Optional[str] = None,
        limit: Optional[int] = None,
        interval: Optional[str] = None,
        direction: Optional[str] = None,
    ) -> Dict[str, Any]:
        start_ns = self._parse_time_to_epoch_ns(start)
        end_ns = self._parse_time_to_epoch_ns(end) or self._now_epoch_ns()
        safe_query = self._fix_empty_stream_selector(query)
        params: Dict[str, Any] = {"query": safe_query, "start": start_ns, "end": end_ns}
        if step:
            params["step"] = step
        if limit is not None:
            params["limit"] = int(limit)
        if interval:
            params["interval"] = interval
        if direction:
            params["direction"] = direction
        return await self._request("GET", "/loki/api/v1/query_range", params=params)

    @status_update("I'm querying Loki for available labels.")
    async def labels(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        since: Optional[str] = None,
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if start:
            params["start"] = self._parse_time_to_epoch_ns(start)
        if end:
            params["end"] = self._parse_time_to_epoch_ns(end) or self._now_epoch_ns()
        if since:
            params["since"] = since
        if query:
            params["query"] = query
        return await self._request("GET", "/loki/api/v1/labels", params=params)

    @status_update("I'm querying Loki for label values.")
    async def label_values(
        self,
        name: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        since: Optional[str] = None,
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if start:
            params["start"] = self._parse_time_to_epoch_ns(start)
        if end:
            params["end"] = self._parse_time_to_epoch_ns(end) or self._now_epoch_ns()
        if since:
            params["since"] = since
        if query:
            params["query"] = query
        return await self._request("GET", f"/loki/api/v1/label/{name}/values", params=params)

    @status_update("I'm querying Loki for series.")
    async def series(
        self, match: List[str], start: Optional[str] = None, end: Optional[str] = None
    ) -> Dict[str, Any]:
        # POST with application/x-www-form-urlencoded to support large match lists
        params: Dict[str, Any] = {}
        if start:
            params["start"] = self._parse_time_to_epoch_ns(start)
        if end:
            params["end"] = self._parse_time_to_epoch_ns(end) or self._now_epoch_ns()
        # Build form data with repeated match[]= selectors
        form_items = []
        for m in match:
            form_items.append(("match[]", m))
        return await self._request("POST", "/loki/api/v1/series", params=params, data=form_items)

    @status_update("I'm querying Loki for log volume.")
    async def volume(
        self,
        query: str,
        start: str,
        end: str,
        limit: Optional[int] = None,
        target_labels: Optional[str] = None,
        aggregate_by: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        # Backwards-compat: accept camelCase aliases from tool calls/schema
        if target_labels is None and "targetLabels" in kwargs:
            target_labels = kwargs.get("targetLabels")
        if aggregate_by is None and "aggregateBy" in kwargs:
            aggregate_by = kwargs.get("aggregateBy")

        start_ns = self._parse_time_to_epoch_ns(start)
        end_ns = self._parse_time_to_epoch_ns(end) or self._now_epoch_ns()
        safe_query = self._fix_empty_stream_selector(query)
        params: Dict[str, Any] = {"query": safe_query, "start": start_ns, "end": end_ns}
        if limit is not None:
            params["limit"] = int(limit)
        if target_labels:
            params["targetLabels"] = target_labels
        if aggregate_by:
            params["aggregateBy"] = aggregate_by
        return await self._request("GET", "/loki/api/v1/index/volume", params=params)

    @status_update("I'm querying Loki for patterns.")
    async def patterns(
        self, query: str, start: str, end: str, step: Optional[str] = None
    ) -> Dict[str, Any]:
        start_ns = self._parse_time_to_epoch_ns(start)
        end_ns = self._parse_time_to_epoch_ns(end) or self._now_epoch_ns()
        safe_query = self._fix_empty_stream_selector(query)
        params: Dict[str, Any] = {"query": safe_query, "start": start_ns, "end": end_ns}
        if step:
            params["step"] = step
        return await self._request("GET", "/loki/api/v1/patterns", params=params)
