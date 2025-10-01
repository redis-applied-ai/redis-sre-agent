import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';

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

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'thinking';
  content: string;
  timestamp: string;
}

interface TaskMonitorProps {
  threadId: string;
  initialQuery?: string;
}

const TaskMonitor: React.FC<TaskMonitorProps> = ({ threadId, initialQuery }) => {
  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [currentStatus, setCurrentStatus] = useState<string>('unknown');

  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const lastMessageIdRef = useRef<string | null>(null);
  const lastRenderTimeRef = useRef<number>(0);
  const isIntentionalCloseRef = useRef<boolean>(false);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // Load thread messages when threadId changes
  useEffect(() => {
    console.log('Thread changed to:', threadId);

    // Reset tracking refs
    lastMessageIdRef.current = null;
    lastRenderTimeRef.current = 0;

    // Fetch thread messages from API
    const loadThreadMessages = async () => {
      try {
        const response = await fetch(`/api/v1/tasks/${threadId}`);
        if (response.ok) {
          const threadData = await response.json();
          console.log('Thread data:', threadData);
          console.log('Context:', threadData.context);
          console.log('Messages:', threadData.context?.messages);
          console.log('Thread status:', threadData.status);

          const threadMessages = threadData.context?.messages || [];

          // Convert to ChatMessage format
          const chatMessages: ChatMessage[] = threadMessages.map((msg: any, index: number) => ({
            id: `${msg.role}-${index}-${msg.timestamp}`,
            role: msg.role,
            content: msg.content,
            timestamp: msg.timestamp,
          }));

          setMessages(chatMessages);
          console.log(`Loaded ${chatMessages.length} messages for thread ${threadId}:`, chatMessages);

          // Set status and thinking indicator based on thread status
          setCurrentStatus(threadData.status);

          // Only show thinking if thread is actually in progress
          const inProgressStatuses = ['queued', 'in_progress', 'running'];
          setIsThinking(inProgressStatuses.includes(threadData.status));
        } else {
          console.error('Failed to load thread:', response.status, response.statusText);
          // If thread doesn't exist yet or error, start fresh
          setMessages([]);
          setIsThinking(false);
        }
      } catch (error) {
        console.error('Error loading thread messages:', error);
        setMessages([]);
        setIsThinking(false);
      }
    };

    loadThreadMessages();
  }, [threadId]);

  // Only scroll when messages change, not on every state update
  useEffect(() => {
    scrollToBottom();
  }, [messages.length]); // Only trigger when message count changes

  useEffect(() => {
    // Add initial user message if provided
    if (initialQuery) {
      setMessages([{
        id: 'initial',
        role: 'user',
        content: initialQuery,
        timestamp: new Date().toISOString(),
      }]);
    }
  }, [initialQuery]);

  const connectWebSocket = () => {
    // Close existing connection if any
    if (wsRef.current) {
      console.log('Closing existing WebSocket connection');
      isIntentionalCloseRef.current = true; // Mark as intentional to avoid error message
      wsRef.current.close();
      wsRef.current = null;
    }

    try {
      // Construct WebSocket URL dynamically based on current location
      const getWebSocketUrl = () => {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const hostname = window.location.hostname;

        // Check if we're in development mode (Vite dev server)
        const isDevelopment = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') &&
                             (window.location.port.startsWith('30') || window.location.port === '5173');

        if (!isDevelopment) {
          const port = window.location.port ? `:${window.location.port}` : '';
          return `${protocol}//${hostname}${port}/api/v1/ws/tasks/${threadId}`;
        }

        return `${protocol}//${hostname}:8000/api/v1/ws/tasks/${threadId}`;
      };

      const wsUrl = getWebSocketUrl();
      console.log('Connecting to WebSocket:', wsUrl);
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('WebSocket connected');
        setIsConnected(true);
        setConnectionError(null);
        isIntentionalCloseRef.current = false; // Reset flag on successful connection
        setIsThinking(true);

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
            return;
          }

          // Handle different update types
          if (data.update_type === 'initial_state') {
            setCurrentStatus(data.status || 'unknown');

            // Process initial updates to extract user query and responses
            // Filter out the final result to avoid duplicates
            if (data.updates) {
              const updatesWithoutFinalResult = data.updates.filter(u => !u.result?.response);
              processUpdates(updatesWithoutFinalResult);
            }

            // Add the final result once
            if (data.result?.response) {
              addAssistantMessage(data.result.response, data.result.turn_completed_at || new Date().toISOString());
              setIsThinking(false);
            }
          } else {
            // Process new update
            processUpdate(data);
          }
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };

      ws.onclose = (event) => {
        console.log('WebSocket closed:', event.code, event.reason);
        setIsConnected(false);

        // Only show error and reconnect if this wasn't an intentional close
        if (!isIntentionalCloseRef.current && event.code !== 1000) {
          setConnectionError('Connection lost. Attempting to reconnect...');
          reconnectTimeoutRef.current = setTimeout(() => {
            connectWebSocket();
          }, 3000);
        } else {
          // Clear error on intentional close
          setConnectionError(null);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setConnectionError('Connection error. Please refresh the page.');
      };

      wsRef.current = ws;
    } catch (error) {
      console.error('Failed to create WebSocket connection:', error);
      setConnectionError('Failed to connect. Please refresh the page.');
    }
  };

  const addAssistantMessage = (content: string, timestamp: string) => {
    // Create a unique ID for this message
    const messageId = `assistant-${timestamp}-${content.substring(0, 50)}`;

    // Check if we've already added this exact message
    if (lastMessageIdRef.current === messageId) {
      console.log('Skipping duplicate message (same ID):', content.substring(0, 50));
      return;
    }

    setMessages(prev => {
      // Check if this message already exists to prevent duplicates
      const exists = prev.some(msg =>
        msg.role === 'assistant' &&
        msg.content === content &&
        msg.timestamp === timestamp
      );

      if (exists) {
        console.log('Duplicate message detected, skipping:', content.substring(0, 50));
        return prev;
      }

      console.log('Adding assistant message:', content.substring(0, 50));
      lastMessageIdRef.current = messageId;
      return [...prev, {
        id: messageId,
        role: 'assistant',
        content,
        timestamp,
      }];
    });
  };

  const processUpdate = (update: TaskUpdate) => {
    // Throttle updates to prevent constant re-renders
    const now = Date.now();
    const timeSinceLastRender = now - lastRenderTimeRef.current;

    // Only process updates if enough time has passed (100ms throttle)
    // OR if it's a final result
    const isFinalResult = update.result?.response ||
                          update.status === 'completed' ||
                          update.status === 'done' ||
                          update.status === 'failed';

    if (!isFinalResult && timeSinceLastRender < 100) {
      return; // Skip this update to prevent flashing
    }

    lastRenderTimeRef.current = now;

    // Update status only if it changed
    if (update.status) {
      setCurrentStatus(prev => {
        if (prev === update.status) return prev; // Avoid unnecessary re-render
        return update.status!;
      });

      // Stop thinking indicator when task completes
      if (update.status === 'completed' || update.status === 'done' || update.status === 'failed') {
        setIsThinking(false);
      }
    }

    // Don't process 'response' type updates here - they're handled by the final result
    // This prevents duplicate messages

    // Handle final result (only from new updates, not initial_state)
    if (update.result?.response) {
      addAssistantMessage(update.result.response, update.timestamp);
      setIsThinking(false);
    }
  };

  const processUpdates = (updates: TaskUpdate[]) => {
    updates.forEach(update => processUpdate(update));
  };

  const disconnect = () => {
    if (wsRef.current) {
      isIntentionalCloseRef.current = true; // Mark as intentional
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

  const formatTimestamp = (timestamp: string) => {
    try {
      return new Date(timestamp).toLocaleTimeString();
    } catch {
      return timestamp;
    }
  };

  return (
    <div className="h-full flex flex-col">
      {/* Connection Error */}
      {connectionError && (
        <div className="flex-shrink-0 p-4">
          <div className="text-sm text-red-600 bg-red-50 border border-red-200 p-3 rounded-md">
            {connectionError}
          </div>
        </div>
      )}

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-4">
        <div className="space-y-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[80%] p-3 rounded-redis-md ${
                  message.role === 'user'
                    ? 'bg-redis-blue-03 text-white'
                    : 'bg-redis-dusk-09 text-foreground'
                }`}
              >
                {message.role === 'assistant' ? (
                  <div className="prose prose-sm max-w-none text-redis-sm markdown-content">
                    <ReactMarkdown
                      components={{
                        h1: ({children}) => <h1 className="text-lg font-bold mb-3 mt-4 first:mt-0">{children}</h1>,
                        h2: ({children}) => <h2 className="text-base font-semibold mb-2 mt-3">{children}</h2>,
                        h3: ({children}) => <h3 className="text-sm font-medium mb-2 mt-3">{children}</h3>,
                        p: ({children}) => <p className="mb-3 leading-relaxed">{children}</p>,
                        ul: ({children}) => <ul className="mb-3 ml-4 space-y-1 list-disc list-outside">{children}</ul>,
                        ol: ({children}) => <ol className="mb-3 ml-4 space-y-1 list-decimal list-outside">{children}</ol>,
                        li: ({children}) => <li className="leading-relaxed ml-1">{children}</li>,
                        code: ({children, ...props}) => {
                          const isInline = !props.className?.includes('language-');
                          return isInline ?
                            <code className="bg-redis-dusk-08 text-foreground px-1 py-0.5 rounded text-xs font-mono">{children}</code> :
                            <code className="block bg-redis-dusk-08 text-foreground p-3 rounded text-xs font-mono whitespace-pre-wrap mb-3">{children}</code>;
                        },
                        pre: ({children}) => <pre className="bg-redis-dusk-08 text-foreground p-3 rounded text-xs font-mono whitespace-pre-wrap mb-3 overflow-x-auto">{children}</pre>,
                        strong: ({children}) => <strong className="font-semibold text-foreground">{children}</strong>,
                        blockquote: ({children}) => <blockquote className="border-l-4 border-gray-300 pl-4 mb-3 italic">{children}</blockquote>,
                      }}
                    >
                      {message.content}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <div className="text-redis-sm whitespace-pre-wrap">{message.content}</div>
                )}
                {message.timestamp && (
                  <div
                    className={`text-redis-xs mt-1 ${
                      message.role === 'user' ? 'text-blue-100' : 'text-redis-dusk-04'
                    }`}
                  >
                    {formatTimestamp(message.timestamp)}
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Thinking Indicator */}
          {isThinking && (
            <div className="flex justify-start">
              <div className="max-w-[80%] p-3 rounded-redis-md bg-redis-dusk-09 text-foreground">
                <div className="flex items-center gap-2">
                  <div className="flex gap-1">
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                  </div>
                  <span className="text-redis-sm text-redis-dusk-04">Thinking...</span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>
    </div>
  );
};

export default TaskMonitor;
