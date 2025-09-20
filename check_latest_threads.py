#!/usr/bin/env python3

import asyncio
from datetime import datetime, timezone

from redis_sre_agent.core.thread_state import get_thread_manager


async def check_latest_threads():
    """Check for the very latest threads."""

    thread_manager = get_thread_manager()

    # Check for threads created after 22:21:50 (just before our last trigger)
    cutoff_time = datetime(2025, 9, 19, 22, 21, 50, tzinfo=timezone.utc)

    print(f"🔍 Checking for threads created after {cutoff_time}")

    try:
        # List threads for scheduler user
        scheduler_threads = await thread_manager.list_threads(user_id="scheduler", limit=20)

        print(f"\n📋 Checking {len(scheduler_threads)} scheduler threads:")

        latest_threads = []

        for thread in scheduler_threads:
            thread_id = thread.get("thread_id", "unknown")
            created_at_str = thread.get("created_at")

            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    if created_at >= cutoff_time:
                        latest_threads.append((thread_id, created_at, thread))
                except Exception as e:
                    print(f"  ❌ Error parsing thread {thread_id}: {e}")

        # Sort by creation time (newest first)
        latest_threads.sort(key=lambda x: x[1], reverse=True)

        if latest_threads:
            print(f"\n✅ Found {len(latest_threads)} threads created after {cutoff_time}:")

            for thread_id, created_at, thread in latest_threads:
                print(f"\n  🧵 Thread: {thread_id}")
                print(f"     Created: {created_at}")
                print(f"     Status: {thread.get('status', 'unknown')}")

                # Get thread details
                try:
                    thread_state = await thread_manager.get_thread_state(thread_id)
                    if thread_state:
                        context = thread_state.context
                        tags = thread_state.metadata.tags if thread_state.metadata.tags else []

                        print(f"     Tags: {tags}")

                        if context.get("manual_trigger"):
                            print("     🎯 MANUAL TRIGGER!")
                        if context.get("schedule_name"):
                            print(f"     📅 Schedule: {context['schedule_name']}")
                        if context.get("scheduled_at"):
                            print(f"     ⏰ Scheduled at: {context['scheduled_at']}")

                        # Check if this looks like our manual trigger
                        session_id = thread_state.metadata.session_id
                        if session_id and "manual_schedule" in session_id:
                            print(f"     🚀 This looks like a manual trigger! Session: {session_id}")

                except Exception as e:
                    print(f"     ❌ Error getting thread state: {e}")
        else:
            print(f"\n❌ No threads found created after {cutoff_time}")
            print("This suggests the manual trigger may not have created a thread successfully.")

    except Exception as e:
        print(f"❌ Error checking threads: {e}")

if __name__ == "__main__":
    asyncio.run(check_latest_threads())
