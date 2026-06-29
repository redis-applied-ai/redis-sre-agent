from unittest.mock import AsyncMock, patch


def test_get_knowledge_document_chunks_returns_chunks(test_client):
    expected = {
        "document_hash": "doc-1",
        "fragments_count": 2,
        "fragments": [
            {"chunk_index": 0, "content": "first"},
            {"chunk_index": 1, "content": "second"},
        ],
        "metadata": {"version": "8.0"},
    }

    with patch(
        "redis_sre_agent.core.knowledge_helpers.get_all_document_fragments",
        new=AsyncMock(return_value=expected),
    ) as get_all_document_fragments:
        response = test_client.get(
            "/api/v1/knowledge/document-chunks/doc-1?version=8.0&index_type=knowledge"
        )

    assert response.status_code == 200
    assert response.json() == {
        "document_hash": "doc-1",
        "index_type": "knowledge",
        "chunk_count": 2,
        "chunks": [
            {"chunk_index": 0, "content": "first"},
            {"chunk_index": 1, "content": "second"},
        ],
        "title": None,
        "source": None,
        "category": None,
        "doc_type": None,
        "name": None,
        "summary": None,
        "priority": None,
        "pinned": None,
        "metadata": {"version": "8.0"},
    }
    get_all_document_fragments.assert_awaited_once_with(
        "doc-1",
        include_metadata=True,
        index_type="knowledge",
        version="8.0",
    )


def test_get_knowledge_document_chunks_returns_404_for_missing_chunks(test_client):
    with patch(
        "redis_sre_agent.core.knowledge_helpers.get_all_document_fragments",
        new=AsyncMock(return_value={"error": "No chunks found", "fragments": []}),
    ):
        response = test_client.get("/api/v1/knowledge/document-chunks/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "No chunks found"


def test_get_knowledge_document_chunks_decodes_document_hash(test_client):
    expected = {
        "document_hash": "doc with space",
        "fragments_count": 1,
        "fragments": [{"chunk_index": 0, "content": "first"}],
    }

    with patch(
        "redis_sre_agent.core.knowledge_helpers.get_all_document_fragments",
        new=AsyncMock(return_value=expected),
    ) as get_all_document_fragments:
        response = test_client.get("/api/v1/knowledge/document-chunks/doc%20with%20space")

    assert response.status_code == 200
    assert response.json()["document_hash"] == "doc with space"
    get_all_document_fragments.assert_awaited_once_with(
        "doc with space",
        include_metadata=True,
        index_type="knowledge",
        version=None,
    )


def test_get_knowledge_document_chunks_returns_404_for_deleted_document(test_client):
    with patch(
        "redis_sre_agent.core.knowledge_helpers.get_all_document_fragments",
        new=AsyncMock(return_value={"error": "Document was deleted", "fragments": []}),
    ):
        response = test_client.get("/api/v1/knowledge/document-chunks/deleted-doc")

    assert response.status_code == 404
    assert response.json()["detail"] == "Document was deleted"
