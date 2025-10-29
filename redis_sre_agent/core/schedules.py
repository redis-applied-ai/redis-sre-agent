"""
Schedule domain model and storage helpers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, Field
from redisvl.query import BaseQuery, FilterQuery

from ..core.redis import get_redis_client, get_schedules_index
from .keys import RedisKeys

logger = logging.getLogger(__name__)


class Schedule(BaseModel):
    """Schedule model for automated agent runs."""

    id: str = Field(default_factory=lambda: __import__("uuid").uuid4().__str__())
    name: str = Field(..., description="Human-readable schedule name")
    description: Optional[str] = Field(None, description="Schedule description")
    interval_type: str = Field(..., description="Interval type: minutes, hours, days, weeks")
    interval_value: int = Field(..., ge=1, description="Interval value (e.g., 30 for '30 minutes')")
    redis_instance_id: Optional[str] = Field(
        None, description="Redis instance ID to use (optional)"
    )
    instructions: str = Field(..., description="Instructions for the agent to execute")
    enabled: bool = Field(True, description="Whether the schedule is active")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_run_at: Optional[str] = Field(None, description="Last execution timestamp")
    next_run_at: Optional[str] = Field(None, description="Next scheduled execution timestamp")

    def calculate_next_run(self) -> datetime:
        """Calculate the next run time based on interval."""
        now = datetime.now(timezone.utc)

        if self.interval_type == "minutes":
            return now + timedelta(minutes=self.interval_value)
        elif self.interval_type == "hours":
            return now + timedelta(hours=self.interval_value)
        elif self.interval_type == "days":
            return now + timedelta(days=self.interval_value)
        elif self.interval_type == "weeks":
            return now + timedelta(weeks=self.interval_value)
        else:
            raise ValueError(f"Unsupported interval type: {self.interval_type}")


def calculate_next_run(schedule: Schedule) -> datetime:
    """Helper to calculate next run from a Schedule instance (pure function)."""
    return schedule.calculate_next_run()


async def _get_schedules(query: Optional[BaseQuery] = None) -> List[Dict]:
    index = await get_schedules_index()

    # Create a filter query to get all schedules
    if not query:
        query = FilterQuery(
            return_fields=[
                "id",
                "name",
                "description",
                "interval_type",
                "interval_value",
                "redis_instance_id",
                "instructions",
                "enabled",
                "created_at",
                "updated_at",
                "last_run_at",
                "next_run_at",
            ],
            filter_expression="*",  # Get all schedules
            sort_by=("created_at", "DESC"),
        )

    # Execute the search
    results = await index.query(query)
    schedules = []

    for result in results:
        try:
            # Convert result to dictionary format
            if isinstance(result, dict):
                schedule_data = result.copy()
            elif hasattr(result, "__dict__"):
                schedule_data = result.__dict__.copy()
            else:
                # Try to access as attributes
                schedule_data = {}
                for field in [
                    "id",
                    "name",
                    "description",
                    "interval_type",
                    "interval_value",
                    "redis_instance_id",
                    "instructions",
                    "enabled",
                    "created_at",
                    "updated_at",
                    "last_run_at",
                    "next_run_at",
                ]:
                    try:
                        schedule_data[field] = getattr(result, field, None)
                    except AttributeError:
                        schedule_data[field] = None

            # Extract actual schedule ID from Redis key (remove "sre_schedules:" prefix)
            redis_key = schedule_data.get("id", "")
            if redis_key.startswith("sre_schedules:"):
                schedule_data["id"] = redis_key[len("sre_schedules:") :]

            # Convert numeric fields back to datetime strings
            for field in ["created_at", "updated_at", "last_run_at", "next_run_at"]:
                if schedule_data.get(field) and schedule_data[field] != 0:
                    try:
                        timestamp = float(schedule_data[field])
                        if timestamp > 0:
                            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                            schedule_data[field] = dt.isoformat()
                        else:
                            schedule_data[field] = None
                    except (ValueError, TypeError):
                        schedule_data[field] = None
                else:
                    schedule_data[field] = None

            # Convert boolean and numeric fields
            schedule_data["enabled"] = schedule_data.get("enabled") == "true"
            try:
                schedule_data["interval_value"] = int(schedule_data.get("interval_value", 0))
            except (ValueError, TypeError):
                schedule_data["interval_value"] = 0

            schedules.append(schedule_data)

        except Exception as e:
            logger.error(f"Failed to process schedule result: {e}")
            continue

    return schedules


async def store_schedule(schedule_data: Dict) -> bool:
    """Store a schedule in Redis with search index."""
    try:
        client = get_redis_client()
        await get_schedules_index()

        schedule_id = schedule_data["id"]

        # Convert datetime strings to timestamps for numeric fields
        redis_data = schedule_data.copy()

        # Convert datetime fields to timestamps
        for field in ["created_at", "updated_at", "last_run_at", "next_run_at"]:
            if redis_data.get(field):
                if isinstance(redis_data[field], str):
                    dt = datetime.fromisoformat(redis_data[field].replace("Z", "+00:00"))
                    redis_data[field] = dt.timestamp()
                elif isinstance(redis_data[field], datetime):
                    redis_data[field] = redis_data[field].timestamp()
            else:
                redis_data[field] = 0  # Default for numeric fields

        # Convert boolean to string for tag field
        redis_data["enabled"] = "true" if redis_data.get("enabled", True) else "false"

        # Convert None values to empty strings for Redis
        for key_name, value in redis_data.items():
            if value is None:
                redis_data[key_name] = ""

        # Store in Redis hash
        key = f"sre_schedules:{schedule_id}"
        await client.hset(key, mapping=redis_data)

        logger.info(f"Stored schedule {schedule_id} in Redis")
        return True

    except Exception as e:
        logger.error(f"Failed to store schedule {schedule_data.get('id', 'unknown')}: {e}")
        return False


async def get_schedule(schedule_id: str) -> Optional[Dict]:
    """Retrieve a schedule from Redis."""
    try:
        client = get_redis_client()
        key = f"sre_schedules:{schedule_id}"

        data = await client.hgetall(key)
        if not data:
            return None

        # Convert bytes to strings and restore proper types
        schedule = {}
        for k, v in data.items():
            key_str = k.decode() if isinstance(k, bytes) else k
            val_str = v.decode() if isinstance(v, bytes) else v
            schedule[key_str] = val_str

        # Convert numeric fields back to datetime strings
        for field in ["created_at", "updated_at", "last_run_at", "next_run_at"]:
            if schedule.get(field) and schedule[field] != "0":
                timestamp = float(schedule[field])
                if timestamp > 0:
                    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                    schedule[field] = dt.isoformat()
                else:
                    schedule[field] = None
            else:
                schedule[field] = None

        # Convert string fields back to proper types
        schedule["enabled"] = schedule.get("enabled", "true") == "true"
        schedule["interval_value"] = int(schedule.get("interval_value", 0))

        return schedule

    except Exception as e:
        logger.error(f"Failed to get schedule {schedule_id}: {e}")
        return None


async def list_schedules() -> List[Dict]:
    """List all schedules from Redis using RedisVL."""
    return await _get_schedules()


async def delete_schedule(schedule_id: str) -> bool:
    """Delete a schedule from Redis."""
    try:
        client = get_redis_client()
        key = RedisKeys.schedule_key(schedule_id)

        result = await client.delete(key)
        if result:
            logger.info(f"Deleted schedule {schedule_id} from Redis")
            return True
        else:
            logger.warning(f"Schedule {schedule_id} not found for deletion")
            return False

    except Exception as e:
        logger.error(f"Failed to delete schedule {schedule_id}: {e}")
        return False


async def find_schedules_needing_runs(current_time: datetime) -> List[Dict]:
    """Find schedules that need to have runs created based on current time."""
    current_timestamp = current_time.timestamp()

    # Create a filter query for enabled schedules where next_run_at <= current_time
    # Using RedisVL FilterQuery for non-vector searches
    query = FilterQuery(
        return_fields=[
            "id",
            "name",
            "description",
            "interval_type",
            "interval_value",
            "redis_instance_id",
            "instructions",
            "enabled",
            "created_at",
            "updated_at",
            "last_run_at",
            "next_run_at",
        ],
        filter_expression=f"@enabled:{{true}} @next_run_at:[0 {current_timestamp}]",
    )

    schedules_needing_runs = await _get_schedules(query)
    logger.info(f"Found {len(schedules_needing_runs)} schedules needing runs")

    return schedules_needing_runs


async def update_schedule_next_run(schedule_id: str, next_run_time: datetime) -> bool:
    """Update the next_run_at time for a schedule."""
    try:
        client = get_redis_client()
        key = f"sre_schedules:{schedule_id}"

        logger.info(
            f"Updating schedule {schedule_id} next_run_at to {next_run_time} (timestamp: {next_run_time.timestamp()})"
        )

        # Update the next_run_at field
        result1 = await client.hset(key, "next_run_at", next_run_time.timestamp())
        result2 = await client.hset(key, "updated_at", datetime.now(timezone.utc).timestamp())

        logger.info(f"Redis hset results: next_run_at={result1}, updated_at={result2}")

        # Verify the update
        updated_value = await client.hget(key, "next_run_at")
        logger.info(f"Verified next_run_at value in Redis: {updated_value}")

        logger.info(
            f"Successfully updated next run time for schedule {schedule_id} to {next_run_time}"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to update next run time for schedule {schedule_id}: {e}")
        return False


async def update_schedule_last_run(schedule_id: str, last_run_time: datetime) -> bool:
    """Update the last_run_at time for a schedule."""
    try:
        client = get_redis_client()
        key = f"sre_schedules:{schedule_id}"

        # Update the last_run_at field
        await client.hset(key, "last_run_at", last_run_time.timestamp())
        await client.hset(key, "updated_at", datetime.now(timezone.utc).timestamp())

        logger.debug(f"Updated last run time for schedule {schedule_id} to {last_run_time}")
        return True

    except Exception as e:
        logger.error(f"Failed to update last run time for schedule {schedule_id}: {e}")
        return False
