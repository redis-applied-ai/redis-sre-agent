"""Cluster CLI commands for managing Redis clusters."""

from __future__ import annotations

import asyncio
import json as _json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import click
from pydantic import SecretStr
from rich.console import Console
from rich.table import Table
from ulid import ULID

from redis_sre_agent.cli.logging_utils import log_cli_exception
from redis_sre_agent.core import clusters as core_clusters
from redis_sre_agent.core.cluster_admin_defaults import (
    build_enterprise_admin_missing_fields_error,
    missing_enterprise_admin_fields,
    resolve_enterprise_admin_fields,
)
from redis_sre_agent.core.migrations.instances_to_clusters import (
    run_instances_to_clusters_migration,
)


@click.group()
def cluster():
    """Manage Redis clusters"""
    pass


def _mask_response(c: core_clusters.RedisCluster) -> Dict[str, Any]:
    """Convert domain model to CLI-safe dict with masked secrets."""
    d = c.model_dump(mode="json", exclude={"admin_password"})
    if c.admin_password:
        d["admin_password"] = "***"
    return d


def _print_clusters_table(items: List[core_clusters.RedisCluster], limit: int = 100):
    if not items:
        click.echo("No clusters found.")
        return

    console = Console()
    table = Table(title="Redis Clusters", show_lines=False)
    table.add_column("ID", no_wrap=True)
    table.add_column("Name")
    table.add_column("Env", no_wrap=True)
    table.add_column("Type", no_wrap=True)
    table.add_column("Admin URL")

    for c in items[:limit]:
        ctype = c.cluster_type.value if c.cluster_type else "-"
        table.add_row(c.id, c.name, c.environment, ctype, c.admin_url or "-")

    console.print(table)


@cluster.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
@click.option("--limit", default=100, help="Max rows to display")
def clusters_list(as_json: bool, limit: int):
    """List configured Redis clusters."""

    async def _list():
        try:
            items = await core_clusters.get_clusters()
        except Exception as e:
            log_cli_exception(__name__, "cluster CLI command failed", e)
            if as_json:
                print(_json.dumps({"error": str(e)}))
            else:
                click.echo(f"❌ Error: {e}")
            return

        if as_json:
            print(_json.dumps([_mask_response(c) for c in items[:limit]], indent=2))
            return

        _print_clusters_table(items, limit=limit)

    asyncio.run(_list())


