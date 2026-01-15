"""Unit tests for instance management functions in core/instances.py."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from redis_sre_agent.core.instances import (
    InstanceQueryResult,
    RedisInstance,
    RedisInstanceType,
    _to_epoch,
    _upsert_instance_index_doc,
    add_session_instance,
    create_instance,
    delete_instance_index_doc,
    get_all_instances,
    get_instance_by_id,
    get_instance_by_name,
    get_instance_map,
    get_instance_name,
    get_instances,
    get_session_instances,
    mask_redis_url,
    query_instances,
    save_instances,
)


class TestMaskRedisUrl:
    """Test mask_redis_url function."""

    def test_mask_url_with_credentials(self):
        """Test masking URL with username and password."""
        url = "redis://user:password@localhost:6379/0"
        masked = mask_redis_url(url)
        assert "user" not in masked
        assert "password" not in masked
        assert "***:***@" in masked
        assert "localhost" in masked

    def test_mask_url_without_credentials(self):
        """Test URL without credentials is unchanged."""
        url = "redis://localhost:6379/0"
        masked = mask_redis_url(url)
        assert masked == url

    def test_mask_url_with_secret_str(self):
        """Test masking SecretStr URL."""
        url = SecretStr("redis://admin:secret@prod.redis.com:6379")
        masked = mask_redis_url(url)
        assert "admin" not in masked
        assert "secret" not in masked
        assert "***:***@" in masked

    def test_mask_url_with_query_params(self):
        """Test URL with query parameters."""
        url = "redis://user:pass@localhost:6379?ssl=true"
        masked = mask_redis_url(url)
        assert "ssl=true" in masked
        assert "***:***@" in masked

    def test_mask_url_invalid(self):
        """Test invalid URL returns as-is when no credentials."""
        # None gets converted to string "None" and returned as-is (no credentials)
        masked = mask_redis_url(None)
        assert masked == "None"

    def test_mask_url_exception_returns_placeholder(self):
        """Test exception in parsing returns generic masked placeholder."""
        # Create an object that will cause an exception when parsed
        class BadUrl:
            def __str__(self):
                raise ValueError("Cannot convert")

        masked = mask_redis_url(BadUrl())
        assert "***:***@" in masked


class TestToEpoch:
    """Test _to_epoch helper function."""

    def test_to_epoch_iso_string(self):
        """Test converting ISO timestamp."""
        ts = "2024-01-01T12:00:00+00:00"
        epoch = _to_epoch(ts)
        assert epoch > 0
        assert isinstance(epoch, float)

    def test_to_epoch_z_suffix(self):
        """Test ISO timestamp with Z suffix."""
        ts = "2024-01-01T12:00:00Z"
        epoch = _to_epoch(ts)
        assert epoch > 0

    def test_to_epoch_none(self):
        """Test None returns 0."""
        assert _to_epoch(None) == 0.0

    def test_to_epoch_empty(self):
        """Test empty string returns 0."""
        assert _to_epoch("") == 0.0

    def test_to_epoch_numeric_string(self):
        """Test numeric string is parsed as float."""
        epoch = _to_epoch("1704067200.0")
        assert epoch == 1704067200.0

    def test_to_epoch_invalid(self):
        """Test invalid string returns 0."""
        assert _to_epoch("not-a-date") == 0.0


class TestRedisInstanceModel:
    """Test RedisInstance Pydantic model."""

    def test_create_instance(self):
        """Test creating a basic instance."""
        inst = RedisInstance(
            id="redis-1",
            name="Test Instance",
            connection_url="redis://localhost:6379",
            environment="development",
            usage="cache",
            description="Test description",
            instance_type=RedisInstanceType.oss_single,
        )
        assert inst.id == "redis-1"
        assert inst.name == "Test Instance"
        assert inst.status == "unknown"

    def test_instance_type_enum(self):
        """Test RedisInstanceType enum values."""
        assert RedisInstanceType.oss_single.value == "oss_single"
        assert RedisInstanceType.redis_cloud.value == "redis_cloud"

    def test_created_by_validator_valid(self):
        """Test created_by validator with valid values."""
        inst = RedisInstance(
            id="redis-1",
            name="Test",
            connection_url="redis://localhost:6379",
            environment="dev",
            usage="cache",
            description="Test",
            instance_type=RedisInstanceType.oss_single,
            created_by="user",
        )
        assert inst.created_by == "user"

        inst2 = RedisInstance(
            id="redis-2",
            name="Test2",
            connection_url="redis://localhost:6380",
            environment="dev",
            usage="cache",
            description="Test",
            instance_type=RedisInstanceType.oss_single,
            created_by="agent",
        )
        assert inst2.created_by == "agent"

    def test_created_by_validator_invalid(self):
        """Test created_by validator with invalid value."""
        with pytest.raises(ValueError, match="created_by must be"):
            RedisInstance(
                id="redis-1",
                name="Test",
                connection_url="redis://localhost:6379",
                environment="dev",
                usage="cache",
                description="Test",
                instance_type=RedisInstanceType.oss_single,
                created_by="invalid",
            )

    def test_connection_url_serialization(self):
        """Test connection_url serialization with SecretStr."""
        inst = RedisInstance(
            id="redis-1",
            name="Test",
            connection_url=SecretStr("redis://secret:pass@localhost:6379"),
            environment="dev",
            usage="cache",
            description="Test",
            instance_type=RedisInstanceType.oss_single,
        )
        # The serializer should return the secret value when dumping to JSON
        dumped = inst.model_dump(mode="json")
        assert dumped["connection_url"] == "redis://secret:pass@localhost:6379"

    def test_admin_password_serialization(self):
        """Test admin_password serialization with SecretStr."""
        inst = RedisInstance(
            id="redis-1",
            name="Test",
            connection_url="redis://localhost:6379",
            environment="dev",
            usage="cache",
            description="Test",
            instance_type=RedisInstanceType.redis_enterprise,
            admin_password=SecretStr("admin-secret"),
        )
        # The serializer should return the secret value when dumping to JSON
        dumped = inst.model_dump(mode="json")
        assert dumped["admin_password"] == "admin-secret"


class TestGetBdbUid:
    """Test RedisInstance.get_bdb_uid method."""

    @pytest.mark.asyncio
    async def test_get_bdb_uid_not_redis_enterprise(self):
        """Test get_bdb_uid returns None for non-Redis Enterprise instances."""
        inst = RedisInstance(
            id="redis-1",
            name="Test",
            connection_url="redis://localhost:6379",
            environment="dev",
            usage="cache",
            description="Test",
            instance_type=RedisInstanceType.oss_single,
        )
        result = await inst.get_bdb_uid()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_bdb_uid_no_admin_url(self):
        """Test get_bdb_uid returns None when no admin_url."""
        inst = RedisInstance(
            id="redis-1",
            name="Test",
            connection_url="redis://localhost:6379",
            environment="dev",
            usage="cache",
            description="Test",
            instance_type=RedisInstanceType.redis_enterprise,
            admin_url=None,
        )
        result = await inst.get_bdb_uid()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_bdb_uid_by_name(self):
        """Test get_bdb_uid finds BDB by name."""
        inst = RedisInstance(
            id="redis-1",
            name="Test",
            connection_url="redis://localhost:6379",
            environment="dev",
            usage="cache",
            description="Test",
            instance_type=RedisInstanceType.redis_enterprise,
            admin_url="https://cluster.example.com:9443",
            admin_username="admin",
            admin_password=SecretStr("password"),
        )

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"name": "my-db", "uid": 1},
            {"name": "other-db", "uid": 2},
        ]
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await inst.get_bdb_uid(bdb_name="my-db")
            assert result == 1

    @pytest.mark.asyncio
    async def test_get_bdb_uid_by_port(self):
        """Test get_bdb_uid finds BDB by port."""
        inst = RedisInstance(
            id="redis-1",
            name="Test",
            connection_url="redis://localhost:12345",
            environment="dev",
            usage="cache",
            description="Test",
            instance_type=RedisInstanceType.redis_enterprise,
            admin_url="https://cluster.example.com:9443",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"name": "db1", "uid": 1, "port": 12345},
            {"name": "db2", "uid": 2, "port": 12346},
        ]
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await inst.get_bdb_uid()
            assert result == 1

    @pytest.mark.asyncio
    async def test_get_bdb_uid_by_ssl_port(self):
        """Test get_bdb_uid finds BDB by SSL port for rediss:// URLs."""
        inst = RedisInstance(
            id="redis-1",
            name="Test",
            connection_url="rediss://localhost:12345",  # TLS
            environment="dev",
            usage="cache",
            description="Test",
            instance_type=RedisInstanceType.redis_enterprise,
            admin_url="https://cluster.example.com:9443",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"name": "db1", "uid": 1, "ssl_port": 12345, "port": 12344},
        ]
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await inst.get_bdb_uid()
            assert result == 1

    @pytest.mark.asyncio
    async def test_get_bdb_uid_error(self):
        """Test get_bdb_uid returns None on error."""
        inst = RedisInstance(
            id="redis-1",
            name="Test",
            connection_url="redis://localhost:6379",
            environment="dev",
            usage="cache",
            description="Test",
            instance_type=RedisInstanceType.redis_enterprise,
            admin_url="https://cluster.example.com:9443",
        )

        with patch("httpx.AsyncClient", side_effect=Exception("Connection error")):
            result = await inst.get_bdb_uid()
            assert result is None


