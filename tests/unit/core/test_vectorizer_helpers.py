"""Unit tests for vectorizer helper functions."""

from unittest.mock import MagicMock, Mock, patch

import redis_sre_agent.core.vectorizer_helpers as vectorizer_helpers
from redis_sre_agent.core.vectorizer_helpers import (
    create_vectorizer,
    get_vectorizer_factory,
    set_vectorizer_factory,
)


class TestVectorizerHelpers:
    """Test vectorizer helper functionality."""

    def teardown_method(self):
        """Reset vectorizer factory state after each test."""
        vectorizer_helpers._vectorizer_factory = None
        vectorizer_helpers._settings_vectorizer_factory = None
        vectorizer_helpers._factory_initialized = False

    def test_get_vectorizer_factory_returns_none_by_default(self):
        """Factory getter should return None when nothing is registered."""
        set_vectorizer_factory(None)
        assert get_vectorizer_factory() is None

    def test_set_vectorizer_factory_registers_factory(self):
        """Programmatic registration should be observable."""
        mock_factory = MagicMock()
        set_vectorizer_factory(mock_factory)
        assert get_vectorizer_factory() is mock_factory

    def test_set_vectorizer_factory_none_clears_factory(self):
        """Resetting the programmatic factory should restore the default path."""
        set_vectorizer_factory(MagicMock())
        set_vectorizer_factory(None)
        assert get_vectorizer_factory() is None

    def test_create_vectorizer_openai_defaults(self):
        """Default factory should create an OpenAI RedisVL vectorizer."""
        mock_cache = Mock()
        mock_vectorizer = Mock(aembed=Mock(), aembed_many=Mock())

        with (
            patch("redis_sre_agent.core.vectorizer_helpers.settings") as mock_settings,
            patch(
                "redis_sre_agent.core.vectorizer_helpers.EmbeddingsCache", return_value=mock_cache
            ),
            patch(
                "redis_sre_agent.core.vectorizer_helpers.OpenAITextVectorizer",
                return_value=mock_vectorizer,
            ) as mock_openai_vectorizer,
        ):
            mock_settings.redis_url.get_secret_value.return_value = "redis://localhost:6379/0"
            mock_settings.embeddings_cache_ttl = 60
            mock_settings.embedding_provider = "openai"
            mock_settings.embedding_model = "text-embedding-3-small"
            mock_settings.openai_api_key = "test-key"
            mock_settings.openai_base_url = "https://proxy.example.com/v1"
            mock_settings.vectorizer_factory = None

            result = create_vectorizer()

        assert result is mock_vectorizer
        mock_openai_vectorizer.assert_called_once_with(
            model="text-embedding-3-small",
            cache=mock_cache,
            api_config={
                "api_key": "test-key",
                "base_url": "https://proxy.example.com/v1",
            },
        )

    def test_create_vectorizer_local_defaults(self):
        """Default factory should create a HuggingFace RedisVL vectorizer."""
        mock_cache = Mock()
        mock_vectorizer = Mock(aembed=Mock(), aembed_many=Mock())

        with (
            patch("redis_sre_agent.core.vectorizer_helpers.settings") as mock_settings,
            patch(
                "redis_sre_agent.core.vectorizer_helpers.EmbeddingsCache", return_value=mock_cache
            ),
            patch(
                "redis_sre_agent.core.vectorizer_helpers.HFTextVectorizer",
                return_value=mock_vectorizer,
            ) as mock_hf_vectorizer,
        ):
            mock_settings.redis_url.get_secret_value.return_value = "redis://localhost:6379/0"
            mock_settings.embeddings_cache_ttl = 120
            mock_settings.embedding_provider = "local"
            mock_settings.embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
            mock_settings.vectorizer_factory = None

            result = create_vectorizer()

        assert result is mock_vectorizer
        mock_hf_vectorizer.assert_called_once_with(
            model="sentence-transformers/all-MiniLM-L6-v2",
            cache=mock_cache,
        )

    def test_custom_factory_receives_provider_model_config_and_cache(self):
        """Programmatic factory should receive the effective vectorizer inputs."""
        mock_cache = Mock()
        mock_vectorizer = Mock(aembed=Mock(), aembed_many=Mock())
        mock_factory = MagicMock(return_value=mock_vectorizer)
        set_vectorizer_factory(mock_factory)

        with (
            patch("redis_sre_agent.core.vectorizer_helpers.settings") as mock_settings,
            patch(
                "redis_sre_agent.core.vectorizer_helpers.EmbeddingsCache", return_value=mock_cache
            ),
        ):
            mock_settings.redis_url.get_secret_value.return_value = "redis://localhost:6379/0"
            mock_settings.embeddings_cache_ttl = 300
            mock_settings.embedding_provider = "openai"
            mock_settings.embedding_model = "text-embedding-3-large"
            mock_settings.vectorizer_factory = None

            result = create_vectorizer()

        assert result is mock_vectorizer
        mock_factory.assert_called_once()
        kwargs = mock_factory.call_args.kwargs
        assert kwargs["provider"] == "openai"
        assert kwargs["model"] == "text-embedding-3-large"
        assert kwargs["config"] is not None
        assert kwargs["cache"] is mock_cache

    def test_load_factory_from_config_success(self):
        """Configured factory path should be imported and used."""
        mock_cache = Mock()
        mock_vectorizer = Mock(aembed=Mock(), aembed_many=Mock())
        module = MagicMock()
        module.custom_factory = MagicMock(return_value=mock_vectorizer)

        with (
            patch("redis_sre_agent.core.vectorizer_helpers.settings") as mock_settings,
            patch(
                "redis_sre_agent.core.vectorizer_helpers.importlib.import_module",
                return_value=module,
            ),
            patch(
                "redis_sre_agent.core.vectorizer_helpers.EmbeddingsCache", return_value=mock_cache
            ),
        ):
            mock_settings.redis_url.get_secret_value.return_value = "redis://localhost:6379/0"
            mock_settings.embeddings_cache_ttl = 30
            mock_settings.embedding_provider = "openai"
            mock_settings.embedding_model = "text-embedding-3-small"
            mock_settings.vectorizer_factory = "my.factories.custom_factory"

            result = create_vectorizer()

        assert result is mock_vectorizer
        module.custom_factory.assert_called_once()
        kwargs = module.custom_factory.call_args.kwargs
        assert kwargs["provider"] == "openai"
        assert kwargs["model"] == "text-embedding-3-small"
        assert kwargs["cache"] is not None

    def test_explicit_config_uses_its_own_factory_path(self):
        """Explicit config injection should resolve the factory from that config object."""
        mock_cache = Mock()
        mock_vectorizer = Mock(aembed=Mock(), aembed_many=Mock())
        module = MagicMock()
        module.custom_factory = MagicMock(return_value=mock_vectorizer)
        config = MagicMock()
        config.redis_url.get_secret_value.return_value = "redis://localhost:6379/0"
        config.embeddings_cache_ttl = 45
        config.embedding_provider = "local"
        config.embedding_model = "sentence-transformers/all-mpnet-base-v2"
        config.vectorizer_factory = "my.factories.custom_factory"

        with (
            patch(
                "redis_sre_agent.core.vectorizer_helpers.importlib.import_module",
                return_value=module,
            ),
            patch(
                "redis_sre_agent.core.vectorizer_helpers.EmbeddingsCache", return_value=mock_cache
            ),
        ):
            result = create_vectorizer(config=config)

        assert result is mock_vectorizer
        module.custom_factory.assert_called_once()
        kwargs = module.custom_factory.call_args.kwargs
        assert kwargs["provider"] == "local"
        assert kwargs["model"] == "sentence-transformers/all-mpnet-base-v2"
        assert kwargs["config"] is config

    def test_explicit_config_factory_wins_after_global_factory_was_loaded(self):
        """Explicit config factory paths should win even after global settings were initialized."""
        mock_cache = Mock()
        settings_vectorizer = Mock(aembed=Mock(), aembed_many=Mock())
        explicit_vectorizer = Mock(aembed=Mock(), aembed_many=Mock())
        settings_factory = MagicMock(return_value=settings_vectorizer)
        explicit_factory = MagicMock(return_value=explicit_vectorizer)
        config = MagicMock()
        config.redis_url.get_secret_value.return_value = "redis://localhost:6379/0"
        config.embeddings_cache_ttl = 45
        config.embedding_provider = "local"
        config.embedding_model = "sentence-transformers/all-mpnet-base-v2"
        config.vectorizer_factory = "custom.explicit_factory"

        def resolve_factory_side_effect(factory_path):
            if factory_path == "global.settings_factory":
                return settings_factory
            if factory_path == "custom.explicit_factory":
                return explicit_factory
            raise AssertionError(f"Unexpected factory path: {factory_path}")

        with (
            patch("redis_sre_agent.core.vectorizer_helpers.settings") as mock_settings,
            patch(
                "redis_sre_agent.core.vectorizer_helpers._resolve_factory_from_path",
                side_effect=resolve_factory_side_effect,
            ),
            patch(
                "redis_sre_agent.core.vectorizer_helpers.EmbeddingsCache", return_value=mock_cache
            ),
        ):
            mock_settings.redis_url.get_secret_value.return_value = "redis://localhost:6379/0"
            mock_settings.embeddings_cache_ttl = 30
            mock_settings.embedding_provider = "openai"
            mock_settings.embedding_model = "text-embedding-3-small"
            mock_settings.vectorizer_factory = "global.settings_factory"

            assert create_vectorizer() is settings_vectorizer
            assert create_vectorizer(config=config) is explicit_vectorizer

        settings_factory.assert_called_once()
        explicit_factory.assert_called_once()

    def test_invalid_factory_path_raises(self):
        """Invalid dot-paths should fail with a clear error."""
        with patch("redis_sre_agent.core.vectorizer_helpers.settings") as mock_settings:
            mock_settings.vectorizer_factory = "invalid_path_without_dot"

            try:
                create_vectorizer()
            except ValueError as exc:
                assert "Invalid VECTORIZER_FACTORY path" in str(exc)
            else:
                raise AssertionError("Expected ValueError for invalid VECTORIZER_FACTORY path")

    def test_non_callable_factory_raises(self):
        """Resolved targets must be callable."""
        module = MagicMock()
        module.not_callable = object()

        with (
            patch("redis_sre_agent.core.vectorizer_helpers.settings") as mock_settings,
            patch(
                "redis_sre_agent.core.vectorizer_helpers.importlib.import_module",
                return_value=module,
            ),
        ):
            mock_settings.vectorizer_factory = "my.factories.not_callable"

            try:
                create_vectorizer()
            except ValueError as exc:
                assert "VECTORIZER_FACTORY 'my.factories.not_callable' is not callable" in str(exc)
            else:
                raise AssertionError(
                    "Expected ValueError for non-callable VECTORIZER_FACTORY target"
                )

    def test_factory_result_must_support_runtime_async_methods(self):
        """Returned objects should fail fast when missing the runtime async API."""
        mock_factory = MagicMock(return_value=object())
        set_vectorizer_factory(mock_factory)

        with patch("redis_sre_agent.core.vectorizer_helpers.settings") as mock_settings:
            mock_settings.redis_url.get_secret_value.return_value = "redis://localhost:6379/0"
            mock_settings.embeddings_cache_ttl = 60
            mock_settings.embedding_provider = "openai"
            mock_settings.embedding_model = "text-embedding-3-small"
            mock_settings.vectorizer_factory = None

            try:
                create_vectorizer()
            except TypeError as exc:
                assert "aembed" in str(exc)
                assert "aembed_many" in str(exc)
            else:
                raise AssertionError("Expected TypeError for invalid vectorizer interface")
