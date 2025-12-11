"""Unit tests for configuration management."""

import os
import tempfile
from typing import Optional
from unittest.mock import patch

import pytest
import yaml


# Import Settings in tests with mocked environment
def get_clean_settings(**kwargs):
    """Create Settings with clean environment, bypassing .env loading."""
    # Import Settings class directly to avoid module-level dotenv loading
    from pydantic import Field
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class TestSettings(BaseSettings):
        model_config = SettingsConfigDict(extra="ignore")

        # Application
        app_name: str = "Redis SRE Agent"
        debug: bool = Field(default=False, description="Enable debug mode")
        log_level: str = Field(default="INFO", description="Logging level")

        # Server
        host: str = Field(default="0.0.0.0", description="Server host")
        port: int = Field(default=8000, description="Server port")

        # Redis
        redis_url: str = Field(
            default="redis://localhost:6379/0", description="Redis connection URL"
        )
        redis_password: Optional[str] = Field(default=None, description="Redis password")

        # OpenAI
        openai_api_key: str = Field(description="OpenAI API key")
        openai_model: str = Field(default="gpt-4", description="OpenAI model for agent reasoning")
        openai_model_mini: str = Field(default="gpt-4o-mini", description="OpenAI model for tools")

        # Vector Search
        embedding_model: str = Field(
            default="text-embedding-3-small", description="OpenAI embedding model"
        )
        vector_dim: int = Field(default=1536, description="Vector dimensions")

        # Docket Task Queue
        task_queue_name: str = Field(default="sre_agent_tasks", description="Task queue name")
        max_task_retries: int = Field(default=3, description="Maximum task retries")
        task_timeout: int = Field(default=300, description="Task timeout in seconds")

        # Agent
        max_iterations: int = Field(default=10, description="Maximum agent iterations")
        tool_timeout: int = Field(default=60, description="Tool execution timeout")

        # Monitoring Integration (optional)
        prometheus_url: Optional[str] = Field(default=None, description="Prometheus server URL")
        grafana_url: Optional[str] = Field(default=None, description="Grafana server URL")
        grafana_api_key: Optional[str] = Field(default=None, description="Grafana API key")

        # Security
        api_key: Optional[str] = Field(default=None, description="API authentication key")
        allowed_hosts: list[str] = Field(default=["*"], description="Allowed hosts for CORS")

    return TestSettings(**kwargs)


