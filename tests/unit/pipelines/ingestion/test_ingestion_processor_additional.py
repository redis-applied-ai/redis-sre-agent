"""Additional focused tests for ingestion processor helpers."""

import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from redis_sre_agent.pipelines.ingestion.processor import (
    DocumentProcessor,
    IngestionPipeline,
    get_knowledge_index,
    get_skills_index,
    get_support_tickets_index,
    get_vectorizer,
)
from redis_sre_agent.pipelines.ingestion.processor_indexing_helpers import (
    delete_cross_index_tracked_entries,
    get_source_tracking_fields,
    index_processed_document,
    select_deduplicator,
)
from redis_sre_agent.pipelines.ingestion.processor_source_helpers import (
    create_scraped_document_from_markdown,
    determine_document_category,
    find_markdown_files,
    find_source_documents_root,
    normalize_doc_type,
    normalize_metadata_key,
    normalize_priority,
    parse_markdown_metadata,
    resolve_source_document_identity,
)
from redis_sre_agent.pipelines.scraper.base import (
    ArtifactStorage,
    DocumentCategory,
    DocumentType,
    ScrapedDocument,
    SeverityLevel,
)


@pytest.fixture
def storage(tmp_path):
    return ArtifactStorage(tmp_path)


@pytest.fixture
def pipeline(storage):
    return IngestionPipeline(storage)


def _make_document(**overrides):
    base = ScrapedDocument(
        title="Doc",
        content="body",
        source_url="https://example.com",
        category=DocumentCategory.SHARED,
        doc_type=DocumentType.KNOWLEDGE,
        severity=SeverityLevel.MEDIUM,
        metadata={},
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def _write_formal_skill_package(root: Path, name: str = "redis-maintenance-triage") -> Path:
    package_dir = root / name
    (package_dir / "references").mkdir(parents=True)
    (package_dir / "scripts").mkdir()
    (package_dir / "assets").mkdir()
    (package_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                f"name: {name}",
                "description: Investigate maintenance mode before failover.",
                "summary: Check maintenance state before disruptive actions.",
                "---",
                "",
                "Entrypoint body",
            ]
        ),
        encoding="utf-8",
    )
    (package_dir / "references" / "maintenance-checklist.md").write_text(
        "---\ntitle: Maintenance Checklist\n---\n\nChecklist body\n",
        encoding="utf-8",
    )
    (package_dir / "scripts" / "collect_context.sh").write_text(
        "#!/usr/bin/env bash\necho collect\n",
        encoding="utf-8",
    )
    (package_dir / "assets" / "example-query.txt").write_text(
        "maintenance mode cluster owner\n",
        encoding="utf-8",
    )
    return package_dir


@pytest.mark.asyncio
async def test_wrapper_functions_delegate_to_core_redis():
    with (
        patch("redis_sre_agent.core.redis.get_knowledge_index", new=AsyncMock(return_value="k")),
        patch("redis_sre_agent.core.redis.get_skills_index", new=AsyncMock(return_value="s")),
        patch(
            "redis_sre_agent.core.redis.get_support_tickets_index",
            new=AsyncMock(return_value="t"),
        ),
        patch("redis_sre_agent.core.redis.get_vectorizer", return_value="v"),
    ):
        assert await get_knowledge_index() == "k"
        assert await get_skills_index() == "s"
        assert await get_support_tickets_index() == "t"
        assert get_vectorizer() == "v"


