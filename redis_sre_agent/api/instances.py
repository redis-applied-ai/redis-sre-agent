"""Redis instance management API endpoints."""

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, SecretStr, field_serializer, field_validator

from redis_sre_agent.core.encryption import encrypt_secret, get_secret_value
from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter()


def mask_redis_url(url: str) -> str:
    """Mask username and password in Redis URL for safe display.

    Args:
        url: Redis connection URL (e.g., redis://user:pass@host:port/db)

    Returns:
        Masked URL (e.g., redis://***:***@host:port/db)
    """
    try:
        parsed = urlparse(url)
        if parsed.username or parsed.password:
            # Reconstruct URL with masked credentials
            masked_netloc = parsed.hostname or ""
            if parsed.port:
                masked_netloc += f":{parsed.port}"
            if parsed.username or parsed.password:
                masked_netloc = f"***:***@{masked_netloc}"

            masked_url = f"{parsed.scheme}://{masked_netloc}{parsed.path}"
            if parsed.query:
                masked_url += f"?{parsed.query}"
            if parsed.fragment:
                masked_url += f"#{parsed.fragment}"
            return masked_url
        return url
    except Exception as e:
        logger.warning(f"Failed to mask URL credentials: {e}")
        return "redis://***:***@<host>:<port>"


class RedisInstance(BaseModel):
    """Redis instance configuration model.

    Represents a Redis database that the agent can monitor and diagnose.
    Instances can be pre-configured by users or created dynamically by the agent.

    Note: This model does NOT validate connection_url on read from Redis,
    to allow loading instances with invalid URLs so they can be fixed in the UI.
    Validation only happens on API create/update requests.
    """

    id: str
    name: str
    connection_url: SecretStr = Field(
        ..., description="Redis connection URL (e.g., redis://localhost:6379)"
    )
    environment: str = Field(..., description="Environment: development, staging, production")

    @field_serializer("connection_url", "admin_password", when_used="json")
    def dump_secret(self, v):
        """Serialize SecretStr fields as plain text when dumping to dict/json."""
        if v is None:
            return None
        # Handle both SecretStr and plain str (in case model_copy passed a plain str)
        return v.get_secret_value() if hasattr(v, "get_secret_value") else v

    usage: str = Field(..., description="Usage type: cache, analytics, session, queue, or custom")
    description: str
    repo_url: Optional[str] = None
    notes: Optional[str] = None
    monitoring_identifier: Optional[str] = Field(
        None, description="Name used in monitoring systems (defaults to instance name)"
    )
    logging_identifier: Optional[str] = Field(
        None, description="Name used in logging systems (defaults to instance name)"
    )
    instance_type: Optional[str] = Field(
        "unknown",
        description="Redis instance type: oss_single, oss_cluster, redis_enterprise, redis_cloud, unknown",
    )
    admin_url: Optional[str] = Field(
        None,
        description="Redis Enterprise admin API URL (e.g., https://cluster.example.com:9443). "
        "Only applicable for instance_type='redis_enterprise'.",
    )
    admin_username: Optional[str] = Field(
        None,
        description="Redis Enterprise admin API username. Only for instance_type='redis_enterprise'.",
    )
    admin_password: Optional[SecretStr] = Field(
        None,
        description="Redis Enterprise admin API password. Only for instance_type='redis_enterprise'.",
    )
    # Redis Cloud identifiers
    redis_cloud_subscription_id: Optional[int] = Field(
        None,
        description="Redis Cloud subscription ID. Only for instance_type='redis_cloud'.",
    )
    redis_cloud_database_id: Optional[int] = Field(
        None,
        description="Redis Cloud database ID. Only for instance_type='redis_cloud'.",
    )
    # Redis Cloud metadata for routing
    redis_cloud_subscription_type: Optional[str] = Field(
        default=None,
        description="Redis Cloud subscription type: 'pro' or 'essentials' (aka 'fixed'). Only for instance_type='redis_cloud'.",
    )
    redis_cloud_database_name: Optional[str] = Field(
        default=None,
        description="Redis Cloud database name (used when ID is not available). Only for instance_type='redis_cloud'.",
    )
    status: Optional[str] = "unknown"
    version: Optional[str] = None
    memory: Optional[str] = None
    connections: Optional[int] = None
    last_checked: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # New fields for provider architecture
    created_by: str = Field(
        default="user",
        description="Who created this instance: 'user' (pre-configured) or 'agent' (dynamically created)",
    )
    user_id: Optional[str] = Field(
        default=None, description="User ID who owns this instance (for pre-configured instances)"
    )

    @field_validator("connection_url")
    @classmethod
    def validate_not_app_redis(cls, v: SecretStr) -> SecretStr:
        """Ensure this is not the application's own Redis database."""
        try:
            from redis_sre_agent.core.config import settings

            url_value = v.get_secret_value() if isinstance(v, SecretStr) else v
            settings_url = (
                settings.redis_url.get_secret_value()
                if isinstance(settings.redis_url, SecretStr)
                else settings.redis_url
            )

            if url_value == settings_url:
                raise ValueError(
                    "Cannot create instance for application's own Redis database. "
                    "The URL is used by the SRE agent application itself "
                    "and should not be diagnosed or monitored by the agent."
                )
        except (ImportError, AttributeError):
            # Settings not available or redis_url not set - allow it
            pass

        return v

    @field_validator("created_by")
    @classmethod
    def validate_created_by(cls, v: str) -> str:
        """Validate created_by field."""
        if v not in ["user", "agent"]:
            raise ValueError(f"created_by must be 'user' or 'agent', got: {v}")
        return v

    def to_response(self) -> "RedisInstanceResponse":
        """Convert to response model with masked credentials."""
        # Handle both SecretStr and plain str (after model_copy)
        conn_url = (
            self.connection_url.get_secret_value()
            if hasattr(self.connection_url, "get_secret_value")
            else self.connection_url
        )
        admin_pwd = (
            self.admin_password.get_secret_value()
            if self.admin_password and hasattr(self.admin_password, "get_secret_value")
            else self.admin_password
        )

        return RedisInstanceResponse(
            id=self.id,
            name=self.name,
            connection_url=mask_redis_url(conn_url),
            environment=self.environment,
            usage=self.usage,
            description=self.description,
            repo_url=self.repo_url,
            notes=self.notes,
            monitoring_identifier=self.monitoring_identifier,
            logging_identifier=self.logging_identifier,
            instance_type=self.instance_type,
            admin_url=self.admin_url,
            admin_username=self.admin_username,
            admin_password="***" if admin_pwd else None,
            status=self.status,
            version=self.version,
            memory=self.memory,
            connections=self.connections,
            last_checked=self.last_checked,
            created_at=self.created_at,
            updated_at=self.updated_at,
            created_by=self.created_by,
            user_id=self.user_id,
            redis_cloud_subscription_id=self.redis_cloud_subscription_id,
            redis_cloud_database_id=self.redis_cloud_database_id,
            redis_cloud_subscription_type=self.redis_cloud_subscription_type,
            redis_cloud_database_name=self.redis_cloud_database_name,
        )


