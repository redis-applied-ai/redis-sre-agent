"""CLI commands for eval scenario inspection and live suites."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click

from redis_sre_agent.evaluation.live_suite import (
    compare_live_eval_reports,
    load_baseline_policy,
    run_live_eval_suite,
)
from redis_sre_agent.evaluation.runtime import load_eval_scenario


def run_live_eval_suite_sync(
    suite_name: str,
    *,
    config_path: str,
    output_dir: str,
    trigger: str = "manual",
    update_baseline: bool = False,
    session_id_prefix: str = "live-eval",
) -> object:
    """Run one configured live eval suite synchronously for Click."""

    return asyncio.run(
        run_live_eval_suite(
            suite_name,
            config_path=config_path,
            output_dir=output_dir,
            baseline_profile="manual_update" if update_baseline else "scheduled_live",
            event_name=trigger,
            update_baseline=update_baseline,
            session_id_prefix=session_id_prefix,
        )
    )


def _summary_json(summary: object) -> str:
    if hasattr(summary, "model_dump_json"):
        return summary.model_dump_json(indent=2)
    if hasattr(summary, "model_dump"):
        return json.dumps(summary.model_dump(mode="json"), indent=2)
    return json.dumps(summary, indent=2)


@click.group()
def eval() -> None:
    """Run eval scenario utilities and live suites."""


@eval.command("live-suite")
@click.argument("suite_name")
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    help="Live suite config YAML.",
)
@click.option(
    "--output-dir",
    required=True,
    type=click.Path(file_okay=False, path_type=str),
    help="Directory where live eval artifacts will be written.",
)
@click.option("--trigger", default="manual", show_default=True)
@click.option("--update-baseline/--no-update-baseline", default=False, show_default=True)
@click.option("--session-id-prefix", default="live-eval", show_default=True)
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def live_suite(
    suite_name: str,
    config_path: str,
    output_dir: str,
    trigger: str,
    update_baseline: bool,
    session_id_prefix: str,
    as_json: bool,
) -> None:
    """Run one configured live-model eval suite."""

    summary = run_live_eval_suite_sync(
        suite_name,
        config_path=config_path,
        output_dir=output_dir,
        trigger=trigger,
        update_baseline=update_baseline,
        session_id_prefix=session_id_prefix,
    )
    click.echo(_summary_json(summary) if as_json else _summary_json(summary))
    if not bool(getattr(summary, "overall_pass", True)):
        raise SystemExit(1)


@eval.command("compare")
@click.argument("baseline_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("candidate_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--policy-file",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Baseline policy file used to interpret comparison thresholds.",
)
@click.option(
    "--profile",
    "baseline_profile",
    default="scheduled_live",
    show_default=True,
    help="Baseline policy profile to use when the policy file defines profiles.",
)
def compare(
    baseline_dir: Path,
    candidate_dir: Path,
    policy_file: Path,
    baseline_profile: str,
) -> None:
    """Compare one live eval artifact directory against a baseline."""

    try:
        baseline_policy = load_baseline_policy(policy_file, profile=baseline_profile)
    except ValueError as exc:
        if "does not define profiles" not in str(exc):
            raise
        baseline_policy = load_baseline_policy(policy_file)
    summary = compare_live_eval_reports(
        baseline_dir,
        candidate_dir,
        baseline_policy=baseline_policy,
    )
    click.echo(json.dumps(summary.model_dump(mode="json"), indent=2))
    if not summary.passed:
        raise SystemExit(1)


@eval.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
@click.option(
    "--root",
    default="evals/scenarios",
    show_default=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Scenario root to scan.",
)
def list_scenarios(as_json: bool, root: Path) -> None:
    """List known eval scenario ids."""

    scenario_ids = [load_eval_scenario(path).id for path in sorted(root.rglob("scenario.yaml"))]
    if as_json:
        click.echo(json.dumps({"scenarios": scenario_ids}, indent=2))
        return
    for scenario_id in scenario_ids:
        click.echo(scenario_id)


__all__ = ["compare", "eval", "list_scenarios", "live_suite", "run_live_eval_suite_sync"]
