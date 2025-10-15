"""Redis instance management API endpoints."""

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter()


class RedisInstance(BaseModel):
    """Redis instance configuration model.

    Represents a Redis database that the agent can monitor and diagnose.
    Instances can be pre-configured by users or created dynamically by the agent.
    """

    id: str
    name: str
    connection_url: str = Field(
        ..., description="Redis connection URL (e.g., redis://localhost:6379)"
    )
    environment: str = Field(..., description="Environment: development, staging, production")
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
    admin_password: Optional[str] = Field(
        None,
        description="Redis Enterprise admin API password. Only for instance_type='redis_enterprise'.",
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
    def validate_not_app_redis(cls, v: str) -> str:
        """Ensure this is not the application's own Redis database."""
        try:
            from redis_sre_agent.core.config import settings

            if v == settings.redis_url:
                raise ValueError(
                    "Cannot create instance for application's own Redis database. "
                    f"The URL {v} is used by the SRE agent application itself "
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


class CreateInstanceRequest(BaseModel):
    """Request model for creating a Redis instance."""

    name: str
    connection_url: str = Field(
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
    admin_password: Optional[str] = Field(
        None,
        description="Redis Enterprise admin API password. Only for instance_type='redis_enterprise'.",
    )
    created_by: str = Field(
        default="user", description="Who created this instance: 'user' or 'agent'"
    )
    user_id: Optional[str] = Field(default=None, description="User ID who owns this instance")

    @field_validator("connection_url")
    @classmethod
    def validate_connection_url(cls, v: str) -> str:
        """Validate that connection_url is a valid Redis URL."""
        from urllib.parse import urlparse

        if not v:
            raise ValueError("Connection URL cannot be empty")

        try:
            parsed = urlparse(v)
            if not parsed.scheme:
                raise ValueError("Connection URL must include a scheme (e.g., redis://)")
            if parsed.scheme not in ["redis", "rediss"]:
                raise ValueError("Connection URL scheme must be 'redis' or 'rediss'")
            if not parsed.hostname:
                raise ValueError("Connection URL must include a hostname")
        except Exception as e:
            raise ValueError(f"Invalid connection URL format: {str(e)}")

        return v

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
    connection_url: Optional[str] = Field(
        None, description="Redis connection URL (e.g., redis://localhost:6379)"
    )
    environment: Optional[str] = None
    usage: Optional[str] = None
    description: Optional[str] = None
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
    admin_password: Optional[str] = Field(
        None,
        description="Redis Enterprise admin API password. Only for instance_type='redis_enterprise'.",
    )
    status: Optional[str] = None
    version: Optional[str] = None
    memory: Optional[str] = None
    connections: Optional[int] = None


async def get_instances_from_redis() -> List[RedisInstance]:
    """Get all instances from Redis storage."""
    try:
        redis_client = get_redis_client()
        instances_data = await redis_client.get(RedisKeys.instances_set())

        if not instances_data:
            return []

        instances_list = json.loads(instances_data)
        return [RedisInstance(**instance) for instance in instances_list]
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
    """Save instances to Redis storage."""
    try:
        redis_client = get_redis_client()
        instances_data = json.dumps([instance.model_dump() for instance in instances])
        await redis_client.set(RedisKeys.instances_set(), instances_data)
        return True
    except Exception as e:
        logger.error(f"Failed to save instances to Redis: {e}")
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
        return [RedisInstance(**instance) for instance in instances_data]

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
            if existing.name == instance.name or existing.connection_url == instance.connection_url:
                logger.info(f"Instance {instance.name} already exists in session {thread_id}")
                return True

        # Add new instance
        instances.append(instance)

        # Serialize and save with TTL (1 hour)
        instances_json = json.dumps([inst.model_dump() for inst in instances])
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
    configured_urls = {inst.connection_url for inst in configured}

    for session_inst in session_instances:
        if session_inst.connection_url not in configured_urls:
            all_instances.append(session_inst)

    return all_instances


@router.get("/instances", response_model=List[RedisInstance])
async def list_instances():
    """List all Redis instances."""
    try:
        instances = await get_instances_from_redis()
        return instances
    except Exception as e:
        logger.error(f"Failed to list instances: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve instances")


@router.post("/instances", response_model=RedisInstance, status_code=201)
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
            created_by=request.created_by,
            user_id=request.user_id,
        )

        # Add to instances list
        instances.append(new_instance)

        # Save to Redis
        if not await save_instances_to_redis(instances):
            raise HTTPException(status_code=500, detail="Failed to save instance")

        logger.info(f"Created Redis instance: {new_instance.name} ({new_instance.id})")
        return new_instance

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create instance: {e}")
        raise HTTPException(status_code=500, detail="Failed to create instance")


@router.get("/instances/{instance_id}", response_model=RedisInstance)
async def get_instance(instance_id: str):
    """Get a specific Redis instance by ID."""
    try:
        instances = await get_instances_from_redis()

        for instance in instances:
            if instance.id == instance_id:
                return instance

        raise HTTPException(status_code=404, detail=f"Instance with ID '{instance_id}' not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get instance {instance_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve instance")


@router.put("/instances/{instance_id}", response_model=RedisInstance)
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
        update_data = request.model_dump(exclude_unset=True)
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Create updated instance
        updated_instance = current_instance.model_copy(update=update_data)
        instances[instance_index] = updated_instance

        # Save to Redis
        if not await save_instances_to_redis(instances):
            raise HTTPException(status_code=500, detail="Failed to save updated instance")

        logger.info(f"Updated Redis instance: {updated_instance.name} ({updated_instance.id})")
        return updated_instance

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
            logger.error(f"Failed to parse connection URL {request.connection_url}: {parse_error}")
            result = {
                "success": False,
                "message": f"Invalid connection URL format: {request.connection_url}",
                "host": "unknown",
                "port": "unknown",
                "tested_at": datetime.now(timezone.utc).isoformat(),
            }

        logger.info(
            f"Connection URL test: {'SUCCESS' if result['success'] else 'FAILED'} - {request.connection_url}"
        )
        return result

    except Exception as e:
        logger.error(f"Failed to test connection URL {request.connection_url}: {e}")
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
        success = await test_redis_connection(url=target_instance.connection_url)

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
