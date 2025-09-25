"""Pipeline orchestrator for managing scraping and ingestion workflows."""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .ingestion.processor import IngestionPipeline
from .scraper.base import ArtifactStorage
from .scraper.redis_docs import RedisDocsScraper, RedisRunbookScraper
from .scraper.redis_kb import RedisKBScraper
from .scraper.redis_cloud_api import RedisCloudAPIScraper
from .scraper.runbook_generator import RunbookGenerator

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Orchestrates the complete data pipeline from scraping to ingestion."""

    def __init__(
        self,
        artifacts_path: str = "./artifacts",
        config: Optional[Dict[str, Any]] = None,
        knowledge_settings=None,
    ):
        self.artifacts_path = Path(artifacts_path)
        self.config = config or {}
        self.knowledge_settings = knowledge_settings

        # Initialize storage
        self.storage = ArtifactStorage(self.artifacts_path)

        # Initialize scrapers
        self.scrapers = {
            "redis_docs": RedisDocsScraper(self.storage, self.config.get("redis_docs", {})),
            "redis_runbooks": RedisRunbookScraper(
                self.storage, self.config.get("redis_runbooks", {})
            ),
            "redis_kb": RedisKBScraper(self.storage, self.config.get("redis_kb", {})),
            "redis_cloud_api": RedisCloudAPIScraper(
                self.storage, self.config.get("redis_cloud_api", {})
            ),
            "runbook_generator": RunbookGenerator(
                self.storage, self.config.get("runbook_generator", {})
            ),
        }

        # Initialize ingestion pipeline with knowledge settings
        self.ingestion = IngestionPipeline(
            self.storage, self.config.get("ingestion", {}), knowledge_settings
        )

    async def run_scraping_pipeline(self, scrapers: Optional[List[str]] = None) -> Dict[str, Any]:
        """Run the complete scraping pipeline."""
        logger.info("Starting scraping pipeline")

        scrapers_to_run = scrapers or list(self.scrapers.keys())

        pipeline_results = {
            "pipeline_type": "scraping",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "batch_date": self.storage.current_date,
            "scrapers_run": scrapers_to_run,
            "scraper_results": {},
            "total_documents": 0,
            "success": False,
        }

        try:
            all_documents = []

            # Run each scraper
            for scraper_name in scrapers_to_run:
                if scraper_name not in self.scrapers:
                    logger.warning(f"Unknown scraper: {scraper_name}")
                    continue

                logger.info(f"Running scraper: {scraper_name}")
                scraper = self.scrapers[scraper_name]

                try:
                    scraper_result = await scraper.run_scraping_job()
                    pipeline_results["scraper_results"][scraper_name] = scraper_result

                    # Collect documents for manifest
                    all_documents.extend(scraper.scraped_documents)

                    logger.info(
                        f"Scraper {scraper_name} completed: {scraper_result['documents_scraped']} documents"
                    )

                except Exception as e:
                    logger.error(f"Scraper {scraper_name} failed: {e}")
                    pipeline_results["scraper_results"][scraper_name] = {
                        "error": str(e),
                        "documents_scraped": 0,
                    }

            # Save batch manifest
            if all_documents:
                manifest_path = self.storage.save_batch_manifest(all_documents)
                pipeline_results["manifest_path"] = str(manifest_path)
                pipeline_results["total_documents"] = len(all_documents)

            pipeline_results["completed_at"] = datetime.now(timezone.utc).isoformat()
            pipeline_results["success"] = True

            logger.info(
                f"Scraping pipeline completed: {pipeline_results['total_documents']} total documents"
            )

        except Exception as e:
            logger.error(f"Scraping pipeline failed: {e}")
            pipeline_results["error"] = str(e)
            pipeline_results["completed_at"] = datetime.now(timezone.utc).isoformat()
            raise

        return pipeline_results

    async def run_ingestion_pipeline(self, batch_date: Optional[str] = None) -> Dict[str, Any]:
        """Run the ingestion pipeline for a specific batch."""
        target_batch = batch_date or self.storage.current_date

        logger.info(f"Starting ingestion pipeline for batch: {target_batch}")

        try:
            ingestion_results = await self.ingestion.ingest_batch(target_batch)

            logger.info(f"Ingestion pipeline completed for batch {target_batch}")
            return ingestion_results

        except Exception as e:
            logger.error(f"Ingestion pipeline failed for batch {target_batch}: {e}")
            raise

    async def run_full_pipeline(self, scrapers: Optional[List[str]] = None) -> Dict[str, Any]:
        """Run complete pipeline: scraping + ingestion."""
        logger.info("Starting full pipeline (scraping + ingestion)")

        full_results = {
            "pipeline_type": "full",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "batch_date": self.storage.current_date,
            "success": False,
        }

        try:
            # Stage 1: Scraping
            logger.info("Stage 1: Running scraping pipeline")
            scraping_results = await self.run_scraping_pipeline(scrapers)
            full_results["scraping"] = scraping_results

            # Only proceed to ingestion if scraping was successful and found documents
            if scraping_results["success"] and scraping_results["total_documents"] > 0:
                # Stage 2: Ingestion
                logger.info("Stage 2: Running ingestion pipeline")
                ingestion_results = await self.run_ingestion_pipeline()
                full_results["ingestion"] = ingestion_results

                full_results["success"] = ingestion_results["success"]
            else:
                logger.warning("Skipping ingestion - no documents scraped successfully")
                full_results["ingestion"] = {"skipped": True, "reason": "no_documents_scraped"}

            full_results["completed_at"] = datetime.now(timezone.utc).isoformat()

            logger.info(f"Full pipeline completed: {full_results}")

        except Exception as e:
            logger.error(f"Full pipeline failed: {e}")
            full_results["error"] = str(e)
            full_results["completed_at"] = datetime.now(timezone.utc).isoformat()
            raise

        return full_results

    async def get_pipeline_status(self) -> Dict[str, Any]:
        """Get current status of pipeline components."""
        status = {
            "artifacts_path": str(self.artifacts_path),
            "current_batch_date": self.storage.current_date,
            "available_batches": self.storage.list_available_batches(),
            "scrapers": {},
            "ingestion": {},
        }

        # Check scraper status
        for name, scraper in self.scrapers.items():
            status["scrapers"][name] = {
                "source": scraper.get_source_name(),
                "config": scraper.config,
            }

        # Check ingestion status
        try:
            ingested_batches = await self.ingestion.list_ingested_batches()
            status["ingestion"] = {
                "batches_ingested": len([b for b in ingested_batches if b.get("success", False)]),
                "recent_batches": ingested_batches[:5],  # Most recent 5
            }
        except Exception as e:
            status["ingestion"]["error"] = str(e)

        return status

    async def cleanup_old_batches(self, keep_days: int = 30) -> Dict[str, Any]:
        """Clean up old batch directories to save space."""
        logger.info(f"Cleaning up batches older than {keep_days} days")

        from datetime import datetime, timedelta

        cutoff_date = datetime.now() - timedelta(days=keep_days)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d")

        cleanup_results = {
            "cutoff_date": cutoff_str,
            "batches_removed": [],
            "batches_kept": [],
            "errors": [],
        }

        try:
            available_batches = self.storage.list_available_batches()

            for batch_date in available_batches:
                if batch_date < cutoff_str:
                    # Remove old batch
                    batch_path = self.storage.base_path / batch_date
                    try:
                        import shutil

                        shutil.rmtree(batch_path)
                        cleanup_results["batches_removed"].append(batch_date)
                        logger.info(f"Removed old batch: {batch_date}")
                    except Exception as e:
                        error_msg = f"Failed to remove batch {batch_date}: {str(e)}"
                        cleanup_results["errors"].append(error_msg)
                        logger.error(error_msg)
                else:
                    cleanup_results["batches_kept"].append(batch_date)

            logger.info(
                f"Cleanup completed: removed {len(cleanup_results['batches_removed'])} batches"
            )

        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            cleanup_results["error"] = str(e)
            raise

        return cleanup_results


# Convenience functions for CLI usage


async def run_scraping_only(
    artifacts_path: str = "./artifacts", config: Optional[Dict[str, Any]] = None
):
    """Run only the scraping pipeline."""
    orchestrator = PipelineOrchestrator(artifacts_path, config)
    return await orchestrator.run_scraping_pipeline()


async def run_ingestion_only(
    batch_date: str, artifacts_path: str = "./artifacts", config: Optional[Dict[str, Any]] = None
):
    """Run only the ingestion pipeline for a specific batch."""
    orchestrator = PipelineOrchestrator(artifacts_path, config)
    return await orchestrator.run_ingestion_pipeline(batch_date)


async def run_full_pipeline(
    artifacts_path: str = "./artifacts", config: Optional[Dict[str, Any]] = None
):
    """Run the complete pipeline."""
    orchestrator = PipelineOrchestrator(artifacts_path, config)
    return await orchestrator.run_full_pipeline()
