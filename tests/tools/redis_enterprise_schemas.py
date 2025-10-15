"""Pydantic schemas for Redis Enterprise admin API responses.

⚠️  THESE SCHEMAS ARE ONLY USED IN TESTS ⚠️

These schemas validate that our mock test responses match the actual API structure.
They are NOT used at runtime in the provider - the provider accepts raw JSON responses.

Based on the official Redis Enterprise REST API documentation:
https://redis.io/docs/latest/operate/rs/references/rest-api/objects/

Purpose:
- Validate mock responses in tests match real API structure
- Catch breaking changes in test data
- Document expected response formats
- Provide type hints for test data construction
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class BDBEndpoint(BaseModel):
    """Database endpoint information."""

    uid: int
    dns_name: str
    port: int
    addr: Optional[List[str]] = None
    proxy_policy: Optional[str] = None
    addr_type: Optional[str] = None


class BDBObject(BaseModel):
    """BDB (database) object schema.

    Based on: https://redis.io/docs/latest/operate/rs/references/rest-api/objects/bdb/
    """

    uid: int
    name: str
    type: Literal["redis", "memcached"]
    memory_size: int
    status: Optional[
        Literal[
            "pending",
            "active",
            "active-change-pending",
            "delete-pending",
            "import-pending",
            "creation-failed",
            "recovery",
        ]
    ] = None
    shards_count: Optional[int] = Field(None, ge=1, le=512)
    replication: Optional[bool] = None
    replica_sources: Optional[List[Dict[str, Any]]] = None
    replica_sync: Optional[Literal["enabled", "disabled", "paused", "stopped"]] = None
    data_persistence: Optional[Literal["disabled", "snapshot", "aof"]] = None
    aof_policy: Optional[Literal["appendfsync-every-sec", "appendfsync-always"]] = None
    snapshot_policy: Optional[List[Dict[str, Any]]] = None
    eviction_policy: Optional[
        Literal[
            "volatile-lru",
            "volatile-ttl",
            "volatile-random",
            "allkeys-lru",
            "allkeys-random",
            "noeviction",
            "volatile-lfu",
            "allkeys-lfu",
        ]
    ] = None
    oss_cluster: Optional[bool] = None
    sharding: Optional[bool] = None
    port: Optional[int] = None
    endpoints: Optional[List[BDBEndpoint]] = None
    redis_version: Optional[str] = None
    version: Optional[str] = None
    created_time: Optional[str] = None
    last_changed_time: Optional[str] = None
    backup: Optional[bool] = None
    backup_status: Optional[Literal["exporting", "succeeded", "failed"]] = None
    import_status: Optional[Literal["idle", "initializing", "importing", "succeeded", "failed"]] = (
        None
    )
    crdt: Optional[bool] = None
    crdt_sync: Optional[Literal["enabled", "disabled", "paused", "stopped"]] = None
    module_list: Optional[List[Dict[str, Any]]] = None
    rack_aware: Optional[bool] = None
    tls_mode: Optional[Literal["enabled", "disabled", "replica_ssl"]] = None
    max_connections: Optional[int] = None
    shard_list: Optional[List[int]] = None

    class Config:
        extra = "allow"  # Allow additional fields from API


class NodeObject(BaseModel):
    """Node object schema.

    Based on: https://redis.io/docs/latest/operate/rs/references/rest-api/objects/node/
    """

    uid: int
    addr: str
    status: Literal["active", "down", "provisioning"]
    accept_servers: bool  # False = maintenance mode
    shard_count: Optional[int] = None
    total_memory: Optional[int] = None
    available_memory: Optional[int] = None
    ephemeral_storage_size: Optional[int] = None
    ephemeral_storage_avail: Optional[int] = None
    persistent_storage_size: Optional[int] = None
    persistent_storage_avail: Optional[int] = None
    cores: Optional[int] = None
    bigstore_driver: Optional[str] = None
    rack_id: Optional[str] = None
    software_version: Optional[str] = None
    uptime: Optional[int] = None
    os_version: Optional[str] = None

    class Config:
        extra = "allow"


class ShardObject(BaseModel):
    """Shard object schema.

    Based on: https://redis.io/docs/latest/operate/rs/references/rest-api/objects/shard/
    """

    uid: int
    bdb_uid: int
    node_uid: int
    role: Literal["master", "slave"]
    slots: Optional[str] = None  # e.g., "0-8191"
    status: Optional[Literal["active", "down", "loading"]] = None
    loading_progress: Optional[float] = None
    assigned_slots: Optional[str] = None
    detailed_status: Optional[str] = None

    class Config:
        extra = "allow"


class ActionObject(BaseModel):
    """Action object schema.

    Based on: https://redis.io/docs/latest/operate/rs/references/rest-api/objects/action/
    """

    action_uid: str
    name: str
    status: Literal["queued", "running", "completed", "failed"]
    progress: Optional[float] = Field(None, ge=0, le=100)
    creation_time: Optional[int] = None
    additional_info: Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow"


class ModuleObject(BaseModel):
    """Module object schema.

    Based on: https://redis.io/docs/latest/operate/rs/references/rest-api/objects/module/
    """

    module_name: str
    semantic_version: str
    display_name: Optional[str] = None
    author: Optional[str] = None
    architecture: Optional[str] = None
    command_line_args: Optional[str] = None
    config_command: Optional[str] = None
    capabilities: Optional[List[str]] = None
    min_redis_version: Optional[str] = None
    min_redis_pack_version: Optional[str] = None

    class Config:
        extra = "allow"


class ClusterObject(BaseModel):
    """Cluster object schema.

    Based on: https://redis.io/docs/latest/operate/rs/references/rest-api/objects/cluster/
    """

    name: str
    nodes_count: Optional[int] = None
    shards_count: Optional[int] = None
    rack_aware: Optional[bool] = None
    email_alerts: Optional[bool] = None
    alert_settings: Optional[Dict[str, Any]] = None
    license: Optional[str] = None
    created_time: Optional[str] = None
    bigstore_driver: Optional[str] = None
    data_internode_encryption: Optional[bool] = None
    cm_port: Optional[int] = None
    cnm_http_port: Optional[int] = None
    cnm_https_port: Optional[int] = None

    class Config:
        extra = "allow"


class StatisticsObject(BaseModel):
    """Statistics object schema.

    Based on: https://redis.io/docs/latest/operate/rs/references/rest-api/objects/statistics/
    """

    intervals: Optional[List[Dict[str, Any]]] = None
    # Statistics can have many dynamic fields, so we allow extras

    class Config:
        extra = "allow"


class AlertSettings(BaseModel):
    """Alert settings schema."""

    # Alert settings have many dynamic fields based on alert types
    class Config:
        extra = "allow"
