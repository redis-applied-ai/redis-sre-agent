"""Top-level `worker` CLI command."""

from __future__ import annotations

import asyncio

import click
from docket import Worker

from redis_sre_agent.core.config import settings
from redis_sre_agent.core.docket_tasks import register_sre_tasks
from redis_sre_agent.observability.tracing import setup_tracing


# TODO: rename start
@click.command()
@click.option("--concurrency", "-c", default=4, help="Number of concurrent tasks")
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
        if not settings.redis_url or not settings.redis_url.get_secret_value():
            click.echo("\u274c Redis URL not configured")
            sys.exit(1)

        redis_url = settings.redis_url.get_secret_value()
        logger.info("Starting SRE Docket worker connected to Redis")

        # OpenTelemetry tracing with centralized setup (includes Redis hooks for filtering)
        setup_tracing("redis-sre-worker", "0.1.0")

        # Start a Prometheus metrics HTTP server to expose worker metrics (incl. LLM tokens)
        try:
            from prometheus_client import start_http_server

            start_http_server(9101)
            logger.info("Prometheus metrics server started on :9101")
        except Exception as _e:
            logger.warning(f"Failed to start Prometheus metrics server in worker: {_e}")

        # Initialize Redis infrastructure (creates indices if they don't exist)
        try:
            from redis_sre_agent.core.redis import create_indices

            indices_created = await create_indices()
            if indices_created:
                logger.info("✅ Redis indices initialized")
            else:
                logger.warning("⚠️ Failed to create some Redis indices")
        except Exception as e:
            logger.error(f"Failed to initialize Redis indices: {e}")
            # Continue anyway - some functionality may still work

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
        click.echo("\nSRE worker stopped by user")
    except Exception as e:
        click.echo(f"Unexpected worker error: {e}")
        raise