def test_document_processor_knowledge_settings_and_helpers():
    knowledge_settings = SimpleNamespace(
        chunk_size=321,
        chunk_overlap=22,
        max_documents_per_batch=7,
        splitting_strategy="semantic",
        enable_metadata_extraction=False,
        enable_semantic_chunking=True,
        similarity_threshold=0.9,
        embedding_model="text-embedding-3-large",
    )
    processor = DocumentProcessor(knowledge_settings=knowledge_settings)
    assert processor.config["chunk_size"] == 321
    assert processor.config["max_chunks_per_doc"] == 7

    assert DocumentProcessor._parse_bool(True) is True
    assert DocumentProcessor._parse_bool(None, default=True) is True
    assert DocumentProcessor._parse_bool("yes") is True
    assert DocumentProcessor._parse_bool("off", default=True) is False
    assert DocumentProcessor._parse_bool("maybe", default=True) is True

    assert processor._strip_yaml_front_matter("plain text") == ("plain text", False)
    assert processor._strip_yaml_front_matter("---\ninvalid") == ("---\ninvalid", False)
    assert processor._strip_yaml_front_matter("---\nkey: value\n---\nbody") == ("body", True)

    assert normalize_doc_type("") == (DocumentType.KNOWLEDGE, "knowledge")
    assert normalize_doc_type("unknown type") == (
        DocumentType.KNOWLEDGE,
        "knowledge",
    )
    assert normalize_priority("critical") == "critical"
    assert normalize_priority("unexpected") == "normal"

    class BrokenText:
        def startswith(self, prefix):
            return True

        def find(self, needle, start):
            raise RuntimeError("boom")

    broken = BrokenText()
    assert processor._strip_yaml_front_matter(broken) == (broken, False)


def test_chunk_document_special_cases_and_empty_body():
    processor = DocumentProcessor({"chunk_size": 40, "chunk_overlap": 0, "min_chunk_size": 1})

    empty_doc = _make_document(title="Empty", content="---\nfoo: bar\n---\n")
    assert processor.chunk_document(empty_doc) == []

    cli_doc = _make_document(
        title="rladmin reference",
        content="rladmin create db",
        source_url="https://example.com/docs",
    )
    assert len(processor.chunk_document(cli_doc)) == 1

    api_doc = _make_document(
        content="curl example",
        source_url="https://example.com/references/rest-api/",
    )
    assert len(processor.chunk_document(api_doc)) == 1

    regular_doc = _make_document(
        content="abcdefghij abcdefghij abcdefghij",
        metadata={"priority": "HIGH", "pinned": "yes"},
    )
    chunks = processor.chunk_document(regular_doc)
    assert len(chunks) == 1
    assert chunks[0]["priority"] == "high"
    assert chunks[0]["pinned"] == "true"

    split_doc = _make_document(content="alpha beta gamma delta epsilon zeta eta theta iota")
    split_chunks = processor.chunk_document(split_doc)
    assert len(split_chunks) == 1


@pytest.mark.asyncio
async def test_build_deduplicators_and_tracking_helpers(pipeline):
    with (
        patch(
            "redis_sre_agent.pipelines.ingestion._processor_impl.get_knowledge_index",
            new=AsyncMock(return_value="knowledge-index"),
        ),
        patch(
            "redis_sre_agent.pipelines.ingestion._processor_impl.get_skills_index",
            new=AsyncMock(return_value="skills-index"),
        ),
        patch(
            "redis_sre_agent.pipelines.ingestion._processor_impl.get_support_tickets_index",
            new=AsyncMock(return_value="tickets-index"),
        ),
    ):
        deduplicators = await pipeline._build_deduplicators()

    assert deduplicators["knowledge"].index == "knowledge-index"
    assert deduplicators["skill"].key_prefix == "sre_skills"
    assert deduplicators["support_ticket"].key_prefix == "sre_support_tickets"

    deduplicators = {
        "knowledge": AsyncMock(),
        "skill": AsyncMock(),
    }
    deduplicators["knowledge"].list_tracked_source_documents.return_value = {
        "shared/doc.md": {"document_hash": "k-hash"}
    }
    deduplicators["skill"].list_tracked_source_documents.return_value = {
        "shared/doc.md": {"document_hash": "s-hash"},
        "enterprise/doc.md": {"document_hash": "e-hash"},
    }

    tracked = await pipeline._list_tracked_source_documents(deduplicators)
    assert tracked["shared/doc.md"] == [
        {"deduplicator_key": "knowledge", "document_hash": "k-hash"},
        {"deduplicator_key": "skill", "document_hash": "s-hash"},
    ]
    assert IngestionPipeline._path_in_scope("shared/doc.md", set()) is False
    assert IngestionPipeline._path_in_scope("shared/doc.md", {""}) is True
    assert IngestionPipeline._path_in_scope("shared/doc.md", {"enterprise/"}) is False
    assert IngestionPipeline._path_in_scope("shared/doc.md", {"shared/"}) is True

    summary = pipeline._empty_source_change_summary()
    pipeline._record_source_change(summary, path="shared/doc.md", action="add", doc_type="skill")
    pipeline._record_source_change(summary, path="shared/doc.md", action="updated", title="Doc")
    pipeline._record_source_change(summary, path="shared/doc.md", action="deleted")
    pipeline._record_source_change(summary, path="shared/doc.md", action="unchanged")
    pipeline._record_source_change(summary, path="shared/doc.md", action="unknown")
    assert summary["added"] == 1
    assert summary["updated"] == 1
    assert summary["deleted"] == 1
    assert summary["unchanged"] == 1
    assert len(summary["files"]) == 4


