"""MCP server CLI commands."""

import click


@click.group()
def mcp():
    """MCP server commands - expose agent capabilities via Model Context Protocol."""
    pass


@mcp.command("serve")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse"]),
    default="stdio",
    help="Transport mode: stdio (for agent integration) or sse (HTTP server)",
)
@click.option(
    "--host",
    default="127.0.0.1",
    help="Host to bind to (SSE mode only)",
)
@click.option(
    "--port",
    default=8080,
    type=int,
    help="Port to bind to (SSE mode only)",
)
def serve(transport: str, host: str, port: int):
    """Start the MCP server.

    The MCP server exposes the Redis SRE Agent's capabilities to other
    MCP-compatible AI agents. Available tools:

    - triage: Start a Redis troubleshooting session
    - knowledge_search: Search Redis documentation and runbooks
    - list_instances: List configured Redis instances
    - create_instance: Register a new Redis instance

    Examples:

        # Run in stdio mode (for Claude Desktop, Cursor, etc.)
        redis-sre-agent mcp serve

        # Run in SSE mode (HTTP server)
        redis-sre-agent mcp serve --transport sse --port 8080
    """
    from redis_sre_agent.mcp_server.server import run_sse, run_stdio

    if transport == "stdio":
        click.echo("Starting MCP server in stdio mode...")
        run_stdio()
    else:
        click.echo(f"Starting MCP server in SSE mode on {host}:{port}...")
        run_sse(host=host, port=port)


@mcp.command("list-tools")
def list_tools():
    """List available MCP tools."""
    from redis_sre_agent.mcp_server.server import mcp as mcp_server

    click.echo("Available MCP tools:\n")
    for tool in mcp_server._tool_manager._tools.values():
        click.echo(f"  {tool.name}")
        if tool.description:
            # Get first line of description
            first_line = tool.description.split("\n")[0].strip()
            click.echo(f"    {first_line}")
        click.echo()