class TestGetInstances:
    """Test get_instances function."""

    @pytest.mark.asyncio
    async def test_get_instances_success(self):
        """Test getting instances from Redis."""
        mock_index = AsyncMock()
        mock_index.exists = AsyncMock(return_value=True)

        inst_data = {
            "id": "redis-1",
            "name": "Test",
            "connection_url": "redis://localhost:6379",
            "environment": "dev",
            "usage": "cache",
            "description": "Test",
            "instance_type": "oss_single",
        }
        mock_index.query = AsyncMock(return_value=[
            {"data": json.dumps(inst_data)}
        ])

        with (
            patch("redis_sre_agent.core.instances.get_instances_index", new_callable=AsyncMock, return_value=mock_index),
            patch("redis_sre_agent.core.instances._ensure_instances_index_exists", new_callable=AsyncMock),
            patch("redis_sre_agent.core.instances.get_secret_value", side_effect=lambda x: x),
        ):
            instances = await get_instances()
            assert len(instances) == 1
            assert instances[0].name == "Test"

    @pytest.mark.asyncio
    async def test_get_instances_empty(self):
        """Test getting instances when none exist."""
        mock_index = AsyncMock()
        mock_index.exists = AsyncMock(return_value=True)
        mock_index.query = AsyncMock(return_value=[])

        with (
            patch("redis_sre_agent.core.instances.get_instances_index", new_callable=AsyncMock, return_value=mock_index),
            patch("redis_sre_agent.core.instances._ensure_instances_index_exists", new_callable=AsyncMock),
        ):
            instances = await get_instances()
            assert instances == []

    @pytest.mark.asyncio
    async def test_get_instances_error(self):
        """Test get_instances returns empty list on error."""
        with patch(
            "redis_sre_agent.core.instances.get_instances_index",
            new_callable=AsyncMock,
            side_effect=Exception("Redis error"),
        ):
            instances = await get_instances()
            assert instances == []


