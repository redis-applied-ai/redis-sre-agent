"""Unit tests for the document enrichment pipeline."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from redis_sre_agent.pipelines.enrichment.document_enricher import DocumentEnricher


def test_document_enricher_init_uses_nano_client_with_default_key():
    """Constructor should create a nano async client with default key."""
    mock_client = MagicMock()
    with patch(
        "redis_sre_agent.pipelines.enrichment.document_enricher.create_nano_async_openai_client",
        return_value=mock_client,
    ) as mock_factory:
        enricher = DocumentEnricher()

    mock_factory.assert_called_once_with(api_key=None)
    assert enricher.client is mock_client


def test_document_enricher_init_uses_nano_client_with_explicit_key():
    """Constructor should pass through explicit OpenAI API key."""
    mock_client = MagicMock()
    with patch(
        "redis_sre_agent.pipelines.enrichment.document_enricher.create_nano_async_openai_client",
        return_value=mock_client,
    ) as mock_factory:
        enricher = DocumentEnricher(openai_api_key="test-key")

    mock_factory.assert_called_once_with(api_key="test-key")
    assert enricher.client is mock_client


@pytest.mark.asyncio
async def test_generate_semantic_description_uses_guarded_chat_completions():
    """Semantic description generation should route through the guarded wrapper."""
    mock_client = MagicMock()
    mock_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"description":"desc","use_case":"ops","when_to_use":"now"}'
                )
            )
        ]
    )

    with (
        patch(
            "redis_sre_agent.pipelines.enrichment.document_enricher.create_nano_async_openai_client",
            return_value=mock_client,
        ),
        patch(
            "redis_sre_agent.pipelines.enrichment.document_enricher.guarded_chat_completions_create",
            return_value=mock_response,
        ) as mock_guarded,
    ):
        enricher = DocumentEnricher()
        result = await enricher.generate_semantic_description("INFO memory", "content")

    assert result["description"] == "desc"
    assert mock_guarded.await_count == 1
