#!/usr/bin/env python3
"""
Docket worker for processing SRE background tasks.
Run with: uv run python -m redis_sre_agent.worker
"""

import asyncio
import logging
import sys
from datetime import timedelta

from docket import Worker

from redis_sre_agent.core.config import settings
from redis_sre_agent.core.tasks import register_sre_tasks

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    """Run the SRE Docket worker."""

    if not settings.redis_url:
        logger.error("❌ Redis URL not configured")
        sys.exit(1)

    logger.info(f"Starting SRE Docket worker connected to {settings.redis_url}")

    try:
        # Register tasks first
        await register_sre_tasks()
        logger.info("✅ SRE tasks registered with Docket")

        # Start the worker
        logger.info("✅ Worker started, waiting for SRE tasks...")
        logger.info("Press Ctrl+C to stop")

        await Worker.run(
            docket_name="sre_docket",
            url=settings.redis_url,
            concurrency=2,  # Allow 2 concurrent SRE tasks
            redelivery_timeout=timedelta(seconds=120),  # 2 minute timeout for SRE tasks
            tasks=["redis_sre_agent.core.tasks:SRE_TASK_COLLECTION"],
        )
    except Exception as e:
        logger.error(f"❌ Worker error: {e}")
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 SRE worker stopped by user")
    except Exception as e:
        logger.error(f"💥 Unexpected worker error: {e}")
        raise
