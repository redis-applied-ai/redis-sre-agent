"""Unit tests for LLM helper functions."""

import pytest
from unittest.mock import patch

from redis_sre_agent.core.llm_helpers import create_llm, create_mini_llm, create_nano_llm


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
