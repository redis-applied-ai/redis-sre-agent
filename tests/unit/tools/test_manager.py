"""Tests for ToolManager."""

from contextlib import AsyncExitStack
from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.core.clusters import RedisCluster, RedisClusterType
from redis_sre_agent.core.config import MCPServerConfig
from redis_sre_agent.core.instances import RedisInstance
from redis_sre_agent.core.targets import TargetBinding
from redis_sre_agent.tools.manager import ToolManager, _command_is_available
from redis_sre_agent.tools.models import ToolCapability, ToolDefinition


@pytest.mark.asyncio
async def test_tool_manager_initialization():
    """Test that ToolManager initializes and loads knowledge provider."""
    async with ToolManager() as mgr:
        tools = mgr.get_tools()

        # Should have at least knowledge tools
        assert len(tools) >= 2

        # All tools should be ToolDefinition objects
        for tool in tools:
            assert isinstance(tool, ToolDefinition)
            assert tool.name
            assert tool.description
            assert tool.parameters

        # Should have routing table entries
        assert len(mgr._routing_table) == len(tools)


@pytest.mark.asyncio
async def test_tool_manager_knowledge_tools():
    """Test that knowledge tools are loaded without instance."""
    async with ToolManager() as mgr:
        tools = mgr.get_tools()
        tool_names = [t.name for t in tools]

        # Without an instance, only knowledge tools should be loaded
        knowledge_tools = [n for n in tool_names if "knowledge_" in n]
        prometheus_tools = [n for n in tool_names if "prometheus_" in n]
        redis_command_tools = [n for n in tool_names if "redis_command_" in n]

        # Knowledge tools (always loaded)
        assert len(knowledge_tools) == 8
        assert any("target_discovery_" in n and "resolve_redis_targets" in n for n in tool_names)
        assert any("search" in n for n in knowledge_tools)
        assert any("ingest" in n for n in knowledge_tools)
        assert any("get_all_fragments" in n for n in knowledge_tools)
        assert any("get_related_fragments" in n for n in knowledge_tools)
        assert any("skills_check" in n for n in knowledge_tools)
        assert any("get_skill" in n for n in knowledge_tools)
        assert any("search_support_tickets" in n for n in knowledge_tools)
        assert any("get_support_ticket" in n for n in knowledge_tools)

        tickets_tools = mgr.get_tools_for_capability(ToolCapability.TICKETS)
        ticket_tool_names = [t.name for t in tickets_tools]
        assert any("search_support_tickets" in n for n in ticket_tool_names)
        assert any("get_support_ticket" in n for n in ticket_tool_names)

        # Instance-specific tools should NOT be loaded without an instance
        assert len(prometheus_tools) == 0
        assert len(redis_command_tools) == 0


@pytest.mark.asyncio
async def test_attach_bound_targets_scopes_instance_tools_to_opaque_handle():
    """Attached targets should re-scope providers to the opaque target handle."""
    binding = TargetBinding(
        target_handle="tgt_opaque_1",
        target_kind="instance",
        resource_id="inst-1",
        display_name="checkout-cache-prod",
        capabilities=["redis", "diagnostics"],
    )
    instance = RedisInstance(
        id="inst-1",
        name="checkout-cache-prod",
        connection_url="redis://localhost:6379",
        environment="production",
        usage="cache",
        description="test",
        instance_type="oss_single",
    )

    mgr = ToolManager()
    mgr._toolset_generation = 1
    with (
        patch(
            "redis_sre_agent.core.instances.get_instance_by_id",
            new=AsyncMock(return_value=instance),
        ),
        patch.object(mgr, "_load_instance_scoped_providers", new=AsyncMock()) as mock_load,
    ):
        attached = await mgr.attach_bound_targets([binding])

    assert attached == [binding]
    scoped_instance = mock_load.await_args.args[0]
    assert scoped_instance.id == "tgt_opaque_1"
    assert scoped_instance.name == "checkout-cache-prod"
    assert mgr.get_toolset_generation() == 2


@pytest.mark.asyncio
async def test_tool_manager_prefers_initial_target_bindings_before_thread_reload():
    """Explicit initial bindings should be attached without depending on thread state."""
    binding = TargetBinding(
        target_handle="tgt_opaque_1",
        target_kind="instance",
        resource_id="inst-1",
        display_name="checkout-cache-prod",
        capabilities=["redis", "diagnostics"],
    )

    mgr = ToolManager(
        initial_target_bindings=[binding],
        initial_toolset_generation=7,
        thread_id="thread-123",
    )

    with (
        patch.object(mgr, "_load_provider", new=AsyncMock()),
        patch.object(mgr, "_load_mcp_providers", new=AsyncMock()),
        patch.object(mgr, "_load_support_package_provider", new=AsyncMock()),
        patch.object(
            mgr, "attach_bound_targets", new=AsyncMock(return_value=[binding])
        ) as mock_attach,
        patch.object(mgr, "_load_thread_attached_targets", new=AsyncMock()) as mock_thread_reload,
    ):
        await mgr.__aenter__()
        await mgr.__aexit__(None, None, None)

    mock_attach.assert_awaited_once_with([binding], generation=7)
    mock_thread_reload.assert_not_awaited()


