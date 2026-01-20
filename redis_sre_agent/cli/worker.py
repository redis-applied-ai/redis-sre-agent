"""Top-level `worker` CLI command group with subcommands."""

from __future__ import annotations

import asyncio
import os
import signal
import sys

import click
from docket import Docket, Worker

from redis_sre_agent.core.config import settings
from redis_sre_agent.core.docket_tasks import register_sre_tasks
from redis_sre_agent.observability.tracing import setup_tracing


@click.group()
def worker():
    """Manage the Docket worker.

    Commands for starting, stopping, and monitoring the worker process.
    """
    pass


@worker.command()
@click.option("--concurrency", "-c", default=4, help="Number of concurrent tasks")
def start(concurrency: int):
    """Start the background worker."""

    async def _worker():
        import inspect
        import logging
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


@worker.command()
@click.option("--verbose", "-v", is_flag=True, help="Show detailed task list for each worker")
def status(verbose: bool):
    """Check the status of the Docket worker."""
    click.echo("Checking worker status...")

    # Check Redis connection (required for worker)
    if not settings.redis_url or not settings.redis_url.get_secret_value():
        click.echo("✗ Redis URL not configured")
        sys.exit(1)

    redis_url = settings.redis_url.get_secret_value()

    try:
        import redis

        r = redis.Redis.from_url(redis_url)
        r.ping()
        click.echo("✓ Redis: Connected")

        # Check for active workers by looking at Docket's worker registry
        async def get_workers():
            async with Docket(name="sre_docket", url=redis_url) as d:
                return await d.workers()

        workers = asyncio.run(get_workers())

        if workers:
            click.echo(f"✓ Workers: {len(workers)} active")
            for w in workers:
                click.echo(f"  │  Worker name: {w.name}")
                click.echo(f"  │  Registered tasks: {len(w.tasks)}")
                if verbose:
                    for task in w.tasks:
                        click.echo(f"  │   └─ Task name: {task}")
        else:
            click.echo("✗ Workers: No active workers found")

    except Exception as e:
        click.echo(f"✗ Redis: Failed to connect ({e})")
        click.echo("  Worker cannot run without Redis")
        sys.exit(1)


@worker.command()
def stop():
    """Stop the Docket worker.

    Workers are stopped by sending SIGTERM to the process (graceful shutdown).
    """
    # Check Redis connection
    if not settings.redis_url or not settings.redis_url.get_secret_value():
        click.echo("✗ Redis URL not configured")
        sys.exit(1)

    redis_url = settings.redis_url.get_secret_value()

    try:
        import redis

        r = redis.Redis.from_url(redis_url)
        r.ping()

        async def get_workers():
            async with Docket(name="sre_docket", url=redis_url) as d:
                return await d.workers()

        workers = asyncio.run(get_workers())

        if not workers:
            click.echo("✗ No workers are currently running")
            return

        # Stop each worker by sending SIGTERM
        for w in workers:
            # Worker name format: HOSTNAME#PID (e.g., "HQM60FP16H-machine#41405")
            try:
                pid = int(w.name.split("#")[-1])
                click.echo(f"Stopping worker {w.name} (PID {pid})...")
                os.kill(pid, signal.SIGTERM)
                click.echo(f"✓ Sent SIGTERM to worker (PID {pid})")
            except ValueError:
                click.echo(f"⚠ Could not parse PID from worker name: {w.name}")
            except ProcessLookupError:
                click.echo(f"⚠ Process {pid} not found (worker may have already stopped)")
            except PermissionError:
                click.echo(f"✗ Permission denied to stop process {pid}")

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)