class TestQueryInstances:
    """Test query_instances function."""

    @pytest.mark.asyncio
    async def test_query_instances_basic(self):
        """Test basic instance query."""
        mock_index = AsyncMock()
        mock_index.exists = AsyncMock(return_value=True)

        inst_data = {
            "id": "redis-1",
            "name": "Prod Cache",
            "connection_url": "redis://localhost:6379",
            "environment": "production",
            "usage": "cache",
            "description": "Production cache",
            "instance_type": "oss_single",
        }
        mock_index.query = AsyncMock(side_effect=[
            10,  # CountQuery result
            [{"data": json.dumps(inst_data)}],  # FilterQuery result
        ])

        with (
            patch("redis_sre_agent.core.instances.get_instances_index", new_callable=AsyncMock, return_value=mock_index),
            patch("redis_sre_agent.core.instances._ensure_instances_index_exists", new_callable=AsyncMock),
            patch("redis_sre_agent.core.instances.get_secret_value", side_effect=lambda x: x),
        ):
            result = await query_instances(environment="production")

            assert isinstance(result, InstanceQueryResult)
            assert len(result.instances) == 1
            assert result.instances[0].environment == "production"

    @pytest.mark.asyncio
    async def test_query_instances_with_filters(self):
        """Test query with multiple filters."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(side_effect=[0, []])  # No results

        with (
            patch("redis_sre_agent.core.instances.get_instances_index", new_callable=AsyncMock, return_value=mock_index),
            patch("redis_sre_agent.core.instances._ensure_instances_index_exists", new_callable=AsyncMock),
        ):
            result = await query_instances(
                environment="production",
                usage="cache",
                status="healthy",
                instance_type="oss_single",
                user_id="user-1",
                search="prod",
            )

            assert result.total == 0
            assert result.instances == []

    @pytest.mark.asyncio
    async def test_query_instances_error(self):
        """Test query_instances returns empty on error."""
        with patch(
            "redis_sre_agent.core.instances._ensure_instances_index_exists",
            new_callable=AsyncMock,
            side_effect=Exception("Index error"),
        ):
            result = await query_instances()
            assert result.instances == []
            assert result.total == 0


class TestUpsertInstanceIndexDoc:
    """Test _upsert_instance_index_doc function."""

    @pytest.mark.asyncio
    async def test_upsert_success(self):
        """Test successful index doc upsert."""
        mock_redis = AsyncMock()
        mock_redis.hset = AsyncMock(return_value=True)

        inst = RedisInstance(
            id="redis-1",
            name="Test",
            connection_url="redis://localhost:6379",
            environment="dev",
            usage="cache",
            description="Test",
            instance_type=RedisInstanceType.oss_single,
        )

        with (
            patch("redis_sre_agent.core.instances.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.instances._ensure_instances_index_exists", new_callable=AsyncMock),
            patch("redis_sre_agent.core.instances.encrypt_secret", side_effect=lambda x: x),
        ):
            result = await _upsert_instance_index_doc(inst)
            assert result is True
            mock_redis.hset.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_failure(self):
        """Test upsert failure returns False."""
        with patch(
            "redis_sre_agent.core.instances._ensure_instances_index_exists",
            new_callable=AsyncMock,
            side_effect=Exception("Error"),
        ):
            inst = RedisInstance(
                id="redis-1",
                name="Test",
                connection_url="redis://localhost:6379",
                environment="dev",
                usage="cache",
                description="Test",
                instance_type=RedisInstanceType.oss_single,
            )
            result = await _upsert_instance_index_doc(inst)
            assert result is False


class TestDeleteInstanceIndexDoc:
    """Test delete_instance_index_doc function."""

    @pytest.mark.asyncio
    async def test_delete_success(self):
        """Test successful deletion."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=1)

        with patch("redis_sre_agent.core.instances.get_redis_client", return_value=mock_redis):
            await delete_instance_index_doc("redis-1")
            mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_failure_silent(self):
        """Test delete failure is silent."""
        with patch(
            "redis_sre_agent.core.instances.get_redis_client",
            side_effect=Exception("Error"),
        ):
            # Should not raise
            await delete_instance_index_doc("redis-1")


class TestGetSessionInstances:
    """Test get_session_instances function."""

    @pytest.mark.asyncio
    async def test_get_session_instances_success(self):
        """Test getting session instances."""
        mock_redis = AsyncMock()
        inst_data = [{
            "id": "session-1",
            "name": "Session Instance",
            "connection_url": "redis://session:6379",
            "environment": "dev",
            "usage": "cache",
            "description": "Session",
            "instance_type": "oss_single",
        }]
        mock_redis.get = AsyncMock(return_value=json.dumps(inst_data).encode())

        with (
            patch("redis_sre_agent.core.instances.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.instances.get_secret_value", side_effect=lambda x: x),
        ):
            instances = await get_session_instances("thread-123")
            assert len(instances) == 1
            assert instances[0].name == "Session Instance"

    @pytest.mark.asyncio
    async def test_get_session_instances_empty(self):
        """Test getting session instances when none exist."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch("redis_sre_agent.core.instances.get_redis_client", return_value=mock_redis):
            instances = await get_session_instances("thread-123")
            assert instances == []

    @pytest.mark.asyncio
    async def test_get_session_instances_error(self):
        """Test get_session_instances returns empty on error."""
        with patch(
            "redis_sre_agent.core.instances.get_redis_client",
            side_effect=Exception("Error"),
        ):
            instances = await get_session_instances("thread-123")
            assert instances == []


class TestAddSessionInstance:
    """Test add_session_instance function."""

    @pytest.mark.asyncio
    async def test_add_session_instance_success(self):
        """Test adding session instance."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock(return_value=True)

        inst = RedisInstance(
            id="session-1",
            name="New Session",
            connection_url="redis://new:6379",
            environment="dev",
            usage="cache",
            description="New",
            instance_type=RedisInstanceType.oss_single,
        )

        with (
            patch("redis_sre_agent.core.instances.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.instances.encrypt_secret", side_effect=lambda x: x),
        ):
            result = await add_session_instance("thread-123", inst)
            assert result is True
            mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_session_instance_duplicate(self):
        """Test adding duplicate instance is skipped."""
        mock_redis = AsyncMock()
        existing = [{
            "id": "session-1",
            "name": "Existing",
            "connection_url": "redis://existing:6379",
            "environment": "dev",
            "usage": "cache",
            "description": "Existing",
            "instance_type": "oss_single",
        }]
        mock_redis.get = AsyncMock(return_value=json.dumps(existing).encode())

        inst = RedisInstance(
            id="session-2",
            name="Existing",  # Same name = duplicate
            connection_url="redis://new:6379",
            environment="dev",
            usage="cache",
            description="New",
            instance_type=RedisInstanceType.oss_single,
        )

        with (
            patch("redis_sre_agent.core.instances.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.instances.get_secret_value", side_effect=lambda x: x),
        ):
            result = await add_session_instance("thread-123", inst)
            assert result is True
            # set should not be called for duplicate
            mock_redis.set.assert_not_called()


