"""Tests for the `knowledge` CLI commands."""

from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from redis_sre_agent.cli.knowledge import knowledge


@pytest.fixture
def cli_runner():
    """Click CLI test runner."""
    return CliRunner()


class TestKnowledgeSearchCLI:
    """Test knowledge search CLI command."""

    def test_search_help_shows_offset_option(self, cli_runner):
        """Test that --offset option is visible in help."""
        result = cli_runner.invoke(knowledge, ["search", "--help"])

        assert result.exit_code == 0
        assert "--offset" in result.output
        assert "-o" in result.output

    def test_search_help_shows_version_option(self, cli_runner):
        """Test that --version option is visible in help."""
        result = cli_runner.invoke(knowledge, ["search", "--help"])

        assert result.exit_code == 0
        assert "--version" in result.output
        assert "-v" in result.output

    def test_search_passes_offset_to_helper(self, cli_runner):
        """Test that offset parameter is passed to search helper."""
        mock_result = {
            "query": "redis memory",
            "results_count": 1,
            "results": [
                {
                    "title": "Redis Memory Guide",
                    "content": "Redis uses memory...",
                    "source": "docs",
                    "category": "documentation",
                    "version": "latest",
                }
            ],
        }

        with patch(
            "redis_sre_agent.cli.knowledge.search_knowledge_base_helper",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = mock_result

            result = cli_runner.invoke(knowledge, ["search", "redis", "memory", "--offset", "5"])

            assert result.exit_code == 0, result.output
            mock_search.assert_called_once()
            call_kwargs = mock_search.call_args.kwargs
            assert call_kwargs["offset"] == 5

    def test_search_passes_version_to_helper(self, cli_runner):
        """Test that version parameter is passed to search helper."""
        mock_result = {
            "query": "redis clustering",
            "results_count": 1,
            "results": [
                {
                    "title": "Clustering Guide",
                    "content": "How to set up clustering...",
                    "source": "docs",
                    "category": "documentation",
                    "version": "7.8",
                }
            ],
        }

        with patch(
            "redis_sre_agent.cli.knowledge.search_knowledge_base_helper",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = mock_result

            result = cli_runner.invoke(
                knowledge, ["search", "redis", "clustering", "--version", "7.8"]
            )

            assert result.exit_code == 0, result.output
            mock_search.assert_called_once()
            call_kwargs = mock_search.call_args.kwargs
            assert call_kwargs["version"] == "7.8"

    def test_search_default_version_is_latest(self, cli_runner):
        """Test that version defaults to 'latest' when not specified."""
        mock_result = {
            "query": "test",
            "results_count": 0,
            "results": [],
        }

        with patch(
            "redis_sre_agent.cli.knowledge.search_knowledge_base_helper",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = mock_result

            result = cli_runner.invoke(knowledge, ["search", "test"])

            assert result.exit_code == 0, result.output
            mock_search.assert_called_once()
            call_kwargs = mock_search.call_args.kwargs
            assert call_kwargs["version"] == "latest"

    def test_search_default_offset_is_zero(self, cli_runner):
        """Test that offset defaults to 0 when not specified."""
        mock_result = {
            "query": "test",
            "results_count": 0,
            "results": [],
        }

        with patch(
            "redis_sre_agent.cli.knowledge.search_knowledge_base_helper",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = mock_result

            result = cli_runner.invoke(knowledge, ["search", "test"])

            assert result.exit_code == 0, result.output
            mock_search.assert_called_once()
            call_kwargs = mock_search.call_args.kwargs
            assert call_kwargs["offset"] == 0

    def test_search_with_all_options(self, cli_runner):
        """Test search with offset, version, and other options combined."""
        mock_result = {
            "query": "redis performance",
            "results_count": 2,
            "results": [
                {
                    "title": "Perf Guide",
                    "content": "Performance tips...",
                    "source": "docs",
                    "category": "performance",
                    "version": "7.4",
                }
            ],
        }

        with patch(
            "redis_sre_agent.cli.knowledge.search_knowledge_base_helper",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = mock_result

            result = cli_runner.invoke(
                knowledge,
                [
                    "search",
                    "redis",
                    "performance",
                    "--offset",
                    "10",
                    "--version",
                    "7.4",
                    "--limit",
                    "5",
                    "--category",
                    "performance",
                ],
            )

            assert result.exit_code == 0, result.output
            mock_search.assert_called_once()
            call_kwargs = mock_search.call_args.kwargs
            assert call_kwargs["offset"] == 10
            assert call_kwargs["version"] == "7.4"
            assert call_kwargs["limit"] == 5
            assert call_kwargs["category"] == "performance"


class TestKnowledgeFragmentsCLI:
    """Test knowledge fragments CLI command."""

    def test_fragments_help_shows_options(self, cli_runner):
        """Test that fragments command shows expected options in help."""
        result = cli_runner.invoke(knowledge, ["fragments", "--help"])

        assert result.exit_code == 0
        assert "DOCUMENT_HASH" in result.output
        assert "--json" in result.output
        assert "--include-metadata" in result.output
        assert "--no-metadata" in result.output

    def test_fragments_passes_document_hash(self, cli_runner):
        """Test that document_hash is passed to helper."""
        mock_result = {
            "title": "Test Doc",
            "source": "test",
            "category": "general",
            "fragments_count": 2,
            "fragments": [
                {"chunk_index": 0, "content": "First chunk"},
                {"chunk_index": 1, "content": "Second chunk"},
            ],
        }

        with patch(
            "redis_sre_agent.cli.knowledge.get_all_document_fragments",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_result

            result = cli_runner.invoke(knowledge, ["fragments", "abc123"])

            assert result.exit_code == 0, result.output
            mock_get.assert_called_once_with("abc123", include_metadata=True)

    def test_fragments_with_no_metadata(self, cli_runner):
        """Test that --no-metadata flag is passed correctly."""
        mock_result = {
            "fragments_count": 1,
            "fragments": [{"chunk_index": 0, "content": "Content"}],
        }

        with patch(
            "redis_sre_agent.cli.knowledge.get_all_document_fragments",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_result

            result = cli_runner.invoke(knowledge, ["fragments", "abc123", "--no-metadata"])

            assert result.exit_code == 0, result.output
            mock_get.assert_called_once_with("abc123", include_metadata=False)

    def test_fragments_json_output(self, cli_runner):
        """Test that --json flag outputs JSON."""
        mock_result = {
            "title": "Test Doc",
            "fragments_count": 1,
            "fragments": [{"chunk_index": 0, "content": "Content"}],
        }

        with patch(
            "redis_sre_agent.cli.knowledge.get_all_document_fragments",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_result

            result = cli_runner.invoke(knowledge, ["fragments", "abc123", "--json"])

            assert result.exit_code == 0, result.output
            # JSON output should be parseable
            import json

            output_data = json.loads(result.output)
            assert output_data["title"] == "Test Doc"

    def test_fragments_handles_error(self, cli_runner):
        """Test that errors are handled gracefully."""
        with patch(
            "redis_sre_agent.cli.knowledge.get_all_document_fragments",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.side_effect = Exception("Document not found")

            result = cli_runner.invoke(knowledge, ["fragments", "nonexistent"])

            assert result.exit_code == 0  # CLI doesn't exit with error code
            assert "Error" in result.output or "error" in result.output


class TestKnowledgeRelatedCLI:
    """Test knowledge related CLI command."""

    def test_related_help_shows_options(self, cli_runner):
        """Test that related command shows expected options in help."""
        result = cli_runner.invoke(knowledge, ["related", "--help"])

        assert result.exit_code == 0
        assert "DOCUMENT_HASH" in result.output
        assert "--chunk-index" in result.output
        assert "--window" in result.output
        assert "--json" in result.output

    def test_related_requires_chunk_index(self, cli_runner):
        """Test that --chunk-index is required."""
        result = cli_runner.invoke(knowledge, ["related", "abc123"])

        assert result.exit_code != 0
        assert "chunk-index" in result.output.lower() or "required" in result.output.lower()

    def test_related_passes_parameters(self, cli_runner):
        """Test that parameters are passed to helper."""
        mock_result = {
            "title": "Test Doc",
            "source": "test",
            "category": "general",
            "target_chunk_index": 5,
            "context_window": 2,
            "related_fragments_count": 3,
            "related_fragments": [
                {"chunk_index": 4, "content": "Before", "is_target_chunk": False},
                {"chunk_index": 5, "content": "Target", "is_target_chunk": True},
                {"chunk_index": 6, "content": "After", "is_target_chunk": False},
            ],
        }

        with patch(
            "redis_sre_agent.cli.knowledge.get_related_document_fragments",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_result

            result = cli_runner.invoke(knowledge, ["related", "abc123", "--chunk-index", "5"])

            assert result.exit_code == 0, result.output
            mock_get.assert_called_once_with("abc123", current_chunk_index=5, context_window=2)

    def test_related_with_custom_window(self, cli_runner):
        """Test that --window parameter is passed correctly."""
        mock_result = {
            "target_chunk_index": 5,
            "context_window": 4,
            "related_fragments_count": 0,
            "related_fragments": [],
        }

        with patch(
            "redis_sre_agent.cli.knowledge.get_related_document_fragments",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_result

            result = cli_runner.invoke(
                knowledge, ["related", "abc123", "--chunk-index", "5", "--window", "4"]
            )

            assert result.exit_code == 0, result.output
            mock_get.assert_called_once_with("abc123", current_chunk_index=5, context_window=4)

    def test_related_json_output(self, cli_runner):
        """Test that --json flag outputs JSON."""
        mock_result = {
            "title": "Test Doc",
            "target_chunk_index": 5,
            "related_fragments_count": 1,
            "related_fragments": [{"chunk_index": 5, "content": "Target"}],
        }

        with patch(
            "redis_sre_agent.cli.knowledge.get_related_document_fragments",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_result

            result = cli_runner.invoke(
                knowledge, ["related", "abc123", "--chunk-index", "5", "--json"]
            )

            assert result.exit_code == 0, result.output
            import json

            output_data = json.loads(result.output)
            assert output_data["target_chunk_index"] == 5

    def test_related_handles_error(self, cli_runner):
        """Test that errors are handled gracefully."""
        with patch(
            "redis_sre_agent.cli.knowledge.get_related_document_fragments",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.side_effect = Exception("Document not found")

            result = cli_runner.invoke(knowledge, ["related", "nonexistent", "--chunk-index", "0"])

            assert result.exit_code == 0  # CLI doesn't exit with error code
            assert "Error" in result.output or "error" in result.output
