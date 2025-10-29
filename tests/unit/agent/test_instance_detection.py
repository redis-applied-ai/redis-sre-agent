"""Tests for instance type detection and credential masking."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from redis_sre_agent.agent.langgraph_agent import (
    _detect_instance_type_with_llm,
    _mask_redis_url_credentials,
)
from redis_sre_agent.core.instances import RedisInstance


@pytest.fixture
def redis_enterprise_instance():
    """Create a Redis Enterprise instance for testing."""
    return RedisInstance(
        id="test-enterprise",
        name="Redis Enterprise Demo",
        connection_url="redis://admin:secretpassword@redis-enterprise:12000/0",
        environment="production",
        usage="enterprise",
        description="Redis Enterprise Software database with advanced clustering",
        notes="Redis Enterprise cluster with 100MB database on port 12000",
        instance_type="unknown",
    )


@pytest.fixture
def oss_single_instance():
    """Create an OSS single instance for testing."""
    return RedisInstance(
        id="test-oss",
        name="Redis OSS Cache",
        connection_url="redis://user:pass@localhost:6379/0",
        environment="development",
        usage="cache",
        description="Standard Redis OSS instance for caching",
        instance_type="unknown",
    )


@pytest.mark.asyncio
async def test_detect_instance_type_masks_credentials(redis_enterprise_instance):
    """Test that credentials are masked when sending to LLM."""
    # Mock the LLM
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "redis_enterprise"
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    # Call detection
    detected_type = await _detect_instance_type_with_llm(redis_enterprise_instance, mock_llm)

    # Verify LLM was called
    assert mock_llm.ainvoke.called
    call_args = mock_llm.ainvoke.call_args[0][0]
    prompt = call_args[0].content

    # Verify credentials are NOT in the connection URL part of the prompt
    # Note: "admin" might appear in other parts like "admin API" which is fine
    assert "admin:secretpassword" not in prompt
    assert "redis://admin:" not in prompt
    assert "secretpassword@" not in prompt

    # Verify masked URL IS in the prompt
    assert "***:***@redis-enterprise:12000" in prompt
    assert "redis://***:***@redis-enterprise:12000/0" in prompt

    # Verify other metadata IS in the prompt (needed for detection)
    assert "redis-enterprise" in prompt
    assert "12000" in prompt
    assert "Redis Enterprise" in prompt

    # Verify detection result
    assert detected_type == "redis_enterprise"


@pytest.mark.asyncio
async def test_detect_instance_type_enterprise(redis_enterprise_instance):
    """Test detection of Redis Enterprise instance."""
    # Mock the LLM to return enterprise
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "redis_enterprise"
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    detected_type = await _detect_instance_type_with_llm(redis_enterprise_instance, mock_llm)

    assert detected_type == "redis_enterprise"


@pytest.mark.asyncio
async def test_detect_instance_type_oss_single(oss_single_instance):
    """Test detection of OSS single instance."""
    # Mock the LLM to return oss_single
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "oss_single"
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    detected_type = await _detect_instance_type_with_llm(oss_single_instance, mock_llm)

    assert detected_type == "oss_single"


@pytest.mark.asyncio
async def test_detect_instance_type_invalid_response():
    """Test handling of invalid LLM response."""
    instance = RedisInstance(
        id="test",
        name="Test",
        connection_url="redis://localhost:6379",
        environment="test",
        usage="cache",
        description="Test instance",
        instance_type="unknown",
    )

    # Mock the LLM to return invalid type
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "invalid_type"
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    detected_type = await _detect_instance_type_with_llm(instance, mock_llm)

    # Should default to unknown for invalid responses
    assert detected_type == "unknown"


@pytest.mark.asyncio
async def test_detect_instance_type_llm_error():
    """Test handling of LLM errors."""
    instance = RedisInstance(
        id="test",
        name="Test",
        connection_url="redis://localhost:6379",
        environment="test",
        usage="cache",
        description="Test instance",
        instance_type="unknown",
    )

    # Mock the LLM to raise an error
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM API error"))

    detected_type = await _detect_instance_type_with_llm(instance, mock_llm)

    # Should return unknown on error
    assert detected_type == "unknown"


def test_mask_credentials_comprehensive():
    """Comprehensive test of credential masking edge cases."""
    test_cases = [
        # (input_url, expected_output, description)
        (
            "redis://user:pass@host:6379/0",
            "redis://***:***@host:6379/0",
            "Standard credentials",
        ),
        (
            "redis://admin%40redis.com:admin@redis-enterprise:12000/0",
            "redis://***:***@redis-enterprise:12000/0",
            "URL-encoded username",
        ),
        (
            "redis://:password@host:6379",
            "redis://***:***@host:6379",
            "Password only",
        ),
        (
            "redis://localhost:6379",
            "redis://localhost:6379",
            "No credentials",
        ),
        (
            "rediss://user:pass@secure:6380/0",
            "rediss://***:***@secure:6380/0",
            "SSL connection",
        ),
        (
            "redis://user:p@ss!w0rd@host:6379",
            "redis://***:***@host:6379",
            "Special chars in password",
        ),
        (
            "redis://user:pass@host:6379/5?timeout=10",
            "redis://***:***@host:6379/5?timeout=10",
            "With query params",
        ),
    ]

    for input_url, expected, description in test_cases:
        result = _mask_redis_url_credentials(input_url)
        assert result == expected, f"Failed for: {description}"

        # Verify no credentials leaked
        if "@" in input_url and ":" in input_url.split("@")[0].split("//")[1]:
            creds_part = input_url.split("@")[0].split("//")[1]
            if ":" in creds_part:
                username, password = creds_part.split(":", 1)
                if username and username != "***":
                    assert username not in result, f"Username leaked in: {description}"
                if password and password != "***":
                    assert password not in result, f"Password leaked in: {description}"


def test_mask_credentials_preserves_important_info():
    """Test that masking preserves hostname and port for detection."""
    url = "redis://admin:secret@redis-enterprise:12000/0"
    masked = _mask_redis_url_credentials(url)

    # Should preserve these for instance type detection
    assert "redis-enterprise" in masked
    assert "12000" in masked
    assert "/0" in masked

    # Should mask these
    assert "admin" not in masked
    assert "secret" not in masked
