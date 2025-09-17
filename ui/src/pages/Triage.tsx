import { useState, useEffect, useRef } from 'react';
import {
  Card,
  CardHeader,
  CardContent,
  Button,
} from '@radar/ui-kit';
import { ConfirmDialog } from '../components/Modal';
import ReactMarkdown from 'react-markdown';
import sreAgentApi, { RedisInstance } from '../services/sreAgentApi';

// Simple fallback components for missing UI kit components
const Loader = ({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) => (
  <div className={`animate-spin rounded-full border-2 border-gray-300 border-t-blue-600 ${
    size === 'sm' ? 'h-4 w-4' : size === 'lg' ? 'h-8 w-8' : 'h-6 w-6'
  }`} />
);

const ErrorMessage = ({ message }: { message: string }) => (
  <div className="bg-red-50 border border-red-200 text-red-600 px-4 py-3 rounded-md">
    {message}
  </div>
);
import sreAgentApi from '../services/sreAgentApi';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  timestamp: string;
  toolCall?: {
    name: string;
    args?: any;
  };
}

interface ChatThread {
  id: string;
  name: string;
  lastMessage: string;
  timestamp: string;
  messageCount: number;
  status: string;
  subject: string;
}

const Triage = () => {
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [agentStatus, setAgentStatus] = useState<'unknown' | 'available' | 'unavailable'>('unknown');
  const [isPolling, setIsPolling] = useState(false);

  const [showNewConversation, setShowNewConversation] = useState(false);
  const [showSidebar, setShowSidebar] = useState(true);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [threadToDelete, setThreadToDelete] = useState<string | null>(null);
  const [instances, setInstances] = useState<RedisInstance[]>([]);
  const [selectedInstanceId, setSelectedInstanceId] = useState<string>('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pollingIntervalRef = useRef<number | null>(null);

  const userId = 'sre-user-1'; // In a real app, this would come from auth

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    // Check agent status and load threads on component mount
    const initializeComponent = async () => {
      try {
        const isHealthy = await sreAgentApi.checkHealth();
        setAgentStatus(isHealthy ? 'available' : 'unavailable');

        // Load existing threads
        await loadThreads();

        // Load available instances
        await loadInstances();
      } catch {
        setAgentStatus('unavailable');
      }
    };

    initializeComponent();
  }, []);

  const loadInstances = async () => {
    try {
      const apiInstances = await sreAgentApi.listInstances();
      setInstances(apiInstances);
    } catch (err) {
      console.error('Failed to load instances:', err);
      // Don't show error to user, just log it
    }
  };

  // Auto-show new conversation if threads exist but none selected
  useEffect(() => {
    if (threads.length > 0 && !activeThreadId && !showNewConversation) {
      setShowNewConversation(true);
    }
  }, [threads.length, activeThreadId, showNewConversation]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
    };
  }, []);

  const loadThreads = async () => {
    try {
      const taskList = await sreAgentApi.listTasks(userId, undefined, 50);
      const threadList: ChatThread[] = taskList
        .filter(task => task.status !== 'cancelled') // Filter out cancelled/deleted threads
        .map(task => ({
          id: task.thread_id,
          name: task.metadata.subject || 'Untitled',
          subject: task.metadata.subject || 'Untitled',
          lastMessage: task.updates.length > 0 ? task.updates[0].message : 'No updates',
          timestamp: task.metadata.updated_at,
          messageCount: task.updates.length,
          status: task.status,
        }));

      setThreads(threadList);
    } catch (err) {
      console.error('Failed to load threads:', err);
    }
  };

  const startPolling = (threadId: string) => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
    }

    setIsPolling(true);

    const poll = async () => {
      try {
        const status = await sreAgentApi.getTaskStatus(threadId);

        // Update messages from task updates
        const newMessages: ChatMessage[] = [];

        // Add original query if available (use original_query from context, not the rewritten subject)
        if (status.context?.original_query) {
          newMessages.push({
            id: `initial-${threadId}`,
            role: 'user',
            content: status.context.original_query,
            timestamp: status.metadata.created_at,
          });
        }

        // Convert task updates to messages
        status.updates.forEach((update, index) => {
          if (update.type === 'response' || update.type === 'completion') {
            newMessages.push({
              id: `update-${index}`,
              role: 'assistant',
              content: update.message,
              timestamp: update.timestamp,
            });
          } else if (update.type === 'user_message') {
            newMessages.push({
              id: `update-${index}`,
              role: 'user',
              content: update.message,
              timestamp: update.timestamp,
            });
          } else if (update.type === 'tool_call') {
            // Show tool calls in a user-friendly way
            const toolName = update.metadata?.tool_name || 'Unknown Tool';
            const toolArgs = update.metadata?.tool_args;

            newMessages.push({
              id: `tool-${index}`,
              role: 'tool',
              content: `Making tool call: ${toolName}`,
              timestamp: update.timestamp,
              toolCall: {
                name: toolName,
                args: toolArgs,
              },
            });
          }
        });

        // Add the final agent response if task is complete and has a result
        if ((status.status === 'done' || status.status === 'completed') && status.result?.response) {
          newMessages.push({
            id: `result-${status.thread_id}`,
            role: 'assistant',
            content: status.result.response,
            timestamp: status.result.turn_completed_at || status.metadata.updated_at,
          });
        }

        setMessages(newMessages);

        // Stop polling if task is complete
        if (status.status === 'done' || status.status === 'completed' || status.status === 'failed' || status.status === 'cancelled') {
          setIsPolling(false);
          setIsLoading(false);
          if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current);
            pollingIntervalRef.current = null;
          }

          // Refresh thread list
          await loadThreads();
        }

      } catch (err) {
        console.error('Polling error:', err);
        setIsPolling(false);
        setIsLoading(false);
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
        }
      }
    };

    // Poll immediately, then every 2 seconds
    poll();
    pollingIntervalRef.current = setInterval(poll, 2000);
  };

  const createNewThread = async () => {
    // Clear current conversation and prepare for new one
    // Don't create placeholder threads - just clear the UI state
    setActiveThreadId(null);
    setMessages([]);
    setError('');
    setShowNewConversation(true);

    // On mobile only, switch to chat view
    if (window.innerWidth < 768) { // md breakpoint
      setShowSidebar(false);
    }

    // Stop any existing polling
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
    setIsPolling(false);
  };

  const selectThread = async (threadId: string) => {
    // Stop any existing polling
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }

    setActiveThreadId(threadId);
    setMessages([]);
    setError('');
    setIsPolling(false);
    setShowNewConversation(false);

    // On mobile only, switch to chat view
    if (window.innerWidth < 768) { // md breakpoint
      setShowSidebar(false);
    }

    // Load conversation history and start polling if task is active
    try {
      const status = await sreAgentApi.getTaskStatus(threadId);

      // Convert task updates to messages
      const newMessages: ChatMessage[] = [];

      // Add original query if available (use original_query from context, not the rewritten subject)
      if (status.context?.original_query) {
        newMessages.push({
          id: `initial-${threadId}`,
          role: 'user',
          content: status.context.original_query,
          timestamp: status.metadata.created_at,
        });
      }

      // Convert updates to messages
      status.updates.forEach((update, index) => {
        if (update.type === 'response' || update.type === 'completion') {
          newMessages.push({
            id: `update-${index}`,
            role: 'assistant',
            content: update.message,
            timestamp: update.timestamp,
          });
        } else if (update.type === 'user_message') {
          newMessages.push({
            id: `update-${index}`,
            role: 'user',
            content: update.message,
            timestamp: update.timestamp,
          });
        } else if (update.type === 'tool_call') {
          // Show tool calls in a user-friendly way
          const toolName = update.metadata?.tool_name || 'Unknown Tool';
          const toolArgs = update.metadata?.tool_args;

          newMessages.push({
            id: `tool-${index}`,
            role: 'tool',
            content: `Making tool call: ${toolName}`,
            timestamp: update.timestamp,
            toolCall: {
              name: toolName,
              args: toolArgs,
            },
          });
        }
      });

      // Add the final agent response if task is complete and has a result
      if ((status.status === 'done' || status.status === 'completed') && status.result?.response) {
        newMessages.push({
          id: `result-${threadId}`,
          role: 'assistant',
          content: status.result.response,
          timestamp: status.result.turn_completed_at || status.metadata.updated_at,
        });
      }

      setMessages(newMessages);

      // Start polling if task is still active
      if (status.status === 'queued' || status.status === 'in_progress') {
        startPolling(threadId);
      }

    } catch (err) {
      console.warn('Could not load thread status:', err);
      // Continue with empty messages - this is expected for new threads
    }
  };

  const sendMessage = async () => {
    if (!inputMessage.trim() || isLoading) return;

    const userMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: inputMessage.trim(),
      timestamp: new Date().toISOString(),
    };

    setMessages(prev => [...prev, userMessage]);
    const messageContent = inputMessage.trim();
    setInputMessage('');
    setIsLoading(true);
    setError('');

    try {
      let threadId = activeThreadId;

      // If no active thread, create a new one
      if (!activeThreadId) {
        const triageResponse = await sreAgentApi.startNewConversation(
          messageContent,
          userId,
          0,
          undefined,
          selectedInstanceId || undefined
        );
        threadId = triageResponse;

        // Update the active thread ID
        setActiveThreadId(threadId);
        setShowNewConversation(false);

        // Add new thread to the list
        const newThread: ChatThread = {
          id: threadId,
          name: messageContent.substring(0, 30) + (messageContent.length > 30 ? '...' : ''),
          subject: messageContent.substring(0, 50) + (messageContent.length > 50 ? '...' : ''),
          lastMessage: 'Agent is thinking...',
          timestamp: new Date().toISOString(),
          messageCount: 1,
          status: 'queued',
        };
        setThreads(prev => [newThread, ...prev]);

      } else {
        // Continue existing conversation
        await sreAgentApi.continueConversation(threadId!, messageContent, userId);
      }

      // Start polling for updates
      if (threadId) {
        startPolling(threadId);
      }

    } catch (err) {
      setError(`Failed to send message: ${err instanceof Error ? err.message : 'Unknown error'}`);
      setIsLoading(false);
    }
  };



  const showDeleteConfirmation = (threadId: string, e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent thread selection when clicking delete
    setThreadToDelete(threadId);
    setShowDeleteConfirm(true);
  };

  const confirmDeleteThread = async () => {
    if (!threadToDelete) return;

    try {
      // Call the API to actually delete the conversation from the backend
      const result = await sreAgentApi.clearConversation(threadToDelete);

      if (!result.cleared) {
        throw new Error(result.message);
      }

      // If this is the active thread, clear it first
      if (activeThreadId === threadToDelete) {
        setActiveThreadId(null);
        setMessages([]);
        setError('');
        setIsPolling(false);

        // Stop polling
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
        }
      }

      // Remove from threads list
      setThreads(prev => prev.filter(thread => thread.id !== threadToDelete));

    } catch (err) {
      console.error('Failed to delete thread:', err);
      setError(`Failed to delete conversation: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setThreadToDelete(null);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="h-[calc(100vh-120px)] flex gap-4">
      {/* Thread Sidebar - Responsive visibility */}
      <div className={`${showSidebar ? 'flex' : 'hidden'} md:flex w-full md:w-80 md:min-w-80 max-w-80 flex-col h-full`}>
        <Card className="flex-1 flex flex-col">
          <CardHeader className="flex-shrink-0">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h3 className="text-redis-lg font-semibold text-redis-dusk-01">Conversations</h3>
                {/* Mobile close sidebar button */}
                <Button
                  variant="outline"
                  size="sm"
                  className="md:hidden"
                  onClick={() => setShowSidebar(false)}
                >
                  ✕
                </Button>
              </div>
              <Button variant="primary" size="sm" onClick={createNewThread}>
                New Chat
              </Button>
            </div>
            {/* Agent Status Indicator */}
            <div className="flex items-center gap-2 mt-2">
              <div className={`h-2 w-2 rounded-full ${
                agentStatus === 'available' ? 'bg-redis-green' :
                agentStatus === 'unavailable' ? 'bg-redis-red' :
                'bg-redis-yellow-500'
              }`} />
              <span className="text-redis-xs text-redis-dusk-04">
                Agent {agentStatus === 'available' ? 'Online' : agentStatus === 'unavailable' ? 'Offline' : 'Checking...'}
              </span>
            </div>
          </CardHeader>
          <CardContent className="flex-1 overflow-y-auto p-0">
            <div className="space-y-1">
              {threads.map((thread) => (
                <div
                  key={thread.id}
                  className={`group p-3 cursor-pointer border-l-2 transition-colors ${
                    activeThreadId === thread.id
                      ? 'bg-redis-blue-03 border-redis-blue-03 text-white'
                      : 'hover:bg-redis-dusk-09 border-transparent'
                  }`}
                  onClick={() => selectThread(thread.id)}
                >
                  <div className="flex items-center justify-between">
                    <div className={`font-medium text-redis-sm truncate ${
                      activeThreadId === thread.id ? 'text-white' : 'text-redis-dusk-01'
                    }`}>
                      {thread.name}
                    </div>
                    <button
                      onClick={(e) => showDeleteConfirmation(thread.id, e)}
                      className={`opacity-0 group-hover:opacity-100 flex items-center justify-center w-5 h-5 rounded transition-all ${
                        activeThreadId === thread.id
                          ? 'text-blue-200 hover:text-white hover:bg-white hover:bg-opacity-20'
                          : 'text-redis-dusk-04 hover:text-redis-red hover:bg-redis-red hover:bg-opacity-10'
                      }`}
                      title="Delete conversation"
                    >
                      <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                      </svg>
                    </button>
                  </div>
                  <div className={`text-redis-xs truncate mt-1 ${
                    activeThreadId === thread.id ? 'text-blue-100' : 'text-redis-dusk-04'
                  }`}>
                    {thread.lastMessage}
                  </div>
                  <div className={`text-redis-xs mt-1 ${
                    activeThreadId === thread.id ? 'text-blue-200' : 'text-redis-dusk-05'
                  }`}>
                    {formatTimestamp(thread.timestamp)} • {thread.messageCount} messages
                  </div>
                </div>
              ))}
              {threads.length === 0 && (
                <div className="p-6 text-center text-redis-dusk-04">
                  <p className="text-redis-sm">No conversations yet.</p>
                  <p className="text-redis-xs mt-1">Click below to start troubleshooting with the SRE Agent.</p>
                  <Button
                    variant="primary"
                    size="sm"
                    className="mt-3 w-full"
                    onClick={createNewThread}
                  >
                    Start New Chat
                  </Button>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Chat Area */}
      <div className={`${showSidebar && !activeThreadId && !showNewConversation ? 'hidden' : 'flex'} md:flex flex-1 flex-col`}>
        <Card className="flex-1 flex flex-col">
          <CardHeader className="flex-shrink-0">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {/* Mobile sidebar toggle */}
                <Button
                  variant="outline"
                  size="sm"
                  className="md:hidden"
                  onClick={() => setShowSidebar(!showSidebar)}
                >
                  ☰
                </Button>
                <div>
                  <h1 className="text-redis-xl font-bold text-redis-dusk-01">SRE Agent Triage</h1>
                <p className="text-redis-sm text-redis-dusk-04 mt-1">
                  {activeThreadId
                    ? 'Chat with the Redis SRE Agent for troubleshooting and support'
                    : showNewConversation
                    ? 'Describe your Redis issue or ask a question to get started'
                    : 'Select a conversation or start a new one to begin'
                  }
                </p>
                {activeThreadId && (isPolling || isLoading) && (
                  <div className="flex items-center gap-2 mt-2">
                    <div className="h-2 w-2 rounded-full bg-redis-blue-03 animate-pulse" />
                    <span className="text-redis-xs text-redis-dusk-04">
                      Agent is thinking...
                    </span>
                  </div>
                )}
                </div>
              </div>

            </div>
          </CardHeader>

          {activeThreadId || showNewConversation ? (
            <>
              {/* Messages Area */}
              <CardContent className="flex-1 overflow-y-auto p-4">
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
                            : message.role === 'tool'
                            ? 'bg-orange-100 text-orange-800 border border-orange-200'
                            : 'bg-redis-dusk-09 text-redis-dusk-01'
                        }`}
                      >
                        {message.role === 'tool' ? (
                          <div>
                            <div className="flex items-center gap-2 mb-2">
                              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                                <path fillRule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clipRule="evenodd" />
                              </svg>
                              <span className="font-medium text-sm">Agent is making a tool call</span>
                            </div>
                            <div className="text-sm">
                              <strong>{message.toolCall?.name}</strong>
                              {message.toolCall?.args && Object.keys(message.toolCall.args).length > 0 && (
                                <div className="mt-1 text-xs opacity-75 bg-white bg-opacity-50 p-2 rounded">
                                  <pre className="whitespace-pre-wrap">{JSON.stringify(message.toolCall.args, null, 2)}</pre>
                                </div>
                              )}
                            </div>
                          </div>
                        ) : message.role === 'assistant' ? (
                          <div className="prose prose-sm max-w-none text-redis-sm">
                            <ReactMarkdown>{message.content}</ReactMarkdown>
                          </div>
                        ) : (
                          <div className="text-redis-sm whitespace-pre-wrap">{message.content}</div>
                        )}
                        <div
                          className={`text-redis-xs mt-1 ${
                            message.role === 'user' ? 'text-blue-100' : 'text-redis-dusk-04'
                          }`}
                        >
                          {formatTimestamp(message.timestamp)}
                        </div>
                      </div>
                    </div>
                  ))}
                  {(isLoading || isPolling) && (
                    <div className="flex justify-start">
                      <div className="bg-redis-dusk-09 p-3 rounded-redis-md">
                        <Loader size="sm" />
                        <span className="text-redis-sm text-redis-dusk-04 ml-2">
                          Agent is thinking...
                        </span>
                      </div>
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                </div>
              </CardContent>

              {/* Error Message */}
              {error && (
                <div className="px-4">
                  <ErrorMessage message={error} />
                </div>
              )}

              {/* Input Area */}
              <div className="p-4 border-t border-redis-dusk-08">
                {/* Instance Selection */}
                {instances.length > 0 && (
                  <div className="mb-3">
                    <label className="block text-redis-sm font-medium text-redis-dusk-01 mb-2">
                      Redis Instance (optional)
                    </label>
                    <select
                      value={selectedInstanceId}
                      onChange={(e) => setSelectedInstanceId(e.target.value)}
                      className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm text-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                      disabled={isLoading || agentStatus !== 'available'}
                    >
                      <option value="">No specific instance (general troubleshooting)</option>
                      {instances.map((instance) => (
                        <option key={instance.id} value={instance.id}>
                          {instance.name} ({instance.host}:{instance.port}) - {instance.environment}
                        </option>
                      ))}
                    </select>
                    <p className="text-redis-xs text-redis-dusk-04 mt-1">
                      Select a Redis instance to provide context for troubleshooting. The agent will have access to this instance's configuration and can perform targeted diagnostics.
                    </p>
                  </div>
                )}

                <div className="flex gap-2">
                  <textarea
                    value={inputMessage}
                    onChange={(e) => setInputMessage(e.target.value)}
                    onKeyPress={handleKeyPress}
                    placeholder="Describe your Redis issue or ask a question..."
                    className="flex-1 p-3 border border-redis-dusk-06 rounded-redis-sm resize-none focus:outline-none focus:ring-2 focus:ring-redis-blue-03 focus:border-transparent min-h-[80px] lg:min-h-[60px]"
                    rows={window.innerWidth < 1024 ? 2 : 3}
                    disabled={isLoading || agentStatus !== 'available'}
                  />
                  <Button
                    variant="primary"
                    onClick={sendMessage}
                    disabled={!inputMessage.trim() || isLoading || agentStatus !== 'available'}
                    className="self-end"
                  >
                    {isLoading ? <Loader size="sm" /> : 'Send'}
                  </Button>
                </div>
                <div className="text-redis-xs text-redis-dusk-04 mt-2">
                  {agentStatus === 'available'
                    ? (isPolling
                        ? 'Agent is thinking... Updates will appear automatically.'
                        : 'Press Enter to send, Shift+Enter for new line')
                    : agentStatus === 'unavailable'
                    ? 'SRE Agent is currently offline. Please check the backend service.'
                    : 'Checking agent status...'
                  }
                </div>
              </div>
            </>
          ) : (
            <CardContent className="flex-1 flex items-center justify-center !p-4">
              <div className="text-center max-w-md">
                <div className="h-16 w-16 bg-redis-blue-03 rounded-full flex items-center justify-center mx-auto mb-4">
                  <svg className="h-8 w-8 text-white" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M20 2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h14l4 4V4c0-1.1-.9-2-2-2zm-2 12H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z"/>
                  </svg>
                </div>
                <h3 className="text-redis-lg font-semibold text-redis-dusk-01 mb-2">
                  Welcome to SRE Agent Triage
                </h3>
                <p className="text-redis-sm text-redis-dusk-04 mb-4">
                  Get started with Redis troubleshooting, performance analysis, and infrastructure management.
                </p>
                <Button variant="primary" onClick={createNewThread}>
                  Start Your First Chat
                </Button>
              </div>
            </CardContent>
          )}
        </Card>
      </div>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showDeleteConfirm}
        onClose={() => {
          setShowDeleteConfirm(false);
          setThreadToDelete(null);
        }}
        onConfirm={confirmDeleteThread}
        title="Delete Conversation"
        message="Are you sure you want to delete this conversation? This action cannot be undone and all messages will be permanently lost."
        confirmText="Delete"
        cancelText="Cancel"
        variant="destructive"
      />
    </div>
  );
};

export default Triage;
