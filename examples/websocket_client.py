#!/usr/bin/env python3
"""
Example WebSocket client for real-time task status updates.

This demonstrates how to connect to the WebSocket endpoint and receive
real-time updates about task progress.
"""

import asyncio
import json
import sys
from typing import Optional

import requests
import websockets


async def monitor_task(thread_id: str, base_url: str = "http://localhost:8000"):
    """Monitor a task's progress via WebSocket."""

    # First, verify the task exists
    try:
        response = requests.get(f"{base_url}/api/v1/tasks/{thread_id}")
        if response.status_code == 404:
            print(f"❌ Task {thread_id} not found")
            return
        elif response.status_code != 200:
            print(f"❌ Error checking task: {response.status_code}")
            return

        task_info = response.json()
        print(f"📋 Monitoring task: {thread_id}")
        print(f"   Status: {task_info['status']}")
        print(f"   Updates: {len(task_info['updates'])}")
        print("🔗 Connecting to WebSocket...")

    except requests.RequestException as e:
        print(f"❌ Failed to check task status: {e}")
        return

    # Connect to WebSocket
    ws_url = f"ws://localhost:8000/api/v1/ws/tasks/{thread_id}"

    try:
        async with websockets.connect(ws_url) as websocket:
            print("✅ Connected to WebSocket")
            print("📡 Listening for updates... (Press Ctrl+C to stop)")
            print("-" * 60)

            # Send periodic pings to keep connection alive
            ping_task = asyncio.create_task(send_pings(websocket))

            try:
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        await handle_update(data)
                    except json.JSONDecodeError:
                        print(f"⚠️  Received invalid JSON: {message}")
                    except Exception as e:
                        print(f"⚠️  Error handling message: {e}")

            except websockets.exceptions.ConnectionClosed:
                print("🔌 WebSocket connection closed")
            finally:
                ping_task.cancel()
                try:
                    await ping_task
                except asyncio.CancelledError:
                    pass

    except websockets.exceptions.WebSocketException as e:
        print(f"❌ WebSocket error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


async def send_pings(websocket):
    """Send periodic ping messages to keep the connection alive."""
    try:
        while True:
            await asyncio.sleep(30)  # Ping every 30 seconds
            await websocket.send(json.dumps({"type": "ping"}))
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"⚠️  Ping error: {e}")


async def handle_update(data: dict):
    """Handle incoming WebSocket updates."""
    update_type = data.get("update_type", "unknown")
    timestamp = data.get("timestamp", "")

    if update_type == "initial_state":
        print("📊 Initial State:")
        print(f"   Status: {data.get('status', 'unknown')}")
        print(f"   Recent Updates: {len(data.get('updates', []))}")
        if data.get("result"):
            print("   Has Result: Yes")
        if data.get("error_message"):
            print(f"   Error: {data.get('error_message')}")
        print()

    elif update_type == "status_change":
        status = data.get("status", "unknown")
        message = data.get("message", "")
        print(f"🔄 Status Changed: {status}")
        if message:
            print(f"   Message: {message}")
        print(f"   Time: {timestamp}")
        print()

    elif update_type == "thread_update":
        message = data.get("message", "")
        update_subtype = data.get("update_type", "progress")
        print(f"📝 Update ({update_subtype}): {message}")
        print(f"   Time: {timestamp}")

        # Show metadata if present
        metadata = data.get("metadata", {})
        if metadata:
            print(f"   Metadata: {json.dumps(metadata, indent=2)}")
        print()

    elif update_type == "result_set":
        print("✅ Task Completed!")
        result = data.get("result", {})
        if result:
            print(f"   Result: {json.dumps(result, indent=2)}")
        print(f"   Time: {timestamp}")
        print()

    elif data.get("type") == "pong":
        print("🏓 Pong received")

    else:
        print(f"📨 Unknown Update Type: {update_type}")
        print(f"   Data: {json.dumps(data, indent=2)}")
        print()


async def create_test_task(base_url: str = "http://localhost:8000") -> Optional[str]:
    """Create a test task for demonstration."""
    try:
        response = requests.post(
            f"{base_url}/api/v1/triage",
            json={
                "query": "Test WebSocket monitoring - check Redis memory usage",
                "user_id": "websocket_test_user",
                "priority": 0,
                "tags": ["test", "websocket", "demo"],
            },
        )

        if response.status_code == 202:
            data = response.json()
            thread_id = data["thread_id"]
            print(f"✅ Created test task: {thread_id}")
            return thread_id
        else:
            print(f"❌ Failed to create test task: {response.status_code}")
            print(response.text)
            return None

    except requests.RequestException as e:
        print(f"❌ Failed to create test task: {e}")
        return None


async def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("WebSocket Task Monitor")
        print("=" * 50)
        print()
        print("Usage:")
        print(f"  {sys.argv[0]} <thread_id>     # Monitor existing task")
        print(f"  {sys.argv[0]} --create-test  # Create and monitor test task")
        print()
        print("Examples:")
        print(f"  {sys.argv[0]} 01HXYZ123456789ABCDEF")
        print(f"  {sys.argv[0]} --create-test")
        return

    base_url = "http://localhost:8000"

    if sys.argv[1] == "--create-test":
        print("🚀 Creating test task...")
        thread_id = await create_test_task(base_url)
        if not thread_id:
            return

        # Wait a moment for the task to start
        print("⏳ Waiting for task to start...")
        await asyncio.sleep(2)
    else:
        thread_id = sys.argv[1]

    try:
        await monitor_task(thread_id, base_url)
    except KeyboardInterrupt:
        print("\n👋 Monitoring stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
