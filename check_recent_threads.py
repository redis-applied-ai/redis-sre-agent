#!/usr/bin/env python3

import asyncio
from datetime import datetime, timedelta, timezone

from redis_sre_agent.core.thread_state import get_thread_manager


async def check_recent_threads():
    """Check for recent threads, especially scheduled ones."""

    thread_manager = get_thread_manager()

    # Get recent threads (last 10 minutes)
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=10)

    print(f"🔍 Checking for threads created after {cutoff_time}")

    try:
        # List threads for scheduler user
        scheduler_threads = await thread_manager.list_threads(user_id="scheduler", limit=10)

        print(f"\n📋 Found {len(scheduler_threads)} scheduler threads:")

        for thread in scheduler_threads:
            thread_id = thread.get("thread_id", "unknown")
            created_at_str = thread.get("created_at")

            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    if created_at >= cutoff_time:
                        print(f"  ✅ Recent thread: {thread_id}")
                        print(f"     Created: {created_at}")
                        print(f"     Status: {thread.get('status', 'unknown')}")

                        # Get thread details
                        thread_state = await thread_manager.get_thread_state(thread_id)
                        if thread_state:
                            context = thread_state.context
                            print(f"     Context: {context}")

                            if context.get("manual_trigger"):
                                print("     🎯 This is a manual trigger!")
                            if context.get("schedule_name"):
                                print(f"     📅 Schedule: {context['schedule_name']}")

                        print()
                    else:
                        print(f"  ⏰ Older thread: {thread_id} (created {created_at})")
                except Exception as e:
                    print(f"  ❌ Error parsing thread {thread_id}: {e}")
            else:
                print(f"  ❓ Thread {thread_id} has no created_at timestamp")

        # Also check for any threads with manual_trigger tag
        print("\n🏷️  Checking for threads with 'manual_trigger' tag...")

        # This is a bit more complex since we need to check thread metadata
        # Let's just check the recent scheduler threads we already have
        manual_trigger_threads = []
        for thread in scheduler_threads:
            thread_id = thread.get("thread_id", "unknown")
            try:
                thread_state = await thread_manager.get_thread_state(thread_id)
                if thread_state and thread_state.metadata.tags:
                    if "manual_trigger" in thread_state.metadata.tags:
                        manual_trigger_threads.append(thread_id)
            except Exception as e:
                print(f"  ❌ Error checking tags for thread {thread_id}: {e}")

        if manual_trigger_threads:
            print(f"  ✅ Found {len(manual_trigger_threads)} manual trigger threads:")
            for thread_id in manual_trigger_threads:
                print(f"     - {thread_id}")
        else:
            print("  ℹ️  No manual trigger threads found")

    except Exception as e:
        print(f"❌ Error checking threads: {e}")

if __name__ == "__main__":
    asyncio.run(check_recent_threads())
