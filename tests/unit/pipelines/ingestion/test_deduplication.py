"""Focused tests for document deduplication helpers."""

import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from redis_sre_agent.pipelines.ingestion.deduplication import DocumentDeduplicator


def _async_iter(items):
    async def generator():
        for item in items:
            yield item

    return generator()


@pytest.fixture
def redis_client():
    client = AsyncMock()
    client.scan_iter = lambda match=None: _async_iter([])
    client.hgetall = AsyncMock(return_value={})
    client.delete = AsyncMock(return_value=0)
    client.hset = AsyncMock(return_value=1)
    return client


@pytest.fixture
def deduplicator(redis_client):
    return DocumentDeduplicator(SimpleNamespace(client=redis_client, load=AsyncMock()))


@pytest.mark.asyncio
async def test_key_generation_and_decode_mapping(deduplicator):
    assert deduplicator.generate_deterministic_chunk_key("abc", 2) == "sre_knowledge:abc:chunk:2"
    assert deduplicator.generate_document_tracking_key("abc") == "sre_knowledge_meta:abc"

    expected_hash = hashlib.sha256(b"shared/file.md").hexdigest()[:16]
    assert (
        deduplicator.generate_source_tracking_key("shared/file.md")
        == f"sre_knowledge_meta:source:{expected_hash}"
    )
    assert DocumentDeduplicator._decode_mapping({b"a": b"1", "b": 2}) == {"a": "1", "b": 2}


@pytest.mark.asyncio
async def test_find_existing_chunks_success_and_scan_errors(redis_client, deduplicator):
    redis_client.scan_iter = lambda match=None: _async_iter(
        [b"sre_knowledge:hash:chunk:0", "sre_knowledge:hash:chunk:1"]
    )

    assert await deduplicator.find_existing_chunks("hash") == [
        "sre_knowledge:hash:chunk:0",
        "sre_knowledge:hash:chunk:1",
    ]

    def broken_scan_iter(match=None):
        raise RuntimeError("boom")

    redis_client.scan_iter = broken_scan_iter
    assert await deduplicator.find_existing_chunks("hash") == []

    broken_deduplicator = DocumentDeduplicator(SimpleNamespace())
    assert await broken_deduplicator.find_existing_chunks("hash") == []


@pytest.mark.asyncio
async def test_delete_existing_chunks_variants(redis_client, deduplicator):
    deduplicator.find_existing_chunks = AsyncMock(return_value=[])
    assert await deduplicator.delete_existing_chunks("hash") == 0

    deduplicator.find_existing_chunks = AsyncMock(return_value=["a", "b"])
    redis_client.delete.return_value = 2
    assert await deduplicator.delete_existing_chunks("hash") == 2

    redis_client.delete.side_effect = RuntimeError("boom")
    assert await deduplicator.delete_existing_chunks("hash") == 0


@pytest.mark.asyncio
async def test_document_metadata_round_trip_and_error_paths(redis_client, deduplicator):
    await deduplicator.update_document_metadata("hash", {"title": "Doc"})
    tracking_key = deduplicator.generate_document_tracking_key("hash")
    redis_client.hset.assert_awaited_once()
    call = redis_client.hset.await_args
    assert call.args[0] == tracking_key
    assert call.kwargs["mapping"]["document_hash"] == "hash"
    assert call.kwargs["mapping"]["title"] == "Doc"
    assert "last_updated" in call.kwargs["mapping"]

    redis_client.hgetall.return_value = {b"title": b"Doc", b"content_hash": b"same"}
    assert await deduplicator.get_document_metadata("hash") == {
        "title": "Doc",
        "content_hash": "same",
    }

    redis_client.hgetall.return_value = {}
    assert await deduplicator.get_document_metadata("hash") is None

    redis_client.hgetall.side_effect = RuntimeError("boom")
    assert await deduplicator.get_document_metadata("hash") is None
    redis_client.hgetall.side_effect = None

    redis_client.delete.return_value = 1
    assert await deduplicator.delete_document_metadata("hash") == 1

    redis_client.delete.side_effect = RuntimeError("boom")
    assert await deduplicator.delete_document_metadata("hash") == 0

    redis_client.hset.side_effect = RuntimeError("boom")
    await deduplicator.update_document_metadata("hash", {"title": "Doc"})


