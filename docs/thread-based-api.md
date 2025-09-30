# Thread-Based Conversation API

This document describes the new thread-based architecture for the Redis SRE Agent, which provides asynchronous, long-running conversations with progress tracking and state management.

## Architecture Overview

The thread-based API transforms SRE conversations from synchronous request-response to asynchronous, stateful interactions:

1. **Client submits query** → Gets `thread_id` immediately
2. **Agent processes in background** → Updates status/progress in Redis
3. **Client polls for updates** → Gets real-time progress and final results

## API Endpoints

### 1. Triage Issue (`POST /api/v1/triage`)

Submit an SRE issue for analysis and get a tracking thread ID.

**Request:**
```json
{
  "query": "Redis memory usage is at 95% and performance is degrading",
  "user_id": "sre-engineer-1",
  "session_id": "optional-session-id",
  "priority": 1,
  "tags": ["redis", "memory", "performance"],
  "context": {
    "environment": "production",
    "cluster": "main-redis-cluster"
  }
}
```

**Response (202 Accepted):**
```json
{
  "thread_id": "01K347ABC123XYZ789",
  "status": "queued",
  "message": "Issue has been triaged and queued for analysis",
  "estimated_completion": "2-5 minutes"
}
```

### 2. Check Task Status (`GET /api/v1/tasks/{thread_id}`)

Get current status, progress updates, and results for a thread.

**Response:**
```json
{
  "thread_id": "01K347ABC123XYZ789",
  "status": "in_progress",
  "updates": [
    {
      "timestamp": "2024-01-01T10:00:00Z",
      "message": "Issue received: Redis memory usage is at 95%...",
      "type": "triage",
      "metadata": {}
    },
    {
      "timestamp": "2024-01-01T10:00:05Z",
      "message": "Executing tool: check_service_health",
      "type": "tool_start",
      "metadata": {}
    },
    {
      "timestamp": "2024-01-01T10:00:15Z",
      "message": "Tool check_service_health completed successfully",
      "type": "tool_complete",
      "metadata": {}
    }
  ],
  "result": null,
  "action_items": [],
  "error_message": null,
  "metadata": {
    "created_at": "2024-01-01T10:00:00Z",
    "updated_at": "2024-01-01T10:00:15Z",
    "user_id": "sre-engineer-1",
    "priority": 1,
    "tags": ["redis", "memory", "performance"]
  }
}
```

**When completed (`status: "done"`):**
```json
{
  "thread_id": "01K347ABC123XYZ789",
  "status": "done",
  "updates": [
    // ... previous updates ...
    {
      "timestamp": "2024-01-01T10:02:30Z",
      "message": "Agent turn completed successfully",
      "type": "turn_complete",
      "metadata": {}
    }
  ],
  "result": {
    "response": "Analysis complete. Your Redis instance is experiencing memory pressure due to...",
    "metadata": {
      "iterations": 3,
      "tool_calls": 2,
      "session_id": "01K347ABC123XYZ789"
    },
    "action_items": [
      {
        "title": "Increase Redis maxmemory setting",
        "description": "Current setting is too low for workload",
        "priority": "high",
        "category": "configuration"
      }
    ],
    "turn_completed_at": "2024-01-01T10:02:30Z"
  },
  "action_items": [
    {
      "id": "01K347DEF456",
      "title": "Increase Redis maxmemory setting",
      "description": "Current setting is too low for workload",
      "priority": "high",
      "category": "configuration",
      "completed": false,
      "due_date": null
    }
  ]
}
```

### 3. Continue Conversation (`POST /api/v1/tasks/{thread_id}/continue`)

Add another message to an existing thread.

**Request:**
```json
{
  "query": "I've increased the maxmemory setting. What should I monitor next?",
  "context": {
    "action_taken": "increased maxmemory to 8GB"
  }
}
```

**Response (202 Accepted):**
```json
{
  "thread_id": "01K347ABC123XYZ789",
  "status": "queued",
  "message": "Conversation continuation queued for processing",
  "estimated_completion": "2-5 minutes"
}
```

### 4. Cancel Task (`DELETE /api/v1/tasks/{thread_id}`)

Cancel a queued or in-progress task.

**Response (204 No Content)**

## Thread Status States

- **`queued`**: Task is waiting to be processed
- **`in_progress`**: Agent is actively working on the task
- **`done`**: Task completed successfully
- **`failed`**: Task failed due to an error
- **`cancelled`**: Task was cancelled by user request

## Update Types

Progress updates include different types to help clients understand what's happening:

- **`triage`**: Initial issue processing
- **`queued`**: Task queued for processing
- **`turn_start`**: Beginning of agent turn
- **`agent_init`**: Agent initialization
- **`agent_processing`**: Agent working
- **`tool_start`**: Starting tool execution
- **`tool_complete`**: Tool execution finished
- **`agent_complete`**: Agent analysis complete
- **`turn_complete`**: Turn finished successfully
- **`continuation`**: Conversation continuation
- **`error`**: Error occurred
- **`cancellation`**: Task cancelled

