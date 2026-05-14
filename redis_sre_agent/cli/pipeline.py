"""CLI commands for data pipeline management."""

import asyncio
import json
from datetime import datetime
from pathlib import Path

import click

from redis_sre_agent.cli.logging_utils import log_cli_exception

from ..pipelines.orchestrator import PipelineOrchestrator


def _parse_scraper_list(scrapers: str | None) -> list[str] | None:
    """Split a comma-delimited scraper list into normalized names."""
    if not scrapers:
        return None
    return [scraper.strip() for scraper in scrapers.split(",")]


def _validate_batch_date(batch_date: str | None) -> str | None:
    """Validate a YYYY-MM-DD batch date override."""
    if not batch_date:
        return None
    try:
        datetime.strptime(batch_date, "%Y-%m-%d")
    except ValueError as exc:
        raise click.BadParameter("Use YYYY-MM-DD") from exc
    return batch_date


def _echo_scraper_results(scraper_results: dict, indent: str = "   ") -> None:
    """Print scraper success and error summaries."""
    for scraper_name, scraper_result in scraper_results.items():
        if "error" in scraper_result:
            click.echo(f"{indent}❌ {scraper_name}: {scraper_result['error']}")
        else:
            click.echo(
                f"{indent}✅ {scraper_name}: {scraper_result['documents_scraped']} documents"
            )


def _echo_source_document_changes(
    source_changes: dict | None,
    *,
    verbose: bool,
    indent: str = "   ",
) -> None:
    """Print source-document add/update/delete summaries."""
    source_changes = source_changes or {}
    if not any(source_changes.get(key, 0) for key in ("added", "updated", "deleted")):
        return
    click.echo(f"{indent}🗂️ Source document changes:")
    click.echo(
        f"{indent}   "
        f"added={source_changes.get('added', 0)} "
        f"updated={source_changes.get('updated', 0)} "
        f"deleted={source_changes.get('deleted', 0)} "
        f"unchanged={source_changes.get('unchanged', 0)}"
    )
    if verbose:
        for change in source_changes.get("files", []):
            click.echo(f"{indent}   • {change['action']}: {change['path']}")


def _merge_source_document_changes(source_changes_list: list[dict | None]) -> dict | None:
    """Aggregate source-document change summaries across multiple results."""
    merged = {
        "added": 0,
        "updated": 0,
        "deleted": 0,
        "unchanged": 0,
        "files": [],
        "scope_prefixes": [],
    }
    saw_changes = False
    for source_changes in source_changes_list:
        if not source_changes:
            continue
        saw_changes = True
        for key in ("added", "updated", "deleted", "unchanged"):
            merged[key] += int(source_changes.get(key, 0) or 0)
        merged["files"].extend(source_changes.get("files", []))
        for scope_prefix in source_changes.get("scope_prefixes", []):
            if scope_prefix not in merged["scope_prefixes"]:
                merged["scope_prefixes"].append(scope_prefix)
    return merged if saw_changes else None


def _echo_runbook_test_result(result: dict) -> None:
    """Print the outcome of a runbook URL extraction check."""
    if result["success"]:
        click.echo("   ✅ Success!")
        click.echo(f"   📊 Content length: {result['content_length']} chars")
        click.echo(f"   🏷️  Source type: {result['source_type']}")
        click.echo(f"   👁️  Preview: {result['content_preview'][:200]}...")
    else:
        click.echo(f"   ❌ Failed: {result.get('error', 'Unknown error')}")


def _echo_generated_runbook(document, saved_path: str | None = None) -> None:
    """Print details for one generated runbook document."""
    click.echo(f"   ✅ Generated runbook: {document.title}")
    click.echo(f"   📂 Category: {document.category}")
    click.echo(f"   🚨 Severity: {document.severity}")
    click.echo(f"   📏 Length: {len(document.content)} characters")
    if saved_path is not None:
        click.echo(f"   💾 Saved to: {saved_path}")


def _echo_runbook_job_results(results: dict) -> None:
    """Print summary details for a full runbook generation pass."""
    click.echo("✅ Runbook generation completed!")
    click.echo(f"   📝 Documents generated: {results['documents_scraped']}")
    click.echo(f"   💾 Documents saved: {results['documents_saved']}")
    click.echo(f"   📅 Batch date: {results['batch_date']}")
    for category, count in results["categories"].items():
        click.echo(f"   📂 {category}: {count} runbooks")


@click.group()
def pipeline():
    """Data pipeline commands for scraping and ingestion."""
    pass


