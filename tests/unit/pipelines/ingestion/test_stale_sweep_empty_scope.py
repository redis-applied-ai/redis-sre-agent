"""Safety: an empty/blank source_document_scope must NEVER authorize deletion.

Regression guard for the empty-scope landmine: once documents are tracked
(via source_document_path), a "" scope previously matched everything in
`_path_in_scope`, so a *partial* ingest would hard-delete every tracked doc it
did not re-emit. The sweep must treat "no declared scope" as "delete nothing".
"""

from unittest.mock import AsyncMock

from redis_sre_agent.pipelines.ingestion.processor import IngestionPipeline
from redis_sre_agent.pipelines.scraper.base import ArtifactStorage


class TestPathInScope:
    def test_empty_string_scope_does_not_match_everything(self):
        # The landmine: {""} must NOT authorize deleting an arbitrary path.
        assert IngestionPipeline._path_in_scope("redis.io/docs/x", {""}) is False

    def test_no_scope_prefixes_matches_nothing(self):
        assert IngestionPipeline._path_in_scope("anything", set()) is False

    def test_only_blank_scopes_match_nothing(self):
        assert IngestionPipeline._path_in_scope("anything", {"", "   "}) is False

    def test_real_prefix_matches(self):
        assert IngestionPipeline._path_in_scope("shared/x.md", {"shared/"}) is True

    def test_real_prefix_non_match(self):
        assert IngestionPipeline._path_in_scope("other/x.md", {"shared/"}) is False

    def test_empty_alongside_real_prefix_ignores_empty(self):
        # "" must be ignored, not widen the match to everything.
        assert IngestionPipeline._path_in_scope("shared/x.md", {"", "shared/"}) is True
        assert IngestionPipeline._path_in_scope("other/x.md", {"", "shared/"}) is False


class TestStaleSweepEmptyScopeDeletesNothing:
    async def test_partial_ingest_with_empty_scope_deletes_nothing(self, tmp_path):
        """The exact landmine scenario: tracked docs, empty scope, partial run."""
        pipe = IngestionPipeline(ArtifactStorage(tmp_path / "artifacts"))

        tracked_by_path = {
            "redis.io/docs/page-a": [
                {"deduplicator_key": "knowledge", "document_hash": "aaaa", "title": "A"}
            ],
            "redis.io/docs/page-b": [
                {"deduplicator_key": "knowledge", "document_hash": "bbbb", "title": "B"}
            ],
        }
        deleted = []
        dedup = AsyncMock()

        async def _rec(doc_hash, path, **kw):
            deleted.append(path)

        dedup.delete_tracked_source_document.side_effect = _rec
        deduplicators = {"knowledge": dedup}

        # Partial run saw only page-a; scope is the real-world empty value.
        result = await pipe._delete_stale_source_documents(
            deduplicators,
            tracked_by_path,
            {"redis.io/docs/page-a"},
            {""},
        )

        assert deleted == []  # nothing deleted despite page-b being "unseen"
        assert result == []

    async def test_real_scope_still_deletes_unseen_in_that_scope(self, tmp_path):
        """The fix must not disable legitimate, bounded deletion."""
        pipe = IngestionPipeline(ArtifactStorage(tmp_path / "artifacts"))
        tracked_by_path = {
            "shared/keep.md": [
                {"deduplicator_key": "knowledge", "document_hash": "k", "title": "Keep"}
            ],
            "shared/gone.md": [
                {"deduplicator_key": "knowledge", "document_hash": "g", "title": "Gone"}
            ],
        }
        deleted = []
        dedup = AsyncMock()

        async def _rec(doc_hash, path, **kw):
            deleted.append(path)

        dedup.delete_tracked_source_document.side_effect = _rec

        result = await pipe._delete_stale_source_documents(
            {"knowledge": dedup},
            tracked_by_path,
            {"shared/keep.md"},  # gone.md not seen this run
            {"shared/"},  # real, bounded scope
        )
        assert deleted == ["shared/gone.md"]
        assert [d["path"] for d in result] == ["shared/gone.md"]
