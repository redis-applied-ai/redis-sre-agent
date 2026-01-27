"""Unit tests for LLM helper functions."""

from unittest.mock import MagicMock, patch

from langchain_core.language_models.chat_models import BaseChatModel

from redis_sre_agent.core.llm_helpers import (
    create_llm,
    create_mini_llm,
    create_nano_llm,
    get_llm_factory,
    set_llm_factory,
)


class TestLLMHelpers:
    """Test LLM helper functions."""

    def test_create_llm_default_settings(self):
        """Test create_llm with default settings."""
        with patch("redis_sre_agent.core.llm_helpers.settings") as mock_settings:
            mock_settings.openai_model = "gpt-5"
            mock_settings.openai_api_key = "test-key"
            mock_settings.llm_timeout = 180.0
            mock_settings.openai_base_url = None

            llm = create_llm()

            assert llm.model_name == "gpt-5"
            assert llm.openai_api_key.get_secret_value() == "test-key"
            assert llm.request_timeout == 180.0
            # base_url should not be set when openai_base_url is None
            assert llm.openai_api_base is None

    def test_create_llm_with_base_url(self):
        """Test create_llm with configured base URL."""
        with patch("redis_sre_agent.core.llm_helpers.settings") as mock_settings:
            mock_settings.openai_model = "gpt-5"
            mock_settings.openai_api_key = "test-key"
            mock_settings.llm_timeout = 180.0
            mock_settings.openai_base_url = "https://custom-api.example.com/v1"

            llm = create_llm()

            assert llm.model_name == "gpt-5"
            assert llm.openai_api_key.get_secret_value() == "test-key"
            assert llm.request_timeout == 180.0
            assert llm.openai_api_base == "https://custom-api.example.com/v1"

    def test_create_llm_with_overrides(self):
        """Test create_llm with parameter overrides."""
        with patch("redis_sre_agent.core.llm_helpers.settings") as mock_settings:
            mock_settings.openai_model = "gpt-5"
            mock_settings.openai_api_key = "test-key"
            mock_settings.llm_timeout = 180.0
            mock_settings.openai_base_url = None

            llm = create_llm(
                model="custom-model",
                api_key="custom-key",
                timeout=60.0,
            )

            assert llm.model_name == "custom-model"
            assert llm.openai_api_key.get_secret_value() == "custom-key"
            assert llm.request_timeout == 60.0

    def test_create_mini_llm_default_settings(self):
        """Test create_mini_llm with default settings."""
        with patch("redis_sre_agent.core.llm_helpers.settings") as mock_settings:
            mock_settings.openai_model_mini = "gpt-5-mini"
            mock_settings.openai_api_key = "test-key"
            mock_settings.llm_timeout = 180.0
            mock_settings.openai_base_url = None

            llm = create_mini_llm()

            assert llm.model_name == "gpt-5-mini"
            assert llm.openai_api_key.get_secret_value() == "test-key"
            assert llm.request_timeout == 180.0
            assert llm.openai_api_base is None

    def test_create_mini_llm_with_base_url(self):
        """Test create_mini_llm with configured base URL."""
        with patch("redis_sre_agent.core.llm_helpers.settings") as mock_settings:
            mock_settings.openai_model_mini = "gpt-5-mini"
            mock_settings.openai_api_key = "test-key"
            mock_settings.llm_timeout = 180.0
            mock_settings.openai_base_url = "https://proxy.example.com/v1"

            llm = create_mini_llm()

            assert llm.model_name == "gpt-5-mini"
            assert llm.openai_api_base == "https://proxy.example.com/v1"

    def test_create_nano_llm_default_settings(self):
        """Test create_nano_llm with default settings."""
        with patch("redis_sre_agent.core.llm_helpers.settings") as mock_settings:
            mock_settings.openai_model_nano = "gpt-5-nano"
            mock_settings.openai_api_key = "test-key"
            mock_settings.llm_timeout = 180.0
            mock_settings.openai_base_url = None

            llm = create_nano_llm()

            assert llm.model_name == "gpt-5-nano"
            assert llm.openai_api_key.get_secret_value() == "test-key"
            assert llm.request_timeout == 180.0
            assert llm.openai_api_base is None

    def test_create_nano_llm_with_base_url(self):
        """Test create_nano_llm with configured base URL."""
        with patch("redis_sre_agent.core.llm_helpers.settings") as mock_settings:
            mock_settings.openai_model_nano = "gpt-5-nano"
            mock_settings.openai_api_key = "test-key"
            mock_settings.llm_timeout = 180.0
            mock_settings.openai_base_url = "https://llm-proxy.example.com/v1"

            llm = create_nano_llm()

            assert llm.model_name == "gpt-5-nano"
            assert llm.openai_api_base == "https://llm-proxy.example.com/v1"

    def test_create_nano_llm_with_custom_timeout(self):
        """Test create_nano_llm with custom timeout (used in router.py)."""
        with patch("redis_sre_agent.core.llm_helpers.settings") as mock_settings:
            mock_settings.openai_model_nano = "gpt-5-nano"
            mock_settings.openai_api_key = "test-key"
            mock_settings.llm_timeout = 180.0
            mock_settings.openai_base_url = None

            llm = create_nano_llm(timeout=10.0)

            assert llm.model_name == "gpt-5-nano"
            assert llm.request_timeout == 10.0