@pipeline.command()
@click.option("--artifacts-path", default="./artifacts", help="Path to store artifacts")
@click.option(
    "--scrapers",
    help="Comma-separated list of scrapers to run (redis_docs,redis_runbooks,redis_kb,runbook_generator)",
)
@click.option(
    "--latest-only",
    is_flag=True,
    help="Only include latest Redis docs (skip versioned docs like 7.x) for redis_docs and redis_docs_local",
)
@click.option(
    "--docs-path",
    default="./redis-docs",
    help="Path to local redis/docs clone (for redis_docs_local scraper)",
)
@click.option("--batch-date", help="Batch date to write (YYYY-MM-DD), defaults to today")
def scrape(
    artifacts_path: str,
    scrapers: str,
    latest_only: bool,
    docs_path: str,
    batch_date: str | None,
):
    """Run the scraping pipeline to collect SRE documents."""
    click.echo("🔍 Starting scraping pipeline...")

    scraper_list = _parse_scraper_list(scrapers)
    validated_batch_date = _validate_batch_date(batch_date)

    async def run_scraping():
        # Configure scrapers to honor latest-only when requested
        config = {
            "redis_docs": {"latest_only": latest_only},
            "redis_docs_local": {"latest_only": latest_only, "docs_repo_path": docs_path},
        }
        orchestrator = PipelineOrchestrator(artifacts_path, config, scrapers=scraper_list)
        if validated_batch_date:
            orchestrator.storage.set_batch_date(validated_batch_date)
        try:
            results = await orchestrator.run_scraping_pipeline(scraper_list)

            click.echo("✅ Scraping completed!")
            click.echo(f"   Batch date: {results['batch_date']}")
            click.echo(f"   Total documents: {results['total_documents']}")
            click.echo(f"   Scrapers run: {', '.join(results['scrapers_run'])}")

            _echo_scraper_results(results["scraper_results"])

            return results

        except Exception as e:
            log_cli_exception(__name__, "pipeline CLI command failed", e)
            click.echo(f"❌ Scraping failed: {e}")
            raise

    return asyncio.run(run_scraping())


@pipeline.command()
@click.option("--batch-date", help="Batch date to ingest (YYYY-MM-DD), defaults to today")
@click.option("--artifacts-path", default="./artifacts", help="Path to artifacts")
@click.option(
    "--latest-only",
    is_flag=True,
    help="Only index latest Redis docs from the batch (skip versioned docs like 7.x)",
)
@click.option("--verbose", "-v", is_flag=True, help="Show per-file source document changes")
def ingest(batch_date: str, artifacts_path: str, latest_only: bool, verbose: bool):
    """Run the ingestion pipeline to process scraped documents."""
    click.echo("📥 Starting ingestion pipeline...")

    async def run_ingestion():
        # Configure ingestion to honor latest-only when requested
        config = {"ingestion": {"latest_only": latest_only}}
        orchestrator = PipelineOrchestrator(artifacts_path, config)
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

            _echo_source_document_changes(
                results.get("source_document_changes"),
                verbose=verbose,
            )

            return results

        except Exception as e:
            log_cli_exception(__name__, "pipeline CLI command failed", e)
            click.echo(f"❌ Ingestion failed: {e}")
            raise

    return asyncio.run(run_ingestion())


@pipeline.command()
@click.option("--artifacts-path", default="./artifacts", help="Path to store artifacts")
@click.option("--scrapers", help="Comma-separated list of scrapers to run")
@click.option(
    "--latest-only",
    is_flag=True,
    help="Only include latest Redis docs (skip versioned docs like 7.x) for both scraping and ingestion",
)
@click.option(
    "--docs-path",
    default="./redis-docs",
    help="Path to local redis/docs clone (for redis_docs_local scraper)",
)
@click.option("--batch-date", help="Batch date to write (YYYY-MM-DD), defaults to today")
def full(
    artifacts_path: str,
    scrapers: str,
    latest_only: bool,
    docs_path: str,
    batch_date: str | None,
):
    """Run the complete pipeline: scraping + ingestion."""
    click.echo("🚀 Starting full pipeline (scraping + ingestion)...")

    scraper_list = _parse_scraper_list(scrapers)
    validated_batch_date = _validate_batch_date(batch_date)

    async def run_full_pipeline():
        # Configure scrapers and ingestion to honor latest-only when requested
        config = {
            "redis_docs": {"latest_only": latest_only},
            "redis_docs_local": {"latest_only": latest_only, "docs_repo_path": docs_path},
            "ingestion": {"latest_only": latest_only},
        }
        orchestrator = PipelineOrchestrator(artifacts_path, config, scrapers=scraper_list)
        if validated_batch_date:
            orchestrator.storage.set_batch_date(validated_batch_date)
        try:
            results = await orchestrator.run_full_pipeline(scraper_list)

            click.echo("✅ Full pipeline completed!")
            click.echo(f"   Batch date: {results['batch_date']}")

            # Scraping results
            if "scraping" in results:
                scraping = results["scraping"]
                click.echo(f"   📥 Scraping: {scraping['total_documents']} documents")

                _echo_scraper_results(scraping["scraper_results"], indent="      ")

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
            log_cli_exception(__name__, "pipeline CLI command failed", e)
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
            log_cli_exception(__name__, "pipeline CLI command failed", e)
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
            log_cli_exception(__name__, "pipeline CLI command failed", e)
            click.echo(f"❌ Cleanup failed: {e}")
            raise

    return asyncio.run(run_cleanup())


