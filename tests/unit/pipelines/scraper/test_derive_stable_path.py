"""Tests for derive_stable_path and the ScrapedDocument source_document_path default.

derive_stable_path is the frozen, content-independent logical identity used to
route scraped documents through the tracked dedup branch (replace-on-change).
Changing its contract re-keys the entire corpus, so these tests pin the contract.
"""

import pytest

from redis_sre_agent.pipelines.scraper.base import (
    DocumentCategory,
    DocumentType,
    ScrapedDocument,
    derive_stable_path,
)


class TestDeriveStablePath:
    @pytest.mark.parametrize(
        "source_url,expected",
        [
            # scheme stripped, host lowercased, query+fragment dropped, trailing slash stripped
            ("HTTPS://Redis.IO/docs/foo/index.html?x=1#y", "redis.io/docs/foo/index.html"),
            ("https://redis.io/docs/foo/", "redis.io/docs/foo"),
            ("https://redis.io/docs/foo", "redis.io/docs/foo"),
            ("http://redis.io/docs/foo", "redis.io/docs/foo"),
            ("https://Redis.io/", "redis.io"),
            ("https://redis.io", "redis.io"),
            # query/fragment only
            ("https://redis.io/a?b=c", "redis.io/a"),
            ("https://redis.io/a#frag", "redis.io/a"),
            # non-http(s) and empty -> "" (route to untracked branch; never machine-specific)
            ("file:///Users/someone/repo/source_documents/shared/foo.md", ""),
            ("mailto:someone@example.com", ""),
            ("ftp://redis.io/x", ""),
            ("", ""),
            ("operate/rs/foo.md", ""),  # relative / unparseable -> no scheme
        ],
    )
    def test_contract_table(self, source_url, expected):
        assert derive_stable_path(source_url) == expected

    def test_deterministic(self):
        url = "https://redis.io/docs/Foo/Bar"
        assert derive_stable_path(url) == derive_stable_path(url)

    def test_cosmetic_variations_collapse_together(self):
        """Same logical page via case / trailing slash / query must map to one identity."""
        canonical = derive_stable_path("https://redis.io/docs/foo")
        assert derive_stable_path("https://REDIS.io/docs/foo/") == canonical
        assert derive_stable_path("https://redis.io/docs/foo?utm=1") == canonical
        assert derive_stable_path("https://redis.io/docs/foo#section") == canonical

    def test_does_not_fold_index_html(self):
        """index.html is intentionally NOT folded (folding can manufacture collisions)."""
        assert derive_stable_path("https://redis.io/docs/foo/index.html") != derive_stable_path(
            "https://redis.io/docs/foo/"
        )

    def test_path_is_content_independent(self):
        """The identity depends only on the URL, never on title/content."""
        a = ScrapedDocument(
            title="One",
            content="alpha",
            source_url="https://redis.io/docs/page",
            category=DocumentCategory.OSS,
            doc_type=DocumentType.DOCUMENTATION,
        )
        b = ScrapedDocument(
            title="Two — totally different",
            content="omega omega omega",
            source_url="https://redis.io/docs/page",
            category=DocumentCategory.OSS,
            doc_type=DocumentType.DOCUMENTATION,
        )
        assert (
            a.metadata["source_document_path"]
            == b.metadata["source_document_path"]
            == "redis.io/docs/page"
        )
        assert a.content_hash != b.content_hash  # content changed, identity did not


class TestScrapedDocumentDefault:
    def _doc(self, source_url, metadata=None):
        return ScrapedDocument(
            title="t",
            content="c",
            source_url=source_url,
            category=DocumentCategory.OSS,
            doc_type=DocumentType.DOCUMENTATION,
            metadata=metadata,
        )

    def test_default_populated_for_http(self):
        doc = self._doc("https://redis.io/docs/x")
        assert doc.metadata["source_document_path"] == "redis.io/docs/x"

    def test_default_empty_for_file_scheme(self):
        """A file:// URL must NOT become a machine-specific identity (A2).

        The default adds no key when derivation is empty, so downstream
        (which reads ``.get(...) or ""``) routes the doc to the untracked
        branch — identical to pre-change behavior.
        """
        doc = self._doc("file:///Users/me/checkout/source_documents/shared/x.md")
        assert doc.metadata.get("source_document_path", "") == ""

    def test_explicit_path_not_overwritten(self):
        doc = self._doc(
            "https://redis.io/docs/x",
            metadata={"source_document_path": "redis-cloud-api/GET /foo"},
        )
        assert doc.metadata["source_document_path"] == "redis-cloud-api/GET /foo"

    def test_explicit_empty_string_not_overwritten_when_url_nonhttp(self):
        doc = self._doc("file://x", metadata={"source_document_path": ""})
        assert doc.metadata["source_document_path"] == ""

    def test_from_dict_synthesizes_for_legacy_http_artifact(self):
        """Reingesting a legacy artifact (no source_document_path) auto-migrates http docs."""
        legacy = {
            "title": "t",
            "content": "c",
            "source_url": "https://redis.io/docs/legacy",
            "category": "oss",
            "doc_type": "documentation",
            "severity": "medium",
            "metadata": {},  # legacy artifact had no source_document_path
        }
        doc = ScrapedDocument.from_dict(legacy)
        assert doc.metadata["source_document_path"] == "redis.io/docs/legacy"

    def test_to_dict_from_dict_roundtrip_preserves_path(self):
        doc = self._doc("https://redis.io/docs/x")
        restored = ScrapedDocument.from_dict(doc.to_dict())
        assert restored.metadata["source_document_path"] == "redis.io/docs/x"
