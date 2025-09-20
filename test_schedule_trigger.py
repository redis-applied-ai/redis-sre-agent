#!/usr/bin/env python3

import asyncio
from datetime import datetime, timezone

import httpx

from redis_sre_agent.core.schedule_storage import list_schedules


async def test_schedule_trigger():
    """Test manual schedule triggering."""

    # First, get the schedule ID
    schedules = await list_schedules()
    if not schedules:
        print("❌ No schedules found")
        return

    schedule = schedules[0]  # Get the first schedule
    schedule_id = schedule["id"]
    schedule_name = schedule["name"]

    print(f"📅 Testing trigger for schedule: {schedule_name} (ID: {schedule_id})")
    print(f"   Current next_run_at: {schedule.get('next_run_at', 'None')}")

    # Test the manual trigger API
    base_url = "http://localhost:8000"

    async with httpx.AsyncClient() as client:
        try:
            print("🚀 Triggering schedule via API...")
            response = await client.post(f"{base_url}/api/v1/schedules/{schedule_id}/trigger")

            if response.status_code == 200:
                result = response.json()
                print("✅ Schedule triggered successfully!")
                print(f"   Response: {result}")
            else:
                print(f"❌ Failed to trigger schedule: {response.status_code}")
                print(f"   Error: {response.text}")

        except Exception as e:
            print(f"❌ Error calling API: {e}")

    # Wait a moment and check if the schedule was updated
    print("\n⏳ Waiting 2 seconds then checking schedule status...")
    await asyncio.sleep(2)

    # Check the updated schedule
    updated_schedules = await list_schedules()
    updated_schedule = next((s for s in updated_schedules if s["id"] == schedule_id), None)

    if updated_schedule:
        print("📅 Updated schedule status:")
        print(f"   next_run_at: {updated_schedule.get('next_run_at', 'None')}")
        print(f"   last_run_at: {updated_schedule.get('last_run_at', 'None')}")

        # Check if next_run_at was updated to current time (indicating our fix worked)
        next_run_str = updated_schedule.get('next_run_at')
        if next_run_str:
            try:
                next_run_time = datetime.fromisoformat(next_run_str.replace('Z', '+00:00'))
                current_time = datetime.now(timezone.utc)
                time_diff = abs((next_run_time - current_time).total_seconds())

                if time_diff < 60:  # Within 1 minute of current time
                    print(f"✅ Schedule next_run_at was updated to current time (diff: {time_diff:.1f}s)")
                else:
                    print(f"⚠️  Schedule next_run_at not updated to current time (diff: {time_diff:.1f}s)")
            except Exception as e:
                print(f"❌ Error parsing next_run_at: {e}")
    else:
        print("❌ Could not find updated schedule")

if __name__ == "__main__":
    asyncio.run(test_schedule_trigger())