@pytest.mark.asyncio
async def test_tool_manager_with_instance():
    """Test that instance-specific tools are loaded when instance is provided."""
    from redis_sre_agent.core.instances import RedisInstance

    # Create a test instance
    test_instance = RedisInstance(
        id="test-instance",
        name="Test Redis",
        connection_url="redis://localhost:6379",
        environment="test",
        usage="cache",
        description="Test instance",
        instance_type="oss_single",
    )

    async with ToolManager(redis_instance=test_instance) as mgr:
        tools = mgr.get_tools()
        tool_names = [t.name for t in tools]

        # Should have knowledge, prometheus, and redis_command tools
        knowledge_tools = [n for n in tool_names if "knowledge_" in n]
        prometheus_tools = [n for n in tool_names if "prometheus_" in n]
        redis_command_tools = [n for n in tool_names if "redis_command_" in n]

        # Knowledge tools (always loaded)
        assert len(knowledge_tools) == 8

        # Instance-specific tools should be loaded
        assert len(prometheus_tools) == 3  # query, query_range, search_metrics
        assert len(redis_command_tools) == 11  # All diagnostic tools


@pytest.mark.asyncio
async def test_tool_manager_routing():
    """Test that ToolManager can route tool calls."""
    async with ToolManager() as mgr:
        tools = mgr.get_tools()

        # Get a tool name
        tool_name = tools[0].name

        # Should be able to find provider in routing table
        provider = mgr._routing_table.get(tool_name)
        assert provider is not None
        assert provider.provider_name == "knowledge"


@pytest.mark.asyncio
async def test_tool_manager_unknown_tool():
    """Test that ToolManager raises error for unknown tools."""
    async with ToolManager() as mgr:
        with pytest.raises(ValueError, match="Unknown tool"):
            await mgr.resolve_tool_call("nonexistent_tool", {})


@pytest.mark.asyncio
async def test_tool_manager_context_cleanup():
    """Test that ToolManager cleans up properly."""
    mgr = ToolManager()

    # Before entering context
    assert mgr._stack is None
    assert len(mgr._tools) == 0

    # Enter context
    await mgr.__aenter__()
    assert mgr._stack is not None
    assert len(mgr._tools) > 0

    # Exit context
    await mgr.__aexit__(None, None, None)

    # Stack should still exist but be closed
    assert mgr._stack is not None


def test_mask_redis_url_credentials():
    """Test that Redis URL credentials are properly masked."""
    from redis_sre_agent.agent.langgraph_agent import _mask_redis_url_credentials

    # Test with username and password
    url_with_creds = "redis://user:password@localhost:6379/0"
    masked = _mask_redis_url_credentials(url_with_creds)
    assert masked == "redis://***:***@localhost:6379/0"
    assert "user" not in masked
    assert "password" not in masked

    # Test with URL-encoded credentials (common in Redis Enterprise)
    url_encoded = "redis://admin%40redis.com:admin@redis-enterprise:12000/0"
    masked = _mask_redis_url_credentials(url_encoded)
    assert masked == "redis://***:***@redis-enterprise:12000/0"
    assert "admin" not in masked

    # Test without credentials
    url_no_creds = "redis://localhost:6379"
    masked = _mask_redis_url_credentials(url_no_creds)
    assert masked == "redis://localhost:6379"

    # Test with only password (edge case)
    url_only_pass = "redis://:password@localhost:6379"
    masked = _mask_redis_url_credentials(url_only_pass)
    assert masked == "redis://***:***@localhost:6379"
    assert "password" not in masked

    # Test with special characters in password
    url_special_chars = "redis://user:p@ssw0rd!@localhost:6379"
    masked = _mask_redis_url_credentials(url_special_chars)
    assert masked == "redis://***:***@localhost:6379"
    assert "p@ssw0rd!" not in masked
    assert "user" not in masked

    # Test with database number
    url_with_db = "redis://user:pass@localhost:6379/5"
    masked = _mask_redis_url_credentials(url_with_db)
    assert masked == "redis://***:***@localhost:6379/5"
    assert "user" not in masked
    assert "pass" not in masked

    # Test with query parameters
    url_with_query = "redis://user:pass@localhost:6379/0?timeout=5"
    masked = _mask_redis_url_credentials(url_with_query)
    assert masked == "redis://***:***@localhost:6379/0?timeout=5"
    assert "user" not in masked
    assert "pass" not in masked

    # Test with non-standard port
    url_enterprise_port = "redis://admin:secret@redis-enterprise:12000/0"
    masked = _mask_redis_url_credentials(url_enterprise_port)
    assert masked == "redis://***:***@redis-enterprise:12000/0"
    assert "admin" not in masked
    assert "secret" not in masked
    # Verify hostname and port are preserved
    assert "redis-enterprise" in masked
    assert "12000" in masked

    # Test with rediss:// (SSL)
    url_ssl = "rediss://user:pass@secure-redis:6380/0"
    masked = _mask_redis_url_credentials(url_ssl)
    assert masked == "rediss://***:***@secure-redis:6380/0"
    assert "user" not in masked
    assert "pass" not in masked

    # Test with complex username (email-like)
    url_email_user = "redis://admin@company.com:password123@redis-host:6379"
    masked = _mask_redis_url_credentials(url_email_user)
    assert masked == "redis://***:***@redis-host:6379"
    assert "admin@company.com" not in masked
    assert "password123" not in masked
    assert "redis-host" in masked


