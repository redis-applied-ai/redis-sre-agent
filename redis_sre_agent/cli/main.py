"""CLI interface for Redis SRE Agent."""

import importlib

import click

# Map command names to their module:attribute for lazy import
_COMMANDS = {
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
}


class LazyGroup(click.MultiCommand):
    """
    Lazy loading of CLI commands to avoid hard dependencies at top level.

    This allows us to split up Click commands into separate files
    without having to import all dependencies at the top level.
    """

    def list_commands(self, ctx):
        # Keep stable ordering for help output
        return list(_COMMANDS.keys())

    def get_command(self, ctx, name):
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
