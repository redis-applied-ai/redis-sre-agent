"""Tests for the `query` CLI command."""

from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from redis_sre_agent.cli.query import query


def test_query_cli_help_shows_instance_option():
    runner = CliRunner()
    result = runner.invoke(query, ["--help"])

    assert result.exit_code == 0
    assert "--redis-instance-id" in result.output
    assert "-r" in result.output


def test_query_without_instance_uses_knowledge_agent():
    runner = CliRunner()

    mock_agent = MagicMock()
    mock_agent.process_query = AsyncMock(return_value="ok")

    with (
        patch("redis_sre_agent.cli.query.get_knowledge_agent", return_value=mock_agent)
        as mock_get_knowledge,
        patch("redis_sre_agent.cli.query.get_sre_agent") as mock_get_sre,
        patch(
            "redis_sre_agent.cli.query.get_instance_by_id",
            new=AsyncMock(),
        ) as mock_get_instance,
    ):
        result = runner.invoke(query, ["What is Redis SRE?"])

    assert result.exit_code == 0, result.output
    mock_get_knowledge.assert_called_once()
    mock_get_sre.assert_not_called()
    mock_get_instance.assert_not_awaited()
    mock_agent.process_query.assert_awaited_once()


def test_query_with_instance_uses_sre_agent_and_passes_instance_context():
    runner = CliRunner()

    class DummyInstance:
        def __init__(self, id: str, name: str):  # noqa: A003 - keep click-style arg name
            self.id = id
            self.name = name

    instance = DummyInstance("redis-prod-123", "Haink Production")

    mock_sre_agent = MagicMock()
    mock_sre_agent.process_query = AsyncMock(return_value="ok")

    with (
        patch(
            "redis_sre_agent.cli.query.get_instance_by_id",
            new=AsyncMock(return_value=instance),
        ) as mock_get_instance,
        patch(
            "redis_sre_agent.cli.query.get_sre_agent", return_value=mock_sre_agent
        ) as mock_get_sre,
        patch("redis_sre_agent.cli.query.get_knowledge_agent") as mock_get_knowledge,
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


def test_query_with_unknown_instance_falls_back_to_knowledge_agent():
    runner = CliRunner()

    mock_agent = MagicMock()
    mock_agent.process_query = AsyncMock(return_value="ok")

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
    ):
        result = runner.invoke(
            query,
            [
                "-r",
                missing_id,
                "Check the health of this instance",
            ],
        )

    assert result.exit_code == 0, result.output

    # We attempted to resolve the instance ID
    mock_get_instance.assert_awaited_once_with(missing_id)

    # Without a resolved instance, we should route to the knowledge agent
    mock_get_knowledge.assert_called_once()
    mock_get_sre.assert_not_called()

    # Knowledge agent is called once; it should not receive a non-None instance context
    mock_agent.process_query.assert_awaited_once()
    _, kwargs = mock_agent.process_query.call_args
    assert kwargs.get("context") is None
