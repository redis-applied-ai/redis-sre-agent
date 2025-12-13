"""MCP server CLI commands."""

import click


@click.group()
def mcp():
    """MCP server commands - expose agent capabilities via Model Context Protocol."""
    pass


@mcp.command("serve")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "http", "sse"]),
    default="stdio",
    help="Transport mode: stdio (local), http (remote/recommended), or sse (legacy)",
)
@click.option(
    "--host",
    default="0.0.0.0",
    help="Host to bind to (http/sse mode only)",
)
@click.option(
    "--port",
    default=8081,
    type=int,
    help="Port to bind to (http/sse mode only)",
)
def serve(transport: str, host: str, port: int):
    """Start the MCP server.

    The MCP server exposes the Redis SRE Agent's capabilities to other
    MCP-compatible AI agents.

    \b
    Available tools:
      - triage: Start a Redis troubleshooting session
      - get_task_status: Check if a triage task is complete
      - get_thread: Get the full results from a triage
      - knowledge_search: Search Redis documentation and runbooks
      - list_instances: List configured Redis instances
      - create_instance: Register a new Redis instance

    \b
    Examples:
      # Run in stdio mode (for Claude Desktop local config)
      redis-sre-agent mcp serve

    \b
      # Run in HTTP mode (for Claude remote connector - RECOMMENDED)
      redis-sre-agent mcp serve --transport http --port 8081
      # Then add in Claude: Settings > Connectors > Add Custom Connector
      # URL: http://your-host:8081/mcp

    \b
      # Run in SSE mode (legacy, for older clients)
      redis-sre-agent mcp serve --transport sse --port 8081
    """
    from redis_sre_agent.mcp_server.server import run_http, run_sse, run_stdio

    if transport == "stdio":
        # Don't print anything to stdout in stdio mode - it corrupts the JSON-RPC stream
        run_stdio()
    elif transport == "http":
        click.echo(f"Starting MCP server in HTTP mode on {host}:{port}...")
        click.echo(f"MCP endpoint: http://{host}:{port}/mcp")
        click.echo("Add this URL as a Custom Connector in Claude settings.")
        run_http(host=host, port=port)
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
