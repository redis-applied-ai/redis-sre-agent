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
  role: 'user' | 'assistant' | 'thinking' | 'status';
  content: string;
  timestamp: string;
}

interface TaskMonitorProps {
  threadId: string;
  initialQuery?: string;
  onStatusChange?: (status: string) => void;
  onCompleted?: (info: { status: string; response?: string }) => void;
}

const TaskMonitor: React.FC<TaskMonitorProps> = ({ threadId, initialQuery, onStatusChange, onCompleted }) => {
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

  // Debounced REST refetch utility
  const refetchTimeoutRef = useRef<number | null>(null);

  const mapThreadToMessages = (threadData: any): ChatMessage[] => {
    const msgs = Array.isArray(threadData?.context?.messages) ? threadData.context.messages : [];
    if (msgs.length > 0) {
      return msgs.map((msg: any, index: number) => ({
        id: `${msg.role}-${index}-${msg.timestamp}`,
        role: msg.role,
        content: msg.content,
        timestamp: msg.timestamp,
      }));
    }
    // Fallback: build from updates if context.messages is missing
    const out: ChatMessage[] = [];
    if (threadData?.context?.original_query) {
      out.push({ id: `initial-${threadId}`, role: 'user', content: threadData.context.original_query, timestamp: threadData.metadata?.created_at || new Date().toISOString() });
    } else if (threadData?.metadata?.subject) {
      out.push({ id: `initial-${threadId}`, role: 'user', content: threadData.metadata.subject, timestamp: threadData.metadata?.created_at || new Date().toISOString() });
    }
    const updates = Array.isArray(threadData?.updates) ? [...threadData.updates].reverse() : [];
    updates.forEach((u: any, idx: number) => {
      if ((u.type === 'response' || u.type === 'completion') && u.message) {
        out.push({ id: `u-${idx}`, role: 'assistant', content: u.message, timestamp: u.timestamp });
      } else if (u.type === 'user_message' && u.message) {
        out.push({ id: `u-${idx}`, role: 'user', content: u.message, timestamp: u.timestamp });
      } else if ((u.type === 'agent_reflection' || u.type === 'agent_processing' || u.type === 'agent_start') && u.message && u.message.length > 10 && !/completed/i.test(u.message)) {
        out.push({ id: `r-${idx}` , role: 'assistant', content: u.message, timestamp: u.timestamp });
      }
    });
    if ((threadData?.status === 'done' || threadData?.status === 'completed') && threadData?.result?.response) {
      out.push({ id: `result-${threadId}`, role: 'assistant', content: threadData.result.response, timestamp: threadData.result.turn_completed_at || threadData.metadata?.updated_at || new Date().toISOString() });
    }
    return out;
  };

  const fetchThreadAndUpdate = async () => {
    try {
      const response = await fetch(`/api/v1/threads/${threadId}`);
      if (!response.ok) {
        console.error('Failed to load thread:', response.status, response.statusText);
        setIsThinking(false);
        return;
      }
      const threadData = await response.json();
      const chatMessages = mapThreadToMessages(threadData);
      setMessages(chatMessages);

      // Derive a status from thread data
      const derivedStatus = threadData?.error_message
        ? 'failed'
        : threadData?.result
        ? 'completed'
        : 'in_progress';

      setCurrentStatus(derivedStatus);
      onStatusChange?.(derivedStatus);
      const inProgress = ['queued', 'in_progress', 'running'].includes(derivedStatus);
      setIsThinking(inProgress);

      // If complete, notify parent and disconnect
      if (['done', 'completed', 'failed', 'cancelled'].includes(derivedStatus)) {
        onCompleted?.({ status: derivedStatus, response: threadData?.result?.response });
        disconnect();
      }
    } catch (error) {
      console.error('Error loading thread messages:', error);
      setIsThinking(false);
    }
  };

  const scheduleRefetch = () => {
    if (refetchTimeoutRef.current) return; // already scheduled
    refetchTimeoutRef.current = window.setTimeout(() => {
      refetchTimeoutRef.current = null;
      fetchThreadAndUpdate();
    }, 300);
  };

  // Load thread transcript on thread change
  useEffect(() => {
    console.log('Thread changed to:', threadId);
    lastMessageIdRef.current = null;
    lastRenderTimeRef.current = 0;
    fetchThreadAndUpdate();
  }, [threadId]);

  // Only scroll when messages change, not on every state update
  useEffect(() => {
    scrollToBottom();
  }, [messages.length]); // Only trigger when message count changes

  useEffect(() => {
    // Append initial user message if provided and not already present
    if (initialQuery) {
      setMessages(prev => {
        const exists = prev.some(m => m.role === 'user' && m.content === initialQuery);
        if (exists) return prev;
        return [
          ...prev,
          {
            id: `initial-${Date.now()}`,
            role: 'user',
            content: initialQuery,
            timestamp: new Date().toISOString(),
          },
        ];
      });
    }
  }, [initialQuery]);

  // Track the active connection instance to ignore Strict Mode double-invoke events
  const currentConnIdRef = useRef(0);
  const nextConnIdRef = useRef(1);

  const connectWebSocket = () => {
    // Close existing connection if any
    if (wsRef.current) {
      console.log('Closing existing WebSocket connection');
      isIntentionalCloseRef.current = true; // intentional to avoid error message
      wsRef.current.close();
      wsRef.current = null;
    }

    try {
      // Construct WebSocket URL dynamically based on current location
      const getWebSocketUrl = () => {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const hostname = window.location.hostname;
        const isDevelopment = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') &&
                              (window.location.port.startsWith('30') || window.location.port === '5173');
        if (!isDevelopment) {
          const port = window.location.port ? `:${window.location.port}` : '';
          return `${protocol}//${hostname}${port}/api/v1/ws/tasks/${threadId}`;
        }
        return `${protocol}//${hostname}:8000/api/v1/ws/tasks/${threadId}`;
      };

      const wsUrl = getWebSocketUrl();
      const myConnId = nextConnIdRef.current++;
      currentConnIdRef.current = myConnId;
      console.log('Connecting to WebSocket:', wsUrl);
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        if (myConnId !== currentConnIdRef.current) return; // stale socket
        console.log('WebSocket connected');
        setIsConnected(true);
        setConnectionError(null);
        isIntentionalCloseRef.current = false; // Reset flag on successful connection
        setIsThinking(true);
        // periodic pings
        const pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          } else {
            clearInterval(pingInterval);
          }
        }, 30000);
      };

      ws.onmessage = (event) => {
        if (myConnId !== currentConnIdRef.current) return; // stale socket
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'pong') return;
          // Treat any WS message as an invalidation to refetch via REST (debounced)
          scheduleRefetch();
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };

      ws.onclose = (event) => {
        if (myConnId !== currentConnIdRef.current) return; // stale socket
        console.log('WebSocket closed:', event.code, event.reason);
        setIsConnected(false);
        // Do not reconnect if intentional, normal close, or thread not found (4004)
        if (!isIntentionalCloseRef.current && event.code !== 1000 && event.code !== 4004) {
          setConnectionError('Connection lost. Attempting to reconnect...');
          reconnectTimeoutRef.current = setTimeout(() => {
            connectWebSocket();
          }, 3000);
        } else {
          setConnectionError(null);
        }
      };

      ws.onerror = (error) => {
        if (myConnId !== currentConnIdRef.current) return; // stale socket
        console.error('WebSocket error:', error);
        // Let onclose decide about reconnects; just surface a message
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
      // Dedup by content to handle minor timestamp differences
      const exists = prev.some(msg =>
        msg.role === 'assistant' &&
        msg.content === content
      );

      if (exists) {
        console.log('Duplicate assistant content detected, skipping:', content.substring(0, 50));
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
  const addAssistantMessagesBatch = (items: Array<{content: string; timestamp: string}>) => {
    if (!items || items.length === 0) return;
    setMessages(prev => {
      const existingContents = new Set(prev.filter(m => m.role === 'assistant').map(m => m.content));
      const next = [...prev];
      items.forEach(({content, timestamp}) => {
        if (!existingContents.has(content)) {
          const id = `assistant-${timestamp}-${content.substring(0,50)}`;
          next.push({ id, role: 'assistant', content, timestamp });
          existingContents.add(content);
        }
      });
      return next;
    });
  };


  const addStatusMessage = (content: string, timestamp: string) => {
    // Create a unique ID for this status message
    const messageId = `status-${timestamp}-${content.substring(0, 30)}`;

    setMessages(prev => {
      // Check if this status message already exists
      const exists = prev.some(msg => msg.id === messageId);

      if (exists) {
        return prev;
      }

      console.log('Adding status message:', content);
      return [...prev, {
        id: messageId,
        role: 'status',
        content,
        timestamp,
      }];
    });
  };

  const processUpdate = (update: TaskUpdate) => {
    // Throttle updates to prevent constant re-renders
    const now = Date.now();
    const timeSinceLastRender = now - lastRenderTimeRef.current;

    // Only process updates if enough time has passed (throttle)
    // OR if it's a final result or important status message
    const isFinalResult = update.result?.response ||
                          update.status === 'completed' ||
                          update.status === 'done' ||
                          update.status === 'failed';

    const isImportantUpdate = update.message && update.message.length > 0;


    if (!isFinalResult && !isImportantUpdate && timeSinceLastRender < 250) {
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

    // Show assistant updates in a stable way (batch-friendly)
    const updateType = update.type || update.update_type;
    if (update.message && update.message.length > 0) {
      if (updateType === 'agent_reflection' || updateType === 'response') {
        addAssistantMessagesBatch([{ content: update.message, timestamp: update.timestamp }]);
      }
    }

    // Handle final result (only from new updates, not initial_state)
    if (update.result?.response) {
      addAssistantMessage(update.result.response, update.timestamp);
      setIsThinking(false);
      onStatusChange?.('completed');
      onCompleted?.({ status: 'completed', response: update.result.response });
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
    // Connect WS for this thread; React Strict Mode may double-invoke effects in dev
    connectWebSocket();

    return () => {
      // Mark as intentional to prevent reconnection from stale socket events
      isIntentionalCloseRef.current = true;
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
              className={`flex ${message.role === 'user' ? 'justify-end' : message.role === 'status' ? 'justify-center' : 'justify-start'}`}
            >
              <div
                className={`${message.role === 'status' ? 'max-w-full' : 'max-w-[80%]'} p-3 rounded-redis-md ${
                  message.role === 'user'
                    ? 'bg-redis-blue-03 text-white'
                    : message.role === 'status'
                    ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800 text-center text-sm italic'
                    : 'bg-redis-dusk-09 text-foreground'
                }`}
              >
                {message.role === 'assistant' ? (
                  <div className="markdown-content text-redis-sm leading-[1.35]">
                    <ReactMarkdown
                      components={{
                        // Use CSS to control spacing; avoid Tailwind margin/space-y utilities here
                        h1: ({children}) => <h1>{children}</h1>,
                        h2: ({children}) => <h2>{children}</h2>,
                        h3: ({children}) => <h3>{children}</h3>,
                        p: ({children}) => <p>{children}</p>,
                        ul: ({children}) => <ul>{children}</ul>,
                        ol: ({children}) => <ol>{children}</ol>,
                        li: ({children}) => <li>{children}</li>,
                        code: ({children, ...props}) => {
                          const isInline = !props.className?.includes('language-');
                          return isInline ?
                            <code className="bg-redis-dusk-08 text-foreground px-1 py-0.5 rounded text-xs font-mono">{children}</code> :
                            <code className="block bg-redis-dusk-08 text-foreground p-2 rounded text-[12px] font-mono whitespace-pre-wrap">{children}</code>;
                        },
                        pre: ({children}) => <pre className="bg-redis-dusk-08 text-foreground p-2 rounded text-[12px] font-mono whitespace-pre-wrap overflow-x-auto">{children}</pre>,
                        strong: ({children}) => <strong className="font-semibold text-foreground">{children}</strong>,
                        blockquote: ({children}) => <blockquote className="border-l-4 border-gray-300 pl-3 italic text-redis-sm">{children}</blockquote>,
                      }}
                    >
                      {message.content}
                    </ReactMarkdown>
                  </div>
                ) : message.role === 'status' ? (
                  <div className="text-redis-sm">{message.content}</div>
                ) : (
                  <div className="text-redis-sm whitespace-pre-wrap">{message.content}</div>
                )}
                {message.timestamp && message.role !== 'status' && (
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