@pytest.mark.asyncio
async def test_processor_wrapper_helpers_delegate_to_extracted_functions(pipeline):
    document = _make_document(metadata={"source_document_path": "shared/doc.md"})
    deduplicators = {"knowledge": MagicMock()}
    deduplicators["knowledge"].delete_tracked_source_document = AsyncMock(return_value=True)

    assert get_source_tracking_fields(document) == ("shared/doc.md", "")
    assert select_deduplicator(document, deduplicators) == (
        "knowledge",
        deduplicators["knowledge"],
    )
    assert (
        await delete_cross_index_tracked_entries(
            deduplicators={"knowledge": deduplicators["knowledge"]},
            tracked_entries=[{"deduplicator_key": "knowledge", "document_hash": "hash-1"}],
            doc_type_key="knowledge",
            source_document_path="shared/doc.md",
        )
        is True
    )
    deduplicators["knowledge"].delete_tracked_source_document.assert_not_awaited()

    assert normalize_metadata_key("Custom-Key") == "custom_key"


@pytest.mark.asyncio
async def test_delete_stale_source_documents_respects_scope_and_current_paths(pipeline):
    knowledge = AsyncMock()
    deletions = await pipeline._delete_stale_source_documents(
        {"knowledge": knowledge},
        {
            "shared/current.md": [{"deduplicator_key": "knowledge", "document_hash": "current"}],
            "shared/deleted.md": [
                {
                    "deduplicator_key": "knowledge",
                    "document_hash": "deleted",
                    "title": "Deleted",
                    "category": "shared",
                    "severity": "high",
                    "doc_type": "knowledge",
                }
            ],
            "enterprise/out-of-scope.md": [
                {"deduplicator_key": "knowledge", "document_hash": "ignored"}
            ],
        },
        {"shared/current.md"},
        {"shared/"},
    )
    knowledge.delete_tracked_source_document.assert_awaited_once_with(
        "deleted", "shared/deleted.md"
    )
    assert deletions == [
        {
            "path": "shared/deleted.md",
            "action": "delete",
            "title": "Deleted",
            "category": "shared",
            "severity": "high",
            "doc_type": "knowledge",
        }
    ]


@pytest.mark.asyncio
async def test_index_processed_document_skips_cross_index_delete_for_non_source_docs():
    document = _make_document(metadata={})
    deduplicator = MagicMock()
    deduplicator.replace_document_chunks = AsyncMock(return_value=2)

    with patch(
        "redis_sre_agent.pipelines.ingestion.processor_indexing_helpers."
        "delete_cross_index_tracked_entries",
        new=AsyncMock(return_value=True),
    ) as delete_cross_index:
        result = await index_processed_document(
            document=document,
            chunks=[{"id": "chunk-1"}],
            vectorizer=MagicMock(),
            deduplicators={"knowledge": deduplicator},
            tracked_source_documents={"shared/doc.md": [{"document_hash": "old"}]},
        )

    delete_cross_index.assert_not_awaited()
    deduplicator.replace_document_chunks.assert_awaited_once()
    assert result["source_document_change"] is None


