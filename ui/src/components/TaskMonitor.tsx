import React, { useState, useEffect, useRef } from 'react';
import {
  Button,
} from '@radar/ui-kit';

interface TaskUpdate {
  timestamp: string;
  update_type: string;
  message?: string;
  status?: string;
  result?: any;
  metadata?: Record<string, any>;
  type?: string;
  updates?: TaskUpdate[];
}

interface TaskMonitorProps {
  threadId: string;
  onClose?: () => void;
}

const TaskMonitor: React.FC<TaskMonitorProps> = ({ threadId, onClose }) => {
  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [updates, setUpdates] = useState<TaskUpdate[]>([]);
  const [currentStatus, setCurrentStatus] = useState<string>('unknown');
  const [taskResult, setTaskResult] = useState<any>(null);
  const [isAutoScroll, setIsAutoScroll] = useState(true);

  const wsRef = useRef<WebSocket | null>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  const connectWebSocket = () => {
    try {
      // Construct WebSocket URL dynamically based on current location
      const getWebSocketUrl = () => {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const hostname = window.location.hostname;

        // Check if we're in development mode (Vite dev server)
        // Vite typically uses ports 3000, 3001, etc. and serves from localhost
        const isDevelopment = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') &&
                             (window.location.port.startsWith('30') || window.location.port === '5173'); // 5173 is Vite's default

        if (!isDevelopment) {
          // In production, use current host (nginx will proxy WebSocket connections)
          const port = window.location.port ? `:${window.location.port}` : '';
          return `${protocol}//${hostname}${port}/api/v1/ws/tasks/${threadId}`;
        }

        // In development, use current hostname but with backend port (8000)
        return `${protocol}//${hostname}:8000/api/v1/ws/tasks/${threadId}`;
      };

      const wsUrl = getWebSocketUrl();
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('WebSocket connected');
        setIsConnected(true);
        setConnectionError(null);

        // Send periodic pings to keep connection alive
        const pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          } else {
            clearInterval(pingInterval);
          }
        }, 30000);
      };

      ws.onmessage = (event) => {
        try {
          const data: TaskUpdate = JSON.parse(event.data);

          if (data.type === 'pong') {
            return; // Ignore pong responses
          }

          // Handle different update types
          if (data.update_type === 'initial_state') {
            setCurrentStatus(data.status || 'unknown');
            if (data.updates) {
              setUpdates([...data.updates].reverse()); // Reverse to show chronological order
            }
            if (data.result) {
              setTaskResult(data.result);
            }
          } else {
            // Add new update
            setUpdates(prev => [...prev, data]);

            if (data.status) {
              setCurrentStatus(data.status);
            }

            if (data.result) {
              setTaskResult(data.result);
            }
          }

          // Auto-scroll to bottom if enabled
          if (isAutoScroll && scrollAreaRef.current) {
            setTimeout(() => {
              const scrollElement = scrollAreaRef.current?.querySelector('[data-radix-scroll-area-viewport]');
              if (scrollElement) {
                scrollElement.scrollTop = scrollElement.scrollHeight;
              }
            }, 100);
          }
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };

      ws.onclose = (event) => {
        console.log('WebSocket closed:', event.code, event.reason);
        setIsConnected(false);

        // Attempt to reconnect after a delay (unless manually closed)
        if (event.code !== 1000) {
          setConnectionError('Connection lost. Attempting to reconnect...');
          reconnectTimeoutRef.current = setTimeout(() => {
            connectWebSocket();
          }, 3000);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setConnectionError('WebSocket connection error');
      };

      wsRef.current = ws;
    } catch (error) {
      console.error('Failed to create WebSocket connection:', error);
      setConnectionError('Failed to create WebSocket connection');
    }
  };

  const disconnect = () => {
    if (wsRef.current) {
      wsRef.current.close(1000, 'Manual disconnect');
      wsRef.current = null;
    }

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    setIsConnected(false);
    setConnectionError(null);
  };

  useEffect(() => {
    connectWebSocket();

    return () => {
      disconnect();
    };
  }, [threadId]);

  const getStatusIcon = (status: string) => {
    switch (status.toLowerCase()) {
      case 'running':
      case 'in_progress':
        return <span className="inline-block w-3 h-3 bg-blue-500 rounded-full animate-pulse"></span>;
      case 'completed':
      case 'success':
        return <span className="inline-block w-3 h-3 bg-green-500 rounded-full"></span>;
      case 'failed':
      case 'error':
        return <span className="inline-block w-3 h-3 bg-red-500 rounded-full"></span>;
      case 'pending':
      case 'queued':
        return <span className="inline-block w-3 h-3 bg-yellow-500 rounded-full"></span>;
      default:
        return <span className="inline-block w-3 h-3 bg-gray-500 rounded-full"></span>;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'running':
      case 'in_progress':
        return 'bg-blue-100 text-blue-800 px-2 py-1 rounded text-xs';
      case 'completed':
      case 'success':
        return 'bg-green-100 text-green-800 px-2 py-1 rounded text-xs';
      case 'failed':
      case 'error':
        return 'bg-red-100 text-red-800 px-2 py-1 rounded text-xs';
      case 'pending':
      case 'queued':
        return 'bg-yellow-100 text-yellow-800 px-2 py-1 rounded text-xs';
      default:
        return 'bg-gray-100 text-gray-800 px-2 py-1 rounded text-xs';
    }
  };

  const formatTimestamp = (timestamp: string) => {
    try {
      return new Date(timestamp).toLocaleTimeString();
    } catch {
      return timestamp;
    }
  };

  return (
    <div className="w-full h-full flex flex-col">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-gray-200 p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-semibold text-gray-900">
            Real-time Task Monitor
          </h3>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
              <span className="text-sm text-gray-600">
                {isConnected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
            {onClose && (
              <Button variant="outline" size="sm" onClick={onClose}>
                Back to Chat
              </Button>
            )}
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="inline-block w-3 h-3 bg-blue-500 rounded-full animate-pulse"></span>
            <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded text-xs">
              Processing
            </span>
          </div>
        </div>

        {connectionError && (
          <div className="text-sm text-red-600 bg-red-50 p-2 rounded mt-2">
            {connectionError}
          </div>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        <div className="h-full overflow-y-auto p-4" ref={scrollAreaRef}>
          <div className="space-y-3">
            {updates.length === 0 ? (
              <div className="text-center text-gray-500 py-8">
                <div className="animate-spin w-6 h-6 border-2 border-gray-300 border-t-blue-600 rounded-full mx-auto mb-2"></div>
                Waiting for updates...
              </div>
            ) : (
              updates
                .filter(update => {
                  // Filter out technical update types that users shouldn't see
                  const technicalTypes = [
                    'task_queued', 'task_started', 'task_completed', 'task_failed',
                    'agent_init', 'agent_complete', 'turn_start', 'turn_complete',
                    'status_update', 'internal', 'debug'
                  ];
                  return !technicalTypes.includes(update.update_type);
                })
                .map((update, index) => (
                <div key={index} className="border rounded-lg p-3 bg-white shadow-sm">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs text-gray-500">
                          {formatTimestamp(update.timestamp)}
                        </span>
                      </div>

                      {update.message && (
                        <p className="text-sm mb-2 text-gray-800">{update.message}</p>
                      )}

                      {update.metadata && Object.keys(update.metadata).length > 0 && (
                        <div className="text-xs text-gray-600">
                          <details>
                            <summary className="cursor-pointer hover:text-gray-800">Metadata</summary>
                            <pre className="mt-1 p-2 bg-gray-50 rounded text-xs overflow-x-auto">
                              {JSON.stringify(update.metadata, null, 2)}
                            </pre>
                          </details>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {taskResult && (
          <div className="border-t border-gray-200 p-4">
            <div className="space-y-2">
              <h4 className="font-semibold text-sm text-gray-900">Task Result:</h4>
              <pre className="text-xs bg-gray-50 p-3 rounded overflow-x-auto text-gray-800">
                {JSON.stringify(taskResult, null, 2)}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default TaskMonitor;
