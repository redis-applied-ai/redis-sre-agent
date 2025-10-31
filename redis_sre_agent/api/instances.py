"""Redis instance management API endpoints."""

import logging
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, SecretStr, field_serializer, field_validator

from redis_sre_agent.core import instances as core_instances

logger = logging.getLogger(__name__)

router = APIRouter()


# TODO: Move basemodels to schemas.py
def to_response(instance: "core_instances.RedisInstance") -> "RedisInstanceResponse":
    """Convert a domain RedisInstance to an API-safe response with masked credentials."""
    conn_url = (
        instance.connection_url.get_secret_value()
        if hasattr(instance.connection_url, "get_secret_value")
        else instance.connection_url
    )
    admin_pwd = (
        instance.admin_password.get_secret_value()
        if getattr(instance, "admin_password", None)
        and hasattr(instance.admin_password, "get_secret_value")
        else getattr(instance, "admin_password", None)
    )
    return RedisInstanceResponse(
        id=instance.id,
        name=instance.name,
        connection_url=core_instances.mask_redis_url(conn_url),
        environment=instance.environment,
        usage=instance.usage,
        description=instance.description,
        repo_url=instance.repo_url,
        notes=instance.notes,
        monitoring_identifier=instance.monitoring_identifier,
        logging_identifier=instance.logging_identifier,
        instance_type=instance.instance_type,
        admin_url=instance.admin_url,
        admin_username=instance.admin_username,
        admin_password="***" if admin_pwd else None,
        status=instance.status,
        version=instance.version,
        memory=instance.memory,
        connections=instance.connections,
        last_checked=instance.last_checked,
        created_at=instance.created_at,
        updated_at=instance.updated_at,
        created_by=instance.created_by,
        user_id=instance.user_id,
        redis_cloud_subscription_id=getattr(instance, "redis_cloud_subscription_id", None),
        redis_cloud_database_id=getattr(instance, "redis_cloud_database_id", None),
        redis_cloud_subscription_type=getattr(instance, "redis_cloud_subscription_type", None),
        redis_cloud_database_name=getattr(instance, "redis_cloud_database_name", None),
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


@router.get("/instances", response_model=List[RedisInstanceResponse])
async def list_instances():
    """List all Redis instances with masked credentials."""
    try:
        instances = await core_instances.get_instances()
        return [to_response(inst) for inst in instances]
    except Exception as e:
        logger.error(f"Failed to list instances: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve instances")


@router.post("/instances", response_model=RedisInstanceResponse, status_code=201)
async def create_instance(request: CreateInstanceRequest):
    """Create a new Redis instance."""
    try:
        # Get existing instances
        instances = await core_instances.get_instances()

        # Check if instance with same name already exists
        if any(inst.name == request.name for inst in instances):
            raise HTTPException(
                status_code=400, detail=f"Instance with name '{request.name}' already exists"
            )

        # Create new instance
        instance_id = f"redis-{request.environment}-{int(datetime.now().timestamp())}"
        new_instance = core_instances.RedisInstance(
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
            instance_type=(request.instance_type or "unknown"),
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
        if not await core_instances.save_instances(instances):
            raise HTTPException(status_code=500, detail="Failed to save instance")

        logger.info(f"Created Redis instance: {new_instance.name} ({new_instance.id})")
        return to_response(new_instance)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create instance: {e}")
        raise HTTPException(status_code=500, detail="Failed to create instance")


@router.get("/instances/{instance_id}", response_model=RedisInstanceResponse)
async def get_instance(instance_id: str):
    """Get a specific Redis instance by ID with masked credentials."""
    try:
        instances = await core_instances.get_instances()

        for instance in instances:
            if instance.id == instance_id:
                return to_response(instance)

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
        instances = await core_instances.get_instances()

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
        if not await core_instances.save_instances(instances):
            raise HTTPException(status_code=500, detail="Failed to save updated instance")

        logger.info(f"Updated Redis instance: {updated_instance.name} ({updated_instance.id})")
        return to_response(updated_instance)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update instance {instance_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update instance")


@router.delete("/instances/{instance_id}")
async def delete_instance(instance_id: str):
    """Delete a Redis instance."""
    try:
        instances = await core_instances.get_instances()

        # Find and remove the instance
        original_count = len(instances)
        instances = [inst for inst in instances if inst.id != instance_id]

        if len(instances) == original_count:
            raise HTTPException(
                status_code=404, detail=f"Instance with ID '{instance_id}' not found"
            )

        # Save updated list to Redis
        if not await core_instances.save_instances(instances):
            raise HTTPException(status_code=500, detail="Failed to save after deletion")

        # Best-effort: remove search index document for this instance
        try:
            await core_instances.delete_instance_index_doc(instance_id)
        except Exception:
            pass

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

        instances = await core_instances.get_instances()

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
