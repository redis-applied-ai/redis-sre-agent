"""Top-level `worker` CLI command.

Extracted from main.py to modularize CLI.
"""

from __future__ import annotations

import asyncio

import click
from docket import Worker

from redis_sre_agent.core.config import settings
from redis_sre_agent.core.docket_tasks import register_sre_tasks


# TODO: rename start
@click.command()
@click.option("--concurrency", "-c", default=2, help="Number of concurrent tasks")
def worker(concurrency: int):
    """Start the background worker."""

    async def _worker():
        import inspect
        import logging
        import sys
        from datetime import timedelta

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(name)s %(levelname)s %(message)s",
            datefmt="%H:%M:%S",
        )
        logger = logging.getLogger(__name__)

        # Validate Redis URL
        if (
            not settings.redis_url
            or not getattr(settings.redis_url, "get_secret_value", lambda: "")()
        ):
            click.echo("\u274c Redis URL not configured")
            sys.exit(1)

        redis_url = settings.redis_url.get_secret_value()
        logger.info("Starting SRE Docket worker connected to Redis")

        try:
            # Register tasks first (support both sync and async implementations)
            reg = register_sre_tasks()
            if inspect.isawaitable(reg):
                await reg
            click.echo("\u2705 SRE tasks registered with Docket")

            # Start the worker
            click.echo("\u2705 Worker started, waiting for SRE tasks... Press Ctrl+C to stop")
            await Worker.run(
                docket_name="sre_docket",
                url=redis_url,
                concurrency=concurrency,
                redelivery_timeout=timedelta(seconds=settings.task_timeout),
                tasks=["redis_sre_agent.core.docket_tasks:SRE_TASK_COLLECTION"],
            )
        except Exception as e:
            logger.error(f"\u274c Worker error: {e}")
            raise

    try:
        asyncio.run(_worker())
    except KeyboardInterrupt:
        click.echo("\n\ud83d\udc4b SRE worker stopped by user")
    except Exception as e:
        click.echo(f"\ud83d\udca5 Unexpected worker error: {e}")
        raise