## Client Usage Patterns

### Basic Issue Submission

```python
import asyncio
import aiohttp

async def submit_and_wait_for_results():
    async with aiohttp.ClientSession() as session:
        # Submit issue
        triage_data = {
            "query": "Redis is running out of memory",
            "user_id": "engineer-1",
            "priority": 1,
            "tags": ["redis", "memory"]
        }

        async with session.post("/api/v1/triage", json=triage_data) as resp:
            result = await resp.json()
            thread_id = result["thread_id"]
            print(f"Submitted issue, tracking: {thread_id}")

        # Poll for completion
        while True:
            async with session.get(f"/api/v1/tasks/{thread_id}") as resp:
                status_data = await resp.json()

                print(f"Status: {status_data['status']}")

                # Print new updates
                for update in status_data["updates"][-3:]:  # Last 3 updates
                    print(f"  {update['timestamp']}: {update['message']}")

                if status_data["status"] in ["done", "failed", "cancelled"]:
                    if status_data["status"] == "done":
                        print("Final response:", status_data["result"]["response"])
                        print("Action items:", len(status_data["action_items"]))
                    break

                await asyncio.sleep(2)  # Poll every 2 seconds

# Run the example
asyncio.run(submit_and_wait_for_results())
```

### Multi-Turn Conversation

```python
async def conversation_example():
    async with aiohttp.ClientSession() as session:
        # Initial submission
        triage_data = {
            "query": "Help me optimize Redis performance",
            "user_id": "engineer-1"
        }

        async with session.post("/api/v1/triage", json=triage_data) as resp:
            result = await resp.json()
            thread_id = result["thread_id"]

        # Wait for first response
        final_result = await wait_for_completion(session, thread_id)
        print("Agent:", final_result["response"])

        # Continue conversation
        follow_up = {
            "query": "What specific metrics should I monitor?",
            "context": {"previous_response": final_result["response"]}
        }

        async with session.post(f"/api/v1/tasks/{thread_id}/continue", json=follow_up) as resp:
            continue_result = await resp.json()

        # Wait for follow-up response
        final_result = await wait_for_completion(session, thread_id)
        print("Agent:", final_result["response"])

async def wait_for_completion(session, thread_id):
    while True:
        async with session.get(f"/api/v1/tasks/{thread_id}") as resp:
            data = await resp.json()
            if data["status"] == "done":
                return data["result"]
            elif data["status"] in ["failed", "cancelled"]:
                raise Exception(f"Task {data['status']}: {data.get('error_message')}")
            await asyncio.sleep(1)
```

## Redis Data Schema

The thread state is stored in Redis with the following key structure:

```
sre:thread:{thread_id}:status        # String: current status
sre:thread:{thread_id}:updates       # List: progress updates (JSON)
sre:thread:{thread_id}:context       # Hash: conversation context
sre:thread:{thread_id}:action_items  # String: action items (JSON)
sre:thread:{thread_id}:metadata      # Hash: thread metadata
sre:thread:{thread_id}:result        # String: final result (JSON)
sre:thread:{thread_id}:error         # String: error message
```

All thread data has a TTL of 24 hours.

## Integration with Docket

The system uses Docket for background task processing:

1. **Triage endpoint** queues a `process_agent_turn` task
2. **Docket worker** picks up the task and runs the LangGraph agent
3. **Agent execution** updates Redis thread state throughout processing
4. **Client polling** reads the updated state from Redis

## Error Handling

### Common Error Scenarios

- **Thread not found** (404): Thread ID doesn't exist or has expired
- **Task in progress** (409): Attempting to continue while another turn is running
- **Agent timeout**: Task fails if agent processing exceeds timeout
- **Redis connection issues**: Task fails with appropriate error message

### Error Response Format

```json
{
  "thread_id": "01K347ABC123XYZ789",
  "status": "failed",
  "error_message": "Agent turn failed: Connection timeout to Redis",
  "updates": [
    // ... previous updates ...
    {
      "timestamp": "2024-01-01T10:01:30Z",
      "message": "Error: Agent turn failed: Connection timeout to Redis",
      "type": "error",
      "metadata": {}
    }
  ]
}
```

## Benefits of Thread-Based Architecture

1. **Non-blocking**: Clients get immediate response with tracking ID
2. **Progress visibility**: Real-time updates on agent processing
3. **Resumable**: Clients can disconnect and reconnect using thread ID
4. **Conversational**: Multi-turn conversations with context preservation
5. **Scalable**: Background processing with multiple Docket workers
6. **Reliable**: Redis-based state management with proper error handling

## Migration from Synchronous API

The original synchronous endpoints (`/api/v1/agent/query`) remain available for backwards compatibility, but new integrations should use the thread-based API for better performance and user experience.

### Key Differences

| Synchronous API | Thread-Based API |
|-----------------|------------------|
| Blocking request/response | Immediate response + polling |
| No progress visibility | Real-time progress updates |
| Single turn only | Multi-turn conversations |
| No resumability | Resumable with thread ID |
| Limited by HTTP timeout | Long-running processing |
