from pathlib import Path

import pytest

from redis_sre_agent.evaluation.fixture_layout import (
    CORPORA_ROOT,
    GOLDENS_ROOT,
    SCENARIOS_ROOT,
    SHARED_FIXTURES_ROOT,
    corpus_documents_dir,
    corpus_manifest_path,
    corpus_reference,
    corpus_skills_dir,
    corpus_tickets_dir,
    corpus_version_dir,
    golden_assertions_path,
    golden_dir,
    golden_expected_response_path,
    golden_metadata_path,
    infer_eval_fixture_root,
    resolve_scenario_reference,
    scenario_dir,
    scenario_fixtures_dir,
    scenario_manifest_path,
    scenario_startup_fixtures_dir,
    scenario_tool_payloads_dir,
    shared_fixture_reference,
)


def test_scenario_paths_use_bundle_manifest_and_fixture_roots():
    assert scenario_dir("redis", "enterprise-maintenance-mode") == (
        SCENARIOS_ROOT / "redis" / "enterprise-maintenance-mode"
    )
    assert scenario_manifest_path("redis", "enterprise-maintenance-mode") == (
        SCENARIOS_ROOT / "redis" / "enterprise-maintenance-mode" / "scenario.yaml"
    )
    assert scenario_fixtures_dir("redis", "enterprise-maintenance-mode") == (
        SCENARIOS_ROOT / "redis" / "enterprise-maintenance-mode" / "fixtures"
    )
    assert scenario_tool_payloads_dir("redis", "enterprise-maintenance-mode") == (
        SCENARIOS_ROOT / "redis" / "enterprise-maintenance-mode" / "fixtures" / "tools"
    )
    assert scenario_startup_fixtures_dir("redis", "enterprise-maintenance-mode") == (
        SCENARIOS_ROOT / "redis" / "enterprise-maintenance-mode" / "fixtures" / "startup"
    )


def test_shared_fixture_reference_stays_two_levels_up_from_any_scenario_manifest():
    assert SHARED_FIXTURES_ROOT == SCENARIOS_ROOT / "_shared"
    assert shared_fixture_reference("tools/metrics/maintenance.json") == Path(
        "../../_shared/tools/metrics/maintenance.json"
    )
    assert shared_fixture_reference("startup/policies/sev1.md") == Path(
        "../../_shared/startup/policies/sev1.md"
    )


def test_corpora_layout_is_versioned_by_source_pack():
    assert corpus_version_dir("redis-docs-curated", "2026-04-01") == (
        CORPORA_ROOT / "redis-docs-curated" / "2026-04-01"
    )
    assert corpus_manifest_path("redis-docs-curated", "2026-04-01") == (
        CORPORA_ROOT / "redis-docs-curated" / "2026-04-01" / "manifest.yaml"
    )
    assert corpus_documents_dir("redis-docs-curated", "2026-04-01") == (
        CORPORA_ROOT / "redis-docs-curated" / "2026-04-01" / "documents"
    )
    assert corpus_skills_dir("redis-docs-curated", "2026-04-01") == (
        CORPORA_ROOT / "redis-docs-curated" / "2026-04-01" / "skills"
    )
    assert corpus_tickets_dir("redis-docs-curated", "2026-04-01") == (
        CORPORA_ROOT / "redis-docs-curated" / "2026-04-01" / "tickets"
    )
    assert corpus_reference(
        "redis-docs-curated", "2026-04-01", "documents/re-node-maintenance.md"
    ) == (Path("../../../corpora/redis-docs-curated/2026-04-01/documents/re-node-maintenance.md"))


def test_goldens_live_outside_scenario_inputs():
    assert golden_dir("redis", "enterprise-maintenance-mode") == (
        GOLDENS_ROOT / "redis" / "enterprise-maintenance-mode"
    )
    assert golden_metadata_path("redis", "enterprise-maintenance-mode") == (
        GOLDENS_ROOT / "redis" / "enterprise-maintenance-mode" / "metadata.yaml"
    )
    assert golden_expected_response_path("redis", "enterprise-maintenance-mode") == (
        GOLDENS_ROOT / "redis" / "enterprise-maintenance-mode" / "expected.md"
    )
    assert golden_assertions_path("redis", "enterprise-maintenance-mode") == (
        GOLDENS_ROOT / "redis" / "enterprise-maintenance-mode" / "assertions.json"
    )


def test_infer_eval_fixture_root_from_canonical_manifest_path(tmp_path: Path):
    manifest_path = (
        tmp_path / "evals" / "scenarios" / "redis" / "enterprise-maintenance-mode" / "scenario.yaml"
    )
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("id: stub\nname: Stub\n", encoding="utf-8")

    assert infer_eval_fixture_root(manifest_path) == (tmp_path / "evals").resolve()


def test_resolve_scenario_reference_supports_local_shared_and_corpora_paths(tmp_path: Path):
    manifest_path = (
        tmp_path / "evals" / "scenarios" / "redis" / "enterprise-maintenance-mode" / "scenario.yaml"
    )
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("id: stub\nname: Stub\n", encoding="utf-8")

    assert (
        resolve_scenario_reference(manifest_path, "fixtures/tools/get_cluster_info.json")
        == (
            tmp_path
            / "evals"
            / "scenarios"
            / "redis"
            / "enterprise-maintenance-mode"
            / "fixtures"
            / "tools"
            / "get_cluster_info.json"
        ).resolve()
    )
    assert (
        resolve_scenario_reference(manifest_path, "../../_shared/startup/sev1.md")
        == (tmp_path / "evals" / "scenarios" / "_shared" / "startup" / "sev1.md").resolve()
    )
    assert (
        resolve_scenario_reference(
            manifest_path, "../../../corpora/redis-docs-curated/2026-04-01/documents/re-node.md"
        )
        == (
            tmp_path
            / "evals"
            / "corpora"
            / "redis-docs-curated"
            / "2026-04-01"
            / "documents"
            / "re-node.md"
        ).resolve()
    )


def test_resolve_scenario_reference_rejects_escape_from_eval_root(tmp_path: Path):
    manifest_path = (
        tmp_path / "evals" / "scenarios" / "redis" / "enterprise-maintenance-mode" / "scenario.yaml"
    )
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("id: stub\nname: Stub\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must stay within the eval fixture root"):
        resolve_scenario_reference(manifest_path, "../../../../outside.md")


def test_resolve_scenario_reference_falls_back_for_noncanonical_manifest_paths(tmp_path: Path):
    manifest_path = tmp_path / "scratch" / "scenario.yaml"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("id: stub\nname: Stub\n", encoding="utf-8")

    assert (
        resolve_scenario_reference(manifest_path, "fixtures/tools/result.json")
        == (tmp_path / "scratch" / "fixtures" / "tools" / "result.json").resolve()
    )


@pytest.mark.parametrize(
    "suite,scenario_id",
    [
        ("", "enterprise-maintenance-mode"),
        ("redis", ""),
        ("../redis", "enterprise-maintenance-mode"),
        ("redis", "../enterprise-maintenance-mode"),
    ],
)
def test_layout_rejects_path_traversal_and_empty_segments(suite: str, scenario_id: str):
    with pytest.raises(ValueError):
        scenario_manifest_path(suite, scenario_id)
