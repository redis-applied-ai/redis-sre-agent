"""CLI commands for data pipeline management."""

import asyncio
import json
from pathlib import Path

import click

from ..pipelines.orchestrator import PipelineOrchestrator


@click.group()
def pipeline():
    """Data pipeline commands for scraping and ingestion."""
    pass


@pipeline.command()
@click.option("--artifacts-path", default="./artifacts", help="Path to store artifacts")
@click.option(
    "--scrapers",
    help="Comma-separated list of scrapers to run (redis_docs,redis_runbooks,runbook_generator)",
)
def scrape(artifacts_path: str, scrapers: str):
    """Run the scraping pipeline to collect SRE documents."""
    click.echo("🔍 Starting scraping pipeline...")

    scraper_list = None
    if scrapers:
        scraper_list = [s.strip() for s in scrapers.split(",")]

    async def run_scraping():
        orchestrator = PipelineOrchestrator(artifacts_path)
        try:
            results = await orchestrator.run_scraping_pipeline(scraper_list)

            click.echo("✅ Scraping completed!")
            click.echo(f"   Batch date: {results['batch_date']}")
            click.echo(f"   Total documents: {results['total_documents']}")
            click.echo(f"   Scrapers run: {', '.join(results['scrapers_run'])}")

            # Show scraper results
            for scraper_name, scraper_result in results["scraper_results"].items():
                if "error" in scraper_result:
                    click.echo(f"   ❌ {scraper_name}: {scraper_result['error']}")
                else:
                    click.echo(
                        f"   ✅ {scraper_name}: {scraper_result['documents_scraped']} documents"
                    )

            return results

        except Exception as e:
            click.echo(f"❌ Scraping failed: {e}")
            raise

    return asyncio.run(run_scraping())


@pipeline.command()
@click.option("--batch-date", help="Batch date to ingest (YYYY-MM-DD), defaults to today")
@click.option("--artifacts-path", default="./artifacts", help="Path to artifacts")
def ingest(batch_date: str, artifacts_path: str):
    """Run the ingestion pipeline to process scraped documents."""
    click.echo("📥 Starting ingestion pipeline...")

    async def run_ingestion():
        orchestrator = PipelineOrchestrator(artifacts_path)
        try:
            results = await orchestrator.run_ingestion_pipeline(batch_date)

            click.echo("✅ Ingestion completed!")
            click.echo(f"   Batch date: {results['batch_date']}")
            click.echo(f"   Documents processed: {results['documents_processed']}")
            click.echo(f"   Chunks created: {results['chunks_created']}")
            click.echo(f"   Chunks indexed: {results['chunks_indexed']}")

            # Show category breakdown
            for category, stats in results["categories_processed"].items():
                click.echo(
                    f"   📂 {category}: {stats['documents_processed']} docs, {stats['chunks_indexed']} chunks"
                )
                if stats["errors"]:
                    click.echo(f"      ⚠️  {len(stats['errors'])} errors")

            return results

        except Exception as e:
            click.echo(f"❌ Ingestion failed: {e}")
            raise

    return asyncio.run(run_ingestion())


@pipeline.command()
@click.option("--artifacts-path", default="./artifacts", help="Path to store artifacts")
@click.option("--scrapers", help="Comma-separated list of scrapers to run")
def full(artifacts_path: str, scrapers: str):
    """Run the complete pipeline: scraping + ingestion."""
    click.echo("🚀 Starting full pipeline (scraping + ingestion)...")

    scraper_list = None
    if scrapers:
        scraper_list = [s.strip() for s in scrapers.split(",")]

    async def run_full_pipeline():
        orchestrator = PipelineOrchestrator(artifacts_path)
        try:
            results = await orchestrator.run_full_pipeline(scraper_list)

            click.echo("✅ Full pipeline completed!")
            click.echo(f"   Batch date: {results['batch_date']}")

            # Scraping results
            if "scraping" in results:
                scraping = results["scraping"]
                click.echo(f"   📥 Scraping: {scraping['total_documents']} documents")

                for scraper_name, scraper_result in scraping["scraper_results"].items():
                    if "error" in scraper_result:
                        click.echo(f"      ❌ {scraper_name}: {scraper_result['error']}")
                    else:
                        click.echo(
                            f"      ✅ {scraper_name}: {scraper_result['documents_scraped']} documents"
                        )

            # Ingestion results
            if "ingestion" in results:
                ingestion = results["ingestion"]
                if ingestion.get("skipped"):
                    click.echo(f"   📤 Ingestion: Skipped ({ingestion.get('reason', 'unknown')})")
                else:
                    click.echo(
                        f"   📤 Ingestion: {ingestion['documents_processed']} docs → {ingestion['chunks_indexed']} chunks"
                    )

            return results

        except Exception as e:
            click.echo(f"❌ Full pipeline failed: {e}")
            raise

    return asyncio.run(run_full_pipeline())


