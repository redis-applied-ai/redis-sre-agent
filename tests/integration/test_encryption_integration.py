"""Integration tests for encryption with instance storage."""

import base64
import os
from unittest.mock import patch

import pytest

from redis_sre_agent.core.encryption import is_encrypted
from redis_sre_agent.core.instances import (
    RedisInstance,
    get_instances,
    save_instances,
)


@pytest.fixture
def master_key():
    """Generate a test master key."""
    key = base64.b64encode(os.urandom(32)).decode()
    with patch.dict(os.environ, {"REDIS_SRE_MASTER_KEY": key}):
        yield key


@pytest.mark.asyncio
class TestEncryptionIntegration:
    """Test full encryption/decryption cycle with instance storage."""

    async def test_save_and_load_instance_with_encryption(self, master_key):
        """Test that instances are encrypted when saved and decrypted when loaded."""
        from unittest.mock import AsyncMock

        # Create instance with plaintext secrets
        instance = RedisInstance(
            id="test-123",
            name="Test Redis",
            connection_url="redis://user:password@localhost:6379/0",
            environment="test",
            usage="cache",
            description="Test instance",
            admin_password="admin-secret-123",
            created_by="user",
            instance_type="oss_single",
        )

        # Mock Redis client
        stored_data = None

        async def mock_set(key, value, **kwargs):
            nonlocal stored_data
            stored_data = value
            return True

        async def mock_get(key):
            return stored_data

        mock_redis = AsyncMock()
        mock_redis.set = mock_set
        mock_redis.get = mock_get

        with patch("redis_sre_agent.core.redis.get_redis_client", return_value=mock_redis):
            # Save instance
            result = await save_instances([instance])
            assert result is True

            # Verify data is encrypted in storage
            import json

            stored_instances = json.loads(stored_data)
            assert len(stored_instances) == 1
            stored_inst = stored_instances[0]

            # Check that connection_url is encrypted
            assert is_encrypted(stored_inst["connection_url"])
            assert stored_inst["connection_url"] != "redis://user:password@localhost:6379/0"

            # Check that admin_password is encrypted
            assert is_encrypted(stored_inst["admin_password"])
            assert stored_inst["admin_password"] != "admin-secret-123"

            # Load instances back
            loaded_instances = await get_instances()
            assert len(loaded_instances) == 1
            loaded_inst = loaded_instances[0]

            # Verify decrypted values match original
            assert loaded_inst.id == "test-123"
            assert loaded_inst.name == "Test Redis"

            # Extract connection_url (handle both SecretStr and str)
            if hasattr(loaded_inst.connection_url, "get_secret_value"):
                loaded_url = loaded_inst.connection_url.get_secret_value()
            else:
                loaded_url = str(loaded_inst.connection_url)
            assert loaded_url == "redis://user:password@localhost:6379/0"

            # Extract admin_password
            if hasattr(loaded_inst.admin_password, "get_secret_value"):
                loaded_pwd = loaded_inst.admin_password.get_secret_value()
            else:
                loaded_pwd = str(loaded_inst.admin_password)
            assert loaded_pwd == "admin-secret-123"

    async def test_multiple_instances_each_encrypted_differently(self, master_key):
        """Test that each instance gets unique encryption."""
        from unittest.mock import AsyncMock

        # Create two instances with same password
        instance1 = RedisInstance(
            id="test-1",
            name="Redis 1",
            connection_url="redis://localhost:6379",
            environment="test",
            usage="cache",
            description="Test 1",
            admin_password="same-password",
            created_by="user",
            instance_type="oss_single",
        )

        instance2 = RedisInstance(
            id="test-2",
            name="Redis 2",
            connection_url="redis://localhost:6380",
            environment="test",
            usage="cache",
            description="Test 2",
            admin_password="same-password",
            created_by="user",
            instance_type="oss_single",
        )

        stored_data = None

        async def mock_set(key, value, **kwargs):
            nonlocal stored_data
            stored_data = value
            return True

        async def mock_get(key):
            return stored_data

        mock_redis = AsyncMock()
        mock_redis.set = mock_set
        mock_redis.get = mock_get

        with patch("redis_sre_agent.core.redis.get_redis_client", return_value=mock_redis):
            # Save both instances
            result = await save_instances([instance1, instance2])
            assert result is True

            # Verify each has different encrypted values (unique DEKs)
            import json

            stored_instances = json.loads(stored_data)
            assert len(stored_instances) == 2

            encrypted_pwd1 = stored_instances[0]["admin_password"]
            encrypted_pwd2 = stored_instances[1]["admin_password"]

            # Same plaintext, but different ciphertext (unique DEKs)
            assert encrypted_pwd1 != encrypted_pwd2
            assert is_encrypted(encrypted_pwd1)
            assert is_encrypted(encrypted_pwd2)

            # Load and verify both decrypt correctly
            loaded_instances = await get_instances()
            assert len(loaded_instances) == 2

            for inst in loaded_instances:
                if hasattr(inst.admin_password, "get_secret_value"):
                    pwd = inst.admin_password.get_secret_value()
                else:
                    pwd = str(inst.admin_password)
                assert pwd == "same-password"

    async def test_instance_without_admin_password(self, master_key):
        """Test that instances without admin_password work correctly."""
        from unittest.mock import AsyncMock

        instance = RedisInstance(
            id="test-no-pwd",
            name="Redis No Password",
            connection_url="redis://localhost:6379",
            environment="test",
            usage="cache",
            description="No admin password",
            created_by="user",
            instance_type="oss_single",
        )

        stored_data = None

        async def mock_set(key, value, **kwargs):
            nonlocal stored_data
            stored_data = value
            return True

        async def mock_get(key):
            return stored_data

        mock_redis = AsyncMock()
        mock_redis.set = mock_set
        mock_redis.get = mock_get

        with patch("redis_sre_agent.core.redis.get_redis_client", return_value=mock_redis):
            # Save instance
            result = await save_instances([instance])
            assert result is True

            # Load back
            loaded_instances = await get_instances()
            assert len(loaded_instances) == 1
            assert loaded_instances[0].admin_password is None

    async def test_connection_url_is_plain_string_after_load(self, master_key):
        """Test that connection_url can be used as a plain string after loading."""
        from unittest.mock import AsyncMock

        instance = RedisInstance(
            id="test-url",
            name="Test URL",
            connection_url="redis://user:pass@host:6379/0",
            environment="test",
            usage="cache",
            description="Test",
            created_by="user",
            instance_type="oss_single",
        )

        stored_data = None

        async def mock_set(key, value, **kwargs):
            nonlocal stored_data
            stored_data = value
            return True

        async def mock_get(key):
            return stored_data

        mock_redis = AsyncMock()
        mock_redis.set = mock_set
        mock_redis.get = mock_get

        with patch("redis_sre_agent.core.redis.get_redis_client", return_value=mock_redis):
            await save_instances([instance])
            loaded_instances = await get_instances()

            loaded_inst = loaded_instances[0]

            # Should be able to extract URL for use with tools
            if hasattr(loaded_inst.connection_url, "get_secret_value"):
                url = loaded_inst.connection_url.get_secret_value()
            else:
                url = str(loaded_inst.connection_url)

            # Should be usable with urlparse
            from urllib.parse import urlparse

            parsed = urlparse(url)
            assert parsed.scheme == "redis"
            assert parsed.hostname == "host"
            assert parsed.port == 6379
            assert parsed.username == "user"
            assert parsed.password == "pass"