class RedisInstanceResponse(BaseModel):
    """Response model for Redis instance with masked credentials."""

    id: str
    name: str
    connection_url: str  # Masked URL
    environment: str
    usage: str
    description: str
    repo_url: Optional[str] = None
    notes: Optional[str] = None
    monitoring_identifier: Optional[str] = None
    logging_identifier: Optional[str] = None
    instance_type: Optional[str] = "unknown"
    admin_url: Optional[str] = None
    admin_username: Optional[str] = None
    admin_password: Optional[str] = None  # Always masked as "***"
    status: Optional[str] = "unknown"
    version: Optional[str] = None
    memory: Optional[str] = None
    connections: Optional[int] = None
    last_checked: Optional[str] = None
    created_at: str
    updated_at: str
    created_by: str = "user"
    user_id: Optional[str] = None
    # Redis Cloud identifiers
    redis_cloud_subscription_id: Optional[int] = None
    redis_cloud_database_id: Optional[int] = None
    # Redis Cloud metadata
    redis_cloud_subscription_type: Optional[str] = None
    redis_cloud_database_name: Optional[str] = None


class CreateInstanceRequest(BaseModel):
    """Request model for creating a Redis instance."""

    name: str
    connection_url: SecretStr = Field(
        ..., description="Redis connection URL (e.g., redis://localhost:6379)"
    )
    environment: str
    usage: str
    description: str
    repo_url: Optional[str] = None
    notes: Optional[str] = None
    monitoring_identifier: Optional[str] = Field(
        None, description="Name used in monitoring systems (defaults to instance name)"
    )
    logging_identifier: Optional[str] = Field(
        None, description="Name used in logging systems (defaults to instance name)"
    )
    instance_type: Optional[str] = Field(
        "unknown",
        description="Redis instance type: oss_single, oss_cluster, redis_enterprise, redis_cloud, unknown",
    )
    admin_url: Optional[str] = Field(
        None,
        description="Redis Enterprise admin API URL. Only for instance_type='redis_enterprise'.",
    )
    admin_username: Optional[str] = Field(
        None,
        description="Redis Enterprise admin API username. Only for instance_type='redis_enterprise'.",
    )
    admin_password: Optional[SecretStr] = Field(
        None,
        description="Redis Enterprise admin API password. Only for instance_type='redis_enterprise'.",
    )
    # Redis Cloud identifiers (optional)
    redis_cloud_subscription_id: Optional[int] = Field(
        None,
        description="Redis Cloud subscription ID. Only for instance_type='redis_cloud'.",
    )
    redis_cloud_database_id: Optional[int] = Field(
        None,
        description="Redis Cloud database ID. Only for instance_type='redis_cloud'.",
    )
    redis_cloud_subscription_type: Optional[str] = Field(
        None,
        description="Redis Cloud subscription type: 'pro' or 'essentials' (aka 'fixed'). Only for instance_type='redis_cloud'.",
    )
    redis_cloud_database_name: Optional[str] = Field(
        None,
        description="Redis Cloud database name (used when ID is not available). Only for instance_type='redis_cloud'.",
    )

    created_by: str = Field(
        default="user", description="Who created this instance: 'user' or 'agent'"
    )
    user_id: Optional[str] = Field(default=None, description="User ID who owns this instance")

    @field_validator("connection_url")
    @classmethod
    def validate_connection_url(cls, v: SecretStr) -> SecretStr:
        """Validate that connection_url is a valid Redis URL."""
        url_value = v.get_secret_value() if isinstance(v, SecretStr) else v

        if not url_value:
            raise ValueError("Connection URL cannot be empty")

        try:
            parsed = urlparse(url_value)
            if not parsed.scheme:
                raise ValueError("Connection URL must include a scheme (e.g., redis://)")
            if parsed.scheme not in ["redis", "rediss"]:
                raise ValueError("Connection URL scheme must be 'redis' or 'rediss'")
            if not parsed.hostname:
                raise ValueError("Connection URL must include a hostname")
        except Exception as e:
            raise ValueError(f"Invalid connection URL format: {str(e)}")

        return v

    @field_serializer("connection_url", "admin_password", when_used="json")
    def dump_secret(self, v):
        """Serialize SecretStr fields as plain text when dumping to dict/json."""
        if v is None:
            return None
        return v.get_secret_value() if isinstance(v, SecretStr) else v

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate that environment is one of the allowed values."""
        allowed_environments = ["development", "staging", "production", "test"]
        if v not in allowed_environments:
            raise ValueError(f"Environment must be one of: {', '.join(allowed_environments)}")
        return v


class UpdateInstanceRequest(BaseModel):
    """Request model for updating a Redis instance."""

    name: Optional[str] = None
    connection_url: Optional[SecretStr] = Field(
        None, description="Redis connection URL (e.g., redis://localhost:6379)"
    )
    environment: Optional[str] = None
    usage: Optional[str] = None
    description: Optional[str] = None

    @field_validator("connection_url")
    @classmethod
    def validate_connection_url(cls, v):
        """Validate that connection_url has a valid Redis URL scheme."""
        if v is None:
            return v
        url_str = v.get_secret_value() if isinstance(v, SecretStr) else str(v)
        if not url_str.startswith(("redis://", "rediss://", "unix://")):
            raise ValueError(
                f"Invalid Redis URL. Must start with redis://, rediss://, or unix://. "
                f"Got: {url_str[:20]}..."
            )
        return v

    @field_serializer("connection_url", "admin_password", when_used="json")
    def dump_secret(self, v):
        """Serialize SecretStr fields as plain text when dumping to dict/json."""
        if v is None:
            return None
        return v.get_secret_value() if isinstance(v, SecretStr) else v

    repo_url: Optional[str] = None
    notes: Optional[str] = None
    monitoring_identifier: Optional[str] = Field(
        None, description="Name used in monitoring systems (defaults to instance name)"
    )
    logging_identifier: Optional[str] = Field(
        None, description="Name used in logging systems (defaults to instance name)"
    )
    instance_type: Optional[str] = Field(
        None,
        description="Redis instance type: oss_single, oss_cluster, redis_enterprise, redis_cloud, unknown",
    )
    admin_url: Optional[str] = Field(
        None,
        description="Redis Enterprise admin API URL. Only for instance_type='redis_enterprise'.",
    )
    admin_username: Optional[str] = Field(
        None,
        description="Redis Enterprise admin API username. Only for instance_type='redis_enterprise'.",
    )
    admin_password: Optional[SecretStr] = Field(
        None,
        description="Redis Enterprise admin API password. Only for instance_type='redis_enterprise'.",
    )
    # Redis Cloud identifiers (optional)
    redis_cloud_subscription_id: Optional[int] = Field(
        None,
        description="Redis Cloud subscription ID. Only for instance_type='redis_cloud'.",
    )
    redis_cloud_database_id: Optional[int] = Field(
        None,
        description="Redis Cloud database ID. Only for instance_type='redis_cloud'.",
    )
    redis_cloud_subscription_type: Optional[str] = Field(
        None,
        description="Redis Cloud subscription type: 'pro' or 'essentials' (aka 'fixed'). Only for instance_type='redis_cloud'.",
    )
    redis_cloud_database_name: Optional[str] = Field(
        None,
        description="Redis Cloud database name (used when ID is not available). Only for instance_type='redis_cloud'.",
    )
    status: Optional[str] = None
    version: Optional[str] = None
    memory: Optional[str] = None
    connections: Optional[int] = None


async def get_instances_from_redis() -> List[RedisInstance]:
    """Get all instances from Redis storage.

    Skips instances that fail validation (e.g., invalid URLs) but logs errors.
    This allows the UI to load and display instances so users can fix them.
    """
    try:
        redis_client = get_redis_client()
        instances_data = await redis_client.get(RedisKeys.instances_set())

        if not instances_data:
            return []

        instances_list = json.loads(instances_data)
        instances = []
        for inst_data in instances_list:
            try:
                # Decrypt connection_url if present
                if inst_data.get("connection_url"):
                    encrypted_url = inst_data["connection_url"]
                    try:
                        decrypted_url = get_secret_value(encrypted_url)
                        inst_data["connection_url"] = decrypted_url
                        logger.debug(
                            f"Decrypted connection_url for {inst_data.get('name', 'unknown')}"
                        )
                    except Exception as decrypt_err:
                        logger.error(
                            f"Failed to decrypt connection_url for {inst_data.get('name', 'unknown')}: {decrypt_err}"
                        )
                        raise

                # Decrypt admin_password if present
                if inst_data.get("admin_password"):
                    encrypted_pwd = inst_data["admin_password"]
                    try:
                        decrypted_pwd = get_secret_value(encrypted_pwd)
                        inst_data["admin_password"] = decrypted_pwd
                        logger.debug(
                            f"Decrypted admin_password for {inst_data.get('name', 'unknown')}"
                        )
                    except Exception as decrypt_err:
                        logger.error(
                            f"Failed to decrypt admin_password for {inst_data.get('name', 'unknown')}: {decrypt_err}"
                        )
                        raise

                instances.append(RedisInstance(**inst_data))
            except Exception as e:
                # Log error but continue loading other instances
                logger.error(
                    f"Failed to load instance '{inst_data.get('name', 'unknown')}' "
                    f"(ID: {inst_data.get('id', 'unknown')}): {e}. "
                    f"This instance will be skipped. Please fix it in the UI."
                )
        return instances
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse instances data from Redis: {e}")
        return []
    except Exception as e:
        logger.error(f"Failed to get instances from Redis: {e}")
        return []


async def create_instance_programmatically(
    name: str,
    connection_url: str,
    environment: str,
    usage: str,
    description: str,
    created_by: str = "agent",
    user_id: Optional[str] = None,
    repo_url: Optional[str] = None,
    notes: Optional[str] = None,
) -> RedisInstance:
    """Create a Redis instance programmatically (e.g., by the agent).

    This is a helper function that can be called by the agent to create instances
    on demand when the user provides connection details.

    Args:
        name: Instance name
        connection_url: Redis connection URL
        environment: Environment (development, staging, production)
        usage: Usage type (cache, analytics, session, queue, custom)
        description: Instance description
        created_by: Who created this instance ('agent' or 'user')
        user_id: Optional user ID who owns this instance
        repo_url: Optional repository URL
        notes: Optional notes

    Returns:
        The created RedisInstance

    Raises:
        ValueError: If instance with same name already exists or validation fails
    """
    try:
        # Get existing instances
        instances = await get_instances_from_redis()

        # Check if instance with same name already exists
        if any(inst.name == name for inst in instances):
            raise ValueError(f"Instance with name '{name}' already exists")

        # Create new instance
        instance_id = f"redis-{environment}-{int(datetime.now().timestamp())}"
        new_instance = RedisInstance(
            id=instance_id,
            name=name,
            connection_url=connection_url,
            environment=environment,
            usage=usage,
            description=description,
            repo_url=repo_url,
            notes=notes,
            created_by=created_by,
            user_id=user_id,
        )

        # Add to instances list
        instances.append(new_instance)

        # Save to Redis
        if not await save_instances_to_redis(instances):
            raise ValueError("Failed to save instance to storage")

        logger.info(
            f"Created Redis instance programmatically: {new_instance.name} ({new_instance.id})"
        )
        return new_instance

    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Failed to create instance programmatically: {e}")
        raise ValueError(f"Failed to create instance: {str(e)}")


async def save_instances_to_redis(instances: List[RedisInstance]) -> bool:
    """Save instances to Redis storage with encrypted secrets."""
    try:
        redis_client = get_redis_client()

        # Serialize instances and encrypt sensitive fields
        instances_list = []
        for instance in instances:
            inst_dict = instance.model_dump(mode="json")

            # Encrypt connection_url if present
            if inst_dict.get("connection_url"):
                inst_dict["connection_url"] = encrypt_secret(inst_dict["connection_url"])

            # Encrypt admin_password if present
            if inst_dict.get("admin_password"):
                inst_dict["admin_password"] = encrypt_secret(inst_dict["admin_password"])

            instances_list.append(inst_dict)

        instances_data = json.dumps(instances_list)
        await redis_client.set(RedisKeys.instances_set(), instances_data)
        return True
    except Exception as e:
        logger.exception(f"Failed to save instances to Redis: {e}")
        return False


async def get_session_instances(thread_id: str) -> List[RedisInstance]:
    """Get dynamically created instances for a session/thread.

    These are instances created by the agent during a conversation,
    stored in session memory with a TTL.
    """
    try:
        redis_client = get_redis_client()
        instances_key = RedisKeys.thread_instances(thread_id)
        instances_json = await redis_client.get(instances_key)

        if not instances_json:
            return []

        if isinstance(instances_json, bytes):
            instances_json = instances_json.decode("utf-8")

        instances_data = json.loads(instances_json)

        # Decrypt secrets in session instances
        instances = []
        for inst_data in instances_data:
            if inst_data.get("connection_url"):
                inst_data["connection_url"] = get_secret_value(inst_data["connection_url"])
            if inst_data.get("admin_password"):
                inst_data["admin_password"] = get_secret_value(inst_data["admin_password"])
            instances.append(RedisInstance(**inst_data))

        return instances

    except Exception as e:
        logger.error(f"Failed to get session instances for thread {thread_id}: {e}")
        return []


async def add_session_instance(thread_id: str, instance: RedisInstance) -> bool:
    """Add a dynamically created instance to session memory.

    Args:
        thread_id: Thread/conversation ID
        instance: RedisInstance to add

    Returns:
        True if successful, False otherwise
    """
    try:
        redis_client = get_redis_client()

        # Get existing session instances
        instances = await get_session_instances(thread_id)

        # Check if instance already exists (by name or URL)
        for existing in instances:
            existing_url = existing.connection_url.get_secret_value()
            instance_url = instance.connection_url.get_secret_value()
            if existing.name == instance.name or existing_url == instance_url:
                logger.info(f"Instance {instance.name} already exists in session {thread_id}")
                return True

        # Add new instance
        instances.append(instance)

        # Serialize and encrypt secrets
        instances_list = []
        for inst in instances:
            inst_dict = inst.model_dump(mode="json")
            if inst_dict.get("connection_url"):
                inst_dict["connection_url"] = encrypt_secret(inst_dict["connection_url"])
            if inst_dict.get("admin_password"):
                inst_dict["admin_password"] = encrypt_secret(inst_dict["admin_password"])
            instances_list.append(inst_dict)

        # Save with TTL (1 hour)
        instances_json = json.dumps(instances_list)
        instances_key = RedisKeys.thread_instances(thread_id)
        await redis_client.set(instances_key, instances_json, ex=3600)

        logger.info(f"Added session instance {instance.name} to thread {thread_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to add session instance {instance.name} to thread {thread_id}: {e}")
        return False


async def get_all_instances(
    user_id: Optional[str] = None, thread_id: Optional[str] = None
) -> List[RedisInstance]:
    """Get all instances: configured + session instances.

    Args:
        user_id: Optional user ID to filter configured instances
        thread_id: Optional thread ID to include session instances

    Returns:
        Combined list of configured and session instances
    """
    # Get configured instances
    configured = await get_instances_from_redis()

    # Filter by user if specified
    if user_id:
        configured = [
            inst for inst in configured if inst.user_id == user_id or inst.user_id is None
        ]

    # Get session instances if thread_id provided
    session_instances = []
    if thread_id:
        session_instances = await get_session_instances(thread_id)

    # Combine, avoiding duplicates (prefer configured over session)
    all_instances = list(configured)
    configured_urls = {inst.connection_url.get_secret_value() for inst in configured}

    for session_inst in session_instances:
        if session_inst.connection_url.get_secret_value() not in configured_urls:
            all_instances.append(session_inst)

    return all_instances


@router.get("/instances", response_model=List[RedisInstanceResponse])
async def list_instances():
    """List all Redis instances with masked credentials."""
    try:
        instances = await get_instances_from_redis()
        return [inst.to_response() for inst in instances]
    except Exception as e:
        logger.error(f"Failed to list instances: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve instances")


@router.post("/instances", response_model=RedisInstanceResponse, status_code=201)
async def create_instance(request: CreateInstanceRequest):
    """Create a new Redis instance."""
    try:
        # Get existing instances
        instances = await get_instances_from_redis()

        # Check if instance with same name already exists
        if any(inst.name == request.name for inst in instances):
            raise HTTPException(
                status_code=400, detail=f"Instance with name '{request.name}' already exists"
            )

        # Create new instance
        instance_id = f"redis-{request.environment}-{int(datetime.now().timestamp())}"
        new_instance = RedisInstance(
            id=instance_id,
            name=request.name,
            connection_url=request.connection_url,
            environment=request.environment,
            usage=request.usage,
            description=request.description,
            repo_url=request.repo_url,
            notes=request.notes,
            monitoring_identifier=request.monitoring_identifier,
            logging_identifier=request.logging_identifier,
            instance_type=request.instance_type,
            admin_url=request.admin_url,
            admin_username=request.admin_username,
            admin_password=request.admin_password,
            # Redis Cloud identifiers
            redis_cloud_subscription_id=request.redis_cloud_subscription_id,
            redis_cloud_database_id=request.redis_cloud_database_id,
            redis_cloud_subscription_type=request.redis_cloud_subscription_type,
            redis_cloud_database_name=request.redis_cloud_database_name,
            created_by=request.created_by,
            user_id=request.user_id,
        )

        # Add to instances list
        instances.append(new_instance)

        # Save to Redis
        if not await save_instances_to_redis(instances):
            raise HTTPException(status_code=500, detail="Failed to save instance")

        logger.info(f"Created Redis instance: {new_instance.name} ({new_instance.id})")
        return new_instance.to_response()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create instance: {e}")
        raise HTTPException(status_code=500, detail="Failed to create instance")


@router.get("/instances/{instance_id}", response_model=RedisInstanceResponse)
async def get_instance(instance_id: str):
    """Get a specific Redis instance by ID with masked credentials."""
    try:
        instances = await get_instances_from_redis()

        for instance in instances:
            if instance.id == instance_id:
                return instance.to_response()

        raise HTTPException(status_code=404, detail=f"Instance with ID '{instance_id}' not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get instance {instance_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve instance")


@router.put("/instances/{instance_id}", response_model=RedisInstanceResponse)
async def update_instance(instance_id: str, request: UpdateInstanceRequest):
    """Update a Redis instance."""
    try:
        instances = await get_instances_from_redis()

        # Find the instance to update
        instance_index = None
        for i, instance in enumerate(instances):
            if instance.id == instance_id:
                instance_index = i
                break

        if instance_index is None:
            raise HTTPException(
                status_code=404, detail=f"Instance with ID '{instance_id}' not found"
            )

        # Update the instance
        current_instance = instances[instance_index]
        # Use mode='json' to trigger field_serializer which extracts SecretStr values
        update_data = request.model_dump(exclude_unset=True, mode="json")
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        # CRITICAL: Skip masked values to preserve existing secrets
        # If the UI sends a masked connection_url (e.g., redis://***:***@host:port),
        # we must NOT overwrite the real encrypted value with the masked one
        if "connection_url" in update_data:
            url_str = update_data["connection_url"]
            # Check if the URL contains masked credentials
            if "***" in url_str or url_str == "**********":
                logger.info(f"Skipping masked connection_url in update for {current_instance.name}")
                del update_data["connection_url"]

        # Same for admin_password
        if "admin_password" in update_data:
            pwd_str = update_data["admin_password"]
            if pwd_str and ("***" in pwd_str or pwd_str == "***"):
                logger.info(f"Skipping masked admin_password in update for {current_instance.name}")
                del update_data["admin_password"]

        # Create updated instance
        updated_instance = current_instance.model_copy(update=update_data)
        instances[instance_index] = updated_instance

        # Save to Redis
        if not await save_instances_to_redis(instances):
            raise HTTPException(status_code=500, detail="Failed to save updated instance")

        logger.info(f"Updated Redis instance: {updated_instance.name} ({updated_instance.id})")
        return updated_instance.to_response()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update instance {instance_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update instance")


@router.delete("/instances/{instance_id}")
async def delete_instance(instance_id: str):
    """Delete a Redis instance."""
    try:
        instances = await get_instances_from_redis()

        # Find and remove the instance
        original_count = len(instances)
        instances = [inst for inst in instances if inst.id != instance_id]

        if len(instances) == original_count:
            raise HTTPException(
                status_code=404, detail=f"Instance with ID '{instance_id}' not found"
            )

        # Save updated list to Redis
        if not await save_instances_to_redis(instances):
            raise HTTPException(status_code=500, detail="Failed to save after deletion")

        logger.info(f"Deleted Redis instance: {instance_id}")
        return {"message": f"Instance {instance_id} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete instance {instance_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete instance")


class TestConnectionRequest(BaseModel):
    """Request model for testing a connection URL."""

    connection_url: str = Field(..., description="Redis connection URL to test")


@router.post("/instances/test-connection-url")
async def test_connection_url(request: TestConnectionRequest):
    """Test a Redis connection URL without creating an instance."""
    try:
        # Parse connection URL to extract host and port
        from urllib.parse import urlparse

        from redis_sre_agent.core.redis import test_redis_connection

        try:
            parsed_url = urlparse(request.connection_url)
            host = parsed_url.hostname or "unknown"
            port = parsed_url.port or 6379

            # Test connection using the core redis function
            success = await test_redis_connection(url=request.connection_url)

            if success:
                message = f"Successfully connected to Redis at {host}:{port}"
            else:
                message = f"Failed to connect to Redis at {host}:{port}"

            result = {
                "success": success,
                "message": message,
                "host": host,
                "port": port,
                "tested_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as parse_error:
            logger.error(f"Failed to parse connection URL: {parse_error}")
            result = {
                "success": False,
                "message": "Invalid connection URL format",
                "host": "unknown",
                "port": "unknown",
                "tested_at": datetime.now(timezone.utc).isoformat(),
            }

        logger.info(f"Connection URL test: {'SUCCESS' if result['success'] else 'FAILED'}")
        return result

    except Exception as e:
        logger.error(f"Failed to test connection URL: {e}")
        raise HTTPException(status_code=500, detail="Failed to test connection URL")


@router.post("/instances/{instance_id}/test-connection")
async def test_instance_connection(instance_id: str):
    """Test connection to a Redis instance."""
    try:
        from redis_sre_agent.core.redis import test_redis_connection

        instances = await get_instances_from_redis()

        # Find the instance
        target_instance = None
        for instance in instances:
            if instance.id == instance_id:
                target_instance = instance
                break

        if not target_instance:
            raise HTTPException(
                status_code=404, detail=f"Instance with ID '{instance_id}' not found"
            )

        # Test connection using the core redis function
        success = await test_redis_connection(url=target_instance.connection_url.get_secret_value())

        if success:
            message = f"Successfully connected to instance {target_instance.name}"
        else:
            message = f"Failed to connect to instance {target_instance.name}"

        result = {
            "success": success,
            "message": message,
            "instance_id": instance_id,
            "tested_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(f"Connection test for {instance_id}: {'SUCCESS' if success else 'FAILED'}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test connection for instance {instance_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to test connection")


class TestAdminApiRequest(BaseModel):
    """Request model for testing Redis Enterprise admin API connection."""

    admin_url: str = Field(..., description="Redis Enterprise admin API URL")
    admin_username: str = Field(..., description="Admin API username")
    admin_password: str = Field(..., description="Admin API password")


@router.post("/instances/test-admin-api")
async def test_admin_api_connection(request: TestAdminApiRequest):
    """Test connection to Redis Enterprise admin API.

    This endpoint validates that the provided admin API credentials can successfully
    connect to the Redis Enterprise cluster management API.
    """
    try:
        import ssl

        # Parse URL to extract host and port
        from urllib.parse import urlparse

        import httpx

        parsed = urlparse(request.admin_url)
        host = parsed.hostname or "unknown"
        port = parsed.port or 9443

        # Create SSL context that doesn't verify certificates (for self-signed certs)
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        # Test connection to /v1/cluster endpoint
        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            try:
                response = await client.get(
                    f"{request.admin_url}/v1/cluster",
                    auth=(request.admin_username, request.admin_password),
                )

                if response.status_code == 200:
                    cluster_data = response.json()
                    cluster_name = cluster_data.get("name", "Unknown")

                    return {
                        "success": True,
                        "message": f"Successfully connected to Redis Enterprise cluster '{cluster_name}'",
                        "host": host,
                        "port": port,
                        "cluster_name": cluster_name,
                        "tested_at": datetime.now(timezone.utc).isoformat(),
                    }
                elif response.status_code == 401:
                    return {
                        "success": False,
                        "message": "Authentication failed. Please check your username and password.",
                        "host": host,
                        "port": port,
                        "tested_at": datetime.now(timezone.utc).isoformat(),
                    }
                else:
                    return {
                        "success": False,
                        "message": f"Admin API returned status {response.status_code}",
                        "host": host,
                        "port": port,
                        "tested_at": datetime.now(timezone.utc).isoformat(),
                    }

            except httpx.ConnectError as e:
                return {
                    "success": False,
                    "message": f"Could not connect to {host}:{port}. Please check the URL and ensure the admin API is accessible.",
                    "host": host,
                    "port": port,
                    "error": str(e),
                    "tested_at": datetime.now(timezone.utc).isoformat(),
                }
            except httpx.TimeoutException:
                return {
                    "success": False,
                    "message": f"Connection to {host}:{port} timed out after 10 seconds.",
                    "host": host,
                    "port": port,
                    "tested_at": datetime.now(timezone.utc).isoformat(),
                }

    except Exception as e:
        logger.error(f"Failed to test admin API connection: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to test admin API connection: {str(e)}"
        )