@pytest.mark.asyncio
async def test_source_tracking_helpers(redis_client, deduplicator):
    await deduplicator.update_source_document_tracking("shared/file.md", {"document_hash": "hash"})
    source_call = redis_client.hset.await_args
    assert source_call.kwargs["mapping"]["source_document_path"] == "shared/file.md"
    assert source_call.kwargs["mapping"]["document_hash"] == "hash"

    redis_client.hgetall.side_effect = [
        {b"source_document_path": b"shared/file.md", b"document_hash": b"hash"},
        {b"source_document_path": b"shared/keep.md", b"document_hash": b"hash-1"},
        {},
        {b"document_hash": b"missing-path"},
        {b"source_document_path": b"enterprise/doc.md", b"document_hash": b"hash-2"},
    ]
    redis_client.scan_iter = lambda match=None: _async_iter(["one", "two", "three", "four"])

    assert await deduplicator.get_source_document_tracking("shared/file.md") == {
        "source_document_path": "shared/file.md",
        "document_hash": "hash",
    }

    redis_client.hgetall.side_effect = None
    redis_client.hgetall.return_value = {}
    assert await deduplicator.get_source_document_tracking("shared/missing.md") is None

    redis_client.hgetall.side_effect = [
        {b"source_document_path": b"shared/keep.md", b"document_hash": b"hash-1"},
        {},
        {b"document_hash": b"missing-path"},
        {b"source_document_path": b"enterprise/doc.md", b"document_hash": b"hash-2"},
    ]
    redis_client.scan_iter = lambda match=None: _async_iter(["one", "two", "three", "four"])
    assert await deduplicator.list_tracked_source_documents() == {
        "shared/keep.md": {
            "source_document_path": "shared/keep.md",
            "document_hash": "hash-1",
        },
        "enterprise/doc.md": {
            "source_document_path": "enterprise/doc.md",
            "document_hash": "hash-2",
        },
    }

    redis_client.hgetall.side_effect = [
        {b"source_document_path": b"shared/keep.md", b"document_hash": b"hash-1"},
        {b"source_document_path": b"enterprise/doc.md", b"document_hash": b"hash-2"},
    ]
    redis_client.scan_iter = lambda match=None: _async_iter(["one", "two"])
    assert await deduplicator.list_tracked_source_documents("shared/") == {
        "shared/keep.md": {
            "source_document_path": "shared/keep.md",
            "document_hash": "hash-1",
        }
    }

    redis_client.scan_iter = lambda match=None: (_ for _ in ()).throw(RuntimeError("boom"))
    assert await deduplicator.list_tracked_source_documents() == {}

    redis_client.hgetall = AsyncMock(side_effect=RuntimeError("boom"))
    assert await deduplicator.get_source_document_tracking("shared/file.md") is None

    redis_client.hset.side_effect = RuntimeError("boom")
    await deduplicator.update_source_document_tracking("shared/file.md", {"document_hash": "hash"})


@pytest.mark.asyncio
async def test_delete_tracked_source_document(redis_client, deduplicator):
    deduplicator.delete_existing_chunks = AsyncMock(return_value=3)
    deduplicator.delete_document_metadata = AsyncMock(return_value=1)
    redis_client.delete.return_value = 1

    assert await deduplicator.delete_tracked_source_document("hash", "shared/file.md") == {
        "chunks_deleted": 3,
        "metadata_deleted": 1,
        "source_tracking_deleted": 1,
    }

    redis_client.delete.side_effect = RuntimeError("boom")
    assert await deduplicator.delete_tracked_source_document("hash", "shared/file.md") == {
        "chunks_deleted": 3,
        "metadata_deleted": 1,
        "source_tracking_deleted": 0,
    }

    redis_client.delete.side_effect = None
    assert await deduplicator.delete_tracked_source_document(
        "hash", "shared/file.md", remove_source_tracking=False
    ) == {
        "chunks_deleted": 3,
        "metadata_deleted": 1,
        "source_tracking_deleted": 0,
    }


