import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { 
  Play, 
  Pause, 
  Square, 
  CheckCircle, 
  XCircle, 
  Clock, 
  Activity,
  Wifi,
  WifiOff
} from 'lucide-react';

interface TaskUpdate {
  timestamp: string;
  update_type: string;
  message?: string;
  status?: string;
  result?: any;
  metadata?: Record<string, any>;
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
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const connectWebSocket = () => {
    try {
      const wsUrl = `ws://localhost:8000/api/v1/ws/tasks/${threadId}`;
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
              setUpdates(data.updates.reverse()); // Reverse to show chronological order
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
        return <Activity className="h-4 w-4 text-blue-500 animate-pulse" />;
      case 'completed':
      case 'success':
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case 'failed':
      case 'error':
        return <XCircle className="h-4 w-4 text-red-500" />;
      case 'pending':
      case 'queued':
        return <Clock className="h-4 w-4 text-yellow-500" />;
      default:
        return <Square className="h-4 w-4 text-gray-500" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'running':
      case 'in_progress':
        return 'bg-blue-100 text-blue-800';
      case 'completed':
      case 'success':
        return 'bg-green-100 text-green-800';
      case 'failed':
      case 'error':
        return 'bg-red-100 text-red-800';
      case 'pending':
      case 'queued':
        return 'bg-yellow-100 text-yellow-800';
      default:
        return 'bg-gray-100 text-gray-800';
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
    <Card className="w-full max-w-4xl mx-auto">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg font-semibold">
            Task Monitor: {threadId.slice(0, 8)}...
          </CardTitle>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1">
              {isConnected ? (
                <Wifi className="h-4 w-4 text-green-500" />
              ) : (
                <WifiOff className="h-4 w-4 text-red-500" />
              )}
              <span className="text-sm text-muted-foreground">
                {isConnected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
            {onClose && (
              <Button variant="outline" size="sm" onClick={onClose}>
                Close
              </Button>
            )}
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            {getStatusIcon(currentStatus)}
            <Badge className={getStatusColor(currentStatus)}>
              {currentStatus}
            </Badge>
          </div>
          
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsAutoScroll(!isAutoScroll)}
            >
              {isAutoScroll ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
              Auto-scroll
            </Button>
          </div>
        </div>
        
        {connectionError && (
          <div className="text-sm text-red-600 bg-red-50 p-2 rounded">
            {connectionError}
          </div>
        )}
      </CardHeader>
      
      <CardContent>
        <ScrollArea className="h-96 w-full" ref={scrollAreaRef}>
          <div className="space-y-2">
            {updates.length === 0 ? (
              <div className="text-center text-muted-foreground py-8">
                No updates yet...
              </div>
            ) : (
              updates.map((update, index) => (
                <div key={index} className="border rounded-lg p-3 bg-card">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <Badge variant="outline" className="text-xs">
                          {update.update_type}
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                          {formatTimestamp(update.timestamp)}
                        </span>
                      </div>
                      
                      {update.message && (
                        <p className="text-sm mb-2">{update.message}</p>
                      )}
                      
                      {update.metadata && Object.keys(update.metadata).length > 0 && (
                        <div className="text-xs text-muted-foreground">
                          <details>
                            <summary className="cursor-pointer">Metadata</summary>
                            <pre className="mt-1 p-2 bg-muted rounded text-xs overflow-x-auto">
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
        </ScrollArea>
        
        {taskResult && (
          <>
            <Separator className="my-4" />
            <div className="space-y-2">
              <h4 className="font-semibold text-sm">Task Result:</h4>
              <pre className="text-xs bg-muted p-3 rounded overflow-x-auto">
                {JSON.stringify(taskResult, null, 2)}
              </pre>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
};

export default TaskMonitor;