@pytest.mark.asyncio
async def test_process_category_latest_only_and_error_paths(pipeline, tmp_path):
    category_path = tmp_path / "enterprise"
    category_path.mkdir()
    docs = {
        "versioned.json": {
            "title": "Old",
            "content": "body",
            "source_url": "https://redis.io/docs/7.4/file",
            "category": "enterprise",
            "doc_type": "knowledge",
            "severity": "medium",
            "metadata": {},
        },
        "non_latest.json": {
            "title": "Old Enterprise",
            "content": "body",
            "source_url": "https://redis.io/operate/rs/reference",
            "category": "enterprise",
            "doc_type": "knowledge",
            "severity": "medium",
            "metadata": {},
        },
        "keep.json": {
            "title": "Keep",
            "content": "body",
            "source_url": "https://redis.io/operate/rs/latest/reference",
            "category": "enterprise",
            "doc_type": "knowledge",
            "severity": "medium",
            "metadata": {},
        },
        "broken.json": "{not valid json",
    }
    for name, content in docs.items():
        path = category_path / name
        if isinstance(content, dict):
            path.write_text(json.dumps(content), encoding="utf-8")
        else:
            path.write_text(content, encoding="utf-8")

    deduplicator = AsyncMock()
    deduplicator.replace_document_chunks.return_value = 1
    latest_only_pipeline = IngestionPipeline(pipeline.storage, {"latest_only": True})

    result = await latest_only_pipeline._process_category(
        category_path,
        "enterprise",
        MagicMock(),
        {"knowledge": deduplicator},
    )

    deduplicator.replace_document_chunks.assert_awaited_once()
    assert result["documents_processed"] == 1
    assert len(result["errors"]) == 1
    assert "broken.json" in result["errors"][0]


@pytest.mark.asyncio
async def test_process_category_ignores_empty_scope_for_non_source_docs(pipeline, tmp_path):
    category_path = tmp_path / "shared"
    category_path.mkdir()
    doc_path = category_path / "doc.json"
    doc_path.write_text(
        json.dumps(
            {
                "title": "Regular Doc",
                "content": "body",
                "source_url": "https://redis.io/docs",
                "category": "shared",
                "doc_type": "knowledge",
                "severity": "medium",
                "metadata": {},
            }
        ),
        encoding="utf-8",
    )

    with (
        patch.object(pipeline.processor, "chunk_document", return_value=[{"id": "chunk-1"}]),
        patch(
            "redis_sre_agent.pipelines.ingestion._processor_impl.index_processed_document",
            new=AsyncMock(
                return_value={
                    "chunks_created": 1,
                    "chunks_indexed": 1,
                    "source_document_change": None,
                    "source_document_path": "",
                    "source_document_scope": "",
                }
            ),
        ),
    ):
        result = await pipeline._process_category(
            category_path,
            "shared",
            MagicMock(),
            {"knowledge": AsyncMock()},
        )

    assert result["documents_processed"] == 1
    assert result["source_document_paths"] == []
    assert result["source_document_scopes"] == []


@pytest.mark.asyncio
async def test_process_category_keeps_failed_source_documents_in_scope(pipeline, tmp_path):
    category_path = tmp_path / "shared"
    category_path.mkdir()
    doc_path = category_path / "doc.json"
    doc_path.write_text(
        json.dumps(
            {
                "title": "Tracked Doc",
                "content": "body",
                "source_url": "https://redis.io/docs",
                "category": "shared",
                "doc_type": "knowledge",
                "severity": "medium",
                "metadata": {
                    "source_document_path": "shared/doc.md",
                    "source_document_scope": "shared/",
                },
            }
        ),
        encoding="utf-8",
    )

    with patch.object(pipeline.processor, "chunk_document", side_effect=RuntimeError("bad doc")):
        result = await pipeline._process_category(
            category_path,
            "shared",
            MagicMock(),
            {"knowledge": AsyncMock()},
        )

    assert result["documents_processed"] == 0
    assert result["source_document_paths"] == ["shared/doc.md"]
    assert result["source_document_scopes"] == ["shared/"]
    assert result["errors"] == ["Failed to process doc.json: bad doc"]


