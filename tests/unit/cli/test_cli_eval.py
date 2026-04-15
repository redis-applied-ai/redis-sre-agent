from __future__ import annotations

from click.testing import CliRunner

from redis_sre_agent.cli.eval import eval
from redis_sre_agent.cli.main import main


def test_eval_cli_help_lists_live_suite_command():
    runner = CliRunner()

    result = runner.invoke(eval, ["--help"])

    assert result.exit_code == 0
    assert "compare" in result.output
    assert "live-suite" in result.output
    assert "list" in result.output


def test_eval_command_is_registered_in_main_cli():
    runner = CliRunner()

    result = runner.invoke(main, ["eval", "--help"])

    assert result.exit_code == 0
    assert "live-suite" in result.output


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