@pipeline.command()
@click.option("--url", help="Add a single URL to generate a runbook from")
@click.option("--test-url", help="Test URL extraction without generating full runbook")
@click.option("--list-urls", is_flag=True, help="List currently configured URLs")
@click.option("--artifacts-path", default="./artifacts", help="Path to store artifacts")
def runbooks(url: str, test_url: str, list_urls: bool, artifacts_path: str):
    """Generate standardized runbooks from web sources using GPT-5."""

    async def run_runbook_operations():
        from ..pipelines.orchestrator import PipelineOrchestrator

        # Only instantiate the runbook_generator scraper
        orchestrator = PipelineOrchestrator(artifacts_path, scrapers=["runbook_generator"])
        generator = orchestrator.scrapers["runbook_generator"]

        if list_urls:
            click.echo("📋 Currently configured runbook URLs:")
            for i, configured_url in enumerate(generator.get_configured_urls(), 1):
                click.echo(f"   {i}. {configured_url}")
            return

        if test_url:
            click.echo(f"🧪 Testing URL extraction: {test_url}")
            result = await generator.test_url_extraction(test_url)
            _echo_runbook_test_result(result)
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
                path = temp_storage.save_document(doc)
                _echo_generated_runbook(doc, path)
            else:
                click.echo(f"   ❌ Failed to generate runbook from {url}")

            return

        # Default: run all configured URLs
        click.echo("🚀 Generating runbooks from all configured URLs...")

        try:
            results = await generator.run_scraping_job()
            _echo_runbook_job_results(results)

        except Exception as e:
            log_cli_exception(__name__, "pipeline CLI command failed", e)
            click.echo(f"❌ Runbook generation failed: {e}")
            raise

    return asyncio.run(run_runbook_operations())


@pipeline.command()
@click.option("--source-dir", "-s", default="source_documents", help="Source documents directory")
@click.option("--batch-date", help="Batch date (YYYY-MM-DD), defaults to today")
@click.option("--prepare-only", is_flag=True, help="Only prepare batch artifacts, don't ingest")
@click.option("--artifacts-path", default="./artifacts", help="Path to artifacts storage")
@click.option("--verbose", "-v", is_flag=True, help="Show per-file source document changes")
def prepare_sources(
    source_dir: str, batch_date: str, prepare_only: bool, artifacts_path: str, verbose: bool
):
    """Prepare source documents as batch artifacts, optionally ingest them."""

    async def run_source_preparation():
        from pathlib import Path

        from ..pipelines.ingestion.processor import IngestionPipeline
        from ..pipelines.scraper.base import ArtifactStorage

        source_path = Path(source_dir)
        if not source_path.exists():
            click.echo(f"❌ Source directory does not exist: {source_path}")
            return

        # Set batch date and storage (don't create dirs yet - will be created on save)
        storage = ArtifactStorage(artifacts_path)
        if batch_date:
            try:
                datetime.strptime(batch_date, "%Y-%m-%d")
                storage.set_batch_date(batch_date)
                batch_date_to_use = batch_date
            except ValueError:
                click.echo(f"❌ Invalid batch date format: {batch_date}. Use YYYY-MM-DD")
                return
        else:
            batch_date_to_use = storage.current_date

        click.echo(f"📂 Preparing source documents from: {source_path}")
        click.echo(f"📅 Batch date: {batch_date_to_use}")

        # Find all markdown files (excluding README files)
        markdown_files = list(source_path.rglob("*.md"))
        markdown_files = [f for f in markdown_files if f.name.lower() != "readme.md"]

        if not markdown_files:
            click.echo(f"❌ No markdown files found in {source_path}")
            return

        click.echo(f"📋 Found {len(markdown_files)} files to prepare")

        try:
            pipeline = IngestionPipeline(storage)

            # Prepare artifacts from source documents
            prepared_count = await pipeline.prepare_source_artifacts(source_path, batch_date_to_use)

            click.echo(f"✅ Prepared {prepared_count} source documents as batch artifacts")
            click.echo(f"📦 Artifacts saved to: {storage.current_batch_path}")

            if not prepare_only:
                click.echo("🚀 Starting ingestion of prepared artifacts...")

                # Now run the standard ingestion on the prepared batch
                results = await pipeline.ingest_prepared_batch(batch_date_to_use)

                successful = [r for r in results if r["status"] == "success"]
                failed = [r for r in results if r["status"] == "error"]

                click.echo("✅ Source document ingestion completed!")
                click.echo(f"   📝 Successfully ingested: {len(successful)} documents")

                if successful:
                    total_chunks = sum(r.get("chunks_indexed", 0) for r in successful)
                    click.echo(f"   📦 Total chunks indexed: {total_chunks}")
                    _echo_source_document_changes(
                        _merge_source_document_changes(
                            [r.get("source_document_changes") for r in successful]
                        ),
                        verbose=verbose,
                    )

                if failed:
                    click.echo(f"   ❌ Failed to ingest: {len(failed)} documents")
            else:
                click.echo(
                    f"✋ Artifacts prepared but not ingested (use --batch-date {batch_date_to_use} with 'ingest' command)"
                )

        except Exception as e:
            log_cli_exception(__name__, "pipeline CLI command failed", e)
            click.echo(f"❌ Source preparation failed: {e}")
            raise

    return asyncio.run(run_source_preparation())


if __name__ == "__main__":
    pipeline()
