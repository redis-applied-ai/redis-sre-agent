"""Instance CLI commands for managing Redis instances.

This module provides a Click command group `instance` with sub-commands to list,
create, get, update, delete, and test Redis instance connections.
"""

from __future__ import annotations

import asyncio
import json as _json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import click
from rich.console import Console
from rich.table import Table

from redis_sre_agent.core import instances as core_instances
from redis_sre_agent.core.redis import test_redis_connection


@click.group()
def instance():
    """Manage Redis instances"""
    pass


# ---------------------------- helpers ---------------------------- #


def _mask_response(inst: core_instances.RedisInstance) -> Dict[str, Any]:
    """Convert domain model to CLI-safe dict with masked secrets."""
    # Avoid unwrapping secrets via field_serializer; add masked fields manually
    d = inst.model_dump(mode="json", exclude={"connection_url", "admin_password"})
    d["connection_url"] = core_instances.mask_redis_url(inst.connection_url)
    # Always mask admin_password if present
    if getattr(inst, "admin_password", None):
        d["admin_password"] = "***"
    return d


def _print_instances_table(items: List[core_instances.RedisInstance], limit: int = 100):
    if not items:
        click.echo("No instances found.")
        return

    console = Console()
    table = Table(title="Redis Instances", show_lines=False)
    table.add_column("ID", no_wrap=True)
    table.add_column("Name")
    table.add_column("Env", no_wrap=True)
    table.add_column("Type", no_wrap=True)
    table.add_column("URL (masked)")

    for inst in items[:limit]:
        masked_url = core_instances.mask_redis_url(inst.connection_url)
        itype = getattr(inst.instance_type, "value", inst.instance_type) or "-"
        table.add_row(inst.id, inst.name, inst.environment, itype, masked_url)

    console.print(table)


# ---------------------------- list ---------------------------- #


@instance.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
@click.option("--limit", default=100, help="Max rows to display")
def instances_list(as_json: bool, limit: int):
    """List configured Redis instances."""

    async def _list():
        try:
            items = await core_instances.get_instances()
        except Exception as e:
            if as_json:
                print(_json.dumps({"error": str(e)}))
            else:
                click.echo(f"❌ Error: {e}")
            return

        if as_json:
            print(_json.dumps([_mask_response(i) for i in items[:limit]], indent=2))
            return

        _print_instances_table(items, limit=limit)

    asyncio.run(_list())


# ---------------------------- get ---------------------------- #


