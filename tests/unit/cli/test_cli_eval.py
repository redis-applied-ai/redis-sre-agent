from __future__ import annotations

import asyncio

from click.testing import CliRunner

from redis_sre_agent.agent.models import AgentResponse
from redis_sre_agent.cli.eval import eval
from redis_sre_agent.cli.main import main
from redis_sre_agent.evaluation.agent_only import AgentOnlyHarnessResult
from redis_sre_agent.evaluation.runtime import EvalFullTurnResult
from redis_sre_agent.evaluation.scenarios import ExecutionLane


def test_eval_cli_help_lists_live_suite_command():
    runner = CliRunner()

    result = runner.invoke(eval, ["--help"])

    assert result.exit_code == 0
    assert "compare" in result.output
    assert "run" in result.output
    assert "live-suite" in result.output
    assert "list" in result.output


def test_eval_command_is_registered_in_main_cli():
    runner = CliRunner()

    result = runner.invoke(main, ["eval", "--help"])

    assert result.exit_code == 0
    assert "run" in result.output
    assert "live-suite" in result.output


def test_eval_run_command_delegates_to_runner(tmp_path, monkeypatch):
    runner = CliRunner()
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text("id: prompt/sample\nname: Sample\n", encoding="utf-8")
    seen: dict[str, object] = {}

    def fake_run_mocked_eval_scenario_sync(
        path,
        *,
        user_id,
        session_id,
        allow_live_llm,
    ) -> dict[str, object]:
        seen.update(
            {
                "path": str(path),
                "user_id": user_id,
                "session_id": session_id,
                "allow_live_llm": allow_live_llm,
            }
        )
        return {
            "scenario_id": "prompt/sample",
            "execution_lane": "agent_only",
            "session_id": "eval::prompt::sample",
            "agent_name": "knowledge_only",
            "response": "ok",
            "result": {"response": "ok"},
        }

    monkeypatch.setattr(
        "redis_sre_agent.cli.eval.run_mocked_eval_scenario_sync",
        fake_run_mocked_eval_scenario_sync,
    )

    result = runner.invoke(
        eval,
        [
            "run",
            str(scenario_path),
            "--user-id",
            "local-eval",
            "--session-id",
            "session-123",
            "--allow-live-llm",
        ],
    )

    assert result.exit_code == 0, result.output
    assert seen == {
        "path": str(scenario_path),
        "user_id": "local-eval",
        "session_id": "session-123",
        "allow_live_llm": True,
    }
    assert "Scenario: prompt/sample" in result.output
    assert "Response:" in result.output
    assert "ok" in result.output