class TestGetInstanceById:
    """Test get_instance_by_id function."""

    @pytest.mark.asyncio
    async def test_get_instance_by_id_success(self):
        """Test getting instance by ID."""
        mock_redis = AsyncMock()
        inst_data = {
            "id": "redis-1",
            "name": "Test",
            "connection_url": "redis://localhost:6379",
            "environment": "dev",
            "usage": "cache",
            "description": "Test",
            "instance_type": "oss_single",
        }
        mock_redis.hget = AsyncMock(return_value=json.dumps(inst_data).encode())

        with (
            patch("redis_sre_agent.core.instances.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.instances.get_secret_value", side_effect=lambda x: x),
        ):
            inst = await get_instance_by_id("redis-1")
            assert inst is not None
            assert inst.id == "redis-1"

    @pytest.mark.asyncio
    async def test_get_instance_by_id_not_found(self):
        """Test getting non-existent instance."""
        mock_redis = AsyncMock()
        mock_redis.hget = AsyncMock(return_value=None)

        with patch("redis_sre_agent.core.instances.get_redis_client", return_value=mock_redis):
            inst = await get_instance_by_id("non-existent")
            assert inst is None

    @pytest.mark.asyncio
    async def test_get_instance_by_id_error(self):
        """Test get_instance_by_id returns None on error."""
        with patch(
            "redis_sre_agent.core.instances.get_redis_client",
            side_effect=Exception("Error"),
        ):
            inst = await get_instance_by_id("redis-1")
            assert inst is None


class TestGetInstanceByName:
    """Test get_instance_by_name function."""

    @pytest.mark.asyncio
    async def test_get_instance_by_name_success(self):
        """Test getting instance by name."""
        mock_index = AsyncMock()
        inst_data = {
            "id": "redis-1",
            "name": "My Instance",
            "connection_url": "redis://localhost:6379",
            "environment": "dev",
            "usage": "cache",
            "description": "Test",
            "instance_type": "oss_single",
        }
        mock_index.query = AsyncMock(return_value=[{"data": json.dumps(inst_data)}])

        with (
            patch("redis_sre_agent.core.instances.get_instances_index", new_callable=AsyncMock, return_value=mock_index),
            patch("redis_sre_agent.core.instances._ensure_instances_index_exists", new_callable=AsyncMock),
            patch("redis_sre_agent.core.instances.get_secret_value", side_effect=lambda x: x),
        ):
            inst = await get_instance_by_name("My Instance")
            assert inst is not None
            assert inst.name == "My Instance"

    @pytest.mark.asyncio
    async def test_get_instance_by_name_not_found(self):
        """Test getting non-existent instance by name."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(return_value=[])

        with (
            patch("redis_sre_agent.core.instances.get_instances_index", new_callable=AsyncMock, return_value=mock_index),
            patch("redis_sre_agent.core.instances._ensure_instances_index_exists", new_callable=AsyncMock),
        ):
            inst = await get_instance_by_name("Non-existent")
            assert inst is None


class TestGetInstanceMap:
    """Test get_instance_map function."""

    @pytest.mark.asyncio
    async def test_get_instance_map(self):
        """Test getting instance map."""
        mock_instances = [
            RedisInstance(
                id="redis-1",
                name="Instance 1",
                connection_url="redis://localhost:6379",
                environment="dev",
                usage="cache",
                description="Test",
                instance_type=RedisInstanceType.oss_single,
            ),
            RedisInstance(
                id="redis-2",
                name="Instance 2",
                connection_url="redis://localhost:6380",
                environment="prod",
                usage="cache",
                description="Test",
                instance_type=RedisInstanceType.oss_single,
            ),
        ]

        with patch("redis_sre_agent.core.instances.get_instances", new_callable=AsyncMock, return_value=mock_instances):
            inst_map = await get_instance_map()
            assert "redis-1" in inst_map
            assert "redis-2" in inst_map
            assert inst_map["redis-1"].name == "Instance 1"


class TestGetInstanceName:
    """Test get_instance_name function."""

    @pytest.mark.asyncio
    async def test_get_instance_name_success(self):
        """Test getting instance name."""
        mock_inst = RedisInstance(
            id="redis-1",
            name="My Instance",
            connection_url="redis://localhost:6379",
            environment="dev",
            usage="cache",
            description="Test",
            instance_type=RedisInstanceType.oss_single,
        )

        with patch("redis_sre_agent.core.instances.get_instance_by_id", new_callable=AsyncMock, return_value=mock_inst):
            name = await get_instance_name("redis-1")
            assert name == "My Instance"

    @pytest.mark.asyncio
    async def test_get_instance_name_not_found(self):
        """Test getting name of non-existent instance."""
        with patch("redis_sre_agent.core.instances.get_instance_by_id", new_callable=AsyncMock, return_value=None):
            name = await get_instance_name("non-existent")
            assert name is None


class TestSaveInstances:
    """Test save_instances function."""

    @pytest.mark.asyncio
    async def test_save_instances_success(self):
        """Test saving instances."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=1)
        mock_redis.hset = AsyncMock(return_value=True)
        mock_redis.scan = AsyncMock(return_value=(0, []))

        mock_index = AsyncMock()
        mock_index.exists = AsyncMock(return_value=True)
        mock_index.query = AsyncMock(return_value=[])

        instances = [
            RedisInstance(
                id="redis-1",
                name="Instance 1",
                connection_url="redis://localhost:6379",
                environment="dev",
                usage="cache",
                description="Test",
                instance_type=RedisInstanceType.oss_single,
            )
        ]

        with (
            patch("redis_sre_agent.core.instances.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.instances.get_instances_index", new_callable=AsyncMock, return_value=mock_index),
            patch("redis_sre_agent.core.instances._ensure_instances_index_exists", new_callable=AsyncMock),
            patch("redis_sre_agent.core.instances.encrypt_secret", side_effect=lambda x: x),
        ):
            result = await save_instances(instances)
            assert result is True

    @pytest.mark.asyncio
    async def test_save_instances_error(self):
        """Test save_instances returns False on error."""
        with patch(
            "redis_sre_agent.core.instances.get_redis_client",
            side_effect=Exception("Error"),
        ):
            result = await save_instances([])
            assert result is False


