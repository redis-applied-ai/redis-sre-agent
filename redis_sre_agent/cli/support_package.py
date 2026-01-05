"""Support package CLI commands."""

from __future__ import annotations

import asyncio
import json as _json
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from redis_sre_agent.core.config import settings
from redis_sre_agent.tools.support_package.manager import SupportPackageManager
from redis_sre_agent.tools.support_package.storage import LocalStorage, S3Storage


def get_manager() -> SupportPackageManager:
    """Get a configured SupportPackageManager."""

    # Determine storage backend from settings
    storage_type = getattr(settings, "support_package_storage_type", "local")

    if storage_type == "s3":
        storage = S3Storage(
            bucket=getattr(settings, "support_package_s3_bucket", ""),
            prefix=getattr(settings, "support_package_s3_prefix", "support-packages/"),
            region=getattr(settings, "support_package_s3_region", None),
            endpoint_url=getattr(settings, "support_package_s3_endpoint", None),
        )
    else:
        storage = LocalStorage(base_path=settings.support_package_artifacts_dir / "storage")

    return SupportPackageManager(
        storage=storage,
        extract_dir=settings.support_package_artifacts_dir / "extracted",
    )


@click.group()
def support_package():
    """Manage support packages."""
    pass


@support_package.command("upload")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--id", "package_id", help="Custom package ID")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def upload(path: Path, package_id: Optional[str], as_json: bool):
    """Upload a support package."""

    async def _upload():
        try:
            manager = get_manager()
            result_id = await manager.upload(path, package_id=package_id)

            if as_json:
                print(_json.dumps({"package_id": result_id, "status": "uploaded"}))
            else:
                click.echo(f"✅ Uploaded support package: {result_id}")
        except Exception as e:
            if as_json:
                print(_json.dumps({"error": str(e)}))
            else:
                click.echo(f"❌ Error: {e}")

    asyncio.run(_upload())


@support_package.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
@click.option("--limit", default=100, help="Max rows to display")
def list_packages(as_json: bool, limit: int):
    """List uploaded support packages."""

    async def _list():
        try:
            manager = get_manager()
            packages = await manager.list_packages()

            if as_json:
                print(_json.dumps([p.model_dump(mode="json") for p in packages[:limit]], indent=2))
                return

            if not packages:
                click.echo("No support packages found.")
                return

            console = Console()
            table = Table(title="Support Packages", show_lines=False)
            table.add_column("ID", no_wrap=True)
            table.add_column("Filename")
            table.add_column("Size")
            table.add_column("Uploaded At")

            for pkg in packages[:limit]:
                size_str = _format_size(pkg.size_bytes)
                table.add_row(
                    pkg.package_id,
                    pkg.filename,
                    size_str,
                    pkg.uploaded_at.strftime("%Y-%m-%d %H:%M:%S"),
                )

            console.print(table)
        except Exception as e:
            if as_json:
                print(_json.dumps({"error": str(e)}))
            else:
                click.echo(f"❌ Error: {e}")

    asyncio.run(_list())


def _format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


@support_package.command("extract")
@click.argument("package_id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def extract(package_id: str, as_json: bool):
    """Extract a support package."""

    async def _extract():
        try:
            manager = get_manager()
            extract_path = await manager.extract(package_id)

            if as_json:
                print(
                    _json.dumps(
                        {
                            "package_id": package_id,
                            "path": str(extract_path),
                            "status": "extracted",
                        }
                    )
                )
            else:
                click.echo(f"✅ Extracted to: {extract_path}")
        except Exception as e:
            if as_json:
                print(_json.dumps({"error": str(e), "package_id": package_id}))
            else:
                click.echo(f"❌ Error: {e}")

    asyncio.run(_extract())


@support_package.command("delete")
@click.argument("package_id")
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def delete(package_id: str, yes: bool, as_json: bool):
    """Delete a support package."""

    async def _delete():
        try:
            if not yes and not as_json:
                if not click.confirm(f"Delete package {package_id}?", default=False):
                    click.echo("Cancelled")
                    return

            manager = get_manager()
            await manager.delete(package_id)

            if as_json:
                print(_json.dumps({"package_id": package_id, "status": "deleted"}))
            else:
                click.echo(f"✅ Deleted package: {package_id}")
        except Exception as e:
            if as_json:
                print(_json.dumps({"error": str(e), "package_id": package_id}))
            else:
                click.echo(f"❌ Error: {e}")

    asyncio.run(_delete())


@support_package.command("info")
@click.argument("package_id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def info(package_id: str, as_json: bool):
    """Get information about a support package."""

    async def _info():
        try:
            manager = get_manager()
            metadata = await manager.get_metadata(package_id)

            if not metadata:
                if as_json:
                    print(_json.dumps({"error": "Package not found", "package_id": package_id}))
                else:
                    click.echo(f"❌ Package not found: {package_id}")
                return

            is_extracted = await manager.is_extracted(package_id)

            if as_json:
                data = metadata.model_dump(mode="json")
                data["is_extracted"] = is_extracted
                print(_json.dumps(data, indent=2))
                return

            console = Console()
            table = Table(title=f"Package: {package_id}")
            table.add_column("Field", no_wrap=True)
            table.add_column("Value")

            table.add_row("Package ID", metadata.package_id)
            table.add_row("Filename", metadata.filename)
            table.add_row("Size", _format_size(metadata.size_bytes))
            table.add_row("Uploaded At", metadata.uploaded_at.strftime("%Y-%m-%d %H:%M:%S"))
            table.add_row("Extracted", "Yes" if is_extracted else "No")
            if metadata.checksum:
                table.add_row("Checksum (SHA-256)", metadata.checksum[:16] + "...")

            console.print(table)
        except Exception as e:
            if as_json:
                print(_json.dumps({"error": str(e), "package_id": package_id}))
            else:
                click.echo(f"❌ Error: {e}")

    asyncio.run(_info())