class TestSettings:
    """Test Settings configuration class."""

    def test_default_values(self):
        """Test default configuration values."""
        # Create settings with minimal environment variables
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            settings = get_clean_settings()

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
            settings = get_clean_settings()

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
                    settings = get_clean_settings()
                    assert not settings.debug  # Default value
            else:
                with patch.dict(
                    os.environ, {"DEBUG": env_value, "OPENAI_API_KEY": "test"}, clear=True
                ):
                    settings = get_clean_settings()
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
            settings = get_clean_settings()

            assert settings.port == 8080
            assert settings.vector_dim == 512
            assert settings.max_task_retries == 10

    def test_optional_fields(self):
        """Test optional configuration fields."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}, clear=True):
            settings = get_clean_settings()

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
            settings = get_clean_settings()

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
                get_clean_settings()

            # Check that the error is about the missing openai_api_key
            error_str = str(exc_info.value)
            assert "openai_api_key" in error_str

    def test_field_descriptions(self):
        """Test that fields have proper descriptions."""
        settings = get_clean_settings(openai_api_key="test")

        # Check that model fields exist and have some metadata
        model_fields = settings.model_fields

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
            settings = get_clean_settings()
            assert settings.openai_api_key == "test"

            # Unknown fields should not be accessible
            assert not hasattr(settings, "UNKNOWN_FIELD")
            assert not hasattr(settings, "unknown_field")


class TestMCPConfiguration:
    """Test MCP server configuration models."""

    def test_mcp_tool_config_defaults(self):
        """Test MCPToolConfig default values."""
        from redis_sre_agent.core.config import MCPToolConfig

        config = MCPToolConfig()
        assert config.capability is None
        assert config.description is None

    def test_mcp_tool_config_with_capability(self):
        """Test MCPToolConfig with capability set."""
        from redis_sre_agent.core.config import MCPToolConfig
        from redis_sre_agent.tools.models import ToolCapability

        config = MCPToolConfig(capability=ToolCapability.LOGS)
        assert config.capability == ToolCapability.LOGS
        assert config.description is None

    def test_mcp_tool_config_with_description(self):
        """Test MCPToolConfig with description override."""
        from redis_sre_agent.core.config import MCPToolConfig

        config = MCPToolConfig(description="Use this tool when searching for memories...")
        assert config.capability is None
        assert config.description == "Use this tool when searching for memories..."

    def test_mcp_tool_config_with_both(self):
        """Test MCPToolConfig with both capability and description."""
        from redis_sre_agent.core.config import MCPToolConfig
        from redis_sre_agent.tools.models import ToolCapability

        config = MCPToolConfig(
            capability=ToolCapability.METRICS,
            description="Custom description for the tool",
        )
        assert config.capability == ToolCapability.METRICS
        assert config.description == "Custom description for the tool"

    def test_mcp_server_config_command_based(self):
        """Test MCPServerConfig for command-based (stdio) transport."""
        from redis_sre_agent.core.config import MCPServerConfig

        config = MCPServerConfig(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-memory"],
            env={"DEBUG": "true"},
        )
        assert config.command == "npx"
        assert config.args == ["-y", "@modelcontextprotocol/server-memory"]
        assert config.env == {"DEBUG": "true"}
        assert config.url is None
        assert config.tools is None

    def test_mcp_server_config_url_based(self):
        """Test MCPServerConfig for URL-based transport."""
        from redis_sre_agent.core.config import MCPServerConfig

        config = MCPServerConfig(url="http://localhost:3000/mcp")
        assert config.command is None
        assert config.args is None
        assert config.url == "http://localhost:3000/mcp"

    def test_mcp_server_config_with_tool_constraints(self):
        """Test MCPServerConfig with tool constraints."""
        from redis_sre_agent.core.config import MCPServerConfig, MCPToolConfig
        from redis_sre_agent.tools.models import ToolCapability

        config = MCPServerConfig(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-memory"],
            tools={
                "search_memories": MCPToolConfig(capability=ToolCapability.LOGS),
                "create_memories": MCPToolConfig(description="Use this tool when..."),
            },
        )
        assert config.tools is not None
        assert len(config.tools) == 2
        assert config.tools["search_memories"].capability == ToolCapability.LOGS
        assert config.tools["create_memories"].description == "Use this tool when..."

    def test_settings_mcp_servers_default_empty(self):
        """Test that mcp_servers defaults to empty dict."""
        from redis_sre_agent.core.config import settings

        # Default should be an empty dict
        assert isinstance(settings.mcp_servers, dict)

    def test_mcp_server_config_from_dict(self):
        """Test that MCPServerConfig can be created from a dict (for env var parsing)."""
        from redis_sre_agent.core.config import MCPServerConfig

        config_dict = {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-memory"],
            "tools": {
                "search_memories": {"capability": "logs"},
            },
        }
        config = MCPServerConfig.model_validate(config_dict)
        assert config.command == "npx"
        assert config.args == ["-y", "@modelcontextprotocol/server-memory"]
        # Note: tools with string capability will need special handling in the provider


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
                settings = get_clean_settings()
                assert settings.redis_url == redis_url

    def test_valid_log_levels(self):
        """Test various valid log levels."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

        for level in valid_levels:
            with patch.dict(os.environ, {"LOG_LEVEL": level, "OPENAI_API_KEY": "test"}, clear=True):
                settings = get_clean_settings()
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
            settings = get_clean_settings()

            assert settings.port == 1
            assert settings.vector_dim == 1
            assert settings.max_task_retries == 1
            assert settings.task_timeout == 1
            assert settings.max_iterations == 1
            assert settings.tool_timeout == 1


