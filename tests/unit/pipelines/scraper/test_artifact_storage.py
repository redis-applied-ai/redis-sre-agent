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
    storage.save_batch_manifest()
    storage.save_document(second)
    manifest_path = storage.save_batch_manifest()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["batch_date"] == "2026-05-12"
    assert manifest["total_documents"] == 2
    assert manifest["categories"] == {"shared": 1, "oss": 1}
    assert manifest["document_types"] == {"knowledge": 1, "documentation": 1}
    assert sorted(manifest["sources"]) == sorted(
        ["source_documents/shared/source.md", "https://redis.io/kb/example"]
    )


def test_save_batch_manifest_ignores_ingestion_manifest(tmp_path):
    storage = ArtifactStorage(tmp_path)
    storage.set_batch_date("2026-05-12")

    document = ScrapedDocument(
        title="Source Doc",
        content="from source_documents",
        source_url="source_documents/shared/source.md",
        category=DocumentCategory.SHARED,
        doc_type=DocumentType.KNOWLEDGE,
    )

    storage.save_document(document)
    batch_path = tmp_path / "2026-05-12"
    (batch_path / "ingestion_manifest.json").write_text(
        json.dumps(
            {
                "batch_date": "2026-05-12",
                "documents_processed": 99,
                "success": True,
            }
        ),
        encoding="utf-8",
    )

    manifest_path = storage.save_batch_manifest()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["total_documents"] == 1
    assert manifest["categories"] == {"shared": 1}
    assert manifest["document_types"] == {"knowledge": 1}


def test_save_batch_manifest_creates_batch_directory_when_empty(tmp_path):
    storage = ArtifactStorage(tmp_path)
    storage.set_batch_date("2026-05-12")

    manifest_path = storage.save_batch_manifest()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest_path.exists()
    assert manifest_path.parent == tmp_path / "2026-05-12"
    assert manifest["total_documents"] == 0
    assert manifest["categories"] == {}
    assert manifest["document_types"] == {}
    assert manifest["sources"] == []
