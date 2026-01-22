"""Top-level `worker` CLI command group with subcommands."""

from __future__ import annotations

import asyncio
import os
import signal
import socket
import sys

import click
import psutil
from docket import Docket, Worker

from redis_sre_agent.core.config import settings
from redis_sre_agent.core.docket_tasks import register_sre_tasks
from redis_sre_agent.observability.tracing import setup_tracing


def _get_active_workers() -> list:
    """Get list of active Docket workers.

    Validates Redis configuration, connects to Redis, and retrieves
    the list of active workers from Docket.

    Returns:
        List of active Worker objects.

    Raises:
        SystemExit: If Redis URL is not configured.
        Exception: If Redis connection or worker retrieval fails.
    """
    if not settings.redis_url or not settings.redis_url.get_secret_value():
        click.echo("✗ Redis URL not configured")
        sys.exit(1)

    redis_url = settings.redis_url.get_secret_value()

    import redis

    with redis.Redis.from_url(redis_url) as r:
        r.ping()

        async def fetch_workers():
            async with Docket(name="sre_docket", url=redis_url) as d:
                return await d.workers()

        return asyncio.run(fetch_workers())


def _validate_worker_process(pid: int, worker_name: str) -> tuple[bool, str]:
    """Validate that a PID belongs to a legitimate worker process.

    Security check to prevent arbitrary process termination via crafted worker names.

    Args:
        pid: The process ID to validate.
        worker_name: The full worker name from Docket (format: HOSTNAME#PID).

    Returns:
        Tuple of (is_valid, reason_message).
    """
    # Check 1: Verify the hostname prefix matches this machine
    # Worker name format: HOSTNAME#PID
    if "#" not in worker_name:
        return False, "Invalid worker name format (missing '#' separator)"

    hostname_prefix = worker_name.rsplit("#", 1)[0]
    current_hostname = socket.gethostname()

    if hostname_prefix != current_hostname:
        return (
            False,
            f"Worker hostname '{hostname_prefix}' does not match this machine '{current_hostname}'",
        )

    # Check 2: Verify the process exists and is a Python process
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return False, "Process does not exist"
    except psutil.AccessDenied:
        return False, "Cannot access process information (permission denied)"

    # Check 3: Verify the process is a Python interpreter
    try:
        proc_name = proc.name().lower()
        if "python" not in proc_name:
            return False, f"Process is not a Python process (found: {proc_name})"
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False, "Cannot verify process name"

    # Check 4: Verify the command line contains worker-related identifiers
    try:
        cmdline = " ".join(proc.cmdline()).lower()
        # Look for indicators that this is our worker process
        worker_indicators = ["docket", "redis-sre-agent", "redis_sre_agent"]
        if not any(indicator in cmdline for indicator in worker_indicators):
            return False, "Process command line does not match expected worker pattern"
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False, "Cannot verify process command line"

    return True, "Process validated as legitimate worker"


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

    try:
        workers = _get_active_workers()
        click.echo("✓ Redis: Connected")

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
    try:
        workers = _get_active_workers()

        if not workers:
            click.echo("✗ No workers are currently running")
            return

        # Stop each worker by sending SIGTERM
        for w in workers:
            # Worker name format: HOSTNAME#PID (e.g., "HQM60FP16H-machine#41405")
            try:
                pid = int(w.name.split("#")[-1])
            except ValueError:
                click.echo(f"⚠ Could not parse PID from worker name: {w.name}")
                continue

            # Security: Validate that the PID belongs to a legitimate worker process
            # This prevents arbitrary process termination via crafted worker names
            is_valid, reason = _validate_worker_process(pid, w.name)
            if not is_valid:
                click.echo(f"⚠ Skipping worker {w.name}: {reason}")
                continue

            try:
                click.echo(f"Stopping worker {w.name} (PID {pid})...")
                os.kill(pid, signal.SIGTERM)
                click.echo(f"✓ Sent SIGTERM to worker (PID {pid})")
            except ProcessLookupError:
                click.echo(f"⚠ Process {pid} not found (worker may have already stopped)")
            except PermissionError:
                click.echo(f"✗ Permission denied to stop process {pid}")

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)
