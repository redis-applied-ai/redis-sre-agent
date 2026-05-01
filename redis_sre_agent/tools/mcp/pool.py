"""MCP Connection Pool for persistent connections across queries.

This module provides a singleton connection pool that keeps MCP server
connections warm between queries, avoiding the 2-3s connection overhead
on each request.
"""

import asyncio
import logging
import os
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp import types as mcp_types
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from redis_sre_agent.core.runtime_overrides import get_active_mcp_servers
from redis_sre_agent.tools.mcp.jsonrpc_http import JSONRPCHTTPSession

if TYPE_CHECKING:
    from redis_sre_agent.core.config import MCPServerConfig

logger = logging.getLogger(__name__)
_EXIT_STACK_CLOSE_TIMEOUT_SECONDS = 5.0


@dataclass
class PooledConnection:
    """A pooled MCP connection with its session and metadata."""

    server_name: str
    session: Any
    tools: List[mcp_types.Tool]
    exit_stack: AsyncExitStack
    connected_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    call_count: int = 0


class MCPConnectionPool:
    """Singleton pool managing persistent MCP server connections.

    Usage:
        # During app startup (lifespan):
        pool = MCPConnectionPool.get_instance()
        await pool.start()

        # During query handling:
        conn = pool.get_connection("github")
        if conn:
            result = await conn.session.call_tool("search_repos", {...})

        # During app shutdown:
        await pool.shutdown()
    """

    _instance: Optional["MCPConnectionPool"] = None

    def __init__(self):
        self._connections: Dict[str, PooledConnection] = {}
        self._configs: Dict[str, "MCPServerConfig"] = {}
        self._started = False

    @classmethod
    def get_instance(cls) -> "MCPConnectionPool":
        """Get or create the singleton pool instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (for testing)."""
        cls._instance = None

    async def start(self) -> Dict[str, bool]:
        """Start the pool and connect to all configured MCP servers."""
        from redis_sre_agent.core.config import MCPServerConfig, settings

        if self._started:
            logger.warning("MCPConnectionPool already started")
            return {name: True for name in self._connections}

        mcp_servers = get_active_mcp_servers(settings.mcp_servers)
        if not mcp_servers:
            logger.info("No MCP servers configured - pool is empty")
            self._started = True
            return {}

        results: Dict[str, bool] = {}
        for server_name, server_config in mcp_servers.items():
            if isinstance(server_config, dict):
                server_config = MCPServerConfig.model_validate(server_config)
            self._configs[server_name] = server_config

            try:
                await self._connect_server(server_name, server_config)
                results[server_name] = True
                logger.info(f"MCP pool: connected to '{server_name}'")
            except Exception as e:
                results[server_name] = False
                logger.error(f"MCP pool: failed to connect to '{server_name}': {e}")

        self._started = True
        connected = sum(1 for v in results.values() if v)
        logger.info(f"MCP connection pool started: {connected}/{len(results)} servers")
        return results

    async def _connect_server(
        self, server_name: str, config: "MCPServerConfig"
    ) -> PooledConnection:
        """Connect to a single MCP server."""
        exit_stack = AsyncExitStack()
        await exit_stack.__aenter__()

        try:
            if config.command:
                # Expand environment variable references like ${REDIS_URL} in env values
                expanded_env = {
                    k: os.path.expandvars(v) if isinstance(v, str) else v
                    for k, v in (config.env or {}).items()
                }
                merged_env = {**os.environ, **expanded_env}
                server_params = StdioServerParameters(
                    command=config.command,
                    args=config.args or [],
                    env=merged_env,
                )
                read_stream, write_stream = await exit_stack.enter_async_context(
                    stdio_client(server_params)
                )
            elif config.url:
                resolved_url = os.path.expandvars(config.url).strip()
                if not resolved_url or "${" in resolved_url:
                    raise ValueError(f"MCP server '{server_name}' has an unresolved URL: {config.url}")
                headers = None
                if config.headers:
                    headers = {k: os.path.expandvars(v) for k, v in config.headers.items()}

                transport_type = (config.transport or "streamable_http").lower()
                if transport_type == "sse":
                    read_stream, write_stream = await exit_stack.enter_async_context(
                        sse_client(resolved_url, headers=headers)
                    )
                elif transport_type == "streamable_http":
                    (read_stream, write_stream, _) = await exit_stack.enter_async_context(
                        streamablehttp_client(resolved_url, headers=headers)
                    )
                elif transport_type == "jsonrpc_http":
                    session = await exit_stack.enter_async_context(
                        JSONRPCHTTPSession(resolved_url, headers=headers)
                    )
                    await _run_discovery_step(
                        server_name,
                        config.tool_discovery_timeout_seconds,
                        "initialize",
                        session.initialize(),
                    )
                    tools_result = await _run_discovery_step(
                        server_name,
                        config.tool_discovery_timeout_seconds,
                        "list_tools",
                        session.list_tools(),
                    )

                    conn = PooledConnection(
                        server_name=server_name,
                        session=session,
                        tools=tools_result.tools,
                        exit_stack=exit_stack,
                    )
                    self._connections[server_name] = conn
                    return conn
                else:
                    raise ValueError(
                        f"Unsupported MCP transport '{transport_type}' for server '{server_name}'"
                    )
            else:
                raise ValueError(f"MCP server '{server_name}' needs 'command' or 'url'")

            session = await exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
            await _run_discovery_step(
                server_name,
                config.tool_discovery_timeout_seconds,
                "initialize",
                session.initialize(),
            )
            tools_result = await _run_discovery_step(
                server_name,
                config.tool_discovery_timeout_seconds,
                "list_tools",
                session.list_tools(),
            )

            conn = PooledConnection(
                server_name=server_name,
                session=session,
                tools=tools_result.tools,
                exit_stack=exit_stack,
            )
            self._connections[server_name] = conn
            return conn
        except Exception:
            await _close_exit_stack(exit_stack, server_name)
            raise

    def get_connection(self, server_name: str) -> Optional[PooledConnection]:
        """Get a pooled connection by server name."""
        conn = self._connections.get(server_name)
        if conn:
            conn.last_used = time.time()
            conn.call_count += 1
        return conn

    def get_all_connections(self) -> Dict[str, PooledConnection]:
        """Get all active connections."""
        return dict(self._connections)

    def is_connected(self, server_name: str) -> bool:
        """Check if a server is connected."""
        return server_name in self._connections

    async def reconnect(self, server_name: str) -> bool:
        """Reconnect to a specific server."""
        if server_name not in self._configs:
            logger.error(f"Cannot reconnect: '{server_name}' not in config")
            return False

        if server_name in self._connections:
            await self._disconnect_server(server_name)

        try:
            await self._connect_server(server_name, self._configs[server_name])
            logger.info(f"MCP pool: reconnected to '{server_name}'")
            return True
        except Exception as e:
            logger.error(f"MCP pool: reconnect to '{server_name}' failed: {e}")
            return False

    async def _disconnect_server(self, server_name: str) -> None:
        """Disconnect from a single server."""
        conn = self._connections.pop(server_name, None)
        if conn:
            try:
                # Use wait_for with timeout to prevent hanging on cleanup
                await asyncio.wait_for(conn.exit_stack.aclose(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"Timeout closing '{server_name}'")
            except asyncio.CancelledError:
                logger.debug(f"Cleanup cancelled for '{server_name}' (expected during shutdown)")
            except RuntimeError as e:
                # This can happen when shutdown is called from a different task than startup
                # (common in CLI mode where the process is exiting anyway)
                if "different task" in str(e):
                    logger.debug(f"Cross-task cleanup for '{server_name}' (expected in CLI mode)")
                else:
                    logger.warning(f"Runtime error closing '{server_name}': {e}")
            except BaseExceptionGroup:
                # anyio wraps exceptions in ExceptionGroups during cleanup
                logger.debug(
                    f"Cleanup exception group for '{server_name}' (expected during shutdown)"
                )
            except Exception as e:
                logger.warning(f"Error closing '{server_name}': {e}")

    async def shutdown(self, force: bool = False) -> None:
        """Shutdown the pool and close all connections.

        Args:
            force: If True, just clear connections without proper cleanup.
                   Use for CLI mode where the process is exiting anyway.
        """
        if force:
            # Just abandon connections - process is exiting anyway
            logger.debug("Force-closing MCP connection pool (process exit)")
            self._connections.clear()
            self._started = False
            return

        logger.info("Shutting down MCP connection pool...")
        for server_name in list(self._connections.keys()):
            await self._disconnect_server(server_name)
        self._started = False
        logger.info("MCP connection pool shut down")

    def stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        now = time.time()
        return {
            "started": self._started,
            "servers_configured": len(self._configs),
            "servers_connected": len(self._connections),
            "connections": {
                name: {
                    "tools": len(conn.tools),
                    "call_count": conn.call_count,
                    "age_seconds": round(now - conn.connected_at, 1),
                    "idle_seconds": round(now - conn.last_used, 1),
                }
                for name, conn in self._connections.items()
            },
        }


async def _run_discovery_step(
    server_name: str,
    timeout_seconds: float | None,
    step: str,
    operation: Any,
) -> Any:
    if timeout_seconds is None:
        return await operation
    try:
        return await asyncio.wait_for(operation, timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        raise TimeoutError(
            f"MCP server '{server_name}' timed out after {timeout_seconds:.1f}s during {step}"
        ) from exc


async def _close_exit_stack(exit_stack: AsyncExitStack, server_name: str) -> None:
    try:
        await asyncio.wait_for(
            exit_stack.aclose(),
            timeout=_EXIT_STACK_CLOSE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Timed out after %.1fs while closing pooled MCP server '%s'",
            _EXIT_STACK_CLOSE_TIMEOUT_SECONDS,
            server_name,
        )