def test_source_document_identity_and_category_resolution(pipeline, tmp_path):
    source_root = tmp_path / "source_documents"
    nested_dir = source_root / "enterprise" / "guides"
    nested_dir.mkdir(parents=True)
    md_file = nested_dir / "doc.md"
    md_file.write_text("# Doc", encoding="utf-8")

    assert find_source_documents_root(nested_dir) == source_root
    assert resolve_source_document_identity(md_file, nested_dir) == (
        "enterprise/guides/doc.md",
        "enterprise/guides/",
    )

    outside_root = tmp_path / "other"
    outside_root.mkdir()
    outside_file = outside_root / "outside.md"
    outside_file.write_text("# Outside", encoding="utf-8")
    assert resolve_source_document_identity(outside_file, outside_root) == (
        "outside.md",
        "",
    )

    with patch(
        "redis_sre_agent.pipelines.ingestion.processor_source_helpers.find_source_documents_root",
        return_value=tmp_path / "unrelated",
    ):
        assert resolve_source_document_identity(md_file, nested_dir) == (
            "doc.md",
            "",
        )

    assert determine_document_category(md_file, {"category": "cloud"}) == DocumentCategory.SHARED
    assert determine_document_category(Path("/tmp/oss/doc.md"), {}) == DocumentCategory.OSS
    assert determine_document_category(Path("/tmp/misc/doc.md"), {}) == DocumentCategory.SHARED


def test_find_markdown_files_returns_sorted_non_readme_paths(tmp_path):
    source_dir = tmp_path / "source_documents"
    source_dir.mkdir()
    (source_dir / "z-last.md").write_text("# Z", encoding="utf-8")
    nested_dir = source_dir / "nested"
    nested_dir.mkdir()
    (nested_dir / "a-first.md").write_text("# A", encoding="utf-8")
    (source_dir / "README.md").write_text("# Ignore", encoding="utf-8")

    assert [
        path.relative_to(source_dir).as_posix() for path in find_markdown_files(source_dir)
    ] == [
        "nested/a-first.md",
        "z-last.md",
    ]


def test_create_scraped_document_from_markdown_additional_paths(pipeline, tmp_path):
    md_file = tmp_path / "ops-guide.md"
    md_file.write_text(
        "---\n"
        "severity: info\n"
        "doc_type: strange\n"
        "name:  \n"
        "summary:  \n"
        "category: enterprise\n"
        "custom-key: value\n"
        "---\n\n",
        encoding="utf-8",
    )

    document = create_scraped_document_from_markdown(md_file)
    assert document.title == "Ops Guide"
    assert document.severity == SeverityLevel.LOW
    assert document.doc_type == DocumentType.KNOWLEDGE
    assert document.metadata["name"] == "ops-guide"
    assert document.metadata["summary"] is None
    assert document.metadata["custom_key"] == "value"
    assert document.category == DocumentCategory.ENTERPRISE

    metadata = parse_markdown_metadata("---\ninvalid\n---\n# Title\n")
    assert metadata["title"] == "Title"


