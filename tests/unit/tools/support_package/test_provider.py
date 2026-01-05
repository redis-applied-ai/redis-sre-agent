"""Tests for support package tool provider."""

from pathlib import Path

import pytest

from redis_sre_agent.tools.models import ToolCapability


class TestSupportPackageToolProvider:
    """Tests for SupportPackageToolProvider."""

    @pytest.fixture
    def sample_package_dir(self, tmp_path: Path) -> Path:
        """Create a sample support package directory structure."""
        # Create database directories
        db4_dir = tmp_path / "database_4"
        db4_dir.mkdir()
        (db4_dir / "database_4.info").write_text(
            "# Server\nredis_version:8.4.0\nused_memory:13694297256\n"
            "# Clients\nconnected_clients:5\n"
        )
        (db4_dir / "database_4.slowlog").write_text(
            "SLOWLOG\n0 2025-11-24T11:42:01+00:00Z 65.325 [b'CLUSTER', b'SYNCSLOTS']\n"
        )
        (db4_dir / "database_4.clientlist").write_text(
            "CLIENT LIST\nid=1000 addr=10.0.101.36:58696 fd=66 name= age=0 idle=0\n"
        )
        (db4_dir / "database_4.rladmin").write_text(
            "DB INFO FOR BDB 4\ndb:4 [test-db-asm]:\nMemory limit: 100GB\n"
        )

        # Create node directories
        node1_dir = tmp_path / "node_1"
        node1_dir.mkdir()
        logs_dir = node1_dir / "logs"
        logs_dir.mkdir()
        (node1_dir / "node_1_sys_info.txt").write_text("System info for node 1")
        (logs_dir / "event_log.log").write_text(
            '2025-11-24 10:53:15 INFO EventLog: {"type":"node_joined"}\n'
            '2025-11-24 10:53:20 CRITICAL EventLog: {"type":"failed"}\n'
        )
        (logs_dir / "dmcproxy.log").write_text("DMC proxy log line 1\n")

        return tmp_path

    def test_provider_name(self, sample_package_dir: Path):
        """Test that provider has correct name."""
        from redis_sre_agent.tools.support_package.provider import SupportPackageToolProvider

        provider = SupportPackageToolProvider(package_path=sample_package_dir)
        assert provider.provider_name == "support_package"

    def test_create_tool_schemas(self, sample_package_dir: Path):
        """Test that provider creates expected tool schemas."""
        from redis_sre_agent.tools.support_package.provider import SupportPackageToolProvider

        provider = SupportPackageToolProvider(package_path=sample_package_dir)
        schemas = provider.create_tool_schemas()

        tool_names = [s.name for s in schemas]
        # Should have tools for diagnostics and logs
        assert any("info" in name for name in tool_names)
        assert any("slowlog" in name for name in tool_names)
        assert any("clientlist" in name for name in tool_names)
        assert any("logs" in name for name in tool_names)

    def test_tools_have_correct_capabilities(self, sample_package_dir: Path):
        """Test that tools have correct capability assignments."""
        from redis_sre_agent.tools.support_package.provider import SupportPackageToolProvider

        provider = SupportPackageToolProvider(package_path=sample_package_dir)
        schemas = provider.create_tool_schemas()

        for schema in schemas:
            # "logs" and "list_node_logs" are LOGS capability
            # Everything else (info, slowlog, clientlist, list_databases, list_nodes) is DIAGNOSTICS
            if "logs" in schema.name.lower() and "list_node" not in schema.name.lower():
                # The "logs" tool reads log files - LOGS capability
                if "_logs" in schema.name and "list_node" not in schema.name:
                    assert schema.capability == ToolCapability.LOGS
            elif "list_node_logs" in schema.name:
                # Listing node logs is a LOGS capability
                assert schema.capability == ToolCapability.LOGS
            else:
                assert schema.capability == ToolCapability.DIAGNOSTICS

    @pytest.mark.asyncio
    async def test_get_database_info(self, sample_package_dir: Path):
        """Test retrieving database INFO from support package."""
        from redis_sre_agent.tools.support_package.provider import SupportPackageToolProvider

        provider = SupportPackageToolProvider(package_path=sample_package_dir)
        result = await provider.info(database_id="4")

        assert result["status"] == "success"
        assert "redis_version:8.4.0" in result["data"]

    @pytest.mark.asyncio
    async def test_get_database_slowlog(self, sample_package_dir: Path):
        """Test retrieving database SLOWLOG from support package."""
        from redis_sre_agent.tools.support_package.provider import SupportPackageToolProvider

        provider = SupportPackageToolProvider(package_path=sample_package_dir)
        result = await provider.slowlog(database_id="4")

        assert result["status"] == "success"
        assert "CLUSTER" in result["data"]

    @pytest.mark.asyncio
    async def test_get_database_clientlist(self, sample_package_dir: Path):
        """Test retrieving database CLIENT LIST from support package."""
        from redis_sre_agent.tools.support_package.provider import SupportPackageToolProvider

        provider = SupportPackageToolProvider(package_path=sample_package_dir)
        result = await provider.clientlist(database_id="4")

        assert result["status"] == "success"
        assert "10.0.101.36" in result["data"]

    @pytest.mark.asyncio
    async def test_get_node_logs(self, sample_package_dir: Path):
        """Test retrieving node logs from support package."""
        from redis_sre_agent.tools.support_package.provider import SupportPackageToolProvider

        provider = SupportPackageToolProvider(package_path=sample_package_dir)
        result = await provider.logs(node_id="1", log_name="event_log.log")

        assert result["status"] == "success"
        assert "node_joined" in result["data"]

    @pytest.mark.asyncio
    async def test_get_node_logs_with_filter(self, sample_package_dir: Path):
        """Test retrieving node logs with severity filter."""
        from redis_sre_agent.tools.support_package.provider import SupportPackageToolProvider

        provider = SupportPackageToolProvider(package_path=sample_package_dir)
        result = await provider.logs(node_id="1", log_name="event_log.log", level="CRITICAL")

        assert result["status"] == "success"
        assert "failed" in result["data"]
        assert "node_joined" not in result["data"]

    @pytest.mark.asyncio
    async def test_list_databases(self, sample_package_dir: Path):
        """Test listing all databases in support package."""
        from redis_sre_agent.tools.support_package.provider import SupportPackageToolProvider

        provider = SupportPackageToolProvider(package_path=sample_package_dir)
        result = await provider.list_databases()

        assert result["status"] == "success"
        assert len(result["databases"]) == 1
        assert result["databases"][0]["database_id"] == "4"

    @pytest.mark.asyncio
    async def test_list_nodes(self, sample_package_dir: Path):
        """Test listing all nodes in support package."""
        from redis_sre_agent.tools.support_package.provider import SupportPackageToolProvider

        provider = SupportPackageToolProvider(package_path=sample_package_dir)
        result = await provider.list_nodes()

        assert result["status"] == "success"
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["node_id"] == "1"

    @pytest.mark.asyncio
    async def test_list_node_logs(self, sample_package_dir: Path):
        """Test listing available log files for a node."""
        from redis_sre_agent.tools.support_package.provider import SupportPackageToolProvider

        provider = SupportPackageToolProvider(package_path=sample_package_dir)
        result = await provider.list_node_logs(node_id="1")

        assert result["status"] == "success"
        assert "event_log.log" in result["log_files"]
        assert "dmcproxy.log" in result["log_files"]

    @pytest.mark.asyncio
    async def test_info_returns_error_for_missing_database(self, sample_package_dir: Path):
        """Test that info returns error for non-existent database."""
        from redis_sre_agent.tools.support_package.provider import SupportPackageToolProvider

        provider = SupportPackageToolProvider(package_path=sample_package_dir)
        result = await provider.info(database_id="999")

        assert result["status"] == "error"
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_logs_returns_error_for_missing_node(self, sample_package_dir: Path):
        """Test that logs returns error for non-existent node."""
        from redis_sre_agent.tools.support_package.provider import SupportPackageToolProvider

        provider = SupportPackageToolProvider(package_path=sample_package_dir)
        result = await provider.logs(node_id="999", log_name="event_log.log")

        assert result["status"] == "error"
        assert "not found" in result["error"].lower()


