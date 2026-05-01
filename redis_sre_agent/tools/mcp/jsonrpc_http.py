"""Legacy JSON-RPC over HTTP client for hosted MCP-style servers.

Some servers expose MCP-compatible methods like ``initialize``, ``tools/list``,
and ``tools/call`` over plain JSON-RPC HTTP POST instead of the standard MCP
streamable transports. This adapter gives the runtime a minimal async session
surface compatible with the existing provider code.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
from mcp import types as mcp_types


class JSONRPCHTTPSession:
    """Minimal session wrapper for JSON-RPC-over-HTTP MCP endpoints."""

    def __init__(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._url = url
        merged_headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if headers:
            merged_headers.update(headers)
        self._client = httpx.AsyncClient(headers=merged_headers, timeout=timeout)
        self._request_id = 0
        self._session_id: str | None = None

    async def __aenter__(self) -> "JSONRPCHTTPSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def initialize(self) -> dict[str, Any]:
        return await self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "redis-sre-agent",
                    "version": "0.3.0",
                },
            },
        )

    async def list_tools(self) -> SimpleNamespace:
        result = await self._request("tools/list", {})
        tools = [mcp_types.Tool.model_validate(item) for item in result.get("tools", [])]
        return SimpleNamespace(tools=tools)

    async def call_tool(
        self,
        name: str,
        *,
        arguments: dict[str, Any] | None = None,
    ) -> mcp_types.CallToolResult:
        result = await self._request(
            "tools/call",
            {
                "name": name,
                "arguments": arguments or {},
            },
        )
        return mcp_types.CallToolResult.model_validate(result)

    async def _request(self, method: str, params: dict[str, Any] | None) -> dict[str, Any]:
        self._request_id += 1
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        headers: dict[str, str] | None = None
        if self._session_id:
            headers = {"mcp-session-id": self._session_id}
        response = await self._client.post(self._url, json=payload, headers=headers)
        response.raise_for_status()
        session_id = response.headers.get("mcp-session-id")
        if session_id:
            self._session_id = session_id
        body = response.json()

        error = body.get("error")
        if error:
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise RuntimeError(message or f"JSON-RPC request failed: {method}")

        result = body.get("result")
        if not isinstance(result, dict):
            return {}
        return result