class TestToolManagerProviders:
    """Test ToolManager provider management."""

    @pytest.mark.asyncio
    async def test_get_tools_returns_tool_definitions(self):
        """Test get_tools returns ToolDefinition objects."""
        async with ToolManager() as mgr:
            tools = mgr.get_tools()

            assert isinstance(tools, list)
            for tool in tools:
                assert isinstance(tool, ToolDefinition)

    @pytest.mark.asyncio
    async def test_tool_manager_has_routing_table(self):
        """Test ToolManager builds routing table."""
        async with ToolManager() as mgr:
            assert hasattr(mgr, "_routing_table")
            assert isinstance(mgr._routing_table, dict)

    @pytest.mark.asyncio
    async def test_tool_manager_multiple_context_entries(self):
        """Test ToolManager handles multiple context entries."""
        mgr = ToolManager()

        await mgr.__aenter__()
        tools1 = mgr.get_tools()

        await mgr.__aexit__(None, None, None)

        # Re-enter context
        await mgr.__aenter__()
        tools2 = mgr.get_tools()

        # Should have same tools available
        assert len(tools1) == len(tools2)

        await mgr.__aexit__(None, None, None)


class TestToolManagerGetStatusUpdate:
    """Test ToolManager get_status_update method."""

    @pytest.mark.asyncio
    async def test_get_status_update_returns_none_for_unknown_tool(self):
        """Test get_status_update returns None for unknown tool."""
        async with ToolManager() as mgr:
            result = mgr.get_status_update("unknown_tool_name", {})
            assert result is None

    @pytest.mark.asyncio
    async def test_get_status_update_for_known_tool(self):
        """Test get_status_update for a known tool."""
        async with ToolManager() as mgr:
            tools = mgr.get_tools()
            if tools:
                tool_name = tools[0].name
                # May return None or a string depending on tool
                result = mgr.get_status_update(tool_name, {})
                assert result is None or isinstance(result, str)


class TestToolManagerMcpConfigValidation:
    """Test MCP provider loading guardrails."""

    def test_command_is_available_handles_missing_path(self):
        """Absolute/relative command paths should return False when missing."""
        assert _command_is_available("/definitely/not/a/real/command") is False

    @pytest.mark.asyncio
    async def test_load_mcp_providers_skips_missing_command(self, caplog):
        """Missing MCP command should be skipped without raising or stack traces."""
        mgr = ToolManager()
        mgr._stack = AsyncExitStack()
        await mgr._stack.__aenter__()
        try:
            with patch("redis_sre_agent.core.config.settings") as mock_settings:
                mock_settings.mcp_servers = {
                    "github": MCPServerConfig(command="definitely-missing-mcp-command-xyz")
                }
                await mgr._load_mcp_providers()

            assert "mcp:github" not in mgr._loaded_provider_keys
            assert "Skipping MCP provider 'github'" in caplog.text
        finally:
            await mgr._stack.__aexit__(None, None, None)


class TestToolDefinitionRepresentation:
    """Tests for ToolDefinition __str__ and __repr__ methods."""

    def test_tool_definition_str(self):
        """Test that __str__ returns expected format."""
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {"arg1": {"type": "string"}}},
            capability=ToolCapability.DIAGNOSTICS,
        )
        assert str(tool) == "ToolDefinition(name=test_tool)"

    def test_tool_definition_repr(self):
        """Test that __repr__ returns expected format with parameter names."""
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters={
                "type": "object",
                "properties": {"arg1": {"type": "string"}, "arg2": {"type": "integer"}},
            },
            capability=ToolCapability.DIAGNOSTICS,
        )
        repr_str = repr(tool)
        assert "ToolDefinition(name=test_tool" in repr_str
        assert "arg1" in repr_str
        assert "arg2" in repr_str

    def test_tool_definition_repr_empty_parameters(self):
        """Test __repr__ with empty parameters."""
        tool = ToolDefinition(
            name="empty_params_tool",
            description="A tool with no parameters",
            parameters={"type": "object", "properties": {}},
            capability=ToolCapability.UTILITIES,
        )
        repr_str = repr(tool)
        assert "ToolDefinition(name=empty_params_tool" in repr_str
        assert "parameters=[]" in repr_str


