from pathlib import Path

import pytest

from redis_sre_agent.evaluation.runner import run_eval_scenario


@pytest.mark.asyncio
async def test_run_eval_scenario_loads_yaml_and_delegates_to_runtime(tmp_path: Path):
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        """
id: redis/enterprise-maintenance-mode
name: Enterprise maintenance mode
provenance:
  source_kind: redis_docs
  source_pack: redis-docs-curated
  source_pack_version: 2026-04-01
  golden:
    expectation_basis: human_from_docs
    review_status: approved
execution:
  lane: full_turn
  query: Investigate failovers on the prod enterprise cluster.
""".strip(),
        encoding="utf-8",
    )

    class StubRuntime:
        def __init__(self) -> None:
            self.seen = None

        async def run(self, scenario, *, user_id=None, extra_context=None):
            self.seen = {
                "scenario": scenario,
                "user_id": user_id,
                "extra_context": extra_context,
            }
            return {"scenario_id": scenario.id, "user_id": user_id}

    runtime = StubRuntime()

    result = await run_eval_scenario(
        scenario_path,
        runtime=runtime,
        user_id="user-1",
        extra_context={"seed": "abc"},
    )

    assert runtime.seen["scenario"].id == "redis/enterprise-maintenance-mode"
    assert runtime.seen["user_id"] == "user-1"
    assert runtime.seen["extra_context"] == {"seed": "abc"}
    assert result == {"scenario_id": "redis/enterprise-maintenance-mode", "user_id": "user-1"}
