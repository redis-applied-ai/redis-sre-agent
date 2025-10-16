import { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Card,
  CardHeader,
  CardContent,
  Button,
} from '@radar/ui-kit';
import { ConfirmDialog } from '../components/Modal';
import ReactMarkdown from 'react-markdown';
import TaskMonitor from '../components/TaskMonitor';
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

/**
 * Extract human-readable operation name from full tool name.
 * Format: {provider}_{hash}_{operation}
 * Example: re_admin_ffffa3_get_cluster_info -> get_cluster_info
 */
const extractOperationName = (fullToolName: string): string => {
  // Match pattern: underscore + 6 hex chars + underscore + operation
  const match = fullToolName.match(/_([0-9a-f]{6})_(.+)$/);
  if (match) {
    return match[2]; // Return the operation part
  }
  // Fallback: return the full name
  return fullToolName;
};

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'tool' | 'system';
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
  isScheduled?: boolean;
  instanceId?: string;
}

const Triage = () => {
  const [searchParams] = useSearchParams();
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
  const [isThinking, setIsThinking] = useState(false);
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

  // Handle URL parameters to auto-select thread
  useEffect(() => {
    const threadParam = searchParams.get('thread');
    if (threadParam && threads.length > 0 && !activeThreadId) {
      // Check if the thread exists in our loaded threads
      const threadExists = threads.some(thread => thread.id === threadParam);
      if (threadExists) {
        selectThread(threadParam);
      }
    }
  }, [threads, searchParams, activeThreadId]);

  // Auto-show new conversation when landing on the page or when threads exist but none selected
  useEffect(() => {
    const threadParam = searchParams.get('thread');
    // Don't auto-show new conversation if we have a thread parameter
    if (!activeThreadId && !showNewConversation && !threadParam) {
      setShowNewConversation(true);
    }
  }, [threads.length, activeThreadId, showNewConversation, searchParams]);

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
      // Load all tasks (including scheduled/automated ones) by passing null for user_id
      const taskList = await sreAgentApi.listTasks(null, undefined, 50);
      const threadList: ChatThread[] = taskList
        .filter(task => task.status !== 'cancelled') // Filter out cancelled/deleted threads
        .map(task => {
          // Check if this is a scheduled/automated task
          const isScheduled = task.metadata.user_id === 'scheduler' ||
                             (task.metadata.tags && task.metadata.tags.includes('scheduled'));

          // Try to get a meaningful name from various sources
          let threadName = 'Untitled';

          // For scheduled tasks, prioritize schedule name and context
          if (isScheduled) {
            // First try schedule name from context
            if (task.context?.schedule_name) {
              threadName = task.context.schedule_name;
            }
            // Then try original query from context
            else if (task.context?.original_query) {
              threadName = task.context.original_query.substring(0, 50) + (task.context.original_query.length > 50 ? '...' : '');
            }
            // Then try subject from metadata
            else if (task.metadata.subject && task.metadata.subject.trim() && task.metadata.subject !== 'Untitled') {
              threadName = task.metadata.subject;
            }
          } else {
            // For manual tasks, prioritize subject first
            if (task.metadata.subject && task.metadata.subject.trim() && task.metadata.subject !== 'Untitled') {
              threadName = task.metadata.subject;
            }
            // If no subject, try to get from original query in context
            else if (task.context?.original_query) {
              threadName = task.context.original_query.substring(0, 50) + (task.context.original_query.length > 50 ? '...' : '');
            }
            // If no original query, try to get from the first user message in updates
            else if (task.updates.length > 0) {
              const firstUserUpdate = task.updates.find(update => update.update_type === 'user_message' || update.update_type === 'query');
              if (firstUserUpdate && firstUserUpdate.message) {
                threadName = firstUserUpdate.message.substring(0, 50) + (firstUserUpdate.message.length > 50 ? '...' : '');
              }
            }
          }

          return {
            id: task.thread_id,
            name: threadName,
            subject: threadName,
            lastMessage: task.updates.length > 0 ? task.updates[0].message : 'No updates',
            timestamp: task.metadata.updated_at,
            messageCount: task.updates.length,
            status: task.status,
            isScheduled: isScheduled,
            instanceId: task.context?.instance_id,
          };
        });

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

        // Convert task updates to messages (reverse to show oldest first)
        const sortedUpdates = [...status.updates].reverse();
        sortedUpdates.forEach((update, index) => {
          // Filter out technical/internal messages that users shouldn't see
          const technicalMessageTypes = [
            'turn_complete', 'agent_complete', 'completion', 'agent_init',
            'turn_start', 'queued', 'triage', 'agent_status', 'task_queued',
            'task_started', 'task_completed', 'task_failed', 'status_update'
          ];

          const technicalMessagePatterns = [
            /agent turn completed successfully/i,
            /task completed/i,
            /task queued/i,
            /task started/i,
            /task failed/i,
            /processing complete/i,
            /initialization complete/i,
            /agent initialized/i,
            /queued for processing/i,
            /task.*processing/i
          ];

          // Skip technical messages
          if (technicalMessageTypes.includes(update.type)) {
            return;
          }

          // Skip messages with technical patterns
          if (update.message && technicalMessagePatterns.some(pattern => pattern.test(update.message))) {
            return;
          }

          if (update.type === 'response') {
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
          } else if (update.type === 'agent_reflection') {
            // Show agent's reasoning and analysis (only if meaningful)
            if (update.message && update.message.length > 10 && !update.message.toLowerCase().includes('completed')) {
              newMessages.push({
                id: `reflection-${index}`,
                role: 'assistant',
                content: update.message,
                timestamp: update.timestamp,
              });
            }
          } else if (update.type === 'safety_check') {
            // Show safety and fact-checking steps
            newMessages.push({
              id: `safety-${index}`,
              role: 'system',
              content: update.message,
              timestamp: update.timestamp,
            });
          } else if (update.type === 'tool_call') {
            // Show tool calls in a user-friendly way
            const fullToolName = update.metadata?.tool_name || 'Unknown Tool';
            const toolArgs = update.metadata?.tool_args;
            const displayName = extractOperationName(fullToolName);

            newMessages.push({
              id: `tool-${index}`,
              role: 'tool',
              content: `Making tool call: ${displayName}`,
              timestamp: update.timestamp,
              toolCall: {
                name: displayName,
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

        // Add error message if task failed
        if (status.status === 'failed') {
          newMessages.push({
            id: `error-${status.thread_id}`,
            role: 'assistant',
            content: `❌ Triage failed. Please try again or contact support if the issue persists.`,
            timestamp: status.metadata.updated_at,
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

  const handleWebSocketMonitorClose = () => {
    setShowWebSocketMonitor(false);
    // Reload the thread to show the completed conversation
    if (activeThreadId) {
      selectThread(activeThreadId);
    }
  };

  const createNewThread = async () => {
    // Clear current conversation and prepare for new one
    // Don't create placeholder threads - just clear the UI state
    setActiveThreadId(null);
    setMessages([]);
    setError('');
    setShowNewConversation(true);
    setShowWebSocketMonitor(false);

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
    setShowWebSocketMonitor(false); // Reset WebSocket monitor state

    // On mobile only, switch to chat view
    if (window.innerWidth < 768) { // md breakpoint
      setShowSidebar(false);
    }

    // Load conversation history and start polling if task is active
    try {
      const status = await sreAgentApi.getTaskStatus(threadId);
      console.log('Thread status loaded:', status);

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

      // Convert updates to messages (reverse to show oldest first)
      const sortedUpdates = [...status.updates].reverse();
      sortedUpdates.forEach((update, index) => {
        // Filter out technical/internal messages that users shouldn't see
        const technicalMessageTypes = [
          'turn_complete', 'agent_complete', 'completion', 'agent_init',
          'turn_start', 'queued', 'triage', 'agent_status'
        ];

        const technicalMessagePatterns = [
          /agent turn completed successfully/i,
          /task completed/i,
          /processing complete/i,
          /initialization complete/i,
          /agent initialized/i
        ];

        // Skip technical messages
        if (technicalMessageTypes.includes(update.type)) {
          return;
        }

        // Skip messages with technical patterns
        if (update.message && technicalMessagePatterns.some(pattern => pattern.test(update.message))) {
          return;
        }

        // Handle different update types based on actual API response
        if (update.type === 'response') {
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
        } else if (update.type === 'agent_reflection' || update.type === 'agent_processing' || update.type === 'agent_start') {
          // Show agent's reasoning and analysis (only if meaningful)
          if (update.message && update.message.length > 10 && !update.message.toLowerCase().includes('completed')) {
            newMessages.push({
              id: `reflection-${index}`,
              role: 'assistant',
              content: update.message,
              timestamp: update.timestamp,
            });
          }
        } else if (update.type === 'safety_check') {
          // Show safety and fact-checking steps
          newMessages.push({
            id: `safety-${index}`,
            role: 'system',
            content: update.message,
            timestamp: update.timestamp,
          });
        } else if (update.type === 'tool_call') {
          // Show tool calls in a user-friendly way
          const fullToolName = update.metadata?.tool_name || 'Unknown Tool';
          const toolArgs = update.metadata?.tool_args;
          const displayName = extractOperationName(fullToolName);

          newMessages.push({
            id: `tool-${index}`,
            role: 'tool',
            content: `Making tool call: ${displayName}`,
            timestamp: update.timestamp,
            toolCall: {
              name: displayName,
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

      // Add error message if processing failed
      if (status.status === 'failed') {
        newMessages.push({
          id: `error-${threadId}`,
          role: 'assistant',
          content: `❌ I encountered an issue while processing your request. Please try again or contact support if the issue persists.`,
          timestamp: status.metadata.updated_at,
        });
      }

      console.log('Processed messages:', newMessages);
      setMessages(newMessages);

      // Show WebSocket monitor for active tasks, traditional chat for completed ones
      if (status.status === 'in_progress') {
        setShowWebSocketMonitor(true);
      } else {
        setShowWebSocketMonitor(false);
        // For completed tasks, we already have the messages loaded above
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

        // Store the initial query for WebSocket display
        sessionStorage.setItem(`thread-${threadId}-query`, messageContent);

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

      // WebSocket will handle updates - reset loading state after API call succeeds
      setIsLoading(false);

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
    <div className="space-y-6">
      {/* Page Header */}
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
            <h1 className="text-redis-xl font-bold text-foreground">SRE Agent Triage</h1>
            <p className="text-redis-sm text-redis-dusk-04 mt-1">
              {activeThreadId
                ? 'Chat with the Redis SRE Agent for troubleshooting and support'
                : 'Describe your Redis issue or ask a question to get started'
              }
            </p>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex gap-4 h-[calc(100vh-200px)]">
        {/* Thread Sidebar - Responsive visibility */}
        <div className={`${showSidebar ? 'flex' : 'hidden'} md:flex w-full md:w-80 md:min-w-80 max-w-80 flex-col h-full`}>
          <Card className="flex-1 flex flex-col h-full" padding="none">
          <CardHeader className="flex-shrink-0 p-4 pb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h3 className="text-redis-lg font-semibold text-foreground">Conversations</h3>
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
            <div className="flex items-center justify-between mt-2">
              <div className="flex items-center gap-2">
                <div className={`h-2 w-2 rounded-full ${
                  agentStatus === 'available' ? 'bg-redis-green' :
                  agentStatus === 'unavailable' ? 'bg-redis-red' :
                  'bg-redis-yellow-500'
                }`} />
                <span className="text-redis-xs text-redis-dusk-04">
                  Agent {agentStatus === 'available' ? 'Online' : agentStatus === 'unavailable' ? 'Offline' : 'Checking...'}
                </span>
              </div>
            </div>
          </CardHeader>
          <div className="overflow-y-auto" style={{maxHeight: 'calc(100vh - 300px)'}}>
            <div className="space-y-1 p-0">
              {threads
                .filter(thread => {
                  // Always show non-scheduled tasks
                  if (!thread.isScheduled) return true;

                  // For scheduled tasks, hide if they're just queued and waiting
                  // (no user interaction yet)
                  if (thread.status === 'queued' &&
                      thread.lastMessage === 'No updates') {
                    return false;
                  }

                  // Show all other scheduled tasks
                  return true;
                })
                .map((thread) => (
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
                    <div className="flex items-center gap-2 flex-1 min-w-0">
                      <div className={`font-medium text-redis-sm truncate ${
                        activeThreadId === thread.id ? 'text-white' : 'text-foreground'
                      }`}>
                        {thread.name}
                      </div>
                      {thread.isScheduled && (
                        <div className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap ${
                          activeThreadId === thread.id
                            ? 'bg-blue-600 text-white'
                            : 'bg-blue-100 text-blue-700'
                        }`}>
                          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
                          </svg>
                          Scheduled
                        </div>
                      )}
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
                  <p className="text-redis-xs mt-1">Click "New Chat" above to start troubleshooting with the SRE Agent.</p>
                </div>
              )}
            </div>
          </div>
        </Card>
      </div>

        {/* Chat Area */}
        <div className={`${showSidebar && !activeThreadId && !showNewConversation ? 'hidden' : 'flex'} md:flex flex-1 flex-col h-full`}>
          <Card className="flex-1 flex flex-col h-full">
            {activeThreadId ? (
            <>
              {/* Chat Header with Instance Info */}
              {threads.find(t => t.id === activeThreadId)?.instanceId &&
                instances.find(i => i.id === threads.find(t => t.id === activeThreadId)?.instanceId) && (
                <div className="px-4 py-3 border-b border-redis-dusk-08 bg-redis-dusk-09">
                  <div className="flex items-center gap-2 text-redis-sm">
                    <span className="text-redis-dusk-04">Redis Instance:</span>
                    <span className="font-medium text-foreground">
                      {instances.find(i => i.id === threads.find(t => t.id === activeThreadId)?.instanceId)?.name}
                    </span>
                    <span className="text-redis-dusk-05">•</span>
                    <span className="text-redis-dusk-04">
                      {instances.find(i => i.id === threads.find(t => t.id === activeThreadId)?.instanceId)?.environment}
                    </span>
                  </div>
                </div>
              )}

              {/* WebSocket Chat Interface */}
              <CardContent className="flex-1 overflow-hidden">
                <TaskMonitor
                  threadId={activeThreadId}
                  initialQuery={sessionStorage.getItem(`thread-${activeThreadId}-query`) || undefined}
                />
              </CardContent>

              {/* Input Area for Follow-up Messages */}
              <div className="p-4 border-t border-redis-dusk-08">
                <div className="flex gap-2">
                  <textarea
                    value={inputMessage}
                    onChange={(e) => setInputMessage(e.target.value)}
                    onKeyPress={handleKeyPress}
                    placeholder="Continue the conversation..."
                    className="flex-1 p-3 border border-redis-dusk-06 rounded-redis-sm resize-none focus:outline-none focus:ring-2 focus:ring-redis-blue-03 focus:border-transparent min-h-[60px]"
                    rows={2}
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
                    ? 'Press Enter to send, Shift+Enter for new line'
                    : 'Agent is currently unavailable'}
                </div>
              </div>
            </>
          ) : (
            <>
              {/* Empty State - No Active Thread */}
              <CardContent className="flex-1 overflow-y-auto p-4">
                <div className="flex items-center justify-center h-full text-center">
                  <div className="text-redis-dusk-04">
                    <div className="text-lg mb-2">💬</div>
                    <div className="text-sm">Select a conversation or start a new one</div>
                  </div>
                </div>
              </CardContent>

              {/* Input Area */}
              <div className="p-4 border-t border-redis-dusk-08">
                {/* Instance Selection */}
                {instances.length > 0 && (
                  <div className="mb-3">
                    <label className="block text-redis-sm font-medium text-foreground mb-2">
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
                          {instance.name} - {instance.environment}
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
                    ? 'Press Enter to send, Shift+Enter for new line'
                    : agentStatus === 'unavailable'
                    ? 'SRE Agent is currently offline. Please check the backend service.'
                    : 'Checking agent status...'
                  }
                </div>
              </div>
            </>
          )}
          </Card>
        </div>
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
