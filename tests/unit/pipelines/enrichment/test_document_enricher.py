"""Unit tests for the document enrichment pipeline."""

from unittest.mock import MagicMock, patch

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