def test_eval_run_command_outputs_json_when_requested(tmp_path, monkeypatch):
    runner = CliRunner()
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text("id: prompt/sample\nname: Sample\n", encoding="utf-8")

    monkeypatch.setattr(
        "redis_sre_agent.cli.eval.run_mocked_eval_scenario_sync",
        lambda *args, **kwargs: {
            "scenario_id": "prompt/sample",
            "execution_lane": "full_turn",
            "session_id": "eval::prompt::sample",
            "response": "ok",
            "result": {"response": "ok"},
        },
    )

    result = runner.invoke(
        eval,
        [
            "run",
            str(scenario_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert '"scenario_id": "prompt/sample"' in result.output
    assert '"execution_lane": "full_turn"' in result.output


def test_run_mocked_eval_scenario_sync_runs_full_turn(monkeypatch):
    scenario = type(
        "Scenario",
        (),
        {
            "id": "prompt/sample",
            "name": "Sample",
            "execution": type(
                "Execution",
                (),
                {"lane": ExecutionLane.FULL_TURN, "llm_mode": "replay"},
            )(),
        },
    )()
    seen: dict[str, object] = {}

    async def fake_run_full_turn_scenario(
        incoming,
        *,
        user_id,
        session_id,
        allow_live_llm,
    ):
        seen.update(
            {
                "scenario": incoming,
                "user_id": user_id,
                "session_id": session_id,
                "allow_live_llm": allow_live_llm,
            }
        )
        return EvalFullTurnResult(
            scenario_id="prompt/sample",
            scenario_name="Sample",
            execution_lane=ExecutionLane.FULL_TURN,
            thread_id="thread-123",
            task_id="task-123",
            task_status="completed",
            turn_result={"response": "full-turn ok"},
        )

    monkeypatch.setattr("redis_sre_agent.cli.eval.load_eval_scenario", lambda path: scenario)
    monkeypatch.setattr(
        "redis_sre_agent.cli.eval.run_full_turn_scenario",
        fake_run_full_turn_scenario,
    )

    from redis_sre_agent.cli.eval import run_mocked_eval_scenario_sync

    payload = run_mocked_eval_scenario_sync("scenario.yaml", user_id="local-eval")

    assert seen["scenario"] is scenario
    assert seen["user_id"] == "local-eval"
    assert seen["session_id"] == "eval::prompt::sample"
    assert seen["allow_live_llm"] is False
    assert payload["thread_id"] == "thread-123"
    assert payload["task_id"] == "task-123"
    assert payload["response"] == "full-turn ok"


def test_run_mocked_eval_scenario_sync_runs_agent_only(monkeypatch):
    scenario = type(
        "Scenario",
        (),
        {
            "id": "prompt/sample",
            "name": "Sample",
            "execution": type(
                "Execution",
                (),
                {"lane": ExecutionLane.AGENT_ONLY, "llm_mode": "replay"},
            )(),
        },
    )()
    seen: dict[str, object] = {}

    async def fake_run_agent_only_scenario_with_eval_overrides(
        incoming,
        *,
        session_id,
        user_id,
    ):
        seen.update(
            {
                "scenario": incoming,
                "session_id": session_id,
                "user_id": user_id,
            }
        )
        return AgentOnlyHarnessResult(
            agent_name="knowledge_only",
            session_id=session_id,
            response=AgentResponse(response="agent-only ok"),
        )

    monkeypatch.setattr("redis_sre_agent.cli.eval.load_eval_scenario", lambda path: scenario)
    monkeypatch.setattr(
        "redis_sre_agent.cli.eval._run_agent_only_scenario_with_eval_overrides",
        fake_run_agent_only_scenario_with_eval_overrides,
    )

    from redis_sre_agent.cli.eval import run_mocked_eval_scenario_sync

    payload = run_mocked_eval_scenario_sync("scenario.yaml", user_id="local-eval")

    assert seen["scenario"] is scenario
    assert seen["session_id"] == "eval::prompt::sample"
    assert seen["user_id"] == "local-eval"
    assert payload["agent_name"] == "knowledge_only"
    assert payload["response"] == "agent-only ok"


def test_run_mocked_eval_scenario_sync_preserves_plain_string_agent_only_response(monkeypatch):
    scenario = type(
        "Scenario",
        (),
        {
            "id": "prompt/sample",
            "name": "Sample",
            "execution": type(
                "Execution",
                (),
                {"lane": ExecutionLane.AGENT_ONLY, "llm_mode": "replay"},
            )(),
        },
    )()

    async def fake_run_agent_only_scenario_with_eval_overrides(
        incoming,
        *,
        session_id,
        user_id,
    ):
        assert incoming is scenario
        assert session_id == "eval::prompt::sample"
        assert user_id == "local-eval"
        return AgentOnlyHarnessResult(
            agent_name="knowledge_only",
            session_id=session_id,
            response="plain-string response",
        )

    monkeypatch.setattr("redis_sre_agent.cli.eval.load_eval_scenario", lambda path: scenario)
    monkeypatch.setattr(
        "redis_sre_agent.cli.eval._run_agent_only_scenario_with_eval_overrides",
        fake_run_agent_only_scenario_with_eval_overrides,
    )

    from redis_sre_agent.cli.eval import run_mocked_eval_scenario_sync

    payload = run_mocked_eval_scenario_sync("scenario.yaml", user_id="local-eval")

    assert payload["response"] == "plain-string response"


def test_run_agent_only_scenario_with_eval_overrides_installs_fixture_backends(monkeypatch):
    scenario = type(
        "Scenario",
        (),
        {
            "id": "prompt/sample",
            "name": "Sample",
            "execution": type(
                "Execution",
                (),
                {"lane": ExecutionLane.AGENT_ONLY, "llm_mode": "replay"},
            )(),
            "tools": type("Tools", (), {"mcp_servers": {}})(),
        },
    )()
    knowledge_backend = object()
    tool_runtime = object()
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        "redis_sre_agent.cli.eval.build_fixture_knowledge_backend",
        lambda incoming: knowledge_backend if incoming is scenario else None,
    )
    monkeypatch.setattr(
        "redis_sre_agent.cli.eval.build_fixture_mcp_runtime",
        lambda incoming, *, state: None if incoming is scenario else state,
    )
    monkeypatch.setattr(
        "redis_sre_agent.cli.eval.build_fixture_tool_runtime",
        lambda incoming, *, state: tool_runtime if incoming is scenario else state,
    )

    async def fake_run_agent_only_scenario(
        incoming,
        *,
        session_id,
        user_id,
    ):
        from redis_sre_agent.evaluation.injection import (
            get_active_knowledge_backend,
            get_active_tool_runtime,
        )

        seen.update(
            {
                "scenario": incoming,
                "session_id": session_id,
                "user_id": user_id,
                "knowledge_backend": get_active_knowledge_backend(),
                "tool_runtime": get_active_tool_runtime(),
            }
        )
        return AgentOnlyHarnessResult(
            agent_name="knowledge_only",
            session_id=session_id,
            response=AgentResponse(response="agent-only ok"),
        )

    monkeypatch.setattr(
        "redis_sre_agent.cli.eval.run_agent_only_scenario",
        fake_run_agent_only_scenario,
    )

    from redis_sre_agent.cli.eval import _run_agent_only_scenario_with_eval_overrides

    payload = asyncio.run(
        _run_agent_only_scenario_with_eval_overrides(
            scenario,
            session_id="eval::prompt::sample",
            user_id="local-eval",
        )
    )

    assert payload.agent_name == "knowledge_only"
    assert seen == {
        "scenario": scenario,
        "session_id": "eval::prompt::sample",
        "user_id": "local-eval",
        "knowledge_backend": knowledge_backend,
        "tool_runtime": tool_runtime,
    }


def test_run_mocked_eval_scenario_sync_rejects_live_llm_without_opt_in(monkeypatch):
    scenario = type(
        "Scenario",
        (),
        {
            "id": "prompt/sample",
            "name": "Sample",
            "execution": type(
                "Execution",
                (),
                {"lane": ExecutionLane.AGENT_ONLY, "llm_mode": "live"},
            )(),
        },
    )()

    monkeypatch.setattr("redis_sre_agent.cli.eval.load_eval_scenario", lambda path: scenario)

    from redis_sre_agent.cli.eval import run_mocked_eval_scenario_sync

    try:
        run_mocked_eval_scenario_sync("scenario.yaml")
    except PermissionError as exc:
        assert "--allow-live-llm" in str(exc)
    else:
        raise AssertionError("expected PermissionError")


def test_eval_live_suite_command_delegates_to_runner(tmp_path, monkeypatch):
    runner = CliRunner()
    config_path = tmp_path / "config.yaml"
    config_path.write_text("suites: {}\n", encoding="utf-8")

    class Summary:
        suite_name = "weekly-live-smoke"
        trigger = "manual"
        git_sha = "deadbeef"
        output_dir = str(tmp_path / "artifacts")
        total_scenarios = 1
        failed_scenarios = 0
        allowed_failed_scenarios = 0
        overall_pass = True

        @staticmethod
        def model_dump_json(*, indent: int) -> str:
            return '{"suite_name":"weekly-live-smoke"}'

    seen: dict[str, object] = {}

    def fake_run_live_eval_suite_sync(
        suite_name: str,
        *,
        config_path: str,
        output_dir: str,
        trigger: str,
        update_baseline: bool,
        session_id_prefix: str,
    ) -> object:
        seen.update(
            {
                "suite_name": suite_name,
                "config_path": config_path,
                "output_dir": output_dir,
                "trigger": trigger,
                "update_baseline": update_baseline,
                "session_id_prefix": session_id_prefix,
            }
        )
        return Summary()

    monkeypatch.setattr(
        "redis_sre_agent.cli.eval.run_live_eval_suite_sync",
        fake_run_live_eval_suite_sync,
    )

    result = runner.invoke(
        eval,
        [
            "live-suite",
            "weekly-live-smoke",
            "--config",
            str(config_path),
            "--output-dir",
            str(tmp_path / "artifacts"),
            "--session-id-prefix",
            "gha-live",
        ],
    )

    assert result.exit_code == 0, result.output
    assert seen == {
        "suite_name": "weekly-live-smoke",
        "config_path": str(config_path),
        "output_dir": str(tmp_path / "artifacts"),
        "trigger": "manual",
        "update_baseline": False,
        "session_id_prefix": "gha-live",
    }
    assert "Suite: weekly-live-smoke" in result.output
    assert "Overall pass: yes" in result.output
    assert '"suite_name"' not in result.output


def test_eval_live_suite_command_outputs_json_when_requested(tmp_path, monkeypatch):
    runner = CliRunner()
    config_path = tmp_path / "config.yaml"
    config_path.write_text("suites: {}\n", encoding="utf-8")

    class Summary:
        overall_pass = True

        @staticmethod
        def model_dump_json(*, indent: int) -> str:
            return '{"suite_name":"weekly-live-smoke"}'

    monkeypatch.setattr(
        "redis_sre_agent.cli.eval.run_live_eval_suite_sync",
        lambda *args, **kwargs: Summary(),
    )

    result = runner.invoke(
        eval,
        [
            "live-suite",
            "weekly-live-smoke",
            "--config",
            str(config_path),
            "--output-dir",
            str(tmp_path / "artifacts"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert result.output.strip() == '{"suite_name":"weekly-live-smoke"}'


def test_eval_live_suite_command_returns_nonzero_when_suite_fails(tmp_path, monkeypatch):
    runner = CliRunner()
    config_path = tmp_path / "config.yaml"
    config_path.write_text("suites: {}\n", encoding="utf-8")

    class FailedSummary:
        overall_pass = False

        @staticmethod
        def model_dump_json(*, indent: int) -> str:
            return '{"suite_name":"weekly-live-smoke"}'

    monkeypatch.setattr(
        "redis_sre_agent.cli.eval.run_live_eval_suite_sync",
        lambda *args, **kwargs: FailedSummary(),
    )

    result = runner.invoke(
        eval,
        [
            "live-suite",
            "weekly-live-smoke",
            "--config",
            str(config_path),
            "--output-dir",
            str(tmp_path / "artifacts"),
        ],
    )

    assert result.exit_code == 1


def test_eval_live_suite_command_defaults_missing_overall_pass_to_failure(tmp_path, monkeypatch):
    runner = CliRunner()
    config_path = tmp_path / "config.yaml"
    config_path.write_text("suites: {}\n", encoding="utf-8")

    class Summary:
        suite_name = "weekly-live-smoke"
        trigger = "manual"
        git_sha = "deadbeef"
        output_dir = str(tmp_path / "artifacts")
        total_scenarios = 1
        failed_scenarios = 1
        allowed_failed_scenarios = 0

    monkeypatch.setattr(
        "redis_sre_agent.cli.eval.run_live_eval_suite_sync",
        lambda *args, **kwargs: Summary(),
    )

    result = runner.invoke(
        eval,
        [
            "live-suite",
            "weekly-live-smoke",
            "--config",
            str(config_path),
            "--output-dir",
            str(tmp_path / "artifacts"),
        ],
    )

    assert result.exit_code == 1
    assert "Overall pass: no" in result.output


def test_eval_list_json_includes_known_scenario():
    runner = CliRunner()

    result = runner.invoke(eval, ["list", "--json"])

    assert result.exit_code == 0, result.output
    assert "prompt/chat-iterative-tool-use" in result.output


def test_eval_compare_command_exits_nonzero_when_comparison_fails(tmp_path):
    runner = CliRunner()
    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    baseline_dir.mkdir()
    candidate_dir.mkdir()
    policy_path = tmp_path / "baseline_policy.yaml"
    policy_path.write_text(
        "mode: scheduled_live\njudge_score_variance_band: 3.0\n", encoding="utf-8"
    )

    for root, scenario_id, score in [
        (baseline_dir, "prompt/knowledge-agent-no-live-access", 91.0),
        (candidate_dir, "prompt/knowledge-agent-no-live-access", 85.0),
    ]:
        scenario_dir = root / scenario_id
        scenario_dir.mkdir(parents=True, exist_ok=True)
        (scenario_dir / "report.json").write_text(
            (
                "{\n"
                '  "scenario_id": "prompt/knowledge-agent-no-live-access",\n'
                '  "git_sha": "deadbeef",\n'
                '  "execution_lane": "agent_only",\n'
                '  "overall_pass": true,\n'
                '  "agent_type": "knowledge_only",\n'
                '  "judge_scores": {\n'
                f'    "overall_score": {score},\n'
                '    "criteria_scores": {},\n'
                '    "strengths": [],\n'
                '    "weaknesses": [],\n'
                '    "factual_errors": [],\n'
                '    "missing_elements": [],\n'
                '    "detailed_feedback": "ok",\n'
                '    "passed": true\n'
                "  }\n"
                "}\n"
            ),
            encoding="utf-8",
        )

    result = runner.invoke(
        eval,
        [
            "compare",
            str(baseline_dir),
            str(candidate_dir),
            "--policy-file",
            str(policy_path),
        ],
    )

    assert result.exit_code == 1
    assert "judge score drop exceeded allowed variance" in result.output