class TestLLMFactory:
    """Test custom LLM factory functionality."""

    def teardown_method(self):
        """Reset factory after each test."""
        set_llm_factory(None)

    def test_get_llm_factory_returns_none_by_default(self):
        """Test that no factory is registered by default."""
        set_llm_factory(None)  # Ensure clean state
        assert get_llm_factory() is None

    def test_set_llm_factory_registers_factory(self):
        """Test that set_llm_factory registers a custom factory."""
        mock_factory = MagicMock()
        set_llm_factory(mock_factory)
        assert get_llm_factory() is mock_factory

    def test_set_llm_factory_none_clears_factory(self):
        """Test that set_llm_factory(None) clears the factory."""
        mock_factory = MagicMock()
        set_llm_factory(mock_factory)
        set_llm_factory(None)
        assert get_llm_factory() is None

    def test_custom_factory_called_for_create_llm(self):
        """Test that custom factory is called when creating main LLM."""
        mock_llm = MagicMock(spec=BaseChatModel)
        mock_factory = MagicMock(return_value=mock_llm)
        set_llm_factory(mock_factory)

        result = create_llm(model="custom-model", timeout=30.0)

        assert result is mock_llm
        mock_factory.assert_called_once()
        call_kwargs = mock_factory.call_args
        assert call_kwargs.kwargs["tier"] == "main"
        assert call_kwargs.kwargs["model"] == "custom-model"
        assert call_kwargs.kwargs["timeout"] == 30.0

    def test_custom_factory_called_for_create_mini_llm(self):
        """Test that custom factory is called when creating mini LLM."""
        mock_llm = MagicMock(spec=BaseChatModel)
        mock_factory = MagicMock(return_value=mock_llm)
        set_llm_factory(mock_factory)

        result = create_mini_llm(model="mini-model")

        assert result is mock_llm
        mock_factory.assert_called_once()
        call_kwargs = mock_factory.call_args
        assert call_kwargs.kwargs["tier"] == "mini"
        assert call_kwargs.kwargs["model"] == "mini-model"

    def test_custom_factory_called_for_create_nano_llm(self):
        """Test that custom factory is called when creating nano LLM."""
        mock_llm = MagicMock(spec=BaseChatModel)
        mock_factory = MagicMock(return_value=mock_llm)
        set_llm_factory(mock_factory)

        result = create_nano_llm(timeout=5.0)

        assert result is mock_llm
        mock_factory.assert_called_once()
        call_kwargs = mock_factory.call_args
        assert call_kwargs.kwargs["tier"] == "nano"
        assert call_kwargs.kwargs["timeout"] == 5.0

    def test_custom_factory_receives_api_key(self):
        """Test that api_key is passed through to custom factory."""
        mock_llm = MagicMock(spec=BaseChatModel)
        mock_factory = MagicMock(return_value=mock_llm)
        set_llm_factory(mock_factory)

        create_llm(api_key="custom-api-key")

        call_kwargs = mock_factory.call_args
        assert call_kwargs.kwargs.get("api_key") == "custom-api-key"

    def test_default_factory_used_when_none_registered(self):
        """Test that default ChatOpenAI factory is used when no custom factory."""
        set_llm_factory(None)

        with patch("redis_sre_agent.core.llm_helpers.settings") as mock_settings:
            mock_settings.openai_model = "gpt-5"
            mock_settings.openai_api_key = "test-key"
            mock_settings.llm_timeout = 180.0
            mock_settings.openai_base_url = None

            llm = create_llm()

            # Should create a ChatOpenAI instance
            assert llm.model_name == "gpt-5"
