"""Unit tests for the retrieval optimizer MCP integration module."""

import pytest

from redis_sre_agent.tools.mcp.retrieval_optimizer import (
    DEFAULT_RETRIEVAL_OPTIMIZER_CONFIG,
    get_retrieval_optimizer_config,
)


class TestGetRetrievalOptimizerConfig:
    """Test get_retrieval_optimizer_config function."""

    def test_returns_valid_config_structure(self):
        """Test that the function returns a valid configuration dictionary."""
        config = get_retrieval_optimizer_config()

        # Check required keys exist
        assert "command" in config
        assert "args" in config
        assert "env" in config
        assert "tools" in config

        # Check types
        assert isinstance(config["command"], str)
        assert isinstance(config["args"], list)
        assert isinstance(config["env"], dict)
        assert isinstance(config["tools"], dict)

    def test_default_command_is_uv(self):
        """Test that the default command is 'uv'."""
        config = get_retrieval_optimizer_config()
        assert config["command"] == "uv"

    def test_default_args_without_directory(self):
        """Test that default args are correct without directory."""
        config = get_retrieval_optimizer_config()

        expected_args = ["run", "redis-retrieval-optimizer-mcp"]
        assert config["args"] == expected_args

    def test_args_with_retrieval_optimizer_dir(self):
        """Test that passing retrieval_optimizer_dir adds --directory flag."""
        test_dir = "/path/to/retrieval-optimizer"
        config = get_retrieval_optimizer_config(retrieval_optimizer_dir=test_dir)

        expected_args = ["run", "--directory", test_dir, "redis-retrieval-optimizer-mcp"]
        assert config["args"] == expected_args

    def test_default_redis_url_env_variable(self):
        """Test that the default REDIS_URL uses environment variable expansion."""
        config = get_retrieval_optimizer_config()
        assert config["env"]["REDIS_URL"] == "${REDIS_URL}"

    def test_custom_redis_url(self):
        """Test that a custom redis_url can be provided."""
        custom_url = "redis://custom-host:6380"
        config = get_retrieval_optimizer_config(redis_url=custom_url)
        assert config["env"]["REDIS_URL"] == custom_url

    def test_include_all_tools_false_includes_tools(self):
        """Test that include_all_tools=False (default) includes tool definitions."""
        config = get_retrieval_optimizer_config(include_all_tools=False)

        assert "tools" in config
        assert len(config["tools"]) > 0

    def test_include_all_tools_true_excludes_tools_key(self):
        """Test that include_all_tools=True excludes the tools key from config."""
        config = get_retrieval_optimizer_config(include_all_tools=True)

        # When include_all_tools=True, no tools filter is applied
        assert "tools" not in config

    def test_default_tools_include_expected_tools(self):
        """Test that default tools include all expected tool names."""
        config = get_retrieval_optimizer_config()

        expected_tools = [
            "run_grid_study_tool",
            "run_bayes_study_tool",
            "run_search_study_tool",
            "optimize_cache_threshold",
            "optimize_router_threshold",
            "get_index_info",
            "evaluate_search_results",
            "estimate_memory_usage",
        ]

        for tool_name in expected_tools:
            assert tool_name in config["tools"], f"Missing tool: {tool_name}"

    def test_tool_descriptions_contain_original_placeholder(self):
        """Test that tool descriptions use {original} placeholder."""
        config = get_retrieval_optimizer_config()

        for tool_name, tool_config in config["tools"].items():
            description = tool_config.get("description", "")
            assert "{original}" in description, (
                f"Tool '{tool_name}' description should contain {{original}} placeholder"
            )

    def test_tool_descriptions_provide_sre_context(self):
        """Test that tool descriptions provide SRE-focused context."""
        config = get_retrieval_optimizer_config()

        # Check that descriptions are non-trivial (provide context beyond just {original})
        for tool_name, tool_config in config["tools"].items():
            description = tool_config.get("description", "")
            # Remove the {original} part and check there's still meaningful content
            context_part = description.replace("{original}", "").strip()
            assert len(context_part) > 20, (
                f"Tool '{tool_name}' should have meaningful SRE context in description"
            )


class TestDefaultRetrievalOptimizerConfig:
    """Test the DEFAULT_RETRIEVAL_OPTIMIZER_CONFIG constant."""

    def test_default_config_is_valid(self):
        """Test that DEFAULT_RETRIEVAL_OPTIMIZER_CONFIG is a valid config."""
        config = DEFAULT_RETRIEVAL_OPTIMIZER_CONFIG

        assert "command" in config
        assert "args" in config
        assert "env" in config
        assert "tools" in config

    def test_default_config_matches_function_output(self):
        """Test that DEFAULT_RETRIEVAL_OPTIMIZER_CONFIG matches get_retrieval_optimizer_config()."""
        expected = get_retrieval_optimizer_config()
        actual = DEFAULT_RETRIEVAL_OPTIMIZER_CONFIG

        assert actual == expected

    def test_default_config_is_not_mutable_risk(self):
        """Test that modifying a copy doesn't affect the original."""
        # Get a reference to the default config
        original_tools = DEFAULT_RETRIEVAL_OPTIMIZER_CONFIG.get("tools", {})
        original_tools_count = len(original_tools)

        # Create a new config and modify it
        new_config = get_retrieval_optimizer_config()
        new_config["tools"]["fake_tool"] = {"description": "fake"}

        # Original should be unchanged
        assert len(DEFAULT_RETRIEVAL_OPTIMIZER_CONFIG.get("tools", {})) == original_tools_count


class TestModuleExports:
    """Test that the module exports are correct."""

    def test_retrieval_optimizer_module_exports(self):
        """Test that retrieval_optimizer module exports expected symbols."""
        from redis_sre_agent.tools.mcp import retrieval_optimizer

        assert hasattr(retrieval_optimizer, "get_retrieval_optimizer_config")
        assert hasattr(retrieval_optimizer, "DEFAULT_RETRIEVAL_OPTIMIZER_CONFIG")

    def test_mcp_init_exports(self):
        """Test that redis_sre_agent.tools.mcp exports retrieval_optimizer helpers."""
        from redis_sre_agent.tools.mcp import (
            DEFAULT_RETRIEVAL_OPTIMIZER_CONFIG,
            MCPToolProvider,
            get_retrieval_optimizer_config,
        )

        # Just verify imports don't raise
        assert MCPToolProvider is not None
        assert get_retrieval_optimizer_config is not None
        assert DEFAULT_RETRIEVAL_OPTIMIZER_CONFIG is not None

    def test_all_exports_defined(self):
        """Test that __all__ in mcp module includes retrieval_optimizer exports."""
        from redis_sre_agent.tools import mcp

        expected_exports = [
            "MCPToolProvider",
            "get_retrieval_optimizer_config",
            "DEFAULT_RETRIEVAL_OPTIMIZER_CONFIG",
        ]

        for export in expected_exports:
            assert export in mcp.__all__, f"Missing export in __all__: {export}"

