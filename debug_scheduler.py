#!/usr/bin/env python3

import asyncio
from datetime import datetime, timezone

from redis_sre_agent.core.schedule_storage import find_schedules_needing_runs, list_schedules


async def debug_scheduler():
    current_time = datetime.now(timezone.utc)
    print(f"Current UTC time: {current_time}")

    schedules = await list_schedules()
    print(f"All schedules ({len(schedules)}):")
    for schedule in schedules:
        next_run = schedule.get("next_run_at", "None")
        print(f"  - {schedule['name']} next run: {next_run}")
        if next_run and next_run != "None":
            next_run_dt = datetime.fromisoformat(next_run.replace("Z", "+00:00"))
            print(f"    Next run timestamp: {next_run_dt.timestamp()}")
            print(f"    Current timestamp: {current_time.timestamp()}")
            print(f"    Should run: {next_run_dt.timestamp() <= current_time.timestamp()}")

    print()
    needing_runs = await find_schedules_needing_runs(current_time)
    print(f"Schedules needing runs: {len(needing_runs)}")


if __name__ == "__main__":
    asyncio.run(debug_scheduler())
