from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
import yaml

import redis_sre_agent.evaluation.live_suite as live_suite_module
from redis_sre_agent.agent.models import AgentResponse
from redis_sre_agent.evaluation.live_suite import (
    LiveEvalScenarioResult,
    compare_live_eval_reports,
    load_live_eval_suite_config,
    run_live_eval_suite,
)
from redis_sre_agent.evaluation.report_schema import (
    EvalBaselinePolicy,
    EvalReportBundle,
    JudgeSummary,
)
from redis_sre_agent.evaluation.scenarios import ExecutionLane, LLMMode


def _write_report(
    root,
    scenario_id: str,
    *,
    score: float | None,
    overall_pass: bool = True,
) -> None:
    judge_scores = (
        None
        if score is None
        else JudgeSummary(
            overall_score=score,
            criteria_scores={},
            detailed_feedback="ok",
            passed=overall_pass,
        )
    )
    bundle = EvalReportBundle(
        scenario_id=scenario_id,
        git_sha="deadbeef",
        execution_lane=ExecutionLane.AGENT_ONLY,
        overall_pass=overall_pass,
        agent_type="knowledge_only",
        judge_scores=judge_scores,
    )
    scenario_dir = root / scenario_id
    scenario_dir.mkdir(parents=True, exist_ok=True)
    (scenario_dir / "report.json").write_text(bundle.model_dump_json(indent=2), encoding="utf-8")


