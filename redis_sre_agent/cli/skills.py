"""CLI commands for Agent Skills discovery and retrieval."""

from __future__ import annotations

import asyncio
import json

import click
from rich.console import Console
from rich.table import Table

from redis_sre_agent.core.knowledge_helpers import (
    get_skill_helper,
    get_skill_resource_helper,
    skills_check_helper,
)
from redis_sre_agent.skills.scaffold import scaffold_skill_package_from_markdown


@click.group()
def skills():
    """Inspect and scaffold Agent Skills packages."""
    pass


@skills.command("list")
@click.option("--query", "-q", type=str, default=None, help="Optional search query")
@click.option("--limit", "-l", default=20, show_default=True, help="Number of skills to return")
@click.option("--offset", "-o", default=0, show_default=True, help="Offset for pagination")
@click.option("--version", "-v", default="latest", show_default=True, help="Version filter")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def skills_list(query: str | None, limit: int, offset: int, version: str, as_json: bool):
    """List skills from the active skill backend."""

    async def _run():
        result = await skills_check_helper(
            query=query,
            limit=limit,
            offset=offset,
            version=version,
        )
        if as_json:
            click.echo(json.dumps(result, indent=2))
            return

        table = Table(title="Skills")
        table.add_column("Name")
        table.add_column("Protocol")
        table.add_column("Summary")
        table.add_column("Matched")
        for skill in result.get("skills", []):
            matched = str(
                skill.get("matched_resource_path") or skill.get("matched_resource_kind") or ""
            )
            table.add_row(
                str(skill.get("name") or ""),
                str(skill.get("protocol") or ""),
                str(skill.get("summary") or ""),
                matched or "-",
            )
        Console().print(table)

    asyncio.run(_run())


@skills.command("show")
@click.argument("skill_name")
@click.option("--version", "-v", default="latest", show_default=True, help="Version filter")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def skills_show(skill_name: str, version: str, as_json: bool):
    """Show one skill manifest or legacy skill body."""

    async def _run():
        result = await get_skill_helper(skill_name=skill_name, version=version)
        if as_json:
            click.echo(json.dumps(result, indent=2))
            return

        if result.get("error"):
            raise click.ClickException(str(result["error"]))

        click.echo(f"Skill: {result.get('skill_name', skill_name)}")
        click.echo(f"Protocol: {result.get('protocol', 'legacy_markdown')}")
        description = str(result.get("description") or "").strip()
        if description:
            click.echo(f"Description: {description}")
        if result.get("references"):
            click.echo("References:")
            for reference in result["references"]:
                click.echo(
                    f"- {reference.get('path')}: {reference.get('title') or reference.get('summary') or ''}".rstrip()
                )
        if result.get("scripts"):
            click.echo("Scripts:")
            for script in result["scripts"]:
                click.echo(f"- {script.get('path')}: {script.get('description') or ''}".rstrip())
        if result.get("assets"):
            click.echo("Assets:")
            for asset in result["assets"]:
                click.echo(f"- {asset.get('path')}")
        click.echo("")
        click.echo(str(result.get("full_content") or ""))

    asyncio.run(_run())


async def _read_resource(skill_name: str, resource_path: str, version: str, as_json: bool):
    result = await get_skill_resource_helper(
        skill_name=skill_name,
        resource_path=resource_path,
        version=version,
    )
    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if result.get("error"):
        raise click.ClickException(str(result["error"]))

    click.echo(f"Skill: {result.get('skill_name', skill_name)}")
    click.echo(f"Resource: {result.get('resource_path', resource_path)}")
    click.echo(f"Kind: {result.get('resource_kind', '')}")
    if result.get("truncated"):
        click.echo(
            f"Truncated to {result.get('char_budget')} chars from {result.get('content_length')} chars."
        )
    click.echo("")
    click.echo(str(result.get("content") or ""))


@skills.command("read-resource")
@click.argument("skill_name")
@click.argument("resource_path")
@click.option("--version", "-v", default="latest", show_default=True, help="Version filter")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def skills_read_resource(skill_name: str, resource_path: str, version: str, as_json: bool):
    """Read one resource from an Agent Skills package."""

    asyncio.run(_read_resource(skill_name, resource_path, version, as_json))


@skills.command("read-reference")
@click.argument("skill_name")
@click.argument("resource_path")
@click.option("--version", "-v", default="latest", show_default=True, help="Version filter")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def skills_read_reference(skill_name: str, resource_path: str, version: str, as_json: bool):
    """Alias for reading a reference resource by path."""

    asyncio.run(_read_resource(skill_name, resource_path, version, as_json))


@skills.command("scaffold")
@click.argument("legacy_skill_path", type=click.Path(exists=True, dir_okay=False, path_type=str))
@click.argument("target_dir", type=click.Path(path_type=str))
@click.option("--force", is_flag=True, help="Allow writing into an existing non-empty directory")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def skills_scaffold(legacy_skill_path: str, target_dir: str, force: bool, as_json: bool):
    """Scaffold an Agent Skills package from a legacy markdown skill."""

    result = scaffold_skill_package_from_markdown(legacy_skill_path, target_dir, force=force)
    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    click.echo(f"Created skill package: {result['package_dir']}")
    for file_name in result["files_created"]:
        click.echo(f"- {file_name}")
