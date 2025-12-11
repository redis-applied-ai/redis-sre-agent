"""Top-level `worker` CLI command."""

from __future__ import annotations

import asyncio
import os

import click
from docket import Worker
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.openai import OpenAIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from redis_sre_agent.core.config import settings
from redis_sre_agent.core.docket_tasks import register_sre_tasks


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

        # OpenTelemetry tracing (enabled when OTEL endpoint is present)
        otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        if not otlp_endpoint:
            logger.info("OTel tracing disabled in worker (no OTEL_EXPORTER_OTLP_ENDPOINT)")
        else:
            resource = Resource.create(
                {
                    "service.name": "redis-sre-worker",
                    "service.version": "0.1.0",
                }
            )
            provider = TracerProvider(resource=resource)
            exporter = OTLPSpanExporter(
                endpoint=otlp_endpoint,
                headers=os.environ.get("OTEL_EXPORTER_OTLP_HEADERS"),
            )
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)

            # Libraries
            RedisInstrumentor().instrument()
            HTTPXClientInstrumentor().instrument()
            AioHttpClientInstrumentor().instrument()
            AsyncioInstrumentor().instrument()
            OpenAIInstrumentor().instrument()

            logger.info("OTel tracing enabled in worker (redis/httpx/aiohttp/asyncio)")

        # Start a Prometheus metrics HTTP server to expose worker metrics (incl. LLM tokens)
        try:
            from prometheus_client import start_http_server

            start_http_server(9101)
            logger.info("Prometheus metrics server started on :9101")
        except Exception as _e:
            logger.warning(f"Failed to start Prometheus metrics server in worker: {_e}")

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
