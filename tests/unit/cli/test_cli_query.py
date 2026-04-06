"""Tests for the `query` CLI command."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from redis_sre_agent.agent.models import AgentResponse
from redis_sre_agent.cli.query import query


@pytest.fixture
def mock_thread_manager():
    """Create a mock ThreadManager that doesn't require Redis."""
    mock_tm = MagicMock()
    mock_tm.create_thread = AsyncMock(return_value="test-thread-id")
    mock_tm.get_thread = AsyncMock(return_value=None)
    mock_tm.update_thread_subject = AsyncMock()
    mock_tm.append_messages = AsyncMock()
    return mock_tm


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client."""
    return MagicMock()


def test_query_cli_help_shows_options():
    runner = CliRunner()
    result = runner.invoke(query, ["--help"])

    assert result.exit_code == 0
    assert "--redis-instance-id" in result.output
    assert "-r" in result.output
    assert "--agent" in result.output
    assert "-a" in result.output
    assert "auto" in result.output
    assert "triage" in result.output
    assert "chat" in result.output
    assert "knowledge" in result.output
    assert "--redis-cluster-id" in result.output
    assert "-c" in result.output
    assert "--user-id" in result.output


def test_query_without_instance_uses_knowledge_agent(mock_thread_manager, mock_redis_client):
    runner = CliRunner()

    mock_agent = MagicMock()
    mock_agent.process_query = AsyncMock(
        return_value=AgentResponse(response="ok", search_results=[])
    )

    with (
        patch(
            "redis_sre_agent.cli.query.get_knowledge_agent", return_value=mock_agent
        ) as mock_get_knowledge,
        patch("redis_sre_agent.cli.query.get_sre_agent") as mock_get_sre,
        patch(
            "redis_sre_agent.cli.query.get_instance_by_id",
            new=AsyncMock(),
        ) as mock_get_instance,
        patch("redis_sre_agent.cli.query.get_redis_client", return_value=mock_redis_client),
        patch("redis_sre_agent.cli.query.ThreadManager", return_value=mock_thread_manager),
    ):
        result = runner.invoke(query, ["What is Redis SRE?"])

    assert result.exit_code == 0, result.output
    mock_get_knowledge.assert_called_once()
    mock_get_sre.assert_not_called()
    mock_get_instance.assert_not_awaited()
    mock_agent.process_query.assert_awaited_once()
    _, kwargs = mock_thread_manager.create_thread.call_args
    assert kwargs["user_id"] is None
    assert kwargs["session_id"].startswith("cli:")


def test_query_with_instance_uses_sre_agent_and_passes_instance_context(
    mock_thread_manager, mock_redis_client
):
    runner = CliRunner()

    class DummyInstance:
        def __init__(self, id: str, name: str):  # noqa: A003 - keep click-style arg name
            self.id = id
            self.name = name
            self.instance_type = "oss_single"  # Required by ChatAgent system prompt
            self.connection_url = "redis://localhost:6379"
            self.environment = "development"
            self.usage = "cache"

    instance = DummyInstance("redis-prod-123", "Haink Production")

    mock_sre_agent = MagicMock()
    mock_sre_agent.process_query = AsyncMock(
        return_value=AgentResponse(response="ok", search_results=[])
    )

    from redis_sre_agent.agent.router import AgentType

    with (
        patch(
            "redis_sre_agent.cli.query.get_instance_by_id",
            new=AsyncMock(return_value=instance),
        ) as mock_get_instance,
        patch(
            "redis_sre_agent.cli.query.get_sre_agent", return_value=mock_sre_agent
        ) as mock_get_sre,
        patch("redis_sre_agent.cli.query.get_knowledge_agent") as mock_get_knowledge,
        patch(
            "redis_sre_agent.cli.query.route_to_appropriate_agent",
            new=AsyncMock(return_value=AgentType.REDIS_TRIAGE),
        ),
        patch("redis_sre_agent.cli.query.get_redis_client", return_value=mock_redis_client),
        patch("redis_sre_agent.cli.query.ThreadManager", return_value=mock_thread_manager),
    ):
        # Use -r / --redis-instance-id option to select instance
        result = runner.invoke(
            query,
            [
                "Should I scale this instance yet?",
                "-r",
                instance.id,
            ],
        )

    assert result.exit_code == 0, result.output

    # Instance lookup should happen once with the provided ID
    mock_get_instance.assert_awaited_once_with(instance.id)

    # SRE agent should be used (not the knowledge agent)
    mock_get_sre.assert_called_once()
    mock_get_knowledge.assert_not_called()

    # The agent should be called exactly once
    mock_sre_agent.process_query.assert_awaited_once()
    _, kwargs = mock_sre_agent.process_query.call_args

    # Critical behavior: CLI must pass instance context through to the agent
    assert kwargs.get("context") == {"instance_id": instance.id}


def test_query_with_unknown_instance_exits_with_error_and_skips_agents(
    mock_thread_manager, mock_redis_client
):
    """If -r is provided but the instance does not exist, CLI should error and exit.

    This directly tests the new existence-check logic in redis_sre_agent.cli.query.
    """

    runner = CliRunner()

    mock_agent = MagicMock()
    mock_agent.process_query = AsyncMock(
        return_value=AgentResponse(response="ok", search_results=[])
    )

    missing_id = "nonexistent-instance-id"

    with (
        patch(
            "redis_sre_agent.cli.query.get_instance_by_id",
            new=AsyncMock(return_value=None),
        ) as mock_get_instance,
        patch(
            "redis_sre_agent.cli.query.get_knowledge_agent", return_value=mock_agent
        ) as mock_get_knowledge,
        patch("redis_sre_agent.cli.query.get_sre_agent") as mock_get_sre,
        patch("redis_sre_agent.cli.query.get_redis_client", return_value=mock_redis_client),
        patch("redis_sre_agent.cli.query.ThreadManager", return_value=mock_thread_manager),
    ):
        result = runner.invoke(
            query,
            [
                "-r",
                missing_id,
                "Check the health of this instance",
            ],
        )

    # CLI should exit with non-zero status (explicitly exit(1) in implementation)
    assert result.exit_code == 1
    assert f"Instance not found: {missing_id}" in result.output

    # We attempted to resolve the instance ID once
    mock_get_instance.assert_awaited_once_with(missing_id)

    # Since the instance doesn't exist, no agent should be initialized or invoked
    mock_get_knowledge.assert_not_called()
    mock_get_sre.assert_not_called()
    mock_agent.process_query.assert_not_awaited()


def test_query_with_cluster_uses_sre_agent_and_passes_cluster_context(
    mock_thread_manager, mock_redis_client
):
    runner = CliRunner()

    class DummyCluster:
        def __init__(self, id: str, name: str):  # noqa: A003
            self.id = id
            self.name = name

    cluster = DummyCluster("cluster-prod-123", "Prod Cluster")

    mock_sre_agent = MagicMock()
    mock_sre_agent.process_query = AsyncMock(
        return_value=AgentResponse(response="ok", search_results=[])
    )

    from redis_sre_agent.agent.router import AgentType

    with (
        patch(
            "redis_sre_agent.cli.query.get_cluster_by_id",
            new=AsyncMock(return_value=cluster),
        ) as mock_get_cluster,
        patch(
            "redis_sre_agent.cli.query.get_sre_agent", return_value=mock_sre_agent
        ) as mock_get_sre,
        patch("redis_sre_agent.cli.query.get_knowledge_agent") as mock_get_knowledge,
        patch(
            "redis_sre_agent.cli.query.route_to_appropriate_agent",
            new=AsyncMock(return_value=AgentType.REDIS_TRIAGE),
        ),
        patch("redis_sre_agent.cli.query.get_redis_client", return_value=mock_redis_client),
        patch("redis_sre_agent.cli.query.ThreadManager", return_value=mock_thread_manager),
    ):
        result = runner.invoke(
            query,
            [
                "Check this cluster",
                "-c",
                cluster.id,
            ],
        )

    assert result.exit_code == 0, result.output
    mock_get_cluster.assert_awaited_once_with(cluster.id)
    mock_get_sre.assert_called_once()
    mock_get_knowledge.assert_not_called()

    mock_sre_agent.process_query.assert_awaited_once()
    _, kwargs = mock_sre_agent.process_query.call_args
    assert kwargs.get("context") == {"cluster_id": cluster.id}


def test_query_with_cluster_uses_chat_agent_when_router_selects_chat(
    mock_thread_manager, mock_redis_client
):
    runner = CliRunner()

    class DummyCluster:
        def __init__(self, id: str, name: str):  # noqa: A003
            self.id = id
            self.name = name
            self.cluster_type = "redis_enterprise"
            self.environment = "production"

    cluster = DummyCluster("cluster-prod-123", "Prod Cluster")

    mock_chat_agent = MagicMock()
    mock_chat_agent.process_query = AsyncMock(
        return_value=AgentResponse(response="ok", search_results=[])
    )

    from redis_sre_agent.agent.router import AgentType

    with (
        patch(
            "redis_sre_agent.cli.query.get_cluster_by_id",
            new=AsyncMock(return_value=cluster),
        ) as mock_get_cluster,
        patch(
            "redis_sre_agent.cli.query.get_chat_agent", return_value=mock_chat_agent
        ) as mock_get_chat,
        patch("redis_sre_agent.cli.query.get_sre_agent") as mock_get_sre,
        patch("redis_sre_agent.cli.query.get_knowledge_agent") as mock_get_knowledge,
        patch(
            "redis_sre_agent.cli.query.route_to_appropriate_agent",
            new=AsyncMock(return_value=AgentType.REDIS_CHAT),
        ),
        patch("redis_sre_agent.cli.query.get_redis_client", return_value=mock_redis_client),
        patch("redis_sre_agent.cli.query.ThreadManager", return_value=mock_thread_manager),
    ):
        result = runner.invoke(
            query,
            [
                "Check this cluster",
                "-c",
                cluster.id,
            ],
        )

    assert result.exit_code == 0, result.output
    mock_get_cluster.assert_awaited_once_with(cluster.id)
    mock_get_chat.assert_called_once_with(redis_instance=None, redis_cluster=cluster)
    mock_get_sre.assert_not_called()
    mock_get_knowledge.assert_not_called()


def test_query_rejects_both_instance_and_cluster_ids(mock_thread_manager, mock_redis_client):
    runner = CliRunner()

    mock_agent = MagicMock()
    mock_agent.process_query = AsyncMock(
        return_value=AgentResponse(response="ok", search_results=[])
    )

    with (
        patch(
            "redis_sre_agent.cli.query.get_knowledge_agent", return_value=mock_agent
        ) as mock_get_knowledge,
        patch("redis_sre_agent.cli.query.get_sre_agent") as mock_get_sre,
        patch("redis_sre_agent.cli.query.get_chat_agent") as mock_get_chat,
        patch("redis_sre_agent.cli.query.get_redis_client", return_value=mock_redis_client),
        patch("redis_sre_agent.cli.query.ThreadManager", return_value=mock_thread_manager),
    ):
        result = runner.invoke(
            query,
            [
                "Check target",
                "-r",
                "redis-prod-1",
                "-c",
                "cluster-prod-1",
            ],
        )

    assert result.exit_code == 1
    assert "only one of --redis-instance-id or --redis-cluster-id" in result.output
    mock_get_knowledge.assert_not_called()
    mock_get_sre.assert_not_called()
    mock_get_chat.assert_not_called()
    mock_agent.process_query.assert_not_awaited()


def test_query_with_agent_triage_forces_triage_agent(mock_thread_manager, mock_redis_client):
    """Test that --agent triage forces use of the triage agent."""
    runner = CliRunner()

    mock_agent = MagicMock()
    mock_agent.process_query = AsyncMock(
        return_value=AgentResponse(response="triage result", search_results=[])
    )

    with (
        patch("redis_sre_agent.cli.query.get_sre_agent", return_value=mock_agent) as mock_get_sre,
        patch("redis_sre_agent.cli.query.get_knowledge_agent") as mock_get_knowledge,
        patch("redis_sre_agent.cli.query.get_chat_agent") as mock_get_chat,
        patch("redis_sre_agent.cli.query.route_to_appropriate_agent") as mock_router,
        patch("redis_sre_agent.cli.query.get_redis_client", return_value=mock_redis_client),
        patch("redis_sre_agent.cli.query.ThreadManager", return_value=mock_thread_manager),
    ):
        result = runner.invoke(query, ["--agent", "triage", "Check my Redis health"])

    assert result.exit_code == 0, result.output
    assert "Triage (selected)" in result.output

    # Triage agent should be used
    mock_get_sre.assert_called_once()
    mock_get_knowledge.assert_not_called()
    mock_get_chat.assert_not_called()

    # Router should NOT be called when agent is explicitly specified
    mock_router.assert_not_called()

    mock_agent.process_query.assert_awaited_once()


def test_query_with_agent_knowledge_forces_knowledge_agent(mock_thread_manager, mock_redis_client):
    """Test that --agent knowledge forces use of the knowledge agent."""
    runner = CliRunner()

    mock_agent = MagicMock()
    mock_agent.process_query = AsyncMock(
        return_value=AgentResponse(response="knowledge result", search_results=[])
    )

    with (
        patch(
            "redis_sre_agent.cli.query.get_knowledge_agent", return_value=mock_agent
        ) as mock_get_knowledge,
        patch("redis_sre_agent.cli.query.get_sre_agent") as mock_get_sre,
        patch("redis_sre_agent.cli.query.get_chat_agent") as mock_get_chat,
        patch("redis_sre_agent.cli.query.route_to_appropriate_agent") as mock_router,
        patch("redis_sre_agent.cli.query.get_redis_client", return_value=mock_redis_client),
        patch("redis_sre_agent.cli.query.ThreadManager", return_value=mock_thread_manager),
    ):
        result = runner.invoke(query, ["-a", "knowledge", "What is Redis replication?"])

    assert result.exit_code == 0, result.output
    assert "Knowledge (selected)" in result.output

    # Knowledge agent should be used
    mock_get_knowledge.assert_called_once()
    mock_get_sre.assert_not_called()
    mock_get_chat.assert_not_called()

    # Router should NOT be called
    mock_router.assert_not_called()

    mock_agent.process_query.assert_awaited_once()


def test_query_with_agent_chat_forces_chat_agent(mock_thread_manager, mock_redis_client):
    """Test that --agent chat forces use of the chat agent."""
    runner = CliRunner()

    class DummyInstance:
        def __init__(self):
            self.id = "test-instance"
            self.name = "Test Instance"
            self.instance_type = "oss_single"
            self.connection_url = "redis://localhost:6379"
            self.environment = "development"
            self.usage = "cache"

    instance = DummyInstance()

    mock_agent = MagicMock()
    mock_agent.process_query = AsyncMock(
        return_value=AgentResponse(response="chat result", search_results=[])
    )

    with (
        patch("redis_sre_agent.cli.query.get_chat_agent", return_value=mock_agent) as mock_get_chat,
        patch("redis_sre_agent.cli.query.get_sre_agent") as mock_get_sre,
        patch("redis_sre_agent.cli.query.get_knowledge_agent") as mock_get_knowledge,
        patch(
            "redis_sre_agent.cli.query.get_instance_by_id",
            new=AsyncMock(return_value=instance),
        ),
        patch("redis_sre_agent.cli.query.route_to_appropriate_agent") as mock_router,
        patch("redis_sre_agent.cli.query.get_redis_client", return_value=mock_redis_client),
        patch("redis_sre_agent.cli.query.ThreadManager", return_value=mock_thread_manager),
    ):
        result = runner.invoke(query, ["--agent", "chat", "-r", "test-instance", "Quick question"])

    assert result.exit_code == 0, result.output
    assert "Chat (selected)" in result.output

    # Chat agent should be used
    mock_get_chat.assert_called_once()
    mock_get_sre.assert_not_called()
    mock_get_knowledge.assert_not_called()

    # Router should NOT be called
    mock_router.assert_not_called()

    mock_agent.process_query.assert_awaited_once()


def test_query_with_agent_auto_uses_router(mock_thread_manager, mock_redis_client):
    """Test that --agent auto (default) uses the router to select agent."""
    runner = CliRunner()

    from redis_sre_agent.agent.router import AgentType

    mock_agent = MagicMock()
    mock_agent.process_query = AsyncMock(
        return_value=AgentResponse(response="routed result", search_results=[])
    )

    with (
        patch(
            "redis_sre_agent.cli.query.get_knowledge_agent", return_value=mock_agent
        ) as mock_get_knowledge,
        patch("redis_sre_agent.cli.query.get_sre_agent") as mock_get_sre,
        patch(
            "redis_sre_agent.cli.query.route_to_appropriate_agent",
            new=AsyncMock(return_value=AgentType.KNOWLEDGE_ONLY),
        ) as mock_router,
        patch("redis_sre_agent.cli.query.get_redis_client", return_value=mock_redis_client),
        patch("redis_sre_agent.cli.query.ThreadManager", return_value=mock_thread_manager),
    ):
        # Default is auto, so router should be called
        result = runner.invoke(query, ["What is Redis?"])

    assert result.exit_code == 0, result.output
    # Should show "Knowledge" without "(selected)" since it was auto-routed
    assert "Agent: Knowledge" in result.output
    assert "(selected)" not in result.output

    # Router should be called
    mock_router.assert_awaited_once()

    mock_get_knowledge.assert_called_once()
    mock_get_sre.assert_not_called()


def test_query_with_explicit_user_id_scopes_thread_and_agent(mock_thread_manager, mock_redis_client):
    runner = CliRunner()
    from redis_sre_agent.agent.router import AgentType

    mock_agent = MagicMock()
    mock_agent.process_query = AsyncMock(
        return_value=AgentResponse(response="ok", search_results=[])
    )

    with (
        patch("redis_sre_agent.cli.query.get_knowledge_agent", return_value=mock_agent),
        patch("redis_sre_agent.cli.query.get_sre_agent"),
        patch("redis_sre_agent.cli.query.get_chat_agent"),
        patch(
            "redis_sre_agent.cli.query.route_to_appropriate_agent",
            new=AsyncMock(return_value=AgentType.KNOWLEDGE_ONLY),
        ),
        patch("redis_sre_agent.cli.query.get_redis_client", return_value=mock_redis_client),
        patch("redis_sre_agent.cli.query.ThreadManager", return_value=mock_thread_manager),
    ):
        result = runner.invoke(query, ["--user-id", "operator-1", "What is Redis?"])

    assert result.exit_code == 0, result.output
    mock_thread_manager.create_thread.assert_awaited_once()
    _, kwargs = mock_thread_manager.create_thread.call_args
    assert kwargs["user_id"] == "operator-1"
    assert kwargs["session_id"].startswith("cli:")

    mock_agent.process_query.assert_awaited_once()
    _, kwargs = mock_agent.process_query.call_args
    assert kwargs["user_id"] == "operator-1"
    assert kwargs["session_id"].startswith("cli:")


def test_query_agent_option_is_case_insensitive(mock_thread_manager, mock_redis_client):
    """Test that --agent option accepts different cases."""
    runner = CliRunner()

    mock_agent = MagicMock()
    mock_agent.process_query = AsyncMock(
        return_value=AgentResponse(response="result", search_results=[])
    )

    with (
        patch("redis_sre_agent.cli.query.get_knowledge_agent", return_value=mock_agent),
        patch("redis_sre_agent.cli.query.route_to_appropriate_agent"),
        patch("redis_sre_agent.cli.query.get_redis_client", return_value=mock_redis_client),
        patch("redis_sre_agent.cli.query.ThreadManager", return_value=mock_thread_manager),
    ):
        # Test uppercase
        result = runner.invoke(query, ["--agent", "KNOWLEDGE", "test query"])
        assert result.exit_code == 0, result.output

        # Test mixed case
        result = runner.invoke(query, ["--agent", "Knowledge", "test query"])
        assert result.exit_code == 0, result.output
