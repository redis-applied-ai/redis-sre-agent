"""MCP (Model Context Protocol) tool provider.

This module provides a dynamic tool provider that connects to an MCP server
and exposes its tools to the agent. It supports tool filtering and description
overrides based on the MCPServerConfig.
"""

import logging
import os
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp import types as mcp_types
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from redis_sre_agent.core.config import MCPServerConfig, MCPToolConfig
from redis_sre_agent.tools.models import Tool, ToolCapability, ToolDefinition, ToolMetadata
from redis_sre_agent.tools.protocols import ToolProvider

if TYPE_CHECKING:
    from redis_sre_agent.core.instances import RedisInstance

logger = logging.getLogger(__name__)


class MCPToolProvider(ToolProvider):
    """Dynamic tool provider that connects to an MCP server.

    This provider:
    1. Connects to an MCP server using the configured transport (stdio or HTTP)
    2. Discovers available tools from the server
    3. Optionally filters tools based on the config's `tools` mapping
    4. Applies capability and description overrides from the config
    5. Exposes the tools to the agent

    Example:
        config = MCPServerConfig(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-memory"],
            tools={
                "search_memories": MCPToolConfig(capability=ToolCapability.LOGS),
            }
        )
        provider = MCPToolProvider(
            server_name="memory",
            server_config=config,
        )
        async with provider:
            tools = provider.tools()
    """

    # Default capability for MCP tools if not specified
    DEFAULT_CAPABILITY = ToolCapability.UTILITIES

    def __init__(
        self,
        server_name: str,
        server_config: MCPServerConfig,
        redis_instance: Optional["RedisInstance"] = None,
        use_pool: bool = True,
    ):
        """Initialize the MCP tool provider.

        Args:
            server_name: Name of the MCP server (used in tool naming)
            server_config: Configuration for the MCP server
            redis_instance: Optional Redis instance (not typically used by MCP)
            use_pool: If True, use pooled connection when available (default: True)
        """
        super().__init__(redis_instance=redis_instance)
        self._server_name = server_name
        self._server_config = server_config
        self._session: Optional[ClientSession] = None
        self._exit_stack: Optional[AsyncExitStack] = None
        self._mcp_tools: List[mcp_types.Tool] = []
        self._tool_cache: List[Tool] = []
        self._use_pool = use_pool
        self._using_pooled_connection = False

    @property
    def provider_name(self) -> str:
        """Return the provider name based on the server name."""
        return f"mcp_{self._server_name}"

    async def __aenter__(self) -> "MCPToolProvider":
        """Enter async context and connect to the MCP server."""
        await self._connect()
        return self

    async def __aexit__(self, *args) -> None:
        """Exit async context and disconnect from the MCP server."""
        await self._disconnect()

    async def _connect(self) -> None:
        """Connect to the MCP server and discover tools.

        This method first tries to use a pooled connection if available.
        Falls back to creating a new connection if pool is empty or disabled.
        """
        # Try to use pooled connection first
        if self._use_pool:
            try:
                from redis_sre_agent.tools.mcp.pool import MCPConnectionPool

                pool = MCPConnectionPool.get_instance()
                pooled_conn = pool.get_connection(self._server_name)
                if pooled_conn:
                    self._session = pooled_conn.session
                    self._mcp_tools = pooled_conn.tools
                    self._tool_cache = []
                    self._using_pooled_connection = True
                    logger.info(
                        f"Using pooled connection for MCP server '{self._server_name}' "
                        f"({len(self._mcp_tools)} tools)"
                    )
                    return
            except Exception as e:
                logger.debug(f"Pool not available for '{self._server_name}': {e}")

        # Fall back to creating a new connection
        try:
            logger.info(
                f"Creating new connection to MCP server '{self._server_name}' "
                f"(command={self._server_config.command}, url={self._server_config.url})"
            )

            self._exit_stack = AsyncExitStack()
            await self._exit_stack.__aenter__()

            # Determine transport type and connect
            if self._server_config.command:
                # Stdio transport - spawn a subprocess
                # Merge parent environment with config-specified env so that
                # env vars like OPENAI_API_KEY are inherited by the subprocess
                merged_env = {**os.environ, **(self._server_config.env or {})}
                server_params = StdioServerParameters(
                    command=self._server_config.command,
                    args=self._server_config.args or [],
                    env=merged_env,
                )
                read_stream, write_stream = await self._exit_stack.enter_async_context(
                    stdio_client(server_params)
                )
            elif self._server_config.url:
                # URL-based transport (SSE or Streamable HTTP)
                # Expand environment variables in headers (e.g., ${GITHUB_TOKEN})
                headers = None
                if self._server_config.headers:
                    headers = {}
                    for key, value in self._server_config.headers.items():
                        # Expand ${VAR} patterns from environment
                        expanded_value = os.path.expandvars(value)
                        headers[key] = expanded_value

                # Determine transport type - default to streamable_http for modern servers
                transport_type = (self._server_config.transport or "streamable_http").lower()

                if transport_type == "sse":
                    # Legacy SSE transport
                    logger.info(f"Using SSE transport for '{self._server_name}'")
                    read_stream, write_stream = await self._exit_stack.enter_async_context(
                        sse_client(self._server_config.url, headers=headers)
                    )
                else:
                    # Streamable HTTP transport (default, works with GitHub remote MCP, etc.)
                    logger.info(f"Using Streamable HTTP transport for '{self._server_name}'")
                    (
                        read_stream,
                        write_stream,
                        _get_session_id,
                    ) = await self._exit_stack.enter_async_context(
                        streamablehttp_client(self._server_config.url, headers=headers)
                    )
            else:
                raise ValueError(
                    f"MCP server '{self._server_name}' must have either 'command' or 'url' configured"
                )

            # Create and initialize the session
            self._session = await self._exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await self._session.initialize()

            # Discover tools from the server
            tools_result = await self._session.list_tools()
            self._mcp_tools = tools_result.tools
            self._tool_cache = []

            logger.info(
                f"MCP server '{self._server_name}' connected with {len(self._mcp_tools)} tools: "
                f"{[t.name for t in self._mcp_tools]}"
            )

        except Exception as e:
            logger.error(f"Failed to connect to MCP server '{self._server_name}': {e}")
            # Clean up on failure
            if self._exit_stack:
                await self._exit_stack.aclose()
                self._exit_stack = None
            raise

    async def _disconnect(self) -> None:
        """Disconnect from the MCP server.

        If using a pooled connection, just clears local references without
        closing the shared session. Only closes connections we own.
        """
        if self._using_pooled_connection:
            # Don't close pooled connections - they're managed by the pool
            logger.debug(f"Releasing pooled connection for '{self._server_name}'")
            self._session = None
            self._using_pooled_connection = False
            return

        try:
            if self._exit_stack:
                logger.info(f"Disconnecting from MCP server '{self._server_name}'")
                await self._exit_stack.aclose()
                self._exit_stack = None
                self._session = None
        except Exception as e:
            logger.warning(f"Error disconnecting from MCP server '{self._server_name}': {e}")

    def _get_tool_config(self, tool_name: str) -> Optional[MCPToolConfig]:
        """Get the configuration for a specific tool, if any."""
        if self._server_config.tools:
            return self._server_config.tools.get(tool_name)
        return None

    def _should_include_tool(self, tool_name: str) -> bool:
        """Check if a tool should be included based on the config.

        If `tools` is specified in the config, only those tools are included.
        If `tools` is None, all tools from the server are included.
        """
        if self._server_config.tools is None:
            return True
        return tool_name in self._server_config.tools

    def _get_capability(self, tool_name: str) -> ToolCapability:
        """Get the capability for a tool, with config override support."""
        config = self._get_tool_config(tool_name)
        if config and config.capability:
            return config.capability
        return self.DEFAULT_CAPABILITY

    def _get_description(self, tool_name: str, mcp_description: str) -> str:
        """Get the description for a tool, with config override/template support.

        If the config provides a description, it can use {original} as a placeholder
        for the MCP tool's original description. This allows adding context while
        preserving the original tool documentation.

        Examples:
            - No override: uses original MCP description
            - Override without placeholder: "Custom description" -> replaces entirely
            - Override with placeholder: "Context. {original}" -> prepends context

        Args:
            tool_name: Name of the MCP tool
            mcp_description: Original description from the MCP server

        Returns:
            Final description (original, override, or templated)
        """
        config = self._get_tool_config(tool_name)
        if config and config.description:
            # Support templating: {original} gets replaced with the MCP description
            if "{original}" in config.description:
                return config.description.replace("{original}", mcp_description)
            return config.description
        return mcp_description

    def create_tool_schemas(self) -> List[ToolDefinition]:
        """Create tool schemas from the MCP server's tools.

        This method transforms MCP tool definitions into ToolDefinition objects,
        applying any configured filters, capability overrides, and description
        overrides.
        """
        schemas: List[ToolDefinition] = []

        for mcp_tool in self._mcp_tools:
            tool_name = mcp_tool.name
            if not tool_name:
                continue

            # Check if tool should be included
            if not self._should_include_tool(tool_name):
                continue

            # Get description (with potential override)
            mcp_description = mcp_tool.description or f"MCP tool: {tool_name}"
            description = self._get_description(tool_name, mcp_description)

            # Get capability (with potential override)
            capability = self._get_capability(tool_name)

            # Build parameters schema from MCP tool input schema
            input_schema = mcp_tool.inputSchema or {}
            parameters = {
                "type": "object",
                "properties": input_schema.get("properties", {}),
                "required": input_schema.get("required", []),
            }

            schema = ToolDefinition(
                name=self._make_tool_name(tool_name),
                description=description,
                capability=capability,
                parameters=parameters,
            )
            schemas.append(schema)

        return schemas

    def tools(self) -> List[Tool]:
        """Return the concrete tools exposed by this provider.

        This caches the tools list to avoid rebuilding on every call.
        """
        if self._tool_cache:
            return self._tool_cache

        schemas = self.create_tool_schemas()
        tools: List[Tool] = []

        for schema in schemas:
            # Extract the original MCP tool name from our tool name
            mcp_tool_name = self.resolve_operation(schema.name, {}) or ""

            meta = ToolMetadata(
                name=schema.name,
                description=schema.description,
                capability=schema.capability,
                provider_name=self.provider_name,
                requires_instance=False,  # MCP tools typically don't require Redis instance
            )

            # Create the invoke closure that calls the MCP server
            async def _invoke(
                args: Dict[str, Any],
                _tool_name: str = mcp_tool_name,
            ) -> Any:
                return await self._call_mcp_tool(_tool_name, args)

            tools.append(Tool(metadata=meta, definition=schema, invoke=_invoke))

        self._tool_cache = tools
        return tools

    async def _call_mcp_tool(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Call an MCP tool on the server.

        Args:
            tool_name: The original MCP tool name (without provider prefix)
            args: Arguments to pass to the tool

        Returns:
            The tool's result from the MCP server
        """
        if not self._session:
            return {
                "status": "error",
                "error": f"MCP server '{self._server_name}' is not connected",
            }

        try:
            logger.info(f"Calling MCP tool '{tool_name}' with args: {args}")
            result = await self._session.call_tool(tool_name, arguments=args)

            # Check for errors
            if result.isError:
                error_text = ""
                for content in result.content:
                    if isinstance(content, mcp_types.TextContent):
                        error_text += content.text
                return {
                    "status": "error",
                    "error": error_text or "Tool execution failed",
                }

            # Extract the result content
            response: Dict[str, Any] = {"status": "success"}

            # If there's structured content, use it
            if result.structuredContent:
                response["data"] = result.structuredContent

            # Also extract text content for compatibility
            text_parts = []
            for content in result.content:
                if isinstance(content, mcp_types.TextContent):
                    text_parts.append(content.text)
                elif isinstance(content, mcp_types.ImageContent):
                    response.setdefault("images", []).append(
                        {
                            "mimeType": content.mimeType,
                            "data": content.data,
                        }
                    )
                elif isinstance(content, mcp_types.EmbeddedResource):
                    resource = content.resource
                    if isinstance(resource, mcp_types.TextResourceContents):
                        response.setdefault("resources", []).append(
                            {
                                "uri": str(resource.uri),
                                "text": resource.text,
                            }
                        )

            if text_parts:
                response["text"] = "\n".join(text_parts)

            return response

        except Exception as e:
            logger.error(f"Error calling MCP tool '{tool_name}': {e}")
            return {
                "status": "error",
                "error": str(e),
            }
