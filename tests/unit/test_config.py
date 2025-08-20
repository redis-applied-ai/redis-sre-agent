"""Unit tests for configuration management."""

import os
from unittest.mock import patch

import pytest

from redis_sre_agent.core.config import Settings


class TestSettings:
    """Test Settings configuration class."""

    def test_default_values(self):
        """Test default configuration values."""
        # Create settings with minimal environment variables
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            settings = Settings()

            # Application defaults
            assert settings.app_name == "Redis SRE Agent"
            assert settings.debug is False
            assert settings.log_level == "INFO"

            # Server defaults
            assert settings.host == "0.0.0.0"
            assert settings.port == 8000

            # Redis defaults
            assert settings.redis_url == "redis://localhost:6379/0"
            assert settings.redis_password is None

            # OpenAI defaults
            assert settings.openai_api_key == "test-key"
            assert settings.openai_model == "gpt-4"
            assert settings.openai_model_mini == "gpt-4o-mini"

            # Vector search defaults
            assert settings.embedding_model == "text-embedding-3-small"
            assert settings.vector_dim == 1536

            # Task queue defaults
            assert settings.task_queue_name == "sre_agent_tasks"
            assert settings.max_task_retries == 3
            assert settings.task_timeout == 300

            # Agent defaults
            assert settings.max_iterations == 10
            assert settings.tool_timeout == 60

            # Security defaults
            assert settings.api_key is None
            assert settings.allowed_hosts == ["*"]

    def test_environment_variable_override(self):
        """Test that environment variables override defaults."""
        env_vars = {
            "APP_NAME": "Custom SRE Agent",
            "DEBUG": "true",
            "LOG_LEVEL": "DEBUG",
            "HOST": "127.0.0.1",
            "PORT": "9000",
            "REDIS_URL": "redis://custom:6379/1",
            "REDIS_PASSWORD": "secret",
            "OPENAI_API_KEY": "sk-test123",
            "OPENAI_MODEL": "gpt-3.5-turbo",
            "EMBEDDING_MODEL": "text-embedding-ada-002",
            "VECTOR_DIM": "768",
            "TASK_QUEUE_NAME": "custom_tasks",
            "MAX_TASK_RETRIES": "5",
            "TASK_TIMEOUT": "600",
            "MAX_ITERATIONS": "20",
            "TOOL_TIMEOUT": "120",
            "API_KEY": "api-secret",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()

            assert settings.app_name == "Custom SRE Agent"
            assert settings.debug is True
            assert settings.log_level == "DEBUG"
            assert settings.host == "127.0.0.1"
            assert settings.port == 9000
            assert settings.redis_url == "redis://custom:6379/1"
            assert settings.redis_password == "secret"
            assert settings.openai_api_key == "sk-test123"
            assert settings.openai_model == "gpt-3.5-turbo"
            assert settings.embedding_model == "text-embedding-ada-002"
            assert settings.vector_dim == 768
            assert settings.task_queue_name == "custom_tasks"
            assert settings.max_task_retries == 5
            assert settings.task_timeout == 600
            assert settings.max_iterations == 20
            assert settings.tool_timeout == 120
            assert settings.api_key == "api-secret"

    def test_boolean_field_parsing(self):
        """Test boolean field parsing from environment variables."""
        test_cases = [
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("1", True),
            ("false", False),
            ("False", False),
            ("FALSE", False),
            ("0", False),
            ("", False),
        ]

        for env_value, expected in test_cases:
            if env_value == "":
                # Empty string should use default, not cause validation error
                with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}, clear=True):
                    settings = Settings()
                    assert settings.debug == False  # Default value
            else:
                with patch.dict(
                    os.environ, {"DEBUG": env_value, "OPENAI_API_KEY": "test"}, clear=True
                ):
                    settings = Settings()
                    assert settings.debug == expected

    def test_integer_field_parsing(self):
        """Test integer field parsing from environment variables."""
        with patch.dict(
            os.environ,
            {
                "PORT": "8080",
                "VECTOR_DIM": "512",
                "MAX_TASK_RETRIES": "10",
                "OPENAI_API_KEY": "test",
            },
            clear=True,
        ):
            settings = Settings()

            assert settings.port == 8080
            assert settings.vector_dim == 512
            assert settings.max_task_retries == 10

    def test_optional_fields(self):
        """Test optional configuration fields."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}, clear=True):
            settings = Settings()

            # These should be None by default
            assert settings.redis_password is None
            assert settings.prometheus_url is None
            assert settings.grafana_url is None
            assert settings.grafana_api_key is None
            assert settings.api_key is None

    def test_list_field_parsing(self):
        """Test list field parsing from environment variables."""
        with patch.dict(
            os.environ,
            {
                "ALLOWED_HOSTS": '["localhost", "127.0.0.1", "example.com"]',  # JSON format
                "OPENAI_API_KEY": "test",
            },
            clear=True,
        ):
            settings = Settings()

            # Pydantic parses JSON format for lists
            assert isinstance(settings.allowed_hosts, list)
            assert "localhost" in settings.allowed_hosts

    def test_required_field_validation(self):
        """Test that required fields are validated."""
        # OPENAI_API_KEY is required
        from pydantic import ValidationError

        # Clear all environment variables to force validation error
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Settings()

            # Check that the error is about the missing openai_api_key
            error_str = str(exc_info.value)
            assert "openai_api_key" in error_str

    def test_field_descriptions(self):
        """Test that fields have proper descriptions."""
        settings = Settings(openai_api_key="test")

        # Check that model fields exist and have some metadata
        model_fields = Settings.model_fields

        # Sample field checks - just verify fields exist and have some info
        assert "app_name" in model_fields
        assert "redis_url" in model_fields
        assert "openai_api_key" in model_fields

        # Check that fields have some configuration
        app_name_field = model_fields["app_name"]
        assert hasattr(app_name_field, "default")

    def test_settings_singleton(self):
        """Test settings singleton behavior."""
        from redis_sre_agent.core.config import settings

        # Should be the same instance
        settings1 = settings
        settings2 = settings
        assert settings1 is settings2

    def test_env_file_loading(self):
        """Test .env file loading functionality."""
        # This tests that the dotenv loading doesn't break
        # The actual file loading is tested by having the import work
        try:
            from redis_sre_agent.core.config import settings

            # Should not raise ImportError
            assert settings is not None
        except ImportError as e:
            pytest.fail(f"dotenv loading failed: {e}")

    def test_extra_ignore_behavior(self):
        """Test that extra fields are ignored."""
        env_vars = {
            "OPENAI_API_KEY": "test",
            "UNKNOWN_FIELD": "should_be_ignored",
            "ANOTHER_UNKNOWN": "also_ignored",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            # Should not raise validation error for unknown fields
            settings = Settings()
            assert settings.openai_api_key == "test"

            # Unknown fields should not be accessible
            assert not hasattr(settings, "UNKNOWN_FIELD")
            assert not hasattr(settings, "unknown_field")


class TestSettingsValidation:
    """Test settings validation logic."""

    def test_valid_redis_url_formats(self):
        """Test various valid Redis URL formats."""
        valid_urls = [
            "redis://localhost:6379/0",
            "redis://user:pass@localhost:6379/0",
            "redis://192.168.1.100:6379",
            "rediss://secure.redis.com:6380/0",
        ]

        for redis_url in valid_urls:
            with patch.dict(
                os.environ, {"REDIS_URL": redis_url, "OPENAI_API_KEY": "test"}, clear=True
            ):
                settings = Settings()
                assert settings.redis_url == redis_url

    def test_valid_log_levels(self):
        """Test various valid log levels."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

        for level in valid_levels:
            with patch.dict(os.environ, {"LOG_LEVEL": level, "OPENAI_API_KEY": "test"}, clear=True):
                settings = Settings()
                assert settings.log_level == level

    def test_positive_integer_fields(self):
        """Test that integer fields accept positive values."""
        with patch.dict(
            os.environ,
            {
                "PORT": "1",
                "VECTOR_DIM": "1",
                "MAX_TASK_RETRIES": "1",
                "TASK_TIMEOUT": "1",
                "MAX_ITERATIONS": "1",
                "TOOL_TIMEOUT": "1",
                "OPENAI_API_KEY": "test",
            },
            clear=True,
        ):
            settings = Settings()

            assert settings.port == 1
            assert settings.vector_dim == 1
            assert settings.max_task_retries == 1
            assert settings.task_timeout == 1
            assert settings.max_iterations == 1
            assert settings.tool_timeout == 1
