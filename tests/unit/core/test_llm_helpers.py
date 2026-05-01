"""Unit tests for LLM helper functions."""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel

import redis_sre_agent.core.llm_helpers as llm_helpers
from redis_sre_agent.core.llm_helpers import (
    create_async_openai_client,
    create_llm,
    create_mini_async_openai_client,
    create_mini_llm,
    create_nano_async_openai_client,
    create_nano_llm,
    get_async_openai_client_factory,
    get_llm_factory,
    set_async_openai_client_factory,
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

    def test_create_llm_falls_back_to_live_env_when_settings_are_empty(self):
        """Resident workers should honor live env even if settings were cached empty."""
        with (
            patch("redis_sre_agent.core.llm_helpers.settings") as mock_settings,
            patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "env-key",
                    "OPENAI_BASE_URL": "https://env-proxy.example.com/v1",
                    "OPENAI_MODEL": "env-model",
                },
                clear=False,
            ),
        ):
            mock_settings.openai_model = ""
            mock_settings.openai_api_key = None
            mock_settings.llm_timeout = 180.0
            mock_settings.openai_base_url = None

            llm = create_llm()

            assert llm.model_name == "env-model"
            assert llm.openai_api_key.get_secret_value() == "env-key"
            assert llm.openai_api_base == "https://env-proxy.example.com/v1"

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


class TestAsyncOpenAIClientHelpers:
    """Test AsyncOpenAI client helper functions."""

    def teardown_method(self):
        """Reset async client factory after each test."""
        llm_helpers._async_openai_client_factory = None
        llm_helpers._async_openai_factory_initialized = False

    def test_create_async_openai_client_default_settings(self):
        """Test default async client creation with settings."""
        with (
            patch("redis_sre_agent.core.llm_helpers.settings") as mock_settings,
            patch("redis_sre_agent.core.llm_helpers.AsyncOpenAI") as mock_async_openai,
        ):
            mock_settings.openai_api_key = "test-key"
            mock_settings.llm_timeout = 180.0
            mock_settings.openai_base_url = None

            create_async_openai_client()

            mock_async_openai.assert_called_once_with(api_key="test-key", timeout=180.0)

    def test_create_async_openai_client_with_base_url(self):
        """Test default async client includes base_url when configured."""
        with (
            patch("redis_sre_agent.core.llm_helpers.settings") as mock_settings,
            patch("redis_sre_agent.core.llm_helpers.AsyncOpenAI") as mock_async_openai,
        ):
            mock_settings.openai_api_key = "test-key"
            mock_settings.llm_timeout = 180.0
            mock_settings.openai_base_url = "https://proxy.example.com/v1"

            create_async_openai_client()

            mock_async_openai.assert_called_once_with(
                api_key="test-key",
                timeout=180.0,
                base_url="https://proxy.example.com/v1",
            )

    def test_create_async_openai_client_with_overrides(self):
        """Test async client creation supports explicit overrides."""
        with (
            patch("redis_sre_agent.core.llm_helpers.settings") as mock_settings,
            patch("redis_sre_agent.core.llm_helpers.AsyncOpenAI") as mock_async_openai,
        ):
            mock_settings.openai_api_key = "default-key"
            mock_settings.llm_timeout = 180.0
            mock_settings.openai_base_url = None

            create_async_openai_client(api_key="custom-key", timeout=30.0, max_retries=2)

            mock_async_openai.assert_called_once_with(
                api_key="custom-key",
                timeout=30.0,
                max_retries=2,
            )

    def test_create_async_openai_client_falls_back_to_live_env_when_settings_are_empty(self):
        """Async client creation should honor live env in resident workers."""
        with (
            patch("redis_sre_agent.core.llm_helpers.settings") as mock_settings,
            patch("redis_sre_agent.core.llm_helpers.AsyncOpenAI") as mock_async_openai,
            patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "env-key",
                    "OPENAI_BASE_URL": "https://env-proxy.example.com/v1",
                },
                clear=False,
            ),
        ):
            mock_settings.openai_api_key = None
            mock_settings.llm_timeout = 180.0
            mock_settings.openai_base_url = None

            create_async_openai_client()

            mock_async_openai.assert_called_once_with(
                api_key="env-key",
                timeout=180.0,
                base_url="https://env-proxy.example.com/v1",
            )

    def test_get_async_openai_client_factory_returns_none_by_default(self):
        """Test async factory getter returns None by default."""
        set_async_openai_client_factory(None)
        assert get_async_openai_client_factory() is None

    def test_set_async_openai_client_factory_registers_factory(self):
        """Test async factory registration and retrieval."""
        mock_factory = MagicMock()
        set_async_openai_client_factory(mock_factory)
        assert get_async_openai_client_factory() is mock_factory

    def test_custom_async_factory_called_for_mini_and_nano(self):
        """Test custom async factory receives tier and args."""
        mock_client = MagicMock()
        mock_factory = MagicMock(return_value=mock_client)
        set_async_openai_client_factory(mock_factory)

        mini = create_mini_async_openai_client(model="gpt-mini", timeout=12.0)
        nano = create_nano_async_openai_client(api_key="nano-key")

        assert mini is mock_client
        assert nano is mock_client
        assert mock_factory.call_count == 2
        first_call = mock_factory.call_args_list[0].kwargs
        second_call = mock_factory.call_args_list[1].kwargs
        assert first_call["tier"] == "mini"
        assert first_call["model"] == "gpt-mini"
        assert first_call["timeout"] == 12.0
        assert second_call["tier"] == "nano"
        assert second_call["api_key"] == "nano-key"

    def test_load_async_openai_factory_from_config_success(self):
        """Test async factory is loaded from ASYNC_OPENAI_CLIENT_FACTORY config."""
        mock_client = MagicMock()
        module = MagicMock()
        module.custom_factory = MagicMock(return_value=mock_client)

        with (
            patch("redis_sre_agent.core.llm_helpers.settings") as mock_settings,
            patch("redis_sre_agent.core.llm_helpers.importlib.import_module", return_value=module),
        ):
            mock_settings.async_openai_client_factory = "my.factories.custom_factory"

            result = create_async_openai_client(model="m1", api_key="k1", timeout=5.0)

        assert result is mock_client
        module.custom_factory.assert_called_once()
        kwargs = module.custom_factory.call_args.kwargs
        assert kwargs["tier"] == "main"
        assert kwargs["model"] == "m1"
        assert kwargs["api_key"] == "k1"
        assert kwargs["timeout"] == 5.0

    def test_load_async_openai_factory_from_config_invalid_path_raises(self):
        """Test invalid async factory path raises ValueError."""
        with patch("redis_sre_agent.core.llm_helpers.settings") as mock_settings:
            mock_settings.async_openai_client_factory = "invalid_path_without_dot"

            with pytest.raises(ValueError, match="Invalid ASYNC_OPENAI_CLIENT_FACTORY path"):
                create_async_openai_client()

    def test_load_async_openai_factory_from_config_non_callable_raises(self):
        """Test non-callable async factory target raises ValueError."""
        module = MagicMock()
        module.not_callable = object()

        with (
            patch("redis_sre_agent.core.llm_helpers.settings") as mock_settings,
            patch("redis_sre_agent.core.llm_helpers.importlib.import_module", return_value=module),
        ):
            mock_settings.async_openai_client_factory = "my.factories.not_callable"

            with pytest.raises(
                ValueError,
                match="ASYNC_OPENAI_CLIENT_FACTORY 'my.factories.not_callable' is not callable",
            ):
                create_async_openai_client()
