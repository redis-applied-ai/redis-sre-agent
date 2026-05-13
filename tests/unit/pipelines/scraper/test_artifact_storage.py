import json

from redis_sre_agent.pipelines.scraper.base import (
    ArtifactStorage,
    DocumentCategory,
    DocumentType,
    ScrapedDocument,
)


def test_save_batch_manifest_reflects_all_saved_documents(tmp_path):
    storage = ArtifactStorage(tmp_path)
    storage.set_batch_date("2026-05-12")

    first = ScrapedDocument(
        title="Source Doc",
        content="from source_documents",
        source_url="source_documents/shared/source.md",
        category=DocumentCategory.SHARED,
        doc_type=DocumentType.KNOWLEDGE,
    )
    second = ScrapedDocument(
        title="KB Doc",
        content="from scraper",
        source_url="https://redis.io/kb/example",
        category=DocumentCategory.OSS,
        doc_type=DocumentType.DOCUMENTATION,
    )

    storage.save_document(first)
    storage.save_batch_manifest([first])
    storage.save_document(second)
    manifest_path = storage.save_batch_manifest([second])

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["batch_date"] == "2026-05-12"
    assert manifest["total_documents"] == 2
    assert manifest["categories"] == {"shared": 1, "oss": 1}
    assert manifest["document_types"] == {"knowledge": 1, "documentation": 1}
    assert sorted(manifest["sources"]) == sorted(
        ["source_documents/shared/source.md", "https://redis.io/kb/example"]
    )