@pytest.mark.asyncio
async def test_get_existing_chunks_with_hashes_and_should_replace(redis_client, deduplicator):
    redis_client.scan_iter = lambda match=None: _async_iter([b"chunk:0", "chunk:1", "chunk:2"])
    redis_client.hgetall.side_effect = [
        {b"content_hash": b"same", b"vector": b"vec"},
        {"content_hash": "other"},
        {},
    ]

    assert await deduplicator.get_existing_chunks_with_hashes("hash") == {
        "chunk:0": {"content_hash": "same", "vector": b"vec"}
    }

    redis_client.scan_iter = lambda match=None: (_ for _ in ()).throw(RuntimeError("boom"))
    assert await deduplicator.get_existing_chunks_with_hashes("hash") == {}

    deduplicator.get_document_metadata = AsyncMock(return_value=None)
    assert await deduplicator.should_replace_document("hash") is True

    deduplicator.get_document_metadata = AsyncMock(return_value={"content_hash": "same"})
    assert await deduplicator.should_replace_document("hash", "different") is True
    assert await deduplicator.should_replace_document("hash", "same") is False
    assert await deduplicator.should_replace_document("hash") is True


def test_prepare_chunks_for_replacement(deduplicator):
    prepared = deduplicator.prepare_chunks_for_replacement(
        [{"document_hash": "hash", "chunk_index": 1, "content": "body"}]
    )
    assert prepared == [
        {
            "document_hash": "hash",
            "chunk_index": 1,
            "content": "body",
            "id": "sre_knowledge:hash:chunk:1",
            "chunk_key": "sre_knowledge:hash:chunk:1",
        }
    ]


@pytest.mark.asyncio
async def test_replace_document_chunks_reuses_and_embeds(redis_client, deduplicator):
    chunks = [
        {
            "document_hash": "hash",
            "chunk_index": 0,
            "title": "Doc",
            "content": "same body",
            "source": "src",
            "category": "shared",
            "doc_type": "knowledge",
            "severity": "medium",
            "summary": "sum",
            "priority": "critical",
            "pinned": "true",
            "metadata": {
                "product_labels": ["redis", "sre"],
                "product_label_tags": "ops",
                "nullable": None,
                "owner": "team",
            },
        },
        {
            "document_hash": "hash",
            "chunk_index": 1,
            "title": "Doc part 2",
            "content": "new body",
            "source": "src",
            "category": "shared",
            "doc_type": "knowledge",
            "severity": "medium",
            "metadata": {
                "product_labels": "redis",
                "product_label_tags": ["ops", "sre"],
            },
        },
    ]

    prepared_first_key = deduplicator.generate_deterministic_chunk_key("hash", 0)
    reused_hash = hashlib.sha256(b"same body").hexdigest()

    deduplicator.should_replace_document = AsyncMock(return_value=True)
    deduplicator.get_existing_chunks_with_hashes = AsyncMock(
        return_value={prepared_first_key: {"content_hash": reused_hash, "vector": b"reused"}}
    )
    deduplicator.delete_existing_chunks = AsyncMock(return_value=1)
    deduplicator.update_document_metadata = AsyncMock()

    vectorizer = AsyncMock()
    vectorizer.aembed_many = AsyncMock(return_value=[b"fresh"])

    indexed_count = await deduplicator.replace_document_chunks(chunks, vectorizer)

    assert indexed_count == 2
    vectorizer.aembed_many.assert_awaited_once_with(["new body"], as_buffer=True)
    deduplicator.delete_existing_chunks.assert_awaited_once_with("hash")
    deduplicator.update_document_metadata.assert_awaited_once()
    deduplicator.index.load.assert_awaited_once()

    indexed_docs = deduplicator.index.load.await_args.kwargs["data"]
    assert indexed_docs[0]["vector"] == b"reused"
    assert indexed_docs[0]["product_labels"] == "redis,sre"
    assert indexed_docs[0]["product_label_tags"] == "ops"
    assert indexed_docs[0]["meta_nullable"] == ""
    assert indexed_docs[0]["meta_owner"] == "team"
    assert indexed_docs[1]["vector"] == b"fresh"
    assert indexed_docs[1]["product_labels"] == "redis"
    assert indexed_docs[1]["product_label_tags"] == "ops,sre"