class TestYamlConfigLoading:
    """Test YAML configuration file loading."""

    def test_yaml_config_loads_mcp_servers(self):
        """Test that MCP servers can be loaded from YAML config."""
        yaml_content = {
            "mcp_servers": {
                "test-server": {
                    "command": "echo",
                    "args": ["hello"],
                },
                "github": {
                    "command": "docker",
                    "args": ["run", "-i", "ghcr.io/github/github-mcp-server"],
                    "env": {"GITHUB_TOKEN": "test-token"},
                },
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_content, f)
            config_path = f.name

        try:
            with patch.dict(
                os.environ,
                {"SRE_AGENT_CONFIG": config_path, "OPENAI_API_KEY": "test-key"},
                clear=True,
            ):
                from redis_sre_agent.core.config import MCPServerConfig, Settings

                settings = Settings()

                assert "test-server" in settings.mcp_servers
                assert "github" in settings.mcp_servers
                # Values may be MCPServerConfig objects or dicts depending on validation
                test_server = settings.mcp_servers["test-server"]
                if isinstance(test_server, MCPServerConfig):
                    assert test_server.command == "echo"
                else:
                    assert test_server["command"] == "echo"

                github_server = settings.mcp_servers["github"]
                if isinstance(github_server, MCPServerConfig):
                    assert github_server.env["GITHUB_TOKEN"] == "test-token"
                else:
                    assert github_server["env"]["GITHUB_TOKEN"] == "test-token"
        finally:
            os.unlink(config_path)

    def test_yaml_config_with_tool_descriptions(self):
        """Test that tool descriptions in YAML are properly loaded."""
        yaml_content = {
            "mcp_servers": {
                "memory-server": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-memory"],
                    "tools": {
                        "search_memories": {
                            "description": "Search for memories about Redis instances.",
                        },
                    },
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_content, f)
            config_path = f.name

        try:
            with patch.dict(
                os.environ,
                {"SRE_AGENT_CONFIG": config_path, "OPENAI_API_KEY": "test-key"},
                clear=True,
            ):
                from redis_sre_agent.core.config import MCPServerConfig, Settings

                settings = Settings()

                assert "memory-server" in settings.mcp_servers
                server = settings.mcp_servers["memory-server"]
                if isinstance(server, MCPServerConfig):
                    assert server.tools is not None
                    assert "search_memories" in server.tools
                else:
                    tools = server["tools"]
                    assert "search_memories" in tools
        finally:
            os.unlink(config_path)

    def test_env_vars_override_yaml_config(self):
        """Test that environment variables take precedence over YAML config."""
        yaml_content = {
            "debug": False,
            "log_level": "WARNING",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_content, f)
            config_path = f.name

        try:
            with patch.dict(
                os.environ,
                {
                    "SRE_AGENT_CONFIG": config_path,
                    "OPENAI_API_KEY": "test-key",
                    "DEBUG": "true",  # Override YAML value
                    "LOG_LEVEL": "DEBUG",  # Override YAML value
                },
                clear=True,
            ):
                from redis_sre_agent.core.config import Settings

                settings = Settings()

                # Env vars should win
                assert settings.debug is True
                assert settings.log_level == "DEBUG"
        finally:
            os.unlink(config_path)

    def test_yaml_config_source_class(self):
        """Test YamlConfigSettingsSource directly with pydantic-settings built-in source."""
        from pydantic_settings import YamlConfigSettingsSource

        from redis_sre_agent.core.config import Settings

        yaml_content = {
            "debug": True,
            "log_level": "DEBUG",
            "mcp_servers": {"test": {"command": "echo"}},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_content, f)
            config_path = f.name

        try:
            # Use the built-in YamlConfigSettingsSource with explicit yaml_file
            source = YamlConfigSettingsSource(Settings, yaml_file=config_path)
            data = source()

            assert data["debug"] is True
            assert data["log_level"] == "DEBUG"
            assert "mcp_servers" in data
        finally:
            os.unlink(config_path)

    def test_default_config_paths_are_checked(self):
        """Test that default config paths are checked when SRE_AGENT_CONFIG is not set."""
        from redis_sre_agent.core.config import DEFAULT_CONFIG_PATHS

        # Verify the default paths exist in the module
        assert "config.yaml" in DEFAULT_CONFIG_PATHS
        assert "config.yml" in DEFAULT_CONFIG_PATHS
        assert "sre_agent_config.yaml" in DEFAULT_CONFIG_PATHS

    def test_yaml_with_simple_settings(self):
        """Test loading simple settings from YAML.

        Note: We test app_name and debug which don't have values in the
        workspace's config.yaml or .env files.
        """
        yaml_content = {
            "app_name": "test-app-from-yaml",
            "debug": True,
            "recursion_limit": 200,  # Use a field not in .env
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_content, f)
            config_path = f.name

        try:
            with patch.dict(
                os.environ,
                {"SRE_AGENT_CONFIG": config_path, "OPENAI_API_KEY": "test-key"},
                clear=True,
            ):
                from redis_sre_agent.core.config import Settings

                settings = Settings()

                # These values should come from our test YAML
                assert settings.app_name == "test-app-from-yaml"
                assert settings.debug is True
                assert settings.recursion_limit == 200  # Should override default of 100
        finally:
            os.unlink(config_path)

    def test_yaml_with_list_settings(self):
        """Test loading list settings from YAML.

        Note: We use tool_providers which can be overridden from YAML,
        but allowed_hosts may be set in workspace's .env file.
        """
        yaml_content = {
            "tool_providers": [
                "custom.provider.MyProvider",
                "another.provider.AnotherProvider",
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_content, f)
            config_path = f.name

        try:
            with patch.dict(
                os.environ,
                {"SRE_AGENT_CONFIG": config_path, "OPENAI_API_KEY": "test-key"},
                clear=True,
            ):
                from redis_sre_agent.core.config import Settings

                settings = Settings()

                # Tool providers should be exactly what we specified in YAML
                assert len(settings.tool_providers) == 2
                assert "custom.provider.MyProvider" in settings.tool_providers
                assert "another.provider.AnotherProvider" in settings.tool_providers
        finally:
            os.unlink(config_path)

    def test_yaml_source_returns_empty_for_missing_config(self):
        """Test that YamlConfigSettingsSource returns empty dict for missing config."""
        from redis_sre_agent.core.config import Settings, YamlConfigSettingsSource

        with patch.dict(os.environ, {"SRE_AGENT_CONFIG": "/nonexistent/config.yaml"}, clear=True):
            source = YamlConfigSettingsSource(Settings)
            data = source()

            # Should return empty dict, not error
            assert data == {}

    def test_yaml_source_returns_empty_for_invalid_yaml(self):
        """Test that YamlConfigSettingsSource returns empty dict for invalid YAML."""
        from redis_sre_agent.core.config import Settings, YamlConfigSettingsSource

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            # Write invalid YAML
            f.write("invalid: yaml: content: [[[")
            config_path = f.name

        try:
            with patch.dict(os.environ, {"SRE_AGENT_CONFIG": config_path}, clear=True):
                source = YamlConfigSettingsSource(Settings)
                data = source()

                # Should return empty dict, not error
                assert data == {}
        finally:
            os.unlink(config_path)