@pytest.mark.asyncio
async def test_ingest_source_documents_paths(pipeline, tmp_path):
    missing_dir = tmp_path / "missing"
    with pytest.raises(ValueError, match="Source directory does not exist"):
        await pipeline.ingest_source_documents(missing_dir)

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert await pipeline.ingest_source_documents(empty_dir) == []

    source_dir = tmp_path / "source_documents" / "shared"
    source_dir.mkdir(parents=True)
    tracked_file = source_dir / "tracked.md"
    tracked_file.write_text("# Tracked\n\nBody", encoding="utf-8")
    broken_file = source_dir / "broken.md"
    broken_file.write_text("# Broken\n\nBody", encoding="utf-8")

    knowledge = AsyncMock()
    skill = AsyncMock()
    knowledge.replace_source_document_chunks.return_value = {"action": "add", "indexed_count": 2}

    def chunk_document_side_effect(document):
        if str(document.metadata.get("file_path", "")).endswith("broken.md"):
            raise RuntimeError("bad doc")
        return [{"document_hash": "new-hash", "source_document_path": "shared/tracked.md"}]

    with (
        patch(
            "redis_sre_agent.pipelines.ingestion._processor_impl.get_vectorizer",
            return_value=MagicMock(),
        ),
        patch.object(
            pipeline,
            "_build_deduplicators",
            return_value={"knowledge": knowledge, "skill": skill},
        ),
        patch.object(
            pipeline,
            "_list_tracked_source_documents",
            return_value={
                "shared/tracked.md": [
                    {"deduplicator_key": "knowledge", "document_hash": "same-type-hash"},
                    {"deduplicator_key": "skill", "document_hash": "old-skill-hash"},
                ],
                "shared/deleted.md": [
                    {
                        "deduplicator_key": "knowledge",
                        "document_hash": "deleted-hash",
                        "title": "Deleted",
                        "category": "shared",
                        "severity": "high",
                    }
                ],
                "shared/broken.md": [
                    {
                        "deduplicator_key": "knowledge",
                        "document_hash": "broken-hash",
                        "title": "Broken",
                    }
                ],
            },
        ),
        patch.object(
            pipeline.processor,
            "chunk_document",
            side_effect=chunk_document_side_effect,
        ),
    ):
        results = await pipeline.ingest_source_documents(source_dir.parent)

    skill.delete_tracked_source_document.assert_awaited_once_with(
        "old-skill-hash", "shared/tracked.md"
    )
    knowledge.delete_tracked_source_document.assert_any_await("deleted-hash", "shared/deleted.md")
    assert (
        call("broken-hash", "shared/broken.md")
        not in knowledge.delete_tracked_source_document.await_args_list
    )
    assert any(
        result["action"] == "update" for result in results if result["file"] == "shared/tracked.md"
    )
    assert any(
        result["action"] == "delete" for result in results if result["file"] == "shared/deleted.md"
    )
    assert {
        key: value
        for key, value in next(
            result for result in results if result["file"] == "shared/deleted.md"
        ).items()
        if key in {"category", "severity"}
    } == {"category": "shared", "severity": "high"}
    assert any(
        result["status"] == "error" and result["file"] == "shared/broken.md" for result in results
    )


def test_load_source_documents_discovers_nested_and_configured_skill_roots(pipeline, tmp_path):
    source_root = tmp_path / "source_documents"
    shared_dir = source_root / "shared"
    shared_dir.mkdir(parents=True)
    (shared_dir / "guide.md").write_text("# Guide\n\nBody", encoding="utf-8")
    _write_formal_skill_package(source_root / "skills", "local-skill")

    external_root = tmp_path / "company-skills"
    _write_formal_skill_package(external_root, "external-skill")
    pipeline.knowledge_settings = SimpleNamespace(skill_roots=[str(external_root)])

    documents = pipeline._load_source_documents(source_root, action="process")
    paths = [str(document.metadata.get("source_document_path") or "") for document in documents]

    assert "shared/guide.md" in paths
    assert "skills/local-skill/SKILL.md" in paths
    assert "skills/local-skill/references/maintenance-checklist.md" in paths
    assert "skills/local-skill/scripts/collect_context.sh" in paths
    assert "skills/local-skill/assets/example-query.txt" in paths
    assert "company-skills/external-skill/SKILL.md" in paths
    assert paths.count("skills/local-skill/references/maintenance-checklist.md") == 1