@instance.command("get")
@click.argument("instance_id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def instances_get(instance_id: str, as_json: bool):
    """Get a single instance by ID."""

    async def _get():
        try:
            inst = await core_instances.get_instance_by_id(instance_id)
            if not inst:
                msg = {"error": "Instance not found", "id": instance_id}
                if as_json:
                    print(_json.dumps(msg))
                else:
                    click.echo("❌ Instance not found")
                return

            if as_json:
                print(_json.dumps(_mask_response(inst), indent=2))
                return

            console = Console()
            table = Table(title=f"Instance {instance_id}")
            table.add_column("Field", no_wrap=True)
            table.add_column("Value")

            d = _mask_response(inst)
            for k in [
                "id",
                "name",
                "connection_url",
                "environment",
                "usage",
                "description",
                "instance_type",
                "repo_url",
                "notes",
                "monitoring_identifier",
                "logging_identifier",
                "admin_url",
                "admin_username",
                "admin_password",
                "status",
                "version",
                "memory",
                "connections",
                "created_by",
                "user_id",
                "created_at",
                "updated_at",
            ]:
                table.add_row(k, str(d.get(k)))

            console.print(table)
        except Exception as e:
            if as_json:
                print(_json.dumps({"error": str(e), "id": instance_id}))
            else:
                click.echo(f"❌ Error: {e}")

    asyncio.run(_get())


# ---------------------------- create ---------------------------- #

_ALLOWED_ENVS = ["development", "staging", "production", "test"]
_ALLOWED_USAGE = ["cache", "analytics", "session", "queue", "custom"]
_ALLOWED_TYPES = ["oss_single", "oss_cluster", "redis_enterprise", "redis_cloud", "unknown"]
_ALLOWED_SUB_TYPES = ["pro", "essentials"]


@instance.command("create")
@click.option("--name", required=True, help="Instance name")
@click.option("--connection-url", required=True, help="Redis connection URL")
@click.option(
    "--environment",
    type=click.Choice(_ALLOWED_ENVS, case_sensitive=False),
    required=True,
)
@click.option("--usage", type=click.Choice(_ALLOWED_USAGE, case_sensitive=False), required=True)
@click.option("--description", required=True, help="Description of the instance")
# Optional metadata
@click.option("--repo-url")
@click.option("--notes")
@click.option("--monitoring-identifier")
@click.option("--logging-identifier")
@click.option(
    "--instance-type", type=click.Choice(_ALLOWED_TYPES, case_sensitive=False), default="unknown"
)
# Redis Enterprise admin (optional)
@click.option("--admin-url")
@click.option("--admin-username")
@click.option("--admin-password")
# Redis Cloud identifiers (optional)
@click.option("--redis-cloud-subscription-id", type=int)
@click.option("--redis-cloud-database-id", type=int)
@click.option(
    "--redis-cloud-subscription-type",
    type=click.Choice(_ALLOWED_SUB_TYPES, case_sensitive=False),
)
@click.option("--redis-cloud-database-name")
@click.option("--user-id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def instances_create(
    name: str,
    connection_url: str,
    environment: str,
    usage: str,
    description: str,
    repo_url: Optional[str],
    notes: Optional[str],
    monitoring_identifier: Optional[str],
    logging_identifier: Optional[str],
    instance_type: str,
    admin_url: Optional[str],
    admin_username: Optional[str],
    admin_password: Optional[str],
    redis_cloud_subscription_id: Optional[int],
    redis_cloud_database_id: Optional[int],
    redis_cloud_subscription_type: Optional[str],
    redis_cloud_database_name: Optional[str],
    user_id: Optional[str],
    as_json: bool,
):
    """Create a new Redis instance."""

    async def _create():
        try:
            instances = await core_instances.get_instances()
            if any(inst.name == name for inst in instances):
                raise RuntimeError(f"Instance with name '{name}' already exists")

            instance_id = f"redis-{environment}-{int(datetime.now().timestamp())}"
            new_inst = core_instances.RedisInstance(
                id=instance_id,
                name=name,
                connection_url=connection_url,
                environment=environment.lower(),
                usage=usage.lower(),
                description=description,
                repo_url=repo_url,
                notes=notes,
                monitoring_identifier=monitoring_identifier,
                logging_identifier=logging_identifier,
                instance_type=instance_type.lower() if instance_type else "unknown",
                admin_url=admin_url,
                admin_username=admin_username,
                admin_password=admin_password,
                redis_cloud_subscription_id=redis_cloud_subscription_id,
                redis_cloud_database_id=redis_cloud_database_id,
                redis_cloud_subscription_type=(
                    redis_cloud_subscription_type.lower() if redis_cloud_subscription_type else None
                ),
                redis_cloud_database_name=redis_cloud_database_name,
                created_by="user",
                user_id=user_id,
            )

            instances.append(new_inst)
            ok = await core_instances.save_instances(instances)
            if not ok:
                raise RuntimeError("Failed to save instance")

            payload = {"id": new_inst.id, "status": "created"}
            if as_json:
                print(_json.dumps(payload))
            else:
                click.echo(f"✅ Created instance {new_inst.id}")
        except Exception as e:
            if as_json:
                print(_json.dumps({"error": str(e)}))
            else:
                click.echo(f"❌ Error: {e}")

    asyncio.run(_create())


# ---------------------------- update ---------------------------- #


@instance.command("update")
@click.argument("instance_id")
@click.option("--name")
@click.option("--connection-url")
@click.option("--environment", type=click.Choice(_ALLOWED_ENVS, case_sensitive=False))
@click.option("--usage", type=click.Choice(_ALLOWED_USAGE, case_sensitive=False))
@click.option("--description")
@click.option("--repo-url")
@click.option("--notes")
@click.option("--monitoring-identifier")
@click.option("--logging-identifier")
@click.option("--instance-type", type=click.Choice(_ALLOWED_TYPES, case_sensitive=False))
@click.option("--admin-url")
@click.option("--admin-username")
@click.option("--admin-password")
@click.option("--redis-cloud-subscription-id", type=int)
@click.option("--redis-cloud-database-id", type=int)
@click.option(
    "--redis-cloud-subscription-type",
    type=click.Choice(_ALLOWED_SUB_TYPES, case_sensitive=False),
)
@click.option("--redis-cloud-database-name")
@click.option("--status")
@click.option("--version")
@click.option("--memory")
@click.option("--connections", type=int)
@click.option("--user-id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def instances_update(
    instance_id: str,
    name: Optional[str],
    connection_url: Optional[str],
    environment: Optional[str],
    usage: Optional[str],
    description: Optional[str],
    repo_url: Optional[str],
    notes: Optional[str],
    monitoring_identifier: Optional[str],
    logging_identifier: Optional[str],
    instance_type: Optional[str],
    admin_url: Optional[str],
    admin_username: Optional[str],
    admin_password: Optional[str],
    redis_cloud_subscription_id: Optional[int],
    redis_cloud_database_id: Optional[int],
    redis_cloud_subscription_type: Optional[str],
    redis_cloud_database_name: Optional[str],
    status: Optional[str],
    version: Optional[str],
    memory: Optional[str],
    connections: Optional[int],
    user_id: Optional[str],
    as_json: bool,
):
    """Update fields of an existing instance."""

    async def _update():
        try:
            items = await core_instances.get_instances()
            idx = None
            for i, it in enumerate(items):
                if it.id == instance_id:
                    idx = i
                    break
            if idx is None:
                raise RuntimeError("Instance not found")

            current = items[idx]
            update_data: Dict[str, Any] = {}
            if name is not None:
                update_data["name"] = name
            if connection_url is not None:
                update_data["connection_url"] = connection_url
            if environment is not None:
                update_data["environment"] = environment.lower()
            if usage is not None:
                update_data["usage"] = usage.lower()
            if description is not None:
                update_data["description"] = description
            if repo_url is not None:
                update_data["repo_url"] = repo_url
            if notes is not None:
                update_data["notes"] = notes
            if monitoring_identifier is not None:
                update_data["monitoring_identifier"] = monitoring_identifier
            if logging_identifier is not None:
                update_data["logging_identifier"] = logging_identifier
            if instance_type is not None:
                update_data["instance_type"] = instance_type.lower()
            if admin_url is not None:
                update_data["admin_url"] = admin_url
            if admin_username is not None:
                update_data["admin_username"] = admin_username
            if admin_password is not None:
                update_data["admin_password"] = admin_password
            if redis_cloud_subscription_id is not None:
                update_data["redis_cloud_subscription_id"] = redis_cloud_subscription_id
            if redis_cloud_database_id is not None:
                update_data["redis_cloud_database_id"] = redis_cloud_database_id
            if redis_cloud_subscription_type is not None:
                update_data["redis_cloud_subscription_type"] = redis_cloud_subscription_type.lower()
            if redis_cloud_database_name is not None:
                update_data["redis_cloud_database_name"] = redis_cloud_database_name
            if status is not None:
                update_data["status"] = status
            if version is not None:
                update_data["version"] = version
            if memory is not None:
                update_data["memory"] = memory
            if connections is not None:
                update_data["connections"] = connections
            if user_id is not None:
                update_data["user_id"] = user_id
            update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

            updated = current.model_copy(update=update_data)
            items[idx] = updated

            ok = await core_instances.save_instances(items)
            if not ok:
                raise RuntimeError("Failed to save updated instance")

            payload = {"id": updated.id, "status": "updated"}
            if as_json:
                print(_json.dumps(payload))
            else:
                click.echo(f"✅ Updated instance {updated.id}")
        except Exception as e:
            if as_json:
                print(_json.dumps({"error": str(e), "id": instance_id}))
            else:
                click.echo(f"❌ Error: {e}")

    asyncio.run(_update())


# ---------------------------- delete ---------------------------- #


@instance.command("delete")
@click.argument("instance_id")
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def instances_delete(instance_id: str, yes: bool, as_json: bool):
    """Delete an instance by ID."""

    async def _delete():
        try:
            if not yes and not as_json:
                if not click.confirm(f"Delete instance {instance_id}?", default=False):
                    click.echo("Cancelled")
                    return

            items = await core_instances.get_instances()
            orig = len(items)
            items = [i for i in items if i.id != instance_id]
            if len(items) == orig:
                raise RuntimeError("Instance not found")

            ok = await core_instances.save_instances(items)
            if not ok:
                raise RuntimeError("Failed to save after deletion")

            # Best-effort: remove search index document for this instance
            try:
                await core_instances.delete_instance_index_doc(instance_id)
            except Exception:
                pass

            payload = {"id": instance_id, "status": "deleted"}
            if as_json:
                print(_json.dumps(payload))
            else:
                click.echo(f"✅ Deleted instance {instance_id}")
        except Exception as e:
            if as_json:
                print(_json.dumps({"error": str(e), "id": instance_id}))
            else:
                click.echo(f"❌ Error: {e}")

    asyncio.run(_delete())


# ---------------------------- test connection ---------------------------- #


@instance.command("test-url")
@click.option("--connection-url", required=True, help="Redis connection URL to test")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def instances_test_url(connection_url: str, as_json: bool):
    """Test a Redis connection URL without creating an instance."""

    async def _test():
        try:
            ok = await test_redis_connection(url=connection_url)
            host_info = connection_url
            payload = {
                "success": ok,
                "message": ("Successfully connected" if ok else "Failed to connect"),
                "url": core_instances.mask_redis_url(connection_url),
            }
            if as_json:
                print(_json.dumps(payload))
            else:
                click.echo(("✅ " if ok else "❌ ") + payload["message"] + f" to {host_info}")
        except Exception as e:
            if as_json:
                print(_json.dumps({"success": False, "error": str(e)}))
            else:
                click.echo(f"❌ Error: {e}")

    asyncio.run(_test())


@instance.command("test")
@click.argument("instance_id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def instances_test(instance_id: str, as_json: bool):
    """Test connection to a configured instance by ID."""

    async def _test():
        try:
            inst = await core_instances.get_instance_by_id(instance_id)
            if not inst:
                raise RuntimeError("Instance not found")
            url = (
                inst.connection_url.get_secret_value()
                if hasattr(inst.connection_url, "get_secret_value")
                else str(inst.connection_url)
            )
            ok = await test_redis_connection(url=url)
            payload = {
                "success": ok,
                "message": ("Successfully connected" if ok else "Failed to connect"),
                "instance_id": instance_id,
            }
            if as_json:
                print(_json.dumps(payload))
            else:
                click.echo(("✅ " if ok else "❌ ") + payload["message"] + f" to {inst.name}")
        except Exception as e:
            if as_json:
                print(_json.dumps({"success": False, "error": str(e), "id": instance_id}))
            else:
                click.echo(f"❌ Error: {e}")

    asyncio.run(_test())
