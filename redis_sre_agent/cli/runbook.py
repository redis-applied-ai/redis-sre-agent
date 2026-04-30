"""
CLI commands for Redis SRE runbook generation and management.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import click

from redis_sre_agent.agent.runbook_generator import RunbookGenerator
from redis_sre_agent.cli.logging_utils import log_cli_exception

logger = logging.getLogger(__name__)


@click.group()
def runbook():
    """Redis SRE runbook generation and management commands."""
    pass


@runbook.command()
@click.argument("topic")
@click.argument("scenario_description")
@click.option(
    "--severity",
    "-s",
    default="warning",
    type=click.Choice(["critical", "warning", "info"]),
    help="Severity level of the runbook",
)
@click.option("--category", "-c", default="operational_runbook", help="Category for the runbook")
@click.option(
    "--output-file", "-o", type=click.Path(), help="Output file path (default: auto-generated)"
)
@click.option(
    "--requirements",
    "-r",
    multiple=True,
    help="Specific requirements for the runbook (can be used multiple times)",
)
@click.option("--max-iterations", default=2, type=int, help="Maximum refinement iterations")
@click.option(
    "--auto-save",
    is_flag=True,
    default=True,
    help="Automatically save to source_documents/runbooks/",
)
def generate(
    topic: str,
    scenario_description: str,
    severity: str,
    category: str,
    output_file: Optional[str],
    requirements: tuple,
    max_iterations: int,
    auto_save: bool,
):
    """Generate a new Redis SRE runbook for the specified topic."""

    async def _generate():
        click.echo(f"🚀 Generating runbook for: {topic}")
        click.echo(f"📋 Scenario: {scenario_description}")

        if requirements:
            click.echo(f"📝 Requirements: {', '.join(requirements)}")

        generator = RunbookGenerator()

        try:
            result = await generator.generate_runbook(
                topic=topic,
                scenario_description=scenario_description,
                severity=severity,
                category=category,
                specific_requirements=list(requirements) if requirements else None,
                max_iterations=max_iterations,
            )

            if result["success"]:
                runbook = result["runbook"]
                evaluation = result["evaluation"]

                click.echo("\n✅ Runbook Generated Successfully!")
                click.echo(f"📊 Quality Score: {evaluation.overall_score:.1f}/5.0")
                click.echo(f"📝 Content Length: {len(runbook.content):,} characters")
                click.echo(f"🔄 Iterations: {result['iterations']}")

                # Display evaluation summary
                click.echo("\n📊 Evaluation Details:")
                click.echo(f"   Technical Accuracy: {evaluation.technical_accuracy}/5")
                click.echo(f"   Completeness: {evaluation.completeness}/5")
                click.echo(f"   Actionability: {evaluation.actionability}/5")
                click.echo(f"   Production Readiness: {evaluation.production_readiness}/5")

                if evaluation.strengths:
                    click.echo("\n💪 Strengths:")
                    for strength in evaluation.strengths:
                        click.echo(f"   • {strength}")

                if evaluation.weaknesses:
                    click.echo("\n⚠️  Areas for Improvement:")
                    for weakness in evaluation.weaknesses:
                        click.echo(f"   • {weakness}")

                if evaluation.recommendations:
                    click.echo("\n💡 Recommendations:")
                    for rec in evaluation.recommendations:
                        click.echo(f"   • {rec}")

                # Save the runbook
                if auto_save or output_file:
                    saved_path = await _save_runbook(runbook, output_file, topic)
                    click.echo(f"\n💾 Runbook saved to: {saved_path}")

                # Show preview
                if click.confirm("\nWould you like to see the full runbook content?"):
                    click.echo("\n" + "=" * 80)
                    click.echo(runbook.content)
                    click.echo("=" * 80)

                # Offer to ingest into knowledge base
                if click.confirm(
                    "\nWould you like to ingest this runbook into the knowledge base?"
                ):
                    await _ingest_runbook(runbook)
                    click.echo("✅ Runbook ingested into knowledge base!")

            else:
                click.echo("❌ Runbook generation failed")
                return 1

        except Exception as e:
            log_cli_exception(__name__, "runbook CLI command failed", e)
            click.echo(f"❌ Error generating runbook: {e}")
            logger.exception("Runbook generation failed")
            return 1

    return asyncio.run(_generate())


@runbook.command()
@click.option(
    "--input-dir",
    "-i",
    type=click.Path(exists=True),
    default="source_documents/runbooks",
    help="Directory containing runbook markdown files",
)
@click.option(
    "--output-file", "-o", type=click.Path(), help="Output JSON file for evaluation results"
)
def evaluate(input_dir: str, output_file: Optional[str]):
    """Evaluate existing runbooks in the source documents directory."""

    async def _evaluate():
        input_path = Path(input_dir)
        click.echo(f"🔍 Evaluating runbooks in: {input_path}")

        markdown_files = list(input_path.glob("*.md"))
        if not markdown_files:
            click.echo("⚠️  No markdown files found to evaluate")
            return 1

        click.echo(f"📄 Found {len(markdown_files)} runbooks to evaluate")

        generator = RunbookGenerator()
        results = []

        for md_file in markdown_files:
            click.echo(f"\n📝 Evaluating: {md_file.name}")

            try:
                # Read the runbook content
                content = md_file.read_text(encoding="utf-8")

                # Extract title from content or filename
                title_line = next(
                    (line for line in content.split("\n") if line.startswith("# ")), None
                )
                title = title_line[2:].strip() if title_line else md_file.stem

                # Create a mock runbook object for evaluation
                from redis_sre_agent.agent.runbook_generator import GeneratedRunbook

                runbook = GeneratedRunbook(
                    title=title,
                    content=content,
                    category="existing_runbook",
                    severity="unknown",
                    sources=["existing_file"],
                    generation_timestamp="",
                )

                # Evaluate the runbook
                evaluation = await generator._evaluate_runbook(runbook)

                result = {
                    "filename": md_file.name,
                    "title": title,
                    "overall_score": evaluation.overall_score,
                    "technical_accuracy": evaluation.technical_accuracy,
                    "completeness": evaluation.completeness,
                    "actionability": evaluation.actionability,
                    "production_readiness": evaluation.production_readiness,
                    "strengths": evaluation.strengths,
                    "weaknesses": evaluation.weaknesses,
                    "recommendations": evaluation.recommendations,
                    "evaluation_summary": evaluation.evaluation_summary,
                }

                results.append(result)

                click.echo(f"   📊 Score: {evaluation.overall_score:.1f}/5.0")
                click.echo(
                    f"   📈 Breakdown: TA:{evaluation.technical_accuracy} C:{evaluation.completeness} A:{evaluation.actionability} PR:{evaluation.production_readiness}"
                )

            except Exception as e:
                log_cli_exception(__name__, "runbook CLI command failed", e)
                click.echo(f"   ❌ Failed to evaluate {md_file.name}: {e}")

        # Summary
        if results:
            avg_score = sum(r["overall_score"] for r in results) / len(results)
            excellent = sum(1 for r in results if r["overall_score"] >= 4.0)
            good = sum(1 for r in results if 3.0 <= r["overall_score"] < 4.0)
            needs_improvement = sum(1 for r in results if r["overall_score"] < 3.0)

            click.echo("\n" + "=" * 60)
            click.echo("📊 Evaluation Summary")
            click.echo("=" * 60)
            click.echo(f"📈 Average Score: {avg_score:.2f}/5.0")
            click.echo(
                f"🟢 Excellent (≥4.0): {excellent}/{len(results)} ({excellent / len(results) * 100:.1f}%)"
            )
            click.echo(
                f"🟡 Good (3.0-3.9): {good}/{len(results)} ({good / len(results) * 100:.1f}%)"
            )
            click.echo(
                f"🔴 Needs Improvement (<3.0): {needs_improvement}/{len(results)} ({needs_improvement / len(results) * 100:.1f}%)"
            )

            # Save results if requested
            if output_file:
                output_path = Path(output_file)
                with output_path.open("w") as f:
                    json.dump(
                        {
                            "evaluation_timestamp": runbook.generation_timestamp or "unknown",
                            "total_runbooks": len(results),
                            "average_score": avg_score,
                            "results": results,
                        },
                        f,
                        indent=2,
                    )
                click.echo(f"\n💾 Detailed results saved to: {output_path}")

    return asyncio.run(_evaluate())


async def _save_runbook(runbook, output_file: Optional[str], topic: str) -> str:
    """Save runbook to file."""
    if output_file:
        output_path = Path(output_file)
    else:
        # Auto-generate filename
        safe_topic = "".join(c if c.isalnum() or c in "-_" else "-" for c in topic.lower())
        output_path = Path("source_documents/runbooks") / f"redis-{safe_topic}.md"

        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write the runbook content
    output_path.write_text(runbook.content, encoding="utf-8")

    return str(output_path)


async def _ingest_runbook(runbook):
    """Ingest runbook into the knowledge base."""
    from redis_sre_agent.core.docket_tasks import ingest_sre_document

    await ingest_sre_document(
        title=runbook.title,
        content=runbook.content,
        source=f"Generated runbook - {runbook.generation_timestamp}",
        category=runbook.category,
        severity=runbook.severity,
    )


if __name__ == "__main__":
    runbook()