class TestGetAllInstances:
    """Test get_all_instances function."""

    @pytest.mark.asyncio
    async def test_get_all_instances_basic(self):
        """Test getting all instances."""
        configured = [
            RedisInstance(
                id="redis-1",
                name="Configured",
                connection_url="redis://configured:6379",
                environment="dev",
                usage="cache",
                description="Test",
                instance_type=RedisInstanceType.oss_single,
            )
        ]

        with (
            patch("redis_sre_agent.core.instances.get_instances", new_callable=AsyncMock, return_value=configured),
            patch("redis_sre_agent.core.instances.get_session_instances", new_callable=AsyncMock, return_value=[]),
        ):
            instances = await get_all_instances()
            assert len(instances) == 1
            assert instances[0].name == "Configured"

    @pytest.mark.asyncio
    async def test_get_all_instances_with_session(self):
        """Test getting all instances including session instances."""
        configured = [
            RedisInstance(
                id="redis-1",
                name="Configured",
                connection_url="redis://configured:6379",
                environment="dev",
                usage="cache",
                description="Test",
                instance_type=RedisInstanceType.oss_single,
            )
        ]
        session = [
            RedisInstance(
                id="session-1",
                name="Session",
                connection_url="redis://session:6379",
                environment="dev",
                usage="cache",
                description="Session",
                instance_type=RedisInstanceType.oss_single,
            )
        ]

        with (
            patch("redis_sre_agent.core.instances.get_instances", new_callable=AsyncMock, return_value=configured),
            patch("redis_sre_agent.core.instances.get_session_instances", new_callable=AsyncMock, return_value=session),
        ):
            instances = await get_all_instances(thread_id="thread-123")
            assert len(instances) == 2

    @pytest.mark.asyncio
    async def test_get_all_instances_filter_by_user(self):
        """Test filtering instances by user_id."""
        configured = [
            RedisInstance(
                id="redis-1",
                name="User1 Instance",
                connection_url="redis://user1:6379",
                environment="dev",
                usage="cache",
                description="Test",
                instance_type=RedisInstanceType.oss_single,
                user_id="user-1",
            ),
            RedisInstance(
                id="redis-2",
                name="User2 Instance",
                connection_url="redis://user2:6379",
                environment="dev",
                usage="cache",
                description="Test",
                instance_type=RedisInstanceType.oss_single,
                user_id="user-2",
            ),
        ]

        with (
            patch("redis_sre_agent.core.instances.get_instances", new_callable=AsyncMock, return_value=configured),
            patch("redis_sre_agent.core.instances.get_session_instances", new_callable=AsyncMock, return_value=[]),
        ):
            instances = await get_all_instances(user_id="user-1")
            assert len(instances) == 1
            assert instances[0].user_id == "user-1"


class TestCreateInstance:
    """Test create_instance function."""

    @pytest.mark.asyncio
    async def test_create_instance_success(self):
        """Test creating a new instance."""
        with (
            patch("redis_sre_agent.core.instances.get_instances", new_callable=AsyncMock, return_value=[]),
            patch("redis_sre_agent.core.instances.save_instances", new_callable=AsyncMock, return_value=True),
        ):
            inst = await create_instance(
                name="New Instance",
                connection_url="redis://new:6379",
                environment="production",
                usage="cache",
                description="New production cache",
            )
            assert inst is not None
            assert inst.name == "New Instance"
            assert inst.environment == "production"
            assert inst.created_by == "agent"

    @pytest.mark.asyncio
    async def test_create_instance_duplicate_name(self):
        """Test creating instance with duplicate name fails."""
        existing = [
            RedisInstance(
                id="redis-1",
                name="Existing",
                connection_url="redis://existing:6379",
                environment="dev",
                usage="cache",
                description="Existing",
                instance_type=RedisInstanceType.oss_single,
            )
        ]

        with patch("redis_sre_agent.core.instances.get_instances", new_callable=AsyncMock, return_value=existing):
            with pytest.raises(ValueError, match="already exists"):
                await create_instance(
                    name="Existing",
                    connection_url="redis://new:6379",
                    environment="production",
                    usage="cache",
                    description="New",
                )

    @pytest.mark.asyncio
    async def test_create_instance_save_failure(self):
        """Test create_instance raises on save failure."""
        with (
            patch("redis_sre_agent.core.instances.get_instances", new_callable=AsyncMock, return_value=[]),
            patch("redis_sre_agent.core.instances.save_instances", new_callable=AsyncMock, return_value=False),
        ):
            with pytest.raises(ValueError, match="Failed to save"):
                await create_instance(
                    name="New Instance",
                    connection_url="redis://new:6379",
                    environment="production",
                    usage="cache",
                    description="New",
                )


