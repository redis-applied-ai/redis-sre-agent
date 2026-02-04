"""CLI interface for Redis SRE Agent."""

import importlib

import click

from redis_sre_agent import __version__

# Map command names to their module:attribute for lazy import
_COMMANDS = {
    "cache": "redis_sre_agent.cli.cache:cache",
    "thread": "redis_sre_agent.cli.threads:thread",
    "schedule": "redis_sre_agent.cli.schedules:schedule",
    "instance": "redis_sre_agent.cli.instance:instance",
    "task": "redis_sre_agent.cli.tasks:task",
    "knowledge": "redis_sre_agent.cli.knowledge:knowledge",
    "pipeline": "redis_sre_agent.cli.pipeline:pipeline",
    "runbook": "redis_sre_agent.cli.runbook:runbook",
    "query": "redis_sre_agent.cli.query:query",
    "worker": "redis_sre_agent.cli.worker:worker",
    "mcp": "redis_sre_agent.cli.mcp:mcp",
    "index": "redis_sre_agent.cli.index:index",
    "support-package": "redis_sre_agent.cli.support_package:support_package",
}

# Built-in commands that don't need lazy loading
_BUILTIN_COMMANDS = {"version"}


@click.command()
def version():
    """Show the Redis SRE Agent version."""
    click.echo(f"redis-sre-agent {__version__}")


class LazyGroup(click.MultiCommand):
    """
    Lazy loading of CLI commands to avoid hard dependencies at top level.

    This allows us to split up Click commands into separate files
    without having to import all dependencies at the top level.
    """

    def list_commands(self, ctx):
        # Keep stable ordering for help output, include built-in commands
        return list(_COMMANDS.keys()) + list(_BUILTIN_COMMANDS)

    def get_command(self, ctx, name):
        # Handle built-in commands
        if name == "version":
            return version

        target = _COMMANDS.get(name)
        if not target:
            return None
        module_path, attr = target.split(":", 1)
        mod = importlib.import_module(module_path)
        return getattr(mod, attr)


@click.command(cls=LazyGroup)
def main():
    """Redis SRE Agent CLI."""
    pass


if __name__ == "__main__":
    main()
