"""Authoritative directory layout helpers for mocked eval fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Final

EVAL_FIXTURE_ROOT = Path("evals")
SCENARIOS_ROOT = EVAL_FIXTURE_ROOT / "scenarios"
SHARED_FIXTURES_ROOT = SCENARIOS_ROOT / "_shared"
CORPORA_ROOT = EVAL_FIXTURE_ROOT / "corpora"
GOLDENS_ROOT = EVAL_FIXTURE_ROOT / "goldens"

SCENARIO_MANIFEST_FILENAME = "scenario.yaml"
CORPUS_MANIFEST_FILENAME = "manifest.yaml"
GOLDEN_METADATA_FILENAME = "metadata.yaml"
GOLDEN_RESPONSE_FILENAME = "expected.md"
GOLDEN_ASSERTIONS_FILENAME = "assertions.json"

SCENARIO_FIXTURES_DIRNAME = "fixtures"
TOOL_PAYLOADS_DIRNAME = "tools"
STARTUP_FIXTURES_DIRNAME = "startup"
CORPUS_DOCUMENTS_DIRNAME = "documents"
CORPUS_SKILLS_DIRNAME = "skills"
CORPUS_TICKETS_DIRNAME = "tickets"
SCENARIO_SHARED_RELATIVE_ROOT: Final[Path] = Path("..") / Path("..") / "_shared"
SCENARIO_CORPORA_RELATIVE_ROOT: Final[Path] = Path("..") / Path("..") / Path("..") / "corpora"


def _normalize_segment(value: str) -> str:
    segment = str(value or "").strip().replace("\\", "/").strip("/")
    if not segment or segment in {".", ".."}:
        raise ValueError("path segments must not be empty")
    parts = [part for part in segment.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise ValueError("path segments must not contain '.' or '..'")
    return "/".join(parts)


def scenario_dir(suite: str, scenario_id: str) -> Path:
    """Return the directory that owns one scenario manifest and local fixtures."""
    return SCENARIOS_ROOT / _normalize_segment(suite) / _normalize_segment(scenario_id)


def scenario_manifest_path(suite: str, scenario_id: str) -> Path:
    """Return the canonical path to a scenario YAML manifest."""
    return scenario_dir(suite, scenario_id) / SCENARIO_MANIFEST_FILENAME


def scenario_fixtures_dir(suite: str, scenario_id: str) -> Path:
    """Return the scenario-local fixture root."""
    return scenario_dir(suite, scenario_id) / SCENARIO_FIXTURES_DIRNAME


def scenario_tool_payloads_dir(suite: str, scenario_id: str) -> Path:
    """Return the scenario-local tool payload directory."""
    return scenario_fixtures_dir(suite, scenario_id) / TOOL_PAYLOADS_DIRNAME


def scenario_startup_fixtures_dir(suite: str, scenario_id: str) -> Path:
    """Return the scenario-local startup fixture directory."""
    return scenario_fixtures_dir(suite, scenario_id) / STARTUP_FIXTURES_DIRNAME


def shared_fixtures_dir(category: str | None = None) -> Path:
    """Return the shared fixture root or one shared subdirectory."""
    if category is None:
        return SHARED_FIXTURES_ROOT
    return SHARED_FIXTURES_ROOT / _normalize_segment(category)


def shared_fixture_reference(path_within_shared: str) -> Path:
    """Return the relative path a scenario YAML should use for a shared fixture."""
    return SCENARIO_SHARED_RELATIVE_ROOT / _normalize_segment(path_within_shared)


def corpus_version_dir(source_pack: str, version: str) -> Path:
    """Return the directory for one versioned fixture-backed corpus pack."""
    return CORPORA_ROOT / _normalize_segment(source_pack) / _normalize_segment(version)


def corpus_documents_dir(source_pack: str, version: str) -> Path:
    return corpus_version_dir(source_pack, version) / CORPUS_DOCUMENTS_DIRNAME


def corpus_skills_dir(source_pack: str, version: str) -> Path:
    return corpus_version_dir(source_pack, version) / CORPUS_SKILLS_DIRNAME


def corpus_tickets_dir(source_pack: str, version: str) -> Path:
    return corpus_version_dir(source_pack, version) / CORPUS_TICKETS_DIRNAME


def corpus_manifest_path(source_pack: str, version: str) -> Path:
    return corpus_version_dir(source_pack, version) / CORPUS_MANIFEST_FILENAME


def corpus_reference(source_pack: str, version: str, path_within_corpus: str | None = None) -> Path:
    """Return the relative path a scenario YAML should use for a corpus fixture."""
    reference = (
        SCENARIO_CORPORA_RELATIVE_ROOT
        / _normalize_segment(source_pack)
        / _normalize_segment(version)
    )
    if path_within_corpus is None:
        return reference
    return reference / _normalize_segment(path_within_corpus)


def infer_eval_fixture_root(manifest_path: str | Path) -> Path | None:
    """Infer the concrete ``evals/`` root from a canonical scenario manifest path."""
    path = Path(manifest_path).expanduser().resolve()
    if path.name != SCENARIO_MANIFEST_FILENAME:
        return None
    if len(path.parts) < 5:
        return None
    if path.parts[-5] != EVAL_FIXTURE_ROOT.name or path.parts[-4] != SCENARIOS_ROOT.name:
        return None
    if path.parts[-3] == SHARED_FIXTURES_ROOT.name:
        return None
    return path.parents[3]


def resolve_scenario_reference(
    manifest_path: str | Path,
    reference: str | Path,
    *,
    eval_fixture_root: str | Path | None = None,
) -> Path:
    """Resolve a scenario-owned reference and keep relative paths inside the eval fixture tree."""
    source_path = Path(manifest_path).expanduser().resolve()
    ref_path = Path(reference)
    if ref_path.is_absolute():
        return ref_path

    resolved = (source_path.parent / ref_path).resolve()
    inferred_root = (
        Path(eval_fixture_root).expanduser().resolve()
        if eval_fixture_root is not None
        else infer_eval_fixture_root(source_path)
    )
    if inferred_root is None:
        return resolved

    try:
        resolved.relative_to(inferred_root)
    except ValueError as exc:
        raise ValueError(
            "scenario fixture references must stay within the eval fixture root"
        ) from exc
    return resolved


def golden_dir(suite: str, scenario_id: str) -> Path:
    """Return the output-neutral golden directory for one scenario."""
    return GOLDENS_ROOT / _normalize_segment(suite) / _normalize_segment(scenario_id)


def golden_metadata_path(suite: str, scenario_id: str) -> Path:
    return golden_dir(suite, scenario_id) / GOLDEN_METADATA_FILENAME


def golden_expected_response_path(suite: str, scenario_id: str) -> Path:
    return golden_dir(suite, scenario_id) / GOLDEN_RESPONSE_FILENAME


def golden_assertions_path(suite: str, scenario_id: str) -> Path:
    return golden_dir(suite, scenario_id) / GOLDEN_ASSERTIONS_FILENAME


__all__ = [
    "CORPORA_ROOT",
    "CORPUS_DOCUMENTS_DIRNAME",
    "CORPUS_MANIFEST_FILENAME",
    "CORPUS_SKILLS_DIRNAME",
    "CORPUS_TICKETS_DIRNAME",
    "EVAL_FIXTURE_ROOT",
    "GOLDENS_ROOT",
    "GOLDEN_ASSERTIONS_FILENAME",
    "GOLDEN_METADATA_FILENAME",
    "GOLDEN_RESPONSE_FILENAME",
    "SCENARIOS_ROOT",
    "SCENARIO_FIXTURES_DIRNAME",
    "SCENARIO_MANIFEST_FILENAME",
    "SHARED_FIXTURES_ROOT",
    "STARTUP_FIXTURES_DIRNAME",
    "TOOL_PAYLOADS_DIRNAME",
    "corpus_documents_dir",
    "corpus_manifest_path",
    "corpus_reference",
    "corpus_skills_dir",
    "corpus_tickets_dir",
    "corpus_version_dir",
    "golden_assertions_path",
    "golden_dir",
    "golden_expected_response_path",
    "golden_metadata_path",
    "infer_eval_fixture_root",
    "resolve_scenario_reference",
    "scenario_dir",
    "scenario_fixtures_dir",
    "scenario_manifest_path",
    "scenario_startup_fixtures_dir",
    "scenario_tool_payloads_dir",
    "shared_fixture_reference",
    "shared_fixtures_dir",
]