@pytest.mark.asyncio
async def test_ingest_source_documents_marks_unchanged_skill_resources(pipeline, tmp_path):
    source_root = tmp_path / "source_documents"
    _write_formal_skill_package(source_root / "skills")

    def _chunk_document(document):
        return [
            {
                "document_hash": f"hash-{document.metadata['resource_path']}",
                "source_document_path": document.metadata["source_document_path"],
            }
        ]

    with (
        patch(
            "redis_sre_agent.pipelines.ingestion._processor_impl.get_vectorizer",
            return_value=MagicMock(),
        ),
        patch.object(
            pipeline,
            "_build_deduplicators",
            return_value={"knowledge": AsyncMock(), "skill": AsyncMock()},
        ),
        patch.object(pipeline, "_list_tracked_source_documents", return_value={}),
        patch.object(pipeline.processor, "chunk_document", side_effect=_chunk_document),
        patch(
            "redis_sre_agent.pipelines.ingestion.pipeline_workflow_mixin.index_processed_document",
            new=AsyncMock(
                side_effect=lambda document, **_: {
                    "chunks_created": 1,
                    "chunks_indexed": 0,
                    "source_document_change": {
                        "action": "unchanged",
                        "source_document_path": document.metadata["source_document_path"],
                    },
                    "source_document_path": document.metadata["source_document_path"],
                    "source_document_scope": document.metadata.get("source_document_scope", ""),
                }
            ),
        ),
    ):
        results = await pipeline.ingest_source_documents(source_root)

    unchanged_paths = {result["file"] for result in results if result["action"] == "unchanged"}
    assert "skills/redis-maintenance-triage/SKILL.md" in unchanged_paths
    assert "skills/redis-maintenance-triage/references/maintenance-checklist.md" in unchanged_paths


@pytest.mark.asyncio
async def test_ingest_source_documents_deletes_removed_skill_resources(pipeline, tmp_path):
    source_root = tmp_path / "source_documents"
    _write_formal_skill_package(source_root / "skills")

    def _chunk_document(document):
        return [
            {
                "document_hash": f"hash-{document.metadata['resource_path']}",
                "source_document_path": document.metadata["source_document_path"],
            }
        ]

    with (
        patch(
            "redis_sre_agent.pipelines.ingestion._processor_impl.get_vectorizer",
            return_value=MagicMock(),
        ),
        patch.object(
            pipeline,
            "_build_deduplicators",
            return_value={"knowledge": AsyncMock(), "skill": AsyncMock()},
        ),
        patch.object(
            pipeline,
            "_list_tracked_source_documents",
            return_value={
                "skills/redis-maintenance-triage/references/old-checklist.md": [
                    {
                        "deduplicator_key": "skill",
                        "document_hash": "old-hash",
                        "title": "Old Checklist",
                        "category": "shared",
                        "severity": "low",
                    }
                ]
            },
        ),
        patch.object(pipeline.processor, "chunk_document", side_effect=_chunk_document),
        patch(
            "redis_sre_agent.pipelines.ingestion.pipeline_workflow_mixin.index_processed_document",
            new=AsyncMock(
                side_effect=lambda document, **_: {
                    "chunks_created": 1,
                    "chunks_indexed": 1,
                    "source_document_change": {
                        "action": "add",
                        "source_document_path": document.metadata["source_document_path"],
                    },
                    "source_document_path": document.metadata["source_document_path"],
                    "source_document_scope": document.metadata.get("source_document_scope", ""),
                }
            ),
        ),
    ):
        results = await pipeline.ingest_source_documents(source_root)

    assert any(
        result["action"] == "delete"
        and result["file"] == "skills/redis-maintenance-triage/references/old-checklist.md"
        for result in results
    )


@pytest.mark.asyncio
async def test_ingest_source_documents_tolerates_missing_source_change(pipeline, tmp_path):
    source_dir = tmp_path / "source_documents"
    source_dir.mkdir()
    md_file = source_dir / "doc.md"
    md_file.write_text("# Doc\n\nBody", encoding="utf-8")

    with (
        patch(
            "redis_sre_agent.pipelines.ingestion._processor_impl.get_vectorizer",
            return_value=MagicMock(),
        ),
        patch.object(
            pipeline,
            "_build_deduplicators",
            return_value={"knowledge": AsyncMock(), "skill": AsyncMock()},
        ),
        patch.object(pipeline, "_list_tracked_source_documents", return_value={}),
        patch.object(pipeline.processor, "chunk_document", return_value=[{"id": "chunk-1"}]),
        patch(
            "redis_sre_agent.pipelines.ingestion.pipeline_workflow_mixin.index_processed_document",
            new=AsyncMock(
                return_value={
                    "chunks_created": 1,
                    "chunks_indexed": 1,
                    "source_document_change": None,
                    "source_document_path": "",
                    "source_document_scope": "",
                }
            ),
        ),
    ):
        results = await pipeline.ingest_source_documents(source_dir)

    assert results == [
        {
            "file": "doc.md",
            "title": "Doc",
            "category": DocumentCategory.SHARED,
            "severity": SeverityLevel.MEDIUM,
            "status": "success",
            "action": "",
            "chunks_created": 1,
            "chunks_indexed": 1,
        }
    ]