@pipeline.command()
@click.option("--artifacts-path", default="./artifacts", help="Path to artifacts")
def status(artifacts_path: str):
    """Show pipeline status and available batches."""
    click.echo("📊 Pipeline Status")

    async def show_status():
        orchestrator = PipelineOrchestrator(artifacts_path)
        try:
            status_info = await orchestrator.get_pipeline_status()

            click.echo(f"   Artifacts path: {status_info['artifacts_path']}")
            click.echo(f"   Current batch: {status_info['current_batch_date']}")
            click.echo(f"   Available batches: {len(status_info['available_batches'])}")

            # Show recent batches
            if status_info["available_batches"]:
                click.echo("   Recent batches:")
                for batch in status_info["available_batches"][-5:]:
                    click.echo(f"      • {batch}")

            # Show scraper info
            click.echo("   Scrapers:")
            for name, scraper_info in status_info["scrapers"].items():
                click.echo(f"      • {name}: {scraper_info['source']}")

            # Show ingestion info
            if "batches_ingested" in status_info["ingestion"]:
                click.echo(f"   Ingested batches: {status_info['ingestion']['batches_ingested']}")

            return status_info

        except Exception as e:
            click.echo(f"❌ Status check failed: {e}")
            raise

    return asyncio.run(show_status())


@pipeline.command()
@click.option("--batch-date", required=True, help="Batch date to show details for")
@click.option("--artifacts-path", default="./artifacts", help="Path to artifacts")
def show_batch(batch_date: str, artifacts_path: str):
    """Show detailed information about a specific batch."""
    click.echo(f"📋 Batch Details: {batch_date}")

    from ..pipelines.scraper.base import ArtifactStorage

    storage = ArtifactStorage(artifacts_path)

    # Show batch manifest
    manifest = storage.get_batch_manifest(batch_date)
    if not manifest:
        click.echo(f"❌ No manifest found for batch {batch_date}")
        return

    click.echo(f"   Created: {manifest['created_at']}")
    click.echo(f"   Total documents: {manifest['total_documents']}")
    click.echo("   Categories:")
    for category, count in manifest["categories"].items():
        click.echo(f"      • {category}: {count} documents")

    click.echo("   Document types:")
    for doc_type, count in manifest["document_types"].items():
        click.echo(f"      • {doc_type}: {count} documents")

    # Check for ingestion manifest
    batch_path = Path(artifacts_path) / batch_date
    ingestion_manifest = batch_path / "ingestion_manifest.json"
    if ingestion_manifest.exists():
        with open(ingestion_manifest) as f:
            ingestion_data = json.load(f)

        click.echo("   Ingestion:")
        click.echo(
            f"      Status: {'✅ Success' if ingestion_data.get('success') else '❌ Failed'}"
        )
        click.echo(f"      Processed: {ingestion_data.get('documents_processed', 0)} docs")
        click.echo(f"      Indexed: {ingestion_data.get('chunks_indexed', 0)} chunks")
    else:
        click.echo("   Ingestion: ⏳ Not ingested yet")


@pipeline.command()
@click.option("--keep-days", default=30, help="Number of days of batches to keep")
@click.option("--artifacts-path", default="./artifacts", help="Path to artifacts")
@click.confirmation_option(prompt="Are you sure you want to cleanup old batches?")
def cleanup(keep_days: int, artifacts_path: str):
    """Clean up old batch directories."""
    click.echo(f"🧹 Cleaning up batches older than {keep_days} days...")

    async def run_cleanup():
        orchestrator = PipelineOrchestrator(artifacts_path)
        try:
            results = await orchestrator.cleanup_old_batches(keep_days)

            click.echo("✅ Cleanup completed!")
            click.echo(f"   Cutoff date: {results['cutoff_date']}")
            click.echo(f"   Batches removed: {len(results['batches_removed'])}")
            click.echo(f"   Batches kept: {len(results['batches_kept'])}")

            if results["batches_removed"]:
                click.echo("   Removed:")
                for batch in results["batches_removed"]:
                    click.echo(f"      • {batch}")

            if results["errors"]:
                click.echo("   Errors:")
                for error in results["errors"]:
                    click.echo(f"      ❌ {error}")

            return results

        except Exception as e:
            click.echo(f"❌ Cleanup failed: {e}")
            raise

    return asyncio.run(run_cleanup())


