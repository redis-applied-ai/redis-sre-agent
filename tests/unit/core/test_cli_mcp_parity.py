"""Tests for CLI to MCP parity auditing helpers."""

import pytest


class TestCliMcpParityHelpers:
    def test_walk_click_commands_skips_missing_children(self):
        import click

        from redis_sre_agent.core.cli_mcp_parity import _walk_click_commands

        class BrokenGroup(click.MultiCommand):
            def list_commands(self, ctx):
                return ["missing", "present"]

            def get_command(self, ctx, name):
                if name == "present":
                    return click.Command(name)
                return None

        assert _walk_click_commands(BrokenGroup("broken"), ("root",)) == {"root present"}

    def test_list_cli_command_paths_discovers_leaf_commands(self):
        from redis_sre_agent.core.cli_mcp_parity import list_cli_command_paths

        paths = list_cli_command_paths()

        assert "version" in paths
        assert "query" in paths
        assert "pipeline show-batch" in paths
        assert "thread trace" in paths
        assert "worker status" in paths
        assert "mcp list-tools" in paths

    def test_list_in_scope_cli_command_paths_excludes_admin_commands(self):
        from redis_sre_agent.core.cli_mcp_parity import list_in_scope_cli_command_paths

        paths = list_in_scope_cli_command_paths()

        assert "worker start" not in paths
        assert "worker status" not in paths
        assert "worker stop" not in paths
        assert "mcp serve" not in paths
        assert "mcp list-tools" not in paths
        assert "thread trace" in paths
        assert "pipeline show-batch" in paths

    def test_audit_cli_mcp_parity_passes_for_current_surface(self):
        from redis_sre_agent.core.cli_mcp_parity import audit_cli_mcp_parity

        report = audit_cli_mcp_parity()

        assert report["status"] == "ok"
        assert report["missing_cli_mappings"] == []
        assert report["missing_mcp_tools"] == {}
        assert report["stale_exclusions"] == []
        assert "worker status" in report["excluded_cli_commands"]
        assert "mcp list-tools" in report["excluded_cli_commands"]

    def test_audit_cli_mcp_parity_reports_unmapped_cli_commands(self):
        from redis_sre_agent.core.cli_mcp_parity import audit_cli_mcp_parity

        report = audit_cli_mcp_parity(
            cli_command_paths={"version", "new command"},
            mcp_tool_names={"redis_sre_version"},
        )

        assert report["status"] == "failed"
        assert report["missing_cli_mappings"] == ["new command"]
        assert report["missing_mcp_tools"] == {}

    def test_audit_cli_mcp_parity_reports_missing_mcp_tools(self):
        from redis_sre_agent.core.cli_mcp_parity import audit_cli_mcp_parity

        report = audit_cli_mcp_parity(
            cli_command_paths={"version"},
            mcp_tool_names=set(),
        )

        assert report["status"] == "failed"
        assert report["missing_cli_mappings"] == []
        assert report["missing_mcp_tools"] == {"version": "redis_sre_version"}

    def test_audit_cli_mcp_parity_reports_stale_exclusions(self, monkeypatch: pytest.MonkeyPatch):
        import redis_sre_agent.core.cli_mcp_parity as parity

        monkeypatch.setattr(
            parity,
            "EXCLUDED_CLI_COMMAND_PATHS",
            parity.EXCLUDED_CLI_COMMAND_PATHS | {"worker restart"},
        )

        report = parity.audit_cli_mcp_parity(
            cli_command_paths={"worker status", "version"},
            mcp_tool_names={"redis_sre_version"},
        )

        assert report["status"] == "failed"
        assert report["stale_exclusions"] == [
            "eval compare",
            "eval list",
            "eval live-suite",
            "eval run",
            "mcp list-tools",
            "mcp serve",
            "worker restart",
            "worker start",
            "worker stop",
        ]

    def test_list_mcp_tool_names_reads_registered_tool_names(self):
        from redis_sre_agent.core.cli_mcp_parity import list_mcp_tool_names

        tool_names = list_mcp_tool_names()

        assert "redis_sre_query" in tool_names
        assert "redis_sre_version" in tool_names
        assert "redis_sre_get_pipeline_status" in tool_names

    @pytest.mark.asyncio
    async def test_list_mcp_tool_names_works_inside_running_event_loop(self):
        from redis_sre_agent.core.cli_mcp_parity import list_mcp_tool_names

        tool_names = list_mcp_tool_names()

        assert "redis_sre_query" in tool_names

    def test_list_cli_command_paths_skips_missing_top_level_commands(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        import redis_sre_agent.core.cli_mcp_parity as parity

        original_get_command = parity.main.get_command

        def fake_get_command(ctx, name):
            if name == "version":
                return None
            return original_get_command(ctx, name)

        monkeypatch.setattr(parity.main, "get_command", fake_get_command)

        paths = parity.list_cli_command_paths()

        assert "version" not in paths
