# Testing WebSocket Integration in the UI

The Redis SRE Agent UI now includes real-time WebSocket task monitoring integrated into the Triage page. This guide explains how to test and use this feature.

## Quick Test

1. **Start the services**:
   ```bash
   docker-compose up -d
   ```

2. **Start the UI development server**:
   ```bash
   cd ui && npm run dev
   ```

3. **Open the UI**: Navigate to `http://localhost:5177` (or the port shown in terminal)

4. **Go to Triage page**: Click on "Triage" in the navigation

5. **Submit a test query**: Enter something like:
   ```
   Analyze Redis memory usage and performance metrics for optimization
   ```

6. **Watch real-time updates**: You'll see the WebSocket monitor showing live progress updates

## How It Works

### UI Flow

1. **Submit Query** → **WebSocket Monitor** → **Chat History**
2. When you submit a triage request, the UI automatically switches to the WebSocket monitor
3. You see real-time updates as the agent processes your request
4. When the task completes, you can switch back to chat view to see the full conversation

### WebSocket Monitor Features

- **Real-time Status**: Shows current task status (queued, in_progress, completed, etc.)
- **Live Updates**: Displays agent progress messages as they happen
- **Connection Status**: Shows WebSocket connection health
- **Auto-scroll**: Automatically scrolls to show latest updates
- **Back to Chat**: Button to switch to traditional chat view

### Traditional Chat View

- **Message History**: Shows the complete conversation
- **Markdown Support**: Properly formatted agent responses
- **Tool Calls**: Displays when the agent uses tools
- **Timestamps**: Shows when each message was sent

## Testing Scenarios

### 1. Basic WebSocket Flow
```bash
# Create a task via UI
# Watch real-time updates
# Verify task completion
# Switch to chat view
```

### 2. Multiple Clients
```bash
# Open UI in multiple browser tabs
# Submit same task ID in WebSocket client:
python examples/websocket_client.py 01K5EP7KHSNVPFDQ03DYK7S3H4
# Verify both receive same updates
```

### 3. Connection Recovery
```bash
# Start monitoring a task
# Restart sre-agent service
# Verify UI reconnects automatically
```

### 4. Task History
```bash
# Complete a task via WebSocket monitor
# Switch to chat view
# Verify full conversation history is shown
# Select different completed tasks from sidebar
```

## API Endpoints for Testing

### Create Test Task
```bash
curl -X POST "http://localhost:8000/api/v1/triage" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Test WebSocket - analyze Redis performance",
    "user_id": "test_user",
    "priority": 0,
    "tags": ["test", "websocket"]
  }'
```

### Check WebSocket Stream Info
```bash
curl "http://localhost:8000/api/v1/tasks/{thread_id}/stream-info"
```

### Monitor with CLI Client
```bash
python examples/websocket_client.py {thread_id}
```

## UI Components

### TaskMonitor Component
- **Location**: `ui/src/components/TaskMonitor.tsx`
- **Props**: `threadId`, `onClose`
- **Features**: Real-time updates, connection management, auto-scroll

### Triage Page Integration
- **Location**: `ui/src/pages/Triage.tsx`
- **Logic**: Switches between WebSocket monitor and chat based on task status
- **State Management**: Handles active tasks vs completed tasks

## Troubleshooting

### WebSocket Connection Issues
1. **Check backend**: Ensure `docker-compose up -d` is running
2. **Check ports**: Backend on 8000, UI on 5177
3. **Check browser console**: Look for WebSocket connection errors
4. **Check network**: Ensure no proxy blocking WebSocket connections

### UI Not Switching to Monitor
1. **Check task status**: Only active tasks (queued/in_progress) show monitor
2. **Check browser console**: Look for JavaScript errors
3. **Refresh page**: Sometimes state gets out of sync

### Missing Updates
1. **Check Redis**: Ensure Redis is running and accessible
2. **Check backend logs**: `docker-compose logs sre-agent`
3. **Check stream info**: Use the stream info endpoint
4. **Check task status**: Verify task is actually running

### Performance Issues
1. **Check Redis memory**: Monitor Redis memory usage
2. **Check network latency**: WebSocket performance depends on network
3. **Check browser resources**: Multiple tabs can impact performance

## Development Notes

### State Management
- `showWebSocketMonitor`: Controls which view to show
- `activeThreadId`: Current task being monitored
- `messages`: Traditional chat messages for completed tasks

### WebSocket Lifecycle
1. **Connection**: Established when task becomes active
2. **Initial State**: Sent immediately with task history
3. **Updates**: Real-time progress messages
4. **Completion**: Task finishes, can switch to chat view
5. **Cleanup**: Connection closed when switching views

### Error Handling
- **Connection Errors**: Automatic reconnection attempts
- **Invalid Tasks**: Error messages shown to user
- **Network Issues**: Graceful degradation to polling fallback

## Future Enhancements

### Planned Features
- **Multiple Task Monitoring**: Monitor several tasks simultaneously
- **Notification System**: Browser notifications for task completion
- **Progress Indicators**: Visual progress bars for long-running tasks
- **Task Cancellation**: Ability to cancel running tasks via UI
- **Export Functionality**: Export task results and conversations

### Technical Improvements
- **Offline Support**: Handle network disconnections gracefully
- **Performance Optimization**: Reduce memory usage for long conversations
- **Mobile Responsiveness**: Better mobile experience for monitoring
- **Accessibility**: Screen reader support and keyboard navigation

## Feedback and Issues

When testing, please note:
- **Performance**: How responsive is the real-time monitoring?
- **Usability**: Is the flow between monitor and chat intuitive?
- **Reliability**: Do WebSocket connections stay stable?
- **Visual Design**: Are updates clearly visible and well-formatted?

Report issues with:
- Browser and version
- Steps to reproduce
- Expected vs actual behavior
- Console errors (if any)
