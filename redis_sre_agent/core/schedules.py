"""Schedule domain model.

Layer: core (domain). No API dependencies.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field


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
