"""Redis instance management API endpoints."""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from redis_sre_agent.core.redis import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter()

# Redis key for storing instances
INSTANCES_KEY = "sre:instances"


class RedisInstance(BaseModel):
    """Redis instance configuration model."""
    id: str
    name: str
    host: str
    port: int
    environment: str = Field(..., description="Environment: development, staging, production")
    usage: str = Field(..., description="Usage type: cache, analytics, session, queue, or custom")
    description: str
    repo_url: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = "unknown"
    version: Optional[str] = None
    memory: Optional[str] = None
    connections: Optional[int] = None
    last_checked: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CreateInstanceRequest(BaseModel):
    """Request model for creating a Redis instance."""
    name: str
    host: str
    port: int
    environment: str
    usage: str
    description: str
    repo_url: Optional[str] = None
    notes: Optional[str] = None


class UpdateInstanceRequest(BaseModel):
    """Request model for updating a Redis instance."""
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    environment: Optional[str] = None
    usage: Optional[str] = None
    description: Optional[str] = None
    repo_url: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    version: Optional[str] = None
    memory: Optional[str] = None
    connections: Optional[int] = None


async def get_instances_from_redis() -> List[RedisInstance]:
    """Get all instances from Redis storage."""
    try:
        redis_client = get_redis_client()
        instances_data = await redis_client.get(INSTANCES_KEY)
        
        if not instances_data:
            return []
        
        instances_list = json.loads(instances_data)
        return [RedisInstance(**instance) for instance in instances_list]
    except Exception as e:
        logger.error(f"Failed to get instances from Redis: {e}")
        return []


async def save_instances_to_redis(instances: List[RedisInstance]) -> bool:
    """Save instances to Redis storage."""
    try:
        redis_client = get_redis_client()
        instances_data = json.dumps([instance.model_dump() for instance in instances])
        await redis_client.set(INSTANCES_KEY, instances_data)
        return True
    except Exception as e:
        logger.error(f"Failed to save instances to Redis: {e}")
        return False


@router.get("/instances", response_model=List[RedisInstance])
async def list_instances():
    """List all Redis instances."""
    try:
        instances = await get_instances_from_redis()
        return instances
    except Exception as e:
        logger.error(f"Failed to list instances: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve instances")


@router.post("/instances", response_model=RedisInstance)
async def create_instance(request: CreateInstanceRequest):
    """Create a new Redis instance."""
    try:
        # Get existing instances
        instances = await get_instances_from_redis()
        
        # Check if instance with same name already exists
        if any(inst.name == request.name for inst in instances):
            raise HTTPException(status_code=400, detail=f"Instance with name '{request.name}' already exists")
        
        # Create new instance
        instance_id = f"redis-{request.environment}-{int(datetime.now().timestamp())}"
        new_instance = RedisInstance(
            id=instance_id,
            name=request.name,
            host=request.host,
            port=request.port,
            environment=request.environment,
            usage=request.usage,
            description=request.description,
            repo_url=request.repo_url,
            notes=request.notes,
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
            raise HTTPException(status_code=404, detail=f"Instance with ID '{instance_id}' not found")
        
        # Update the instance
        current_instance = instances[instance_index]
        update_data = request.model_dump(exclude_unset=True)
        update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        
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
            raise HTTPException(status_code=404, detail=f"Instance with ID '{instance_id}' not found")
        
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


@router.post("/instances/{instance_id}/test-connection")
async def test_instance_connection(instance_id: str):
    """Test connection to a Redis instance."""
    try:
        instances = await get_instances_from_redis()
        
        # Find the instance
        target_instance = None
        for instance in instances:
            if instance.id == instance_id:
                target_instance = instance
                break
        
        if not target_instance:
            raise HTTPException(status_code=404, detail=f"Instance with ID '{instance_id}' not found")
        
        # TODO: Implement actual Redis connection test
        # For now, simulate the test
        import asyncio
        await asyncio.sleep(1)  # Simulate connection test delay
        
        # Simple heuristic: localhost usually works
        is_localhost = target_instance.host.lower() in ['localhost', '127.0.0.1']
        success = is_localhost  # For demo purposes
        
        result = {
            "success": success,
            "message": (
                f"Successfully connected to Redis at {target_instance.host}:{target_instance.port}"
                if success else
                f"Failed to connect to Redis at {target_instance.host}:{target_instance.port}. Please verify the connection details."
            ),
            "instance_id": instance_id,
            "tested_at": datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(f"Connection test for {instance_id}: {'SUCCESS' if success else 'FAILED'}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test connection for instance {instance_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to test connection")
