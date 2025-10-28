"""CLI interface for Redis SRE Agent."""

import click

from .instance import instance
from .knowledge import knowledge
from .pipeline import pipeline
from .query import query
from .runbook import runbook
from .schedules import schedule
from .tasks import task
from .threads import thread
from .worker import worker


@click.group()
def main():
    """Redis SRE Agent CLI."""
    pass


main.add_command(thread)
main.add_command(schedule)
main.add_command(instance)
main.add_command(task)
main.add_command(knowledge)
main.add_command(pipeline)
main.add_command(runbook)
main.add_command(query)
main.add_command(worker)


if __name__ == "__main__":
    main()