@cluster.command("get")
@click.argument("cluster_id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def clusters_get(cluster_id: str, as_json: bool):
    """Get a single cluster by ID."""

    async def _get():
        try:
            c = await core_clusters.get_cluster_by_id(cluster_id)
            if not c:
                msg = {"error": "Cluster not found", "id": cluster_id}
                if as_json:
                    print(_json.dumps(msg))
                else:
                    click.echo("❌ Cluster not found")
                return

            if as_json:
                print(_json.dumps(_mask_response(c), indent=2))
                return

            console = Console()
            table = Table(title=f"Cluster {cluster_id}")
            table.add_column("Field", no_wrap=True)
            table.add_column("Value")

            d = _mask_response(c)
            for k in [
                "id",
                "name",
                "cluster_type",
                "environment",
                "description",
                "notes",
                "admin_url",
                "admin_username",
                "admin_password",
                "status",
                "version",
                "last_checked",
                "created_by",
                "user_id",
                "created_at",
                "updated_at",
            ]:
                table.add_row(k, str(d.get(k)))

            ext_data = d.get("extension_data")
            if ext_data:
                table.add_row("", "")
                table.add_row("[bold]extension_data[/bold]", "")
                for ek, ev in ext_data.items():
                    table.add_row(f"  {ek}", str(ev))

            console.print(table)
        except Exception as e:
            log_cli_exception(__name__, "cluster CLI command failed", e)
            if as_json:
                print(_json.dumps({"error": str(e), "id": cluster_id}))
            else:
                click.echo(f"❌ Error: {e}")

    asyncio.run(_get())


_ALLOWED_ENVS = ["development", "staging", "production", "test"]
_ALLOWED_TYPES = ["oss_cluster", "redis_enterprise", "redis_cloud", "unknown"]
_ALLOWED_CREATED_BY = ["user", "agent"]


@cluster.command("create")
@click.option("--name", required=True, help="Cluster name")
@click.option(
    "--cluster-type",
    type=click.Choice(_ALLOWED_TYPES, case_sensitive=False),
    default="unknown",
)
@click.option(
    "--environment",
    type=click.Choice(_ALLOWED_ENVS, case_sensitive=False),
    required=True,
)
@click.option("--description", required=True, help="Description of the cluster")
@click.option("--notes")
@click.option("--admin-url")
@click.option("--admin-username")
@click.option("--admin-password")
@click.option("--status")
@click.option("--version")
@click.option("--last-checked")
@click.option(
    "--created-by",
    type=click.Choice(_ALLOWED_CREATED_BY, case_sensitive=False),
    default="user",
)
@click.option("--user-id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def clusters_create(
    name: str,
    cluster_type: str,
    environment: str,
    description: str,
    notes: Optional[str],
    admin_url: Optional[str],
    admin_username: Optional[str],
    admin_password: Optional[str],
    status: Optional[str],
    version: Optional[str],
    last_checked: Optional[str],
    created_by: str,
    user_id: Optional[str],
    as_json: bool,
):
    """Create a new Redis cluster."""

    async def _create():
        try:
            clusters = await core_clusters.get_clusters()
            if any(c.name == name for c in clusters):
                raise RuntimeError(f"Cluster with name '{name}' already exists")

            normalized_cluster_type = cluster_type.lower() if cluster_type else "unknown"
            resolved_admin = resolve_enterprise_admin_fields(
                cluster_type=normalized_cluster_type,
                admin_url=admin_url,
                admin_username=admin_username,
                admin_password=admin_password,
            )
            if normalized_cluster_type == "redis_enterprise":
                missing_fields = missing_enterprise_admin_fields(
                    admin_url=resolved_admin.admin_url,
                    admin_username=resolved_admin.admin_username,
                    admin_password=resolved_admin.admin_password,
                )
                if missing_fields:
                    raise RuntimeError(build_enterprise_admin_missing_fields_error(missing_fields))

            cluster_id = f"cluster-{environment.lower()}-{ULID()}"
            new_cluster = core_clusters.RedisCluster(
                id=cluster_id,
                name=name,
                cluster_type=normalized_cluster_type,
                environment=environment.lower(),
                description=description,
                notes=notes,
                admin_url=resolved_admin.admin_url,
                admin_username=resolved_admin.admin_username,
                admin_password=resolved_admin.admin_password,
                status=status,
                version=version,
                last_checked=last_checked,
                created_by=created_by.lower() if created_by else "user",
                user_id=user_id,
            )

            clusters.append(new_cluster)
            ok = await core_clusters.save_clusters(clusters)
            if not ok:
                raise RuntimeError("Failed to save cluster")

            payload = {"id": new_cluster.id, "status": "created"}
            if as_json:
                print(_json.dumps(payload))
            else:
                click.echo(f"✅ Created cluster {new_cluster.id}")
        except Exception as e:
            log_cli_exception(__name__, "cluster CLI command failed", e)
            if as_json:
                print(_json.dumps({"error": str(e)}))
            else:
                click.echo(f"❌ Error: {e}")

    asyncio.run(_create())


@cluster.command("update")
@click.argument("cluster_id")
@click.option("--name")
@click.option("--cluster-type", type=click.Choice(_ALLOWED_TYPES, case_sensitive=False))
@click.option("--environment", type=click.Choice(_ALLOWED_ENVS, case_sensitive=False))
@click.option("--description")
@click.option("--notes")
@click.option("--admin-url")
@click.option("--admin-username")
@click.option("--admin-password")
@click.option("--status")
@click.option("--version")
@click.option("--last-checked")
@click.option("--created-by", type=click.Choice(_ALLOWED_CREATED_BY, case_sensitive=False))
@click.option("--user-id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def clusters_update(
    cluster_id: str,
    name: Optional[str],
    cluster_type: Optional[str],
    environment: Optional[str],
    description: Optional[str],
    notes: Optional[str],
    admin_url: Optional[str],
    admin_username: Optional[str],
    admin_password: Optional[str],
    status: Optional[str],
    version: Optional[str],
    last_checked: Optional[str],
    created_by: Optional[str],
    user_id: Optional[str],
    as_json: bool,
):
    """Update fields of an existing cluster."""

    async def _update():
        try:
            clusters = await core_clusters.get_clusters()
            idx = None
            for i, c in enumerate(clusters):
                if c.id == cluster_id:
                    idx = i
                    break
            if idx is None:
                raise RuntimeError("Cluster not found")

            current = clusters[idx]
            update_data: Dict[str, Any] = {}
            if name is not None:
                update_data["name"] = name
            if cluster_type is not None:
                update_data["cluster_type"] = cluster_type.lower()
            if environment is not None:
                update_data["environment"] = environment.lower()
            if description is not None:
                update_data["description"] = description
            if notes is not None:
                update_data["notes"] = notes
            if admin_url is not None:
                update_data["admin_url"] = admin_url
            if admin_username is not None:
                update_data["admin_username"] = admin_username
            if admin_password is not None:
                update_data["admin_password"] = (
                    SecretStr(admin_password) if admin_password else None
                )
            if status is not None:
                update_data["status"] = status
            if version is not None:
                update_data["version"] = version
            if last_checked is not None:
                update_data["last_checked"] = last_checked
            if created_by is not None:
                update_data["created_by"] = created_by.lower()
            if user_id is not None:
                update_data["user_id"] = user_id

            update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

            updated = current.model_copy(update=update_data)
            validated = core_clusters.RedisCluster(**updated.model_dump(mode="json"))
            clusters[idx] = validated

            ok = await core_clusters.save_clusters(clusters)
            if not ok:
                raise RuntimeError("Failed to save updated cluster")

            payload = {"id": validated.id, "status": "updated"}
            if as_json:
                print(_json.dumps(payload))
            else:
                click.echo(f"✅ Updated cluster {validated.id}")
        except Exception as e:
            log_cli_exception(__name__, "cluster CLI command failed", e)
            if as_json:
                print(_json.dumps({"error": str(e), "id": cluster_id}))
            else:
                click.echo(f"❌ Error: {e}")

    asyncio.run(_update())


@cluster.command("delete")
@click.argument("cluster_id")
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def clusters_delete(cluster_id: str, yes: bool, as_json: bool):
    """Delete a cluster by ID."""

    async def _delete():
        try:
            if not yes and not as_json:
                if not click.confirm(f"Delete cluster {cluster_id}?", default=False):
                    click.echo("Cancelled")
                    return

            clusters = await core_clusters.get_clusters()
            orig = len(clusters)
            clusters = [c for c in clusters if c.id != cluster_id]
            if len(clusters) == orig:
                raise RuntimeError("Cluster not found")

            ok = await core_clusters.save_clusters(clusters)
            if not ok:
                raise RuntimeError("Failed to save after deletion")

            try:
                await core_clusters.delete_cluster_index_doc(cluster_id)
            except Exception:
                pass

            payload = {"id": cluster_id, "status": "deleted"}
            if as_json:
                print(_json.dumps(payload))
            else:
                click.echo(f"✅ Deleted cluster {cluster_id}")
        except Exception as e:
            log_cli_exception(__name__, "cluster CLI command failed", e)
            if as_json:
                print(_json.dumps({"error": str(e), "id": cluster_id}))
            else:
                click.echo(f"❌ Error: {e}")

    asyncio.run(_delete())


@cluster.command("backfill-instance-links")
@click.option("--dry-run", is_flag=True, help="Preview migration changes without writing")
@click.option("--force", is_flag=True, help="Run even if completion marker already exists")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def clusters_backfill_instance_links(dry_run: bool, force: bool, as_json: bool):
    """Backfill cluster links for existing instance records."""

    async def _backfill():
        try:
            summary = await run_instances_to_clusters_migration(
                dry_run=dry_run,
                force=force,
                source="cli_cluster_backfill",
            )
            payload = summary.to_dict()
            if as_json:
                print(_json.dumps(payload, indent=2))
                return

            click.echo("Instance-cluster backfill completed")
            click.echo(f"  scanned: {payload['scanned']}")
            click.echo(f"  eligible: {payload['eligible']}")
            click.echo(f"  clusters_created: {payload['clusters_created']}")
            click.echo(f"  clusters_reused: {payload['clusters_reused']}")
            click.echo(f"  instances_linked: {payload['instances_linked']}")
            if payload.get("skipped_due_marker"):
                click.echo("  skipped_due_marker: true")
            if payload.get("skipped_due_lock"):
                click.echo("  skipped_due_lock: true")
            if payload.get("errors"):
                click.echo(f"  errors: {len(payload['errors'])}")
                for err in payload["errors"]:
                    click.echo(f"    - {err}")
        except Exception as e:
            log_cli_exception(__name__, "cluster CLI command failed", e)
            if as_json:
                print(_json.dumps({"error": str(e)}))
            else:
                click.echo(f"❌ Error: {e}")

    asyncio.run(_backfill())