class TestGetInstancesEdgeCases:
    """Test edge cases for get_instances function."""

    @pytest.mark.asyncio
    async def test_get_instances_bytes_data(self):
        """Test get_instances handles bytes data."""
        mock_index = AsyncMock()
        mock_index.exists = AsyncMock(return_value=True)

        inst_data = {
            "id": "redis-1",
            "name": "Test",
            "connection_url": "redis://localhost:6379",
            "environment": "dev",
            "usage": "cache",
            "description": "Test",
            "instance_type": "oss_single",
        }
        # Return bytes instead of string
        mock_index.query = AsyncMock(return_value=[
            {"data": json.dumps(inst_data).encode("utf-8")}
        ])

        with (
            patch("redis_sre_agent.core.instances.get_instances_index", new_callable=AsyncMock, return_value=mock_index),
            patch("redis_sre_agent.core.instances._ensure_instances_index_exists", new_callable=AsyncMock),
            patch("redis_sre_agent.core.instances.get_secret_value", side_effect=lambda x: x),
        ):
            instances = await get_instances()
            assert len(instances) == 1

    @pytest.mark.asyncio
    async def test_get_instances_count_exception(self):
        """Test get_instances handles count query exception."""
        mock_index = AsyncMock()
        mock_index.exists = AsyncMock(return_value=True)

        inst_data = {
            "id": "redis-1",
            "name": "Test",
            "connection_url": "redis://localhost:6379",
            "environment": "dev",
            "usage": "cache",
            "description": "Test",
            "instance_type": "oss_single",
        }
        # First call (CountQuery) raises, second call (FilterQuery) succeeds
        mock_index.query = AsyncMock(side_effect=[
            Exception("Count failed"),
            [{"data": json.dumps(inst_data)}],
        ])

        with (
            patch("redis_sre_agent.core.instances.get_instances_index", new_callable=AsyncMock, return_value=mock_index),
            patch("redis_sre_agent.core.instances._ensure_instances_index_exists", new_callable=AsyncMock),
            patch("redis_sre_agent.core.instances.get_secret_value", side_effect=lambda x: x),
        ):
            instances = await get_instances()
            assert len(instances) == 1

    @pytest.mark.asyncio
    async def test_get_instances_invalid_doc(self):
        """Test get_instances skips invalid documents."""
        mock_index = AsyncMock()
        mock_index.exists = AsyncMock(return_value=True)

        # Return invalid JSON
        mock_index.query = AsyncMock(return_value=[
            {"data": "not valid json"},
            {"data": None},  # No data
        ])

        with (
            patch("redis_sre_agent.core.instances.get_instances_index", new_callable=AsyncMock, return_value=mock_index),
            patch("redis_sre_agent.core.instances._ensure_instances_index_exists", new_callable=AsyncMock),
        ):
            instances = await get_instances()
            assert instances == []


class TestQueryInstancesEdgeCases:
    """Test edge cases for query_instances function."""

    @pytest.mark.asyncio
    async def test_query_instances_bytes_data(self):
        """Test query_instances handles bytes data."""
        mock_index = AsyncMock()

        inst_data = {
            "id": "redis-1",
            "name": "Test",
            "connection_url": "redis://localhost:6379",
            "environment": "dev",
            "usage": "cache",
            "description": "Test",
            "instance_type": "oss_single",
        }
        mock_index.query = AsyncMock(side_effect=[
            1,  # CountQuery
            [{"data": json.dumps(inst_data).encode("utf-8")}],  # FilterQuery with bytes
        ])

        with (
            patch("redis_sre_agent.core.instances.get_instances_index", new_callable=AsyncMock, return_value=mock_index),
            patch("redis_sre_agent.core.instances._ensure_instances_index_exists", new_callable=AsyncMock),
            patch("redis_sre_agent.core.instances.get_secret_value", side_effect=lambda x: x),
        ):
            result = await query_instances()
            assert len(result.instances) == 1

    @pytest.mark.asyncio
    async def test_query_instances_invalid_doc(self):
        """Test query_instances skips invalid documents."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(side_effect=[
            1,  # CountQuery
            [{"data": "invalid json"}],  # Invalid JSON
        ])

        with (
            patch("redis_sre_agent.core.instances.get_instances_index", new_callable=AsyncMock, return_value=mock_index),
            patch("redis_sre_agent.core.instances._ensure_instances_index_exists", new_callable=AsyncMock),
        ):
            result = await query_instances()
            assert result.instances == []


class TestSaveInstancesEdgeCases:
    """Test edge cases for save_instances function."""

    @pytest.mark.asyncio
    async def test_save_instances_with_stale_cleanup(self):
        """Test save_instances cleans up stale documents."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=1)
        mock_redis.hset = AsyncMock(return_value=True)

        mock_index = AsyncMock()
        mock_index.exists = AsyncMock(return_value=True)

        # Existing docs include one that's not in the new list
        existing_data = {
            "id": "stale-instance",
            "name": "Stale",
            "connection_url": "redis://stale:6379",
            "environment": "dev",
            "usage": "cache",
            "description": "Stale",
            "instance_type": "oss_single",
        }
        mock_index.query = AsyncMock(side_effect=[
            1,  # CountQuery
            [{"data": json.dumps(existing_data)}],  # FilterQuery returns stale doc
        ])

        new_instances = [
            RedisInstance(
                id="redis-1",
                name="New Instance",
                connection_url="redis://new:6379",
                environment="dev",
                usage="cache",
                description="New",
                instance_type=RedisInstanceType.oss_single,
            )
        ]

        with (
            patch("redis_sre_agent.core.instances.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.instances.get_instances_index", new_callable=AsyncMock, return_value=mock_index),
            patch("redis_sre_agent.core.instances._ensure_instances_index_exists", new_callable=AsyncMock),
            patch("redis_sre_agent.core.instances.encrypt_secret", side_effect=lambda x: x),
        ):
            result = await save_instances(new_instances)
            assert result is True
            # Should have deleted the stale instance
            assert mock_redis.delete.call_count >= 1


