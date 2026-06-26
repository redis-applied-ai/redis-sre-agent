"""Pre-indexing collision detection for source_document_path (A3)."""

import json
from pathlib import Path

from redis_sre_agent.pipelines.ingestion._processor_impl import (
    detect_source_path_collisions,
)


def _write_doc(path: Path, source_url: str, source_document_path=None) -> Path:
    metadata = {}
    if source_document_path is not None:
        metadata["source_document_path"] = source_document_path
    path.write_text(
        json.dumps(
            {
                "title": path.stem,
                "content": "c",
                "source_url": source_url,
                "category": "enterprise",
                "doc_type": "reference",
                "severity": "medium",
                "metadata": metadata,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_explicit_path_collision_is_detected_and_deduped(tmp_path):
    a = _write_doc(
        tmp_path / "a.json", "https://x/a#one", source_document_path="redis-cloud-api/GET /foo"
    )
    b = _write_doc(
        tmp_path / "b.json", "https://x/b#two", source_document_path="redis-cloud-api/GET /foo"
    )
    c = _write_doc(
        tmp_path / "c.json", "https://x/c", source_document_path="redis-cloud-api/GET /bar"
    )

    files_to_process, collisions = detect_source_path_collisions([a, b, c])

    # The colliding pair is reduced to a single indexed file; the unique one stays.
    assert a in files_to_process and c in files_to_process
    assert b not in files_to_process
    assert "redis-cloud-api/GET /foo" in collisions
    assert set(collisions["redis-cloud-api/GET /foo"]) == {a, b}
    assert "redis-cloud-api/GET /bar" not in collisions


def test_derived_path_collision_is_detected(tmp_path):
    """Two URLs that normalize to the same path collide even without explicit metadata."""
    a = _write_doc(tmp_path / "a.json", "https://redis.io/docs/foo")
    b = _write_doc(tmp_path / "b.json", "https://redis.io/docs/foo/?utm=1")

    files_to_process, collisions = detect_source_path_collisions([a, b])

    assert len(files_to_process) == 1
    assert "redis.io/docs/foo" in collisions


def test_untracked_docs_never_collide(tmp_path):
    """Empty effective paths (file:// / non-http) route to the untracked branch."""
    a = _write_doc(tmp_path / "a.json", "file:///Users/x/a.md")
    b = _write_doc(tmp_path / "b.json", "file:///Users/y/b.md")

    files_to_process, collisions = detect_source_path_collisions([a, b])

    assert set(files_to_process) == {a, b}
    assert collisions == {}


def test_whitespace_only_difference_is_a_collision(tmp_path):
    """Paths differing only by surrounding whitespace collide (tracking strips them)."""
    a = _write_doc(
        tmp_path / "a.json", "https://x/a", source_document_path="redis-cloud-api/GET /foo"
    )
    b = _write_doc(
        tmp_path / "b.json", "https://x/b", source_document_path="  redis-cloud-api/GET /foo  "
    )

    files_to_process, collisions = detect_source_path_collisions([a, b])

    assert len(files_to_process) == 1
    assert "redis-cloud-api/GET /foo" in collisions


def test_no_collision_passes_all_through(tmp_path):
    a = _write_doc(tmp_path / "a.json", "https://redis.io/docs/a")
    b = _write_doc(tmp_path / "b.json", "https://redis.io/docs/b")

    files_to_process, collisions = detect_source_path_collisions([a, b])

    assert set(files_to_process) == {a, b}
    assert collisions == {}