@pipeline.command()
@click.option("--url", help="Add a single URL to generate a runbook from")
@click.option("--test-url", help="Test URL extraction without generating full runbook")
@click.option("--list-urls", is_flag=True, help="List currently configured URLs")
@click.option("--artifacts-path", default="./artifacts", help="Path to store artifacts")
def runbooks(url: str, test_url: str, list_urls: bool, artifacts_path: str):
    """Generate standardized runbooks from web sources using GPT-4o."""

    async def run_runbook_operations():
        from ..pipelines.orchestrator import PipelineOrchestrator

        orchestrator = PipelineOrchestrator(artifacts_path)
        generator = orchestrator.scrapers["runbook_generator"]

        if list_urls:
            click.echo("📋 Currently configured runbook URLs:")
            for i, configured_url in enumerate(generator.get_configured_urls(), 1):
                click.echo(f"   {i}. {configured_url}")
            return

        if test_url:
            click.echo(f"🧪 Testing URL extraction: {test_url}")
            result = await generator.test_url_extraction(test_url)

            if result["success"]:
                click.echo("   ✅ Success!")
                click.echo(f"   📊 Content length: {result['content_length']} chars")
                click.echo(f"   🏷️  Source type: {result['source_type']}")
                click.echo(f"   👁️  Preview: {result['content_preview'][:200]}...")
            else:
                click.echo(f"   ❌ Failed: {result.get('error', 'Unknown error')}")
            return

        if url:
            # Add single URL and generate runbook
            click.echo(f"📝 Adding URL and generating runbook: {url}")

            added = await generator.add_runbook_url(url)
            if added:
                click.echo("   ✅ URL added to configuration")
            else:
                click.echo("   ℹ️  URL already in configuration")

            # Generate runbook for just this URL
            temp_config = generator.config.copy()
            temp_config["runbook_urls"] = [url]

            from ..pipelines.scraper.base import ArtifactStorage

            temp_storage = ArtifactStorage(artifacts_path)
            temp_generator = generator.__class__(temp_storage, temp_config)

            documents = await temp_generator.scrape()

            if documents:
                doc = documents[0]
                click.echo(f"   ✅ Generated runbook: {doc.title}")
                click.echo(f"   📂 Category: {doc.category}")
                click.echo(f"   🚨 Severity: {doc.severity}")
                click.echo(f"   📏 Length: {len(doc.content)} characters")

                # Save the document
                path = temp_storage.save_document(doc)
                click.echo(f"   💾 Saved to: {path}")
            else:
                click.echo(f"   ❌ Failed to generate runbook from {url}")

            return

        # Default: run all configured URLs
        click.echo("🚀 Generating runbooks from all configured URLs...")

        try:
            results = await generator.run_scraping_job()

            click.echo("✅ Runbook generation completed!")
            click.echo(f"   📝 Documents generated: {results['documents_scraped']}")
            click.echo(f"   💾 Documents saved: {results['documents_saved']}")
            click.echo(f"   📅 Batch date: {results['batch_date']}")

            # Show category breakdown
            for category, count in results["categories"].items():
                click.echo(f"   📂 {category}: {count} runbooks")

        except Exception as e:
            click.echo(f"❌ Runbook generation failed: {e}")
            raise

    return asyncio.run(run_runbook_operations())


@pipeline.command()
@click.option("--source-dir", "-s", default="source_documents", help="Source documents directory")
@click.option(
    "--dry-run", is_flag=True, help="Show what would be ingested without actually ingesting"
)
@click.option("--artifacts-path", default="./artifacts", help="Path to artifacts storage")
def ingest_sources(source_dir: str, dry_run: bool, artifacts_path: str):
    """Ingest runbooks from source_documents directory using existing ingestion pipeline."""

    async def run_source_ingestion():
        from pathlib import Path

        from ..pipelines.ingestion.processor import IngestionPipeline
        from ..pipelines.scraper.base import ArtifactStorage

        source_path = Path(source_dir)
        if not source_path.exists():
            click.echo(f"❌ Source directory does not exist: {source_path}")
            return

        click.echo(f"📂 Ingesting from: {source_path}")

        if dry_run:
            # Just list what would be processed
            markdown_files = list(source_path.rglob("*.md"))
            markdown_files = [f for f in markdown_files if f.name.lower() != "readme.md"]

            click.echo(f"📋 Would process {len(markdown_files)} files:")
            for md_file in markdown_files:
                click.echo(f"   • {md_file.relative_to(source_path)}")
            return

        try:
            # Use existing ingestion pipeline
            storage = ArtifactStorage(artifacts_path)
            pipeline = IngestionPipeline(storage)

            results = await pipeline.ingest_source_documents(source_path)

            successful = [r for r in results if r["status"] == "success"]
            failed = [r for r in results if r["status"] == "error"]

            click.echo("✅ Source document ingestion completed!")
            click.echo(f"   📝 Successfully ingested: {len(successful)} documents")

            if successful:
                total_chunks = sum(r.get("chunks_indexed", 0) for r in successful)
                click.echo(f"   📦 Total chunks indexed: {total_chunks}")

                click.echo("   📚 Documents processed:")
                for success in successful[:5]:  # Show first 5
                    chunks = success.get("chunks_indexed", 0)
                    click.echo(f"      • {success['title']} ({chunks} chunks)")
                if len(successful) > 5:
                    click.echo(f"      ... and {len(successful) - 5} more")

            if failed:
                click.echo(f"   ❌ Failed to ingest: {len(failed)} documents")
                for failure in failed:
                    click.echo(f"      • {failure['file']}: {failure['error']}")

        except Exception as e:
            click.echo(f"❌ Source ingestion failed: {e}")
            raise

    return asyncio.run(run_source_ingestion())


if __name__ == "__main__":
    pipeline()