class TestAddSessionInstanceEdgeCases:
    """Test edge cases for add_session_instance function."""

    @pytest.mark.asyncio
    async def test_add_session_instance_duplicate_url(self):
        """Test adding instance with duplicate URL is skipped."""
        mock_redis = AsyncMock()
        existing = [{
            "id": "session-1",
            "name": "Existing",
            "connection_url": "redis://same:6379",
            "environment": "dev",
            "usage": "cache",
            "description": "Existing",
            "instance_type": "oss_single",
        }]
        mock_redis.get = AsyncMock(return_value=json.dumps(existing).encode())

        inst = RedisInstance(
            id="session-2",
            name="Different Name",
            connection_url="redis://same:6379",  # Same URL = duplicate
            environment="dev",
            usage="cache",
            description="New",
            instance_type=RedisInstanceType.oss_single,
        )

        with (
            patch("redis_sre_agent.core.instances.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.instances.get_secret_value", side_effect=lambda x: x),
        ):
            result = await add_session_instance("thread-123", inst)
            assert result is True
            # set should not be called for duplicate
            mock_redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_session_instance_error(self):
        """Test add_session_instance returns False on error."""
        with patch(
            "redis_sre_agent.core.instances.get_redis_client",
            side_effect=Exception("Error"),
        ):
            inst = RedisInstance(
                id="session-1",
                name="Test",
                connection_url="redis://test:6379",
                environment="dev",
                usage="cache",
                description="Test",
                instance_type=RedisInstanceType.oss_single,
            )
            result = await add_session_instance("thread-123", inst)
            assert result is False


class TestGetInstanceByNameEdgeCases:
    """Test edge cases for get_instance_by_name function."""

    @pytest.mark.asyncio
    async def test_get_instance_by_name_bytes_data(self):
        """Test get_instance_by_name handles bytes data."""
        mock_index = AsyncMock()
        inst_data = {
            "id": "redis-1",
            "name": "My Instance",
            "connection_url": "redis://localhost:6379",
            "environment": "dev",
            "usage": "cache",
            "description": "Test",
            "instance_type": "oss_single",
        }
        mock_index.query = AsyncMock(return_value=[{"data": json.dumps(inst_data).encode("utf-8")}])

        with (
            patch("redis_sre_agent.core.instances.get_instances_index", new_callable=AsyncMock, return_value=mock_index),
            patch("redis_sre_agent.core.instances._ensure_instances_index_exists", new_callable=AsyncMock),
            patch("redis_sre_agent.core.instances.get_secret_value", side_effect=lambda x: x),
        ):
            inst = await get_instance_by_name("My Instance")
            assert inst is not None
            assert inst.name == "My Instance"

    @pytest.mark.asyncio
    async def test_get_instance_by_name_no_data(self):
        """Test get_instance_by_name returns None when data is empty."""
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(return_value=[{"data": None}])

        with (
            patch("redis_sre_agent.core.instances.get_instances_index", new_callable=AsyncMock, return_value=mock_index),
            patch("redis_sre_agent.core.instances._ensure_instances_index_exists", new_callable=AsyncMock),
        ):
            inst = await get_instance_by_name("My Instance")
            assert inst is None

    @pytest.mark.asyncio
    async def test_get_instance_by_name_error(self):
        """Test get_instance_by_name returns None on error."""
        with patch(
            "redis_sre_agent.core.instances._ensure_instances_index_exists",
            new_callable=AsyncMock,
            side_effect=Exception("Error"),
        ):
            inst = await get_instance_by_name("My Instance")
            assert inst is None


class TestGetInstanceByIdEdgeCases:
    """Test edge cases for get_instance_by_id function."""

    @pytest.mark.asyncio
    async def test_get_instance_by_id_bytes_data(self):
        """Test get_instance_by_id handles bytes data."""
        mock_redis = AsyncMock()
        inst_data = {
            "id": "redis-1",
            "name": "Test",
            "connection_url": "redis://localhost:6379",
            "environment": "dev",
            "usage": "cache",
            "description": "Test",
            "instance_type": "oss_single",
        }
        mock_redis.hget = AsyncMock(return_value=json.dumps(inst_data).encode("utf-8"))

        with (
            patch("redis_sre_agent.core.instances.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.instances.get_secret_value", side_effect=lambda x: x),
        ):
            inst = await get_instance_by_id("redis-1")
            assert inst is not None
            assert inst.id == "redis-1"

    @pytest.mark.asyncio
    async def test_get_instance_by_id_with_admin_password(self):
        """Test get_instance_by_id handles admin_password."""
        mock_redis = AsyncMock()
        inst_data = {
            "id": "redis-1",
            "name": "Test",
            "connection_url": "redis://localhost:6379",
            "environment": "dev",
            "usage": "cache",
            "description": "Test",
            "instance_type": "redis_enterprise",
            "admin_password": "encrypted-password",
        }
        mock_redis.hget = AsyncMock(return_value=json.dumps(inst_data))

        with (
            patch("redis_sre_agent.core.instances.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.instances.get_secret_value", side_effect=lambda x: x),
        ):
            inst = await get_instance_by_id("redis-1")
            assert inst is not None


