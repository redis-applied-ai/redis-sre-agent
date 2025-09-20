#!/usr/bin/env python3

import asyncio
from datetime import datetime, timezone

from docket import Docket

from redis_sre_agent.core.schedule_storage import list_schedules
from redis_sre_agent.core.tasks import get_redis_url, process_agent_turn
from redis_sre_agent.core.thread_state import get_thread_manager


async def test_manual_trigger_direct():
    """Test manual trigger logic directly."""

    # Get the schedule
    schedules = await list_schedules()
    if not schedules:
        print("❌ No schedules found")
        return

    schedule_data = schedules[0]
    schedule_id = schedule_data["id"]
    schedule_name = schedule_data["name"]

    print(f"📅 Testing direct manual trigger for: {schedule_name} (ID: {schedule_id})")

    current_time = datetime.now(timezone.utc)

    # Create thread for the manual run
    thread_manager = get_thread_manager()

    # Prepare context for the manual run
    run_context = {
        "schedule_id": schedule_id,
        "schedule_name": schedule_data["name"],
        "automated": True,
        "manual_trigger": True,  # Mark as manual trigger
        "original_query": schedule_data["instructions"],
        "scheduled_at": current_time.isoformat(),
    }

    if schedule_data.get("redis_instance_id"):
        run_context["instance_id"] = schedule_data["redis_instance_id"]

    print("🧵 Creating thread...")

    try:
        # Create thread for the manual run
        thread_id = await thread_manager.create_thread(
            user_id="scheduler",
            session_id=f"manual_schedule_{schedule_id}_{current_time.strftime('%Y%m%d_%H%M%S')}",
            initial_context=run_context,
            tags=["automated", "scheduled", "manual_trigger"]
        )

        print(f"✅ Created thread: {thread_id}")

        # Submit the agent task directly
        print("🚀 Submitting agent task...")

        async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
            # Use a deduplication key for the manual trigger
            task_key = f"manual_schedule_test_{schedule_id}_{current_time.strftime('%Y%m%d_%H%M%S')}"

            try:
                task_func = docket.add(process_agent_turn, key=task_key)
                agent_task_id = await task_func(
                    thread_id=thread_id,
                    message=schedule_data["instructions"],
                    context=run_context
                )
                print(f"✅ Submitted agent task: {agent_task_id}")
                print(f"   Task key: {task_key}")

            except Exception as e:
                print(f"❌ Failed to submit agent task: {e}")
                return

        # Wait a moment and check the thread
        print("\n⏳ Waiting 3 seconds then checking thread status...")
        await asyncio.sleep(3)

        thread_state = await thread_manager.get_thread_state(thread_id)
        if thread_state:
            print(f"📊 Thread status: {thread_state.status if hasattr(thread_state, 'status') else 'unknown'}")
            print(f"   Context: {thread_state.context}")
            print(f"   Tags: {thread_state.metadata.tags}")
        else:
            print("❌ Could not retrieve thread state")

    except Exception as e:
        print(f"❌ Error in manual trigger test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_manual_trigger_direct())