class TestToolManagerIntegration:
    """Tests for ToolManager integration with support packages."""

    @pytest.fixture
    def sample_package_dir(self, tmp_path: Path) -> Path:
        """Create a sample support package directory structure."""
        # Create database directories
        db4_dir = tmp_path / "database_4"
        db4_dir.mkdir()
        (db4_dir / "database_4.info").write_text(
            "# Server\nredis_version:8.4.0\nused_memory:13694297256\n"
        )
        return tmp_path

    @pytest.mark.asyncio
    async def test_tool_manager_loads_support_package_provider(self, sample_package_dir: Path):
        """Test that ToolManager loads support package tools when path is provided."""
        from redis_sre_agent.tools.manager import ToolManager

        async with ToolManager(
            redis_instance=None,
            support_package_path=sample_package_dir,
        ) as tool_mgr:
            tools = tool_mgr.get_tools()
            tool_names = [t.name for t in tools]

            # Should have support package tools (format: support_package_{hash}_{operation})
            assert any("support_package" in name for name in tool_names)
            assert any("_info" in name for name in tool_names)
            assert any("_logs" in name for name in tool_names)

    @pytest.mark.asyncio
    async def test_tool_manager_without_support_package(self):
        """Test that ToolManager works without support package path."""
        from redis_sre_agent.tools.manager import ToolManager

        async with ToolManager(
            redis_instance=None,
            support_package_path=None,
        ) as tool_mgr:
            tools = tool_mgr.get_tools()
            tool_names = [t.name for t in tools]

            # Should NOT have support package tools
            assert not any("support_pkg" in name for name in tool_names)
