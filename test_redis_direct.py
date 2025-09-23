#!/usr/bin/env python3

import asyncio
from datetime import datetime, timezone

from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.schedule_storage import list_schedules, update_schedule_next_run


async def test_redis_direct():
    """Test direct Redis access to see if updates are working."""

    # Get schedules
    schedules = await list_schedules()
    if not schedules:
        print("❌ No schedules found")
        return

    schedule = schedules[0]
    schedule_id = schedule["id"]
    schedule_name = schedule["name"]

    print(f"📅 Testing Redis direct access for schedule: {schedule_name}")
    print(f"   Schedule ID: {schedule_id}")
    print(f"   Current next_run_at (from index): {schedule.get('next_run_at', 'None')}")

    # Check direct Redis hash
    client = get_redis_client()
    key = f"sre_schedules:{schedule_id}"

    print(f"\n🔍 Checking direct Redis hash: {key}")
    hash_data = await client.hgetall(key)
    print(f"   Direct Redis data: {hash_data}")

    if b"next_run_at" in hash_data:
        next_run_timestamp = float(hash_data[b"next_run_at"])
        next_run_dt = datetime.fromtimestamp(next_run_timestamp, tz=timezone.utc)
        print(f"   Direct next_run_at: {next_run_dt.isoformat()}")

    # Test updating the next_run_at
    current_time = datetime.now(timezone.utc)
    print(f"\n🔄 Updating next_run_at to current time: {current_time}")

    success = await update_schedule_next_run(schedule_id, current_time)
    print(f"   Update result: {success}")

    # Check direct Redis hash again
    print("\n🔍 Checking direct Redis hash after update:")
    hash_data_after = await client.hgetall(key)
    print(f"   Direct Redis data after: {hash_data_after}")

    if b"next_run_at" in hash_data_after:
        next_run_timestamp_after = float(hash_data_after[b"next_run_at"])
        next_run_dt_after = datetime.fromtimestamp(next_run_timestamp_after, tz=timezone.utc)
        print(f"   Direct next_run_at after: {next_run_dt_after.isoformat()}")

        time_diff = abs((next_run_dt_after - current_time).total_seconds())
        print(f"   Time difference: {time_diff:.1f} seconds")

        if time_diff < 5:
            print("✅ Direct Redis update worked!")
        else:
            print("❌ Direct Redis update failed or has wrong time")

    # Now check if the index reflects the change
    print("\n📊 Checking if RedisVL index reflects the change...")
    await asyncio.sleep(1)  # Give index time to update

    updated_schedules = await list_schedules()
    updated_schedule = next((s for s in updated_schedules if s["id"] == schedule_id), None)

    if updated_schedule:
        print(f"   Index next_run_at: {updated_schedule.get('next_run_at', 'None')}")

        index_next_run_str = updated_schedule.get("next_run_at")
        if index_next_run_str:
            try:
                index_next_run_dt = datetime.fromisoformat(
                    index_next_run_str.replace("Z", "+00:00")
                )
                index_time_diff = abs((index_next_run_dt - current_time).total_seconds())
                print(f"   Index time difference: {index_time_diff:.1f} seconds")

                if index_time_diff < 5:
                    print("✅ RedisVL index also updated!")
                else:
                    print("⚠️  RedisVL index not updated yet or has wrong time")
            except Exception as e:
                print(f"❌ Error parsing index next_run_at: {e}")
    else:
        print("❌ Could not find schedule in index")


if __name__ == "__main__":
    asyncio.run(test_redis_direct())