class TestEnterpriseCredentialResolution:
    """Tests for Redis Enterprise cluster-first credential resolution in ToolManager."""

    @pytest.mark.asyncio
    async def test_loads_re_admin_tools_from_linked_cluster_credentials(self):
        """Redis Enterprise instance should load re_admin tools from linked cluster creds."""
        from redis_sre_agent.core.instances import RedisInstance

        instance = RedisInstance(
            id="re-inst-1",
            name="enterprise-db",
            connection_url="redis://localhost:12000",
            environment="test",
            usage="cache",
            description="enterprise instance",
            instance_type="redis_enterprise",
            cluster_id="cluster-1",
        )
        cluster = RedisCluster(
            id="cluster-1",
            name="enterprise-cluster",
            cluster_type=RedisClusterType.redis_enterprise,
            environment="test",
            description="cluster creds",
            admin_url="https://cluster.example.com:9443",
            admin_username="admin@redis.com",
            admin_password="secret",
        )

        with patch(
            "redis_sre_agent.core.clusters.get_cluster_by_id",
            new=AsyncMock(return_value=cluster),
        ):
            async with ToolManager(redis_instance=instance) as mgr:
                tool_names = [t.name for t in mgr.get_tools()]
                assert any(name.startswith("re_admin_") for name in tool_names)
                assert mgr.redis_instance.admin_url == "https://cluster.example.com:9443"
                assert mgr.redis_instance.admin_username == "admin@redis.com"

    @pytest.mark.asyncio
    async def test_falls_back_to_deprecated_instance_admin_fields(self):
        """If linked cluster is unavailable, fallback to deprecated instance admin fields."""
        from redis_sre_agent.core.instances import RedisInstance

        instance = RedisInstance(
            id="re-inst-2",
            name="enterprise-db-fallback",
            connection_url="redis://localhost:12001",
            environment="test",
            usage="cache",
            description="enterprise instance fallback",
            instance_type="redis_enterprise",
            cluster_id="missing-cluster",
            admin_url="https://legacy-instance.example.com:9443",
            admin_username="legacy-admin@redis.com",
            admin_password="legacy-secret",
        )

        with patch(
            "redis_sre_agent.core.clusters.get_cluster_by_id",
            new=AsyncMock(return_value=None),
        ):
            async with ToolManager(redis_instance=instance) as mgr:
                tool_names = [t.name for t in mgr.get_tools()]
                assert any(name.startswith("re_admin_") for name in tool_names)
                assert mgr.redis_instance.admin_url == "https://legacy-instance.example.com:9443"

    @pytest.mark.asyncio
    async def test_skips_re_admin_tools_when_no_cluster_or_instance_admin_credentials(self):
        """Without cluster or instance admin URL, re_admin tools should not load."""
        from redis_sre_agent.core.instances import RedisInstance

        instance = RedisInstance(
            id="re-inst-3",
            name="enterprise-db-no-admin",
            connection_url="redis://localhost:12002",
            environment="test",
            usage="cache",
            description="enterprise instance no admin creds",
            instance_type="redis_enterprise",
            cluster_id="missing-cluster",
        )

        with patch(
            "redis_sre_agent.core.clusters.get_cluster_by_id",
            new=AsyncMock(return_value=None),
        ):
            async with ToolManager(redis_instance=instance) as mgr:
                tool_names = [t.name for t in mgr.get_tools()]
                assert not any(name.startswith("re_admin_") for name in tool_names)

    @pytest.mark.asyncio
    async def test_loads_re_admin_tools_from_cluster_without_instance(self):
        """Cluster-only Redis Enterprise queries should still load admin tools."""
        cluster = RedisCluster(
            id="cluster-only-1",
            name="enterprise-cluster-only",
            cluster_type=RedisClusterType.redis_enterprise,
            environment="test",
            description="cluster-only creds",
            admin_url="https://cluster-only.example.com:9443",
            admin_username="admin@redis.com",
            admin_password="secret",
        )

        async with ToolManager(redis_cluster=cluster) as mgr:
            tool_names = [t.name for t in mgr.get_tools()]
            assert any(name.startswith("re_admin_") for name in tool_names)
            assert mgr.redis_instance is None
