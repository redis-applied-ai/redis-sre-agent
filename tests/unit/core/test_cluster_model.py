"""Unit tests for RedisCluster and updated RedisInstance model validation."""

import pytest
from pydantic import SecretStr

from redis_sre_agent.core.clusters import RedisCluster, RedisClusterType
from redis_sre_agent.core.instances import RedisInstance, RedisInstanceType


class TestRedisClusterModel:
    """Validation tests for RedisCluster."""

    def test_create_enterprise_cluster_success(self):
        cluster = RedisCluster(
            id="cluster-1",
            name="Enterprise Cluster",
            cluster_type=RedisClusterType.redis_enterprise,
            environment="production",
            description="Primary enterprise cluster",
            admin_url="https://cluster.example.com:9443",
            admin_username="admin@redis.com",
            admin_password=SecretStr("secret"),
        )
        assert cluster.cluster_type == RedisClusterType.redis_enterprise

    def test_enterprise_requires_all_admin_fields(self):
        with pytest.raises(ValueError, match="requires admin_url, admin_username, and admin_password"):
            RedisCluster(
                id="cluster-1",
                name="Enterprise Cluster",
                cluster_type=RedisClusterType.redis_enterprise,
                environment="production",
                description="Primary enterprise cluster",
                admin_url="https://cluster.example.com:9443",
                admin_username="admin@redis.com",
                # Missing admin_password
            )

    def test_non_enterprise_rejects_admin_fields(self):
        with pytest.raises(
            ValueError, match="admin_url/admin_username/admin_password are only valid"
        ):
            RedisCluster(
                id="cluster-1",
                name="OSS Cluster",
                cluster_type=RedisClusterType.oss_cluster,
                environment="production",
                description="OSS cluster",
                admin_url="https://cluster.example.com:9443",
                admin_username="admin@redis.com",
                admin_password=SecretStr("secret"),
            )

    def test_environment_validation(self):
        with pytest.raises(ValueError, match="Environment must be one of"):
            RedisCluster(
                id="cluster-1",
                name="Cluster",
                cluster_type=RedisClusterType.unknown,
                environment="qa",
                description="Test cluster",
            )

    def test_created_by_validation(self):
        with pytest.raises(ValueError, match="created_by must be 'user' or 'agent'"):
            RedisCluster(
                id="cluster-1",
                name="Cluster",
                cluster_type=RedisClusterType.unknown,
                environment="test",
                description="Test cluster",
                created_by="system",
            )

    def test_admin_password_serializes_in_json_dump(self):
        cluster = RedisCluster(
            id="cluster-1",
            name="Enterprise Cluster",
            cluster_type=RedisClusterType.redis_enterprise,
            environment="production",
            description="Primary enterprise cluster",
            admin_url="https://cluster.example.com:9443",
            admin_username="admin@redis.com",
            admin_password=SecretStr("secret"),
        )
        dumped = cluster.model_dump(mode="json")
        assert dumped["admin_password"] == "secret"


class TestRedisInstanceModelPhase1:
    """Validation tests for updated RedisInstance model."""

    def test_cluster_id_optional_for_enterprise(self):
        inst = RedisInstance(
            id="redis-1",
            name="Enterprise DB",
            connection_url="redis://localhost:12000",
            environment="production",
            usage="cache",
            description="Enterprise DB instance",
            instance_type=RedisInstanceType.redis_enterprise,
            cluster_id=None,
        )
        assert inst.cluster_id is None

    def test_cluster_id_optional_for_oss_cluster(self):
        inst = RedisInstance(
            id="redis-1",
            name="OSS Cluster DB",
            connection_url="redis://localhost:7000",
            environment="production",
            usage="cache",
            description="OSS cluster database instance",
            instance_type=RedisInstanceType.oss_cluster,
            cluster_id=None,
        )
        assert inst.cluster_id is None

    def test_created_by_validation_unchanged(self):
        with pytest.raises(ValueError, match="created_by must be 'user' or 'agent'"):
            RedisInstance(
                id="redis-1",
                name="DB",
                connection_url="redis://localhost:6379",
                environment="test",
                usage="cache",
                description="DB instance",
                instance_type=RedisInstanceType.oss_single,
                created_by="system",
            )

