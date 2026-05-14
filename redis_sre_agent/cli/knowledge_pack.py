"""CLI commands for building, inspecting, and loading knowledge packs."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from redis_sre_agent.cli.logging_utils import log_cli_exception
from redis_sre_agent.knowledge_pack.builder import build_knowledge_pack
from redis_sre_agent.knowledge_pack.loader import inspect_knowledge_pack, load_knowledge_pack


def _parse_csv_list(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


@click.group(name="knowledge-pack")
def knowledge_pack():
    """Build, inspect, and load release knowledge packs."""
    pass


@knowledge_pack.command("build")
@click.option("--batch-date", required=True, help="Artifact batch date to package (YYYY-MM-DD)")
@click.option("--artifacts-path", default="./artifacts", help="Artifacts root path")
@click.option("--output", required=True, help="Path for the output .zip")
@click.option("--release-tag", help="Optional release tag recorded in the manifest")
@click.option("--repo-sha", help="Optional repo sha recorded in the manifest")
@click.option(
    "--scrapers-run",
    help="Optional comma-separated list of scrapers recorded in the manifest",
)
@click.option(
    "--profile",
    "profile_name",
    type=click.Choice(["runtime", "airgap"]),
    default="runtime",
    show_default=True,
    help="Embedding profile recorded in the manifest",
)
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def build(
    batch_date: str,
    artifacts_path: str,
    output: str,
    release_tag: str | None,
    repo_sha: str | None,
    scrapers_run: str | None,
    profile_name: str,
    as_json: bool,
):
    """Build a knowledge-pack zip from live Redis knowledge data."""

    async def _run():
        try:
            result = await build_knowledge_pack(
                batch_date=batch_date,
                output_path=Path(output),
                artifacts_path=Path(artifacts_path),
                release_tag=release_tag,
                repo_sha=repo_sha,
                scrapers_run=_parse_csv_list(scrapers_run),
                profile_name=profile_name,
            )
        except Exception as exc:
            log_cli_exception(__name__, "knowledge-pack CLI command failed", exc)
            click.echo(f"❌ Knowledge-pack build failed: {exc}")
            raise

        if as_json:
            print(json.dumps(result, indent=2))
            return

        click.echo("✅ Knowledge pack built")
        click.echo(f"   📦 Output: {result['output_path']}")
        click.echo(f"   📅 Batch date: {result['batch_date']}")
        click.echo(f"   🧬 Profile: {result['pack_profile']}")
        click.echo(f"   🆔 Pack id: {result['pack_id']}")
        click.echo(
            "   📊 Records: "
            f"artifacts={result['record_counts']['artifact_documents']} "
            f"chunks={result['record_counts']['chunk_records']} "
            f"document_meta={result['record_counts']['document_meta_records']} "
            f"source_meta={result['record_counts']['source_meta_records']}"
        )

    asyncio.run(_run())


@knowledge_pack.command("inspect")
@click.option("--pack", "pack_path", required=True, help="Path to the knowledge-pack zip")
@click.option("--skip-checksums", is_flag=True, help="Skip checksum verification")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def inspect(pack_path: str, skip_checksums: bool, as_json: bool):
    """Inspect a knowledge-pack manifest and restore compatibility."""
    try:
        inspection = inspect_knowledge_pack(Path(pack_path), verify_checksums=not skip_checksums)
    except Exception as exc:
        log_cli_exception(__name__, "knowledge-pack CLI command failed", exc)
        click.echo(f"❌ Knowledge-pack inspect failed: {exc}")
        raise

    payload = inspection.model_dump()
    if as_json:
        print(json.dumps(payload, indent=2))
        return

    manifest = inspection.manifest
    console = Console()
    table = Table(title="Knowledge Pack")
    table.add_column("Field", no_wrap=True)
    table.add_column("Value")
    table.add_row("Pack ID", manifest.pack_id)
    table.add_row("Profile", manifest.pack_profile)
    table.add_row("Batch Date", manifest.batch_date)
    table.add_row("Release Tag", manifest.release_tag or "-")
    table.add_row("Embedding", f"{manifest.embedding_provider}/{manifest.embedding_model}")
    table.add_row("Vector Dim", str(manifest.vector_dim))
    table.add_row("Checksums", "verified" if inspection.checksums_verified else "skipped")
    table.add_row(
        "Restore Compatible",
        "yes" if inspection.restore_compatible else f"no ({inspection.compatibility_reason})",
    )
    console.print(table)


@knowledge_pack.command("load")
@click.option("--pack", "pack_path", required=True, help="Path to the knowledge-pack zip")
@click.option(
    "--mode",
    type=click.Choice(["auto", "restore", "reingest"]),
    default="auto",
    show_default=True,
    help="How to load the pack",
)
@click.option("--artifacts-path", default="./artifacts", help="Artifacts root for reingest mode")
@click.option(
    "--replace-existing",
    is_flag=True,
    help="Allow loading when the knowledge index already contains unmanaged content",
)
@click.option("--skip-checksums", is_flag=True, help="Skip checksum verification")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def load(
    pack_path: str,
    mode: str,
    artifacts_path: str,
    replace_existing: bool,
    skip_checksums: bool,
    as_json: bool,
):
    """Load a knowledge pack into Redis via restore or reingest."""

    async def _run():
        try:
            result = await load_knowledge_pack(
                pack_path=Path(pack_path),
                mode=mode,
                artifacts_path=Path(artifacts_path),
                replace_existing=replace_existing,
                skip_checksums=skip_checksums,
            )
        except Exception as exc:
            log_cli_exception(__name__, "knowledge-pack CLI command failed", exc)
            click.echo(f"❌ Knowledge-pack load failed: {exc}")
            raise

        if as_json:
            print(json.dumps(result, indent=2))
            return

        click.echo("✅ Knowledge pack loaded")
        click.echo(f"   🆔 Pack id: {result['pack_id']}")
        click.echo(f"   🧬 Profile: {result['pack_profile']}")
        click.echo(f"   🚚 Mode: {result['mode']}")
        click.echo(f"   📅 Batch date: {result['batch_date']}")
        if result["mode"] == "restore":
            click.echo(
                "   📊 Restored: "
                f"chunks={result['chunk_records_loaded']} "
                f"document_meta={result['document_meta_records_loaded']} "
                f"source_meta={result['source_meta_records_loaded']}"
            )
        else:
            click.echo(
                "   📥 Reingested: "
                f"docs={result['ingestion'].get('documents_processed', 0)} "
                f"chunks={result['ingestion'].get('chunks_indexed', 0)}"
            )

    asyncio.run(_run())