@pytest.mark.asyncio
async def test_prepare_source_artifacts_and_ingest_prepared_batch(pipeline, tmp_path):
    missing_dir = tmp_path / "missing"
    with pytest.raises(ValueError, match="Source directory does not exist"):
        await pipeline.prepare_source_artifacts(missing_dir, "2025-01-20")

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert await pipeline.prepare_source_artifacts(empty_dir, "2025-01-20") == 0

    source_dir = tmp_path / "source_documents"
    source_dir.mkdir()
    first = source_dir / "first.md"
    second = source_dir / "second.md"
    first.write_text("# First", encoding="utf-8")
    second.write_text("# Second", encoding="utf-8")

    document = _make_document()
    created_documents = patch(
        "redis_sre_agent.pipelines.ingestion.pipeline_workflow_mixin.create_scraped_document_from_markdown",
        side_effect=[document, RuntimeError("bad file")],
    )
    with (
        created_documents as create_document,
        patch.object(pipeline.storage, "save_document") as save_document,
        patch.object(pipeline.storage, "save_batch_manifest") as save_manifest,
    ):
        prepared_count = await pipeline.prepare_source_artifacts(source_dir, "2025-01-20")

    assert prepared_count == 1
    assert sorted(
        create_document.call_args_list, key=lambda recorded_call: recorded_call.args[0].name
    ) == [
        call(first, source_dir),
        call(second, source_dir),
    ]
    save_document.assert_called_once_with(document)
    save_manifest.assert_called_once()

    with patch.object(
        pipeline, "ingest_batch", return_value={"success": True, "chunks_indexed": 2}
    ):
        assert await pipeline.ingest_prepared_batch("2025-01-20") == [
            {"status": "success", "batch_date": "2025-01-20", "success": True, "chunks_indexed": 2}
        ]

    with patch.object(pipeline, "ingest_batch", return_value={"success": False}):
        assert await pipeline.ingest_prepared_batch("2025-01-20") == [
            {"status": "error", "batch_date": "2025-01-20", "error": "Batch ingestion failed"}
        ]


@pytest.mark.asyncio
async def test_ingest_batch_error_path(pipeline, tmp_path):
    batch_date = "2025-01-20"
    batch_path = tmp_path / batch_date
    (batch_path / "shared").mkdir(parents=True)
    manifest = {"batch_date": batch_date, "documents": [{"category": "shared"}]}

    with (
        patch.object(pipeline.storage, "get_batch_manifest", return_value=manifest),
        patch.object(pipeline, "_build_deduplicators", return_value={"knowledge": AsyncMock()}),
        patch(
            "redis_sre_agent.pipelines.ingestion._processor_impl.get_vectorizer",
            return_value=MagicMock(),
        ),
        patch.object(pipeline, "_list_tracked_source_documents", return_value={}),
        patch.object(pipeline, "_process_category", side_effect=RuntimeError("process boom")),
    ):
        with pytest.raises(RuntimeError, match="process boom"):
            await pipeline.ingest_batch(batch_date)


def test_pipeline_module_main_executes_help():
    original_argv = sys.argv[:]
    sys.argv = ["redis_sre_agent.cli.pipeline", "--help"]
    try:
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_module("redis_sre_agent.cli.pipeline", run_name="__main__")
        assert exc_info.value.code == 0
    finally:
        sys.argv = original_argv