@pytest.mark.asyncio
async def test_replace_document_chunks_all_reused_and_error_paths(deduplicator):
    chunks = [
        {
            "document_hash": "hash",
            "chunk_index": 0,
            "title": "Doc",
            "content": "same body",
            "source": "src",
            "category": "shared",
            "doc_type": "knowledge",
            "severity": "medium",
            "metadata": {},
        }
    ]

    prepared_key = deduplicator.generate_deterministic_chunk_key("hash", 0)
    reused_hash = hashlib.sha256(b"same body").hexdigest()

    assert await deduplicator.replace_document_chunks([], AsyncMock()) == 0

    deduplicator.should_replace_document = AsyncMock(return_value=False)
    assert await deduplicator.replace_document_chunks(chunks, AsyncMock()) == 0

    deduplicator.should_replace_document = AsyncMock(return_value=True)
    deduplicator.get_existing_chunks_with_hashes = AsyncMock(
        return_value={prepared_key: {"content_hash": reused_hash, "vector": b"reused"}}
    )
    deduplicator.delete_existing_chunks = AsyncMock(return_value=0)
    deduplicator.update_document_metadata = AsyncMock()

    vectorizer = AsyncMock()
    vectorizer.aembed_many = AsyncMock()
    await deduplicator.replace_document_chunks(chunks, vectorizer)
    vectorizer.aembed_many.assert_not_called()

    deduplicator.index.load.side_effect = RuntimeError("boom")
    with pytest.raises(RuntimeError, match="boom"):
        await deduplicator.replace_document_chunks(chunks, AsyncMock())


@pytest.mark.asyncio
async def test_replace_source_document_chunks_variants(deduplicator):
    vectorizer = AsyncMock()

    assert await deduplicator.replace_source_document_chunks([], vectorizer) == {
        "action": "unchanged",
        "indexed_count": 0,
    }

    deduplicator.replace_document_chunks = AsyncMock(return_value=4)
    assert await deduplicator.replace_source_document_chunks(
        [{"document_hash": "hash", "source_document_path": ""}],
        vectorizer,
    ) == {"action": "add", "indexed_count": 4}

    chunks = [{"document_hash": "hash", "source_document_path": "shared/file.md"}]
    deduplicator.get_source_document_tracking = AsyncMock(return_value={"document_hash": "hash"})
    assert await deduplicator.replace_source_document_chunks(chunks, vectorizer) == {
        "action": "unchanged",
        "indexed_count": 0,
        "document_hash": "hash",
        "previous_document_hash": "hash",
        "source_document_path": "shared/file.md",
    }

    deduplicator.get_source_document_tracking = AsyncMock(
        return_value={"document_hash": "old-hash"}
    )
    deduplicator.delete_tracked_source_document = AsyncMock()
    deduplicator.replace_document_chunks = AsyncMock(return_value=2)
    deduplicator.update_source_document_tracking = AsyncMock()
    updated = await deduplicator.replace_source_document_chunks(
        [
            {
                "document_hash": "new-hash",
                "source_document_path": "shared/file.md",
                "title": "Doc",
                "source": "file://doc",
                "category": "shared",
                "severity": "high",
                "doc_type": "skill",
                "source_document_scope": "shared/",
                "pinned": "true",
            }
        ],
        vectorizer,
    )
    deduplicator.delete_tracked_source_document.assert_awaited_once_with(
        "old-hash", "shared/file.md", remove_source_tracking=False
    )
    deduplicator.update_source_document_tracking.assert_awaited_once_with(
        "shared/file.md",
        {
            "document_hash": "new-hash",
            "title": "Doc",
            "source": "file://doc",
            "category": "shared",
            "severity": "high",
            "doc_type": "skill",
            "source_document_scope": "shared/",
            "pinned": "true",
        },
    )
    assert updated["action"] == "update"
    assert updated["previous_document_hash"] == "old-hash"

    deduplicator.get_source_document_tracking = AsyncMock(return_value=None)
    added = await deduplicator.replace_source_document_chunks(
        [{"document_hash": "new-hash", "source_document_path": "shared/new.md"}],
        vectorizer,
    )
    assert added["action"] == "add"
    assert added["previous_document_hash"] is None