class TestGetBdbUidEdgeCases:
    """Test additional edge cases for get_bdb_uid."""

    @pytest.mark.asyncio
    async def test_get_bdb_uid_with_endpoints_fallback(self):
        """Test get_bdb_uid uses endpoints array when port is None."""
        inst = RedisInstance(
            id="redis-1",
            name="Test",
            connection_url="redis://localhost:12345",
            environment="dev",
            usage="cache",
            description="Test",
            instance_type=RedisInstanceType.redis_enterprise,
            admin_url="https://cluster.example.com:9443",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "name": "db1",
                "uid": 1,
                "port": None,  # No port, use endpoints
                "endpoints": [{"port": 12345, "tls": False}],
            },
        ]
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await inst.get_bdb_uid()
            assert result == 1

    @pytest.mark.asyncio
    async def test_get_bdb_uid_dict_response(self):
        """Test get_bdb_uid handles dict response with bdbs key."""
        inst = RedisInstance(
            id="redis-1",
            name="Test",
            connection_url="redis://localhost:12345",
            environment="dev",
            usage="cache",
            description="Test",
            instance_type=RedisInstanceType.redis_enterprise,
            admin_url="https://cluster.example.com:9443",
        )

        mock_response = MagicMock()
        # Some versions return {"bdbs": [...]} instead of [...]
        mock_response.json.return_value = {
            "bdbs": [{"name": "my-db", "uid": 1, "port": 12345}]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await inst.get_bdb_uid()
            assert result == 1

    @pytest.mark.asyncio
    async def test_get_bdb_uid_no_match(self):
        """Test get_bdb_uid returns None when no match found."""
        inst = RedisInstance(
            id="redis-1",
            name="Test",
            connection_url="redis://localhost:99999",  # Port that doesn't match
            environment="dev",
            usage="cache",
            description="Test",
            instance_type=RedisInstanceType.redis_enterprise,
            admin_url="https://cluster.example.com:9443",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"name": "db1", "uid": 1, "port": 12345},
        ]
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await inst.get_bdb_uid()
            assert result is None

    @pytest.mark.asyncio
    async def test_get_bdb_uid_verify_ssl_env(self):
        """Test get_bdb_uid respects TOOLS_REDIS_ENTERPRISE_ADMIN_VERIFY_SSL env."""
        import os

        inst = RedisInstance(
            id="redis-1",
            name="Test",
            connection_url="redis://localhost:12345",
            environment="dev",
            usage="cache",
            description="Test",
            instance_type=RedisInstanceType.redis_enterprise,
            admin_url="https://cluster.example.com:9443",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = [{"name": "db1", "uid": 1, "port": 12345}]
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.dict(os.environ, {"TOOLS_REDIS_ENTERPRISE_ADMIN_VERIFY_SSL": "false"}),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await inst.get_bdb_uid()
            assert result == 1


class TestEnsureInstancesIndexExists:
    """Test _ensure_instances_index_exists function."""

    @pytest.mark.asyncio
    async def test_ensure_index_creates_when_not_exists(self):
        """Test index is created when it doesn't exist."""
        from redis_sre_agent.core.instances import _ensure_instances_index_exists

        mock_index = AsyncMock()
        mock_index.exists = AsyncMock(return_value=False)
        mock_index.create = AsyncMock()

        with patch("redis_sre_agent.core.instances.get_instances_index", new_callable=AsyncMock, return_value=mock_index):
            await _ensure_instances_index_exists()
            mock_index.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_index_skips_when_exists(self):
        """Test index creation is skipped when it exists."""
        from redis_sre_agent.core.instances import _ensure_instances_index_exists

        mock_index = AsyncMock()
        mock_index.exists = AsyncMock(return_value=True)
        mock_index.create = AsyncMock()

        with patch("redis_sre_agent.core.instances.get_instances_index", new_callable=AsyncMock, return_value=mock_index):
            await _ensure_instances_index_exists()
            mock_index.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_index_handles_error(self):
        """Test _ensure_instances_index_exists handles errors gracefully."""
        from redis_sre_agent.core.instances import _ensure_instances_index_exists

        with patch(
            "redis_sre_agent.core.instances.get_instances_index",
            new_callable=AsyncMock,
            side_effect=Exception("Index error"),
        ):
            # Should not raise
            await _ensure_instances_index_exists()


class TestGetInstancesWithAdminPassword:
    """Test get_instances with admin_password handling."""

    @pytest.mark.asyncio
    async def test_get_instances_with_admin_password(self):
        """Test get_instances handles admin_password field."""
        mock_index = AsyncMock()
        mock_index.exists = AsyncMock(return_value=True)

        inst_data = {
            "id": "redis-1",
            "name": "Test",
            "connection_url": "redis://localhost:6379",
            "environment": "dev",
            "usage": "cache",
            "description": "Test",
            "instance_type": "redis_enterprise",
            "admin_password": "encrypted-password",
        }
        mock_index.query = AsyncMock(return_value=[{"data": json.dumps(inst_data)}])

        with (
            patch("redis_sre_agent.core.instances.get_instances_index", new_callable=AsyncMock, return_value=mock_index),
            patch("redis_sre_agent.core.instances._ensure_instances_index_exists", new_callable=AsyncMock),
            patch("redis_sre_agent.core.instances.get_secret_value", side_effect=lambda x: x),
        ):
            instances = await get_instances()
            assert len(instances) == 1