def test_live_suite_config_accepts_single_suite_manifest_with_policy_profile(tmp_path):
    policy_path = tmp_path / "baseline_policy.yaml"
    policy_path.write_text(
        yaml.safe_dump(
            {
                "profiles": {
                    "scheduled_live": {
                        "baseline_id": "live-smoke-v1",
                        "update_allowed": False,
                        "allowed_triggers": ["schedule", "workflow_dispatch"],
                        "review_required": True,
                        "acceptable_variance": {"overall_score_max_drop": 3.0},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    suite_path = tmp_path / "live-suite.yaml"
    suite_path.write_text(
        yaml.safe_dump(
            {
                "name": "live-agent-only-smoke",
                "description": "Smoke suite",
                "policy_file": str(policy_path),
                "scenarios": [
                    "evals/scenarios/prompt/knowledge-agent-no-live-access/scenario.yaml"
                ],
            }
        ),
        encoding="utf-8",
    )

    config = load_live_eval_suite_config(suite_path, baseline_profile="scheduled_live")

    suite = config.suites["live-agent-only-smoke"]
    assert suite.description == "Smoke suite"
    assert suite.scenarios == [
        "evals/scenarios/prompt/knowledge-agent-no-live-access/scenario.yaml"
    ]
    assert suite.baseline_policy.mode == "scheduled_live"
    assert suite.baseline_policy.baseline_id == "live-smoke-v1"
    assert suite.baseline_policy.allowed_triggers == ["schedule", "workflow_dispatch"]
    assert suite.baseline_policy.acceptable_variance == {"overall_score_max_drop": 3.0}


def test_live_suite_config_override_selects_requested_policy_profile(tmp_path):
    policy_path = tmp_path / "baseline_policy.yaml"
    policy_path.write_text(
        yaml.safe_dump(
            {
                "profiles": {
                    "scheduled_live": {"update_allowed": False},
                    "manual_update": {"update_allowed": True, "max_failed_scenarios": 1},
                }
            }
        ),
        encoding="utf-8",
    )
    suite_path = tmp_path / "live-suite.yaml"
    suite_path.write_text(
        yaml.safe_dump(
            {
                "name": "live-agent-only-smoke",
                "policy_file": str(policy_path),
                "scenarios": ["scenario.yaml"],
            }
        ),
        encoding="utf-8",
    )

    config = load_live_eval_suite_config(suite_path, baseline_profile="manual_update")

    policy = config.suites["live-agent-only-smoke"].baseline_policy
    assert policy.mode == "manual_update"
    assert policy.update_allowed is True
    assert policy.max_failed_scenarios == 1


@pytest.mark.asyncio
async def test_run_live_eval_suite_coerces_scenarios_to_live_and_writes_summary(
    tmp_path,
    monkeypatch,
):
    policy_path = tmp_path / "baseline_policy.yaml"
    policy_path.write_text(
        yaml.safe_dump(
            {
                "profiles": {
                    "scheduled_live": {
                        "baseline_id": "live-smoke-v1",
                        "update_allowed": False,
                        "allowed_triggers": ["workflow_dispatch"],
                        "max_failed_scenarios": 0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        """
id: prompt/sample
name: Sample
provenance:
  source_kind: synthetic
  source_pack: prompt-core
  source_pack_version: 2026-04-14
  golden:
    expectation_basis: human_authored
    review_status: reviewed
execution:
  lane: agent_only
  agent: knowledge_only
  query: hi
knowledge:
  mode: startup_only
  version: latest
""".strip(),
        encoding="utf-8",
    )
    suite_path = tmp_path / "live-suite.yaml"
    suite_path.write_text(
        yaml.safe_dump(
            {
                "name": "live-agent-only-smoke",
                "policy_file": str(policy_path),
                "scenarios": [str(scenario_path)],
            }
        ),
        encoding="utf-8",
    )

    seen: dict[str, object] = {}

    async def fake_run_scenario_live(
        scenario,
        *,
        user_id,
        session_id_prefix,
        output_dir,
        git_sha,
        baseline_policy,
        **_kwargs,
    ):
        seen["llm_mode"] = scenario.execution.llm_mode
        seen["user_id"] = user_id
        seen["session_id_prefix"] = session_id_prefix
        seen["git_sha"] = git_sha
        seen["policy_mode"] = baseline_policy.mode
        return LiveEvalScenarioResult(
            scenario_id=scenario.id,
            execution_lane=ExecutionLane.AGENT_ONLY,
            overall_pass=True,
            report_json=str(output_dir / scenario.id / "report.json"),
            report_markdown=str(output_dir / scenario.id / "report.md"),
        )

    monkeypatch.setattr(
        "redis_sre_agent.evaluation.live_suite._run_scenario_live", fake_run_scenario_live
    )
    monkeypatch.setattr(
        "redis_sre_agent.evaluation.live_suite.live_eval_git_sha", lambda: "deadbeefcafe"
    )

    summary = await run_live_eval_suite(
        "live-agent-only-smoke",
        config_path=suite_path,
        output_dir=tmp_path / "artifacts",
        user_id="ci-user",
        session_id_prefix="gha-live",
        event_name="workflow_dispatch",
    )

    summary_path = tmp_path / "artifacts" / "live-agent-only-smoke" / "summary.json"
    assert seen == {
        "llm_mode": LLMMode.LIVE,
        "user_id": "ci-user",
        "session_id_prefix": "gha-live",
        "git_sha": "deadbeefcafe",
        "policy_mode": "scheduled_live",
    }
    assert summary.overall_pass is True
    assert summary.trigger == "workflow_dispatch"
    assert json.loads(summary_path.read_text(encoding="utf-8"))["git_sha"] == "deadbeefcafe"


@pytest.mark.asyncio
async def test_run_live_eval_suite_rejects_disallowed_trigger(tmp_path):
    policy_path = tmp_path / "baseline_policy.yaml"
    policy_path.write_text(
        yaml.safe_dump(
            {
                "profiles": {
                    "manual_update": {
                        "update_allowed": True,
                        "allowed_triggers": ["workflow_dispatch"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    suite_path = tmp_path / "live-suite.yaml"
    suite_path.write_text(
        yaml.safe_dump(
            {
                "name": "live-agent-only-smoke",
                "policy_file": str(policy_path),
                "baseline_profile": "manual_update",
                "scenarios": [
                    "evals/scenarios/prompt/knowledge-agent-no-live-access/scenario.yaml"
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="restricted"):
        await run_live_eval_suite(
            "live-agent-only-smoke",
            config_path=suite_path,
            output_dir=tmp_path / "artifacts",
            event_name="pull_request",
        )


@pytest.mark.asyncio
async def test_run_scenario_live_allows_agent_only_scenarios_without_mcp_servers(
    tmp_path,
    monkeypatch,
):
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        """
id: prompt/no-mcp
name: No MCP
provenance:
  source_kind: synthetic
  source_pack: prompt-core
  source_pack_version: 2026-04-15
  golden:
    expectation_basis: human_authored
    review_status: reviewed
execution:
  lane: agent_only
  agent: knowledge_only
  query: hi
knowledge:
  mode: startup_only
  version: latest
""".strip(),
        encoding="utf-8",
    )
    scenario = live_suite_module._coerce_live_scenario(
        live_suite_module.load_eval_scenario(scenario_path)
    )
    seen: dict[str, object] = {}

    @contextmanager
    def fake_eval_injection_scope(**kwargs):
        seen["mcp_runtime"] = kwargs["mcp_runtime"]
        seen["mcp_servers"] = kwargs["mcp_servers"]
        yield

    async def fake_run_agent_only_scenario(*_args, **_kwargs):
        return SimpleNamespace(
            context={"scope": "ok"},
            response=AgentResponse(response="all good"),
            agent_name="knowledge_only",
        )

    monkeypatch.setattr(live_suite_module, "eval_injection_scope", fake_eval_injection_scope)
    monkeypatch.setattr(live_suite_module, "run_agent_only_scenario", fake_run_agent_only_scenario)
    monkeypatch.setattr(
        live_suite_module,
        "build_eval_artifact_bundle",
        lambda *args, **kwargs: SimpleNamespace(overall_pass=True),
    )
    monkeypatch.setattr(
        live_suite_module,
        "write_eval_artifact_bundle",
        lambda bundle, output_dir: {
            "report_json": output_dir / "report.json",
            "report_markdown": output_dir / "report.md",
        },
    )

    result = await live_suite_module._run_scenario_live(
        scenario,
        user_id="ci-user",
        session_id_prefix="gha-live",
        output_dir=tmp_path / "artifacts",
        git_sha="deadbeef",
        baseline_policy=EvalBaselinePolicy(mode="scheduled_live"),
    )

    assert scenario.tools.mcp_servers == {}
    assert seen == {"mcp_runtime": None, "mcp_servers": None}
    assert result == LiveEvalScenarioResult(
        scenario_id="prompt/no-mcp",
        execution_lane=ExecutionLane.AGENT_ONLY,
        overall_pass=True,
        report_json=str(tmp_path / "artifacts" / "report.json"),
        report_markdown=str(tmp_path / "artifacts" / "report.md"),
    )


def test_compare_live_eval_reports_flags_score_drop_and_missing_candidate(tmp_path):
    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    _write_report(baseline_dir, "prompt/knowledge-agent-no-live-access", score=91.0)
    _write_report(candidate_dir, "prompt/knowledge-agent-no-live-access", score=85.0)
    _write_report(baseline_dir, "sources/pinned-sev1-escalation-policy", score=89.0)

    summary = compare_live_eval_reports(
        baseline_dir,
        candidate_dir,
        baseline_policy=EvalBaselinePolicy(
            mode="scheduled_live",
            judge_score_variance_band=3.0,
        ),
    )

    assert summary.passed is False
    assert [row.scenario_id for row in summary.rows] == [
        "prompt/knowledge-agent-no-live-access",
        "sources/pinned-sev1-escalation-policy",
    ]
    assert summary.rows[0].violations == [
        "judge score drop exceeded allowed variance (91.0 -> 85.0, allowed 3.0)"
    ]
    assert summary.rows[1].violations == ["missing candidate report"]
