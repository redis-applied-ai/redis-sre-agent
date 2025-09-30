# WebSocket Task Monitoring

The Redis SRE Agent now supports real-time task monitoring through WebSocket connections. This allows clients to receive live updates about task progress without polling.

## Overview

The WebSocket system uses Redis Streams to broadcast task updates to multiple connected clients in real-time. When a task's status changes, progress updates are added, or results become available, all connected clients receive immediate notifications.

## Architecture

```
Task Updates → ThreadManager → Redis Streams → WebSocket Clients
                     ↓
              TaskStreamManager
                     ↓
              WebSocket Endpoint
```

### Components

1. **TaskStreamManager**: Manages Redis Streams for task updates and WebSocket client broadcasting
2. **WebSocket Endpoint**: `/api/v1/ws/tasks/{thread_id}` - Real-time connection for task monitoring
3. **Stream Integration**: ThreadManager publishes updates to Redis Streams automatically
4. **Client Management**: Automatic connection tracking and cleanup

## API Endpoints

### WebSocket Connection

```
ws://localhost:8000/api/v1/ws/tasks/{thread_id}
```

**Connection Flow:**
1. Client connects to WebSocket endpoint with task ID
2. Server verifies task exists
3. Server sends initial task state immediately
4. Server starts Redis Stream consumer for real-time updates
5. All subsequent task updates are broadcast to connected clients

### Stream Information

```http
GET /api/v1/tasks/{thread_id}/stream-info
```

Returns information about the task's stream status:

```json
{
  "thread_id": "01K5ENJF3BZDZ1J2TRSHG1G45S",
  "stream_key": "sre:stream:task:01K5ENJF3BZDZ1J2TRSHG1G45S",
  "stream_length": 5,
  "active_connections": 2,
  "consumer_active": true
}
```

## Message Types

### Initial State
Sent immediately upon connection:

```json
{
  "update_type": "initial_state",
  "thread_id": "01K5ENJF3BZDZ1J2TRSHG1G45S",
  "status": "in_progress",
  "updates": [...],
  "result": null,
  "error_message": null,
  "timestamp": "2025-09-18T15:03:19.417853+00:00"
}
```

### Status Changes
When task status changes:

```json
{
  "update_type": "status_change",
  "thread_id": "01K5ENJF3BZDZ1J2TRSHG1G45S",
  "status": "completed",
  "message": "Status changed to completed",
  "timestamp": "2025-09-18T15:05:30.123456+00:00"
}
```

### Progress Updates
When new progress updates are added:

```json
{
  "update_type": "thread_update",
  "thread_id": "01K5ENJF3BZDZ1J2TRSHG1G45S",
  "message": "Analyzing Redis memory usage...",
  "update_type": "progress",
  "metadata": {"step": 2, "total": 5},
  "timestamp": "2025-09-18T15:04:15.789012+00:00"
}
```

### Task Results
When task completes with results:

```json
{
  "update_type": "result_set",
  "thread_id": "01K5ENJF3BZDZ1J2TRSHG1G45S",
  "result": {"analysis": "...", "recommendations": "..."},
  "message": "Task result available",
  "timestamp": "2025-09-18T15:06:45.345678+00:00"
}
```

## Client Implementation

### Python Example

```python
import asyncio
import json
import websockets

async def monitor_task(thread_id):
    uri = f"ws://localhost:8000/api/v1/ws/tasks/{thread_id}"

    async with websockets.connect(uri) as websocket:
        print(f"Connected to task {thread_id}")

        async for message in websocket:
            data = json.loads(message)
            print(f"Update: {data['update_type']} - {data.get('message', '')}")

            if data.get('status') == 'completed':
                print("Task completed!")
                break

# Usage
asyncio.run(monitor_task("01K5ENJF3BZDZ1J2TRSHG1G45S"))
```

### JavaScript Example

```javascript
const ws = new WebSocket(`ws://localhost:8000/api/v1/ws/tasks/${threadId}`);

ws.onopen = () => {
    console.log('Connected to task monitoring');
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Task update:', data);

    if (data.update_type === 'status_change') {
        updateTaskStatus(data.status);
    } else if (data.update_type === 'thread_update') {
        addProgressUpdate(data.message);
    }
};

ws.onclose = () => {
    console.log('WebSocket connection closed');
};
```

### React Component

```tsx
import { TaskMonitor } from '@/components/TaskMonitor';

function TaskPage({ threadId }) {
    return (
        <div>
            <h1>Task Monitoring</h1>
            <TaskMonitor threadId={threadId} />
        </div>
    );
}
```

## Features

### Multi-Client Support
- Multiple clients can monitor the same task simultaneously
- Each client receives all updates independently
- Automatic cleanup when clients disconnect

### Connection Management
- Automatic reconnection on connection loss
- Ping/pong heartbeat to keep connections alive
- Graceful handling of client disconnections

### Performance
- Redis Streams provide efficient message broadcasting
- Stream consumers start/stop automatically based on client connections
- TTL on streams (24 hours) for automatic cleanup

### Error Handling
- Invalid task IDs return error messages
- Connection errors are handled gracefully
- Failed message delivery removes disconnected clients

## Testing

### Example Client
Use the provided example client to test WebSocket functionality:

```bash
# Monitor existing task
python examples/websocket_client.py 01K5ENJF3BZDZ1J2TRSHG1G45S

# Create and monitor new task
python examples/websocket_client.py --create-test
```

### Manual Testing
1. Create a task via the triage endpoint
2. Connect to the WebSocket endpoint
3. Observe real-time updates as the task progresses

### Unit Tests
Run the comprehensive test suite:

```bash
pytest tests/unit/test_websockets.py -v
```

## Configuration

### Redis Streams
- Stream key format: `sre:stream:task:{thread_id}`
- TTL: 24 hours (86400 seconds)
- Consumer group: Automatic per-task management

### WebSocket Settings
- Ping interval: 30 seconds
- Connection timeout: Handled by FastAPI/Uvicorn
- Max connections: No artificial limit (system dependent)

## Monitoring

### Stream Information
Check stream status and active connections:

```bash
curl http://localhost:8000/api/v1/tasks/{thread_id}/stream-info
```

### Redis Monitoring
Monitor Redis Streams directly:

```bash
# List all task streams
redis-cli KEYS "sre:stream:task:*"

# Check stream length
redis-cli XLEN sre:stream:task:01K5ENJF3BZDZ1J2TRSHG1G45S

# View recent messages
redis-cli XRANGE sre:stream:task:01K5ENJF3BZDZ1J2TRSHG1G45S - + COUNT 10
```

## Troubleshooting

### Connection Issues
- Verify task exists before connecting
- Check WebSocket URL format
- Ensure Redis is running and accessible

### Missing Updates
- Check Redis Stream exists and has messages
- Verify ThreadManager is publishing updates
- Check for consumer errors in logs

### Performance Issues
- Monitor Redis memory usage for large streams
- Consider stream trimming for long-running tasks
- Check network latency for remote connections
