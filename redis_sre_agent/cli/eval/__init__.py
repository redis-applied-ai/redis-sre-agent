"""CLI commands for eval scenario inspection and live suites."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import click

from redis_sre_agent.evaluation.agent_only import run_agent_only_scenario
from redis_sre_agent.evaluation.fake_mcp import build_fixture_mcp_runtime
from redis_sre_agent.evaluation.injection import (
    eval_injection_scope,
    get_active_eval_injection_overrides,
)
from redis_sre_agent.evaluation.knowledge_backend import build_fixture_knowledge_backend
from redis_sre_agent.evaluation.live_suite import (
    compare_live_eval_reports,
    load_baseline_policy,
    run_live_eval_suite,
)
from redis_sre_agent.evaluation.runtime import load_eval_scenario, run_full_turn_scenario
from redis_sre_agent.evaluation.scenarios import ExecutionLane
from redis_sre_agent.evaluation.tool_runtime import FixtureBehaviorState, build_fixture_tool_runtime


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


def _summary_overall_pass(summary: object) -> bool:
    return bool(getattr(summary, "overall_pass", False))


def _summary_text(summary: object) -> str:
    if not hasattr(summary, "suite_name"):
        return _summary_json(summary)

    lines = [
        f"Suite: {getattr(summary, 'suite_name', '')}",
        f"Trigger: {getattr(summary, 'trigger', '')}",
        f"Git SHA: {getattr(summary, 'git_sha', '')}",
        f"Output dir: {getattr(summary, 'output_dir', '')}",
        (
            "Scenarios: "
            f"{getattr(summary, 'total_scenarios', 0)} total, "
            f"{getattr(summary, 'failed_scenarios', 0)} failed "
            f"(allowed {getattr(summary, 'allowed_failed_scenarios', 0)})"
        ),
        f"Overall pass: {'yes' if _summary_overall_pass(summary) else 'no'}",
    ]
    return "\n".join(lines)


def _default_eval_session_id(scenario_id: str) -> str:
    return f"eval::{scenario_id.replace('/', '::')}"


def _json_compatible(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _extract_response_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        response = value.get("response")
        return response if isinstance(response, str) else None
    response = getattr(value, "response", None)
    return response if isinstance(response, str) else None


async def _run_agent_only_scenario_with_eval_overrides(
    scenario: Any,
    *,
    session_id: str,
    user_id: str | None,
) -> Any:
    inherited_overrides = get_active_eval_injection_overrides()
    behavior_state = FixtureBehaviorState()
    knowledge_backend = (
        inherited_overrides.knowledge_backend
        if inherited_overrides and inherited_overrides.knowledge_backend is not None
        else build_fixture_knowledge_backend(scenario)
    )
    mcp_runtime = (
        inherited_overrides.mcp_runtime
        if inherited_overrides and inherited_overrides.mcp_runtime is not None
        else build_fixture_mcp_runtime(scenario, state=behavior_state)
    )
    tool_runtime = (
        inherited_overrides.tool_runtime
        if inherited_overrides and inherited_overrides.tool_runtime is not None
        else build_fixture_tool_runtime(scenario, state=behavior_state)
    )
    mcp_servers = inherited_overrides.mcp_servers if inherited_overrides else None
    if mcp_servers is None and mcp_runtime is not None:
        mcp_servers = mcp_runtime.get_server_configs()

    with eval_injection_scope(
        knowledge_backend=knowledge_backend,
        mcp_servers=mcp_servers,
        mcp_runtime=mcp_runtime,
        tool_runtime=tool_runtime,
    ):
        return await run_agent_only_scenario(
            scenario,
            session_id=session_id,
            user_id=user_id,
        )


def run_mocked_eval_scenario_sync(
    scenario_path: str | Path,
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    allow_live_llm: bool = False,
) -> dict[str, Any]:
    """Run one mocked eval scenario and return a normalized payload."""

    scenario = load_eval_scenario(scenario_path)
    effective_session_id = session_id or _default_eval_session_id(scenario.id)
    llm_mode = getattr(getattr(scenario, "execution", None), "llm_mode", None)
    llm_mode_name = getattr(llm_mode, "value", llm_mode)
    if llm_mode_name == "live" and not allow_live_llm:
        raise PermissionError("Live-model eval scenarios require --allow-live-llm")

    if scenario.execution.lane is ExecutionLane.FULL_TURN:
        result = asyncio.run(
            run_full_turn_scenario(
                scenario,
                user_id=user_id,
                session_id=effective_session_id,
                allow_live_llm=allow_live_llm,
            )
        )
        return {
            "scenario_id": scenario.id,
            "scenario_name": scenario.name,
            "execution_lane": scenario.execution.lane.value,
            "session_id": effective_session_id,
            "user_id": user_id,
            "thread_id": result.thread_id,
            "task_id": result.task_id,
            "task_status": result.task_status,
            "response": _extract_response_text(result.turn_result),
            "result": _json_compatible(result),
        }

    result = asyncio.run(
        _run_agent_only_scenario_with_eval_overrides(
            scenario,
            session_id=effective_session_id,
            user_id=user_id,
        )
    )
    return {
        "scenario_id": scenario.id,
        "scenario_name": scenario.name,
        "execution_lane": scenario.execution.lane.value,
        "session_id": effective_session_id,
        "user_id": user_id,
        "agent_name": result.agent_name,
        "response": _extract_response_text(result.response),
        "result": _json_compatible(result),
    }


def _scenario_run_text(payload: dict[str, Any]) -> str:
    lines = [
        f"Scenario: {payload.get('scenario_id', '')}",
        f"Lane: {payload.get('execution_lane', '')}",
        f"Session ID: {payload.get('session_id', '')}",
    ]
    if payload.get("thread_id"):
        lines.append(f"Thread ID: {payload['thread_id']}")
    if payload.get("task_id"):
        lines.append(f"Task ID: {payload['task_id']}")
    if payload.get("task_status"):
        lines.append(f"Task status: {payload['task_status']}")
    if payload.get("agent_name"):
        lines.append(f"Agent: {payload['agent_name']}")
    response = payload.get("response")
    if response:
        lines.extend(["", "Response:", str(response)])
    else:
        lines.extend(["", "Result:", json.dumps(payload.get("result", {}), indent=2)])
    return "\n".join(lines)


@click.group()
def eval() -> None:
    """Run eval scenario utilities and live suites."""


@eval.command("run")
@click.argument(
    "scenario_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--user-id", type=str, default=None, help="Optional user id for the eval run.")
@click.option(
    "--session-id",
    type=str,
    default=None,
    help="Optional session id. Defaults to one derived from the scenario id.",
)
@click.option(
    "--allow-live-llm",
    is_flag=True,
    help="Explicitly allow scenarios configured with llm_mode=live.",
)
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def run_scenario(
    scenario_path: Path,
    user_id: str | None,
    session_id: str | None,
    allow_live_llm: bool,
    as_json: bool,
) -> None:
    """Run one mocked eval scenario."""

    payload = run_mocked_eval_scenario_sync(
        scenario_path,
        user_id=user_id,
        session_id=session_id,
        allow_live_llm=allow_live_llm,
    )
    click.echo(json.dumps(payload, indent=2) if as_json else _scenario_run_text(payload))


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
    click.echo(_summary_json(summary) if as_json else _summary_text(summary))
    if not _summary_overall_pass(summary):
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


__all__ = [
    "compare",
    "eval",
    "list_scenarios",
    "live_suite",
    "run_live_eval_suite_sync",
    "run_mocked_eval_scenario_sync",
    "run_scenario",
]
