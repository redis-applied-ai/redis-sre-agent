"""Tests for shared CLI logging helpers."""

import logging
import os
from unittest.mock import patch

import click
import pytest
from click.testing import CliRunner

from redis_sre_agent.cli.logging_utils import log_cli_exception
from redis_sre_agent.cli.main import LazyGroup, main


def test_log_cli_exception_uses_explicit_exception_info_outside_except(caplog):
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        captured = exc

    with (
        patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}, clear=False),
        caplog.at_level(logging.DEBUG),
    ):
        log_cli_exception(__name__, "debug failure", captured)

    record = next(record for record in caplog.records if record.getMessage() == "debug failure")
    assert record.exc_info is not None
    assert record.exc_info[1] is captured


def test_lazy_group_skips_duplicate_logging_for_already_logged_exception():
    group = LazyGroup(name="test")
    ctx = click.Context(group)

    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        captured = exc

    with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}, clear=False):
        log_cli_exception(__name__, "command failure", captured)

        with patch("redis_sre_agent.cli.main.log_cli_exception") as mock_log:
            with patch.object(click.MultiCommand, "invoke", side_effect=captured):
                with pytest.raises(RuntimeError, match="boom"):
                    group.invoke(ctx)

    mock_log.assert_not_called()


def test_lazy_group_does_not_log_successful_click_exit():
    group = LazyGroup(name="test")
    ctx = click.Context(group)

    with patch("redis_sre_agent.cli.main.log_cli_exception") as mock_log:
        with patch.object(click.MultiCommand, "invoke", side_effect=click.exceptions.Exit(0)):
            with pytest.raises(click.exceptions.Exit) as raised:
                group.invoke(ctx)

    assert raised.value.exit_code == 0
    mock_log.assert_not_called()


def test_nested_help_does_not_log_cli_failure():
    result = CliRunner().invoke(main, ["pipeline", "--help"])
    combined_output = result.output
    if result.stderr:
        combined_output += result.stderr

    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "CLI command failed" not in combined_output
    assert "click.exceptions.Exit" not in combined_output
