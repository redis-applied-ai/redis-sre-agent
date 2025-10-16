// SRE Agent API service - Task-based implementation
export interface ChatMessage {
  role: 'user' | 'assistant' | 'tool' | 'system';
  content: string;
  timestamp?: string;
}

export interface TaskUpdate {
  timestamp: string;
  message: string;
  type: string;
  metadata: Record<string, any>;
}

export interface TaskStatusResponse {
  thread_id: string;
  status: 'queued' | 'in_progress' | 'completed' | 'done' | 'failed' | 'cancelled';
  updates: TaskUpdate[];
  result?: Record<string, any>;
  action_items: any[];
  error_message?: string;
  metadata: {
    created_at: string;
    updated_at: string;
    user_id?: string;
    session_id?: string;
    priority: number;
    tags: string[];
    subject?: string;
  };
  context: Record<string, any>;
}

export interface TriageResponse {
  thread_id: string;
  status: string;
  message: string;
  estimated_completion?: string;
}

export interface ThreadSummary {
  thread_id: string;
  status: string;
  subject: string;
  created_at: string;
  updated_at: string;
  user_id?: string;
  latest_message: string;
  tags: string[];
  priority: number;
  instance_id?: string;
}

export interface RedisInstance {
  id: string;
  name: string;
  connection_url: string;
  environment: string;
  usage: string;
  description: string;
  repo_url?: string;
  notes?: string;
  monitoring_identifier?: string;
  logging_identifier?: string;
  instance_type?: string;
  admin_url?: string;
  admin_username?: string;
  admin_password?: string;
  status?: string;
  version?: string;
  memory?: string;
  connections?: number;
  last_checked?: string;
  created_at: string;
  updated_at: string;
}

export interface CreateInstanceRequest {
  name: string;
  connection_url: string;
  environment: string;
  usage: string;
  description: string;
  repo_url?: string;
  notes?: string;
  monitoring_identifier?: string;
  logging_identifier?: string;
  instance_type?: string;
  admin_url?: string;
  admin_username?: string;
  admin_password?: string;
}

export interface UpdateInstanceRequest {
  name?: string;
  connection_url?: string;
  environment?: string;
  usage?: string;
  description?: string;
  repo_url?: string;
  notes?: string;
  monitoring_identifier?: string;
  logging_identifier?: string;
  instance_type?: string;
  admin_url?: string;
  admin_username?: string;
  admin_password?: string;
  status?: string;
  version?: string;
  memory?: string;
  connections?: number;
}

export interface ConnectionTestResult {
  success: boolean;
  message: string;
  instance_id?: string;
  host?: string;
  port?: number;
  tested_at: string;
}

export interface TestConnectionUrlRequest {
  connection_url: string;
}

export interface AgentStatus {
  agent_available: boolean;
  workers_available?: boolean;
  system_health: {
    redis_connection: boolean;
    vectorizer: boolean;
    vector_search: boolean;
    task_queue: boolean;
  };
  tools_available: string[];
  version: string;
  status?: string;
}

class SREAgentAPI {
  private tasksBaseUrl: string;

  constructor(baseUrl?: string) {
    // Determine the base URL dynamically
    const apiBaseUrl = this.getApiBaseUrl(baseUrl);
    this.tasksBaseUrl = `${apiBaseUrl}`;
  }

  private getApiBaseUrl(providedBaseUrl?: string): string {
    // 1. Use provided base URL if given
    if (providedBaseUrl) {
      return providedBaseUrl;
    }

    // 2. Use environment variable if available (for build-time configuration)
    if (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL) {
      return import.meta.env.VITE_API_BASE_URL;
    }

    // 3. In production builds or when using nginx proxy, use relative URLs
    if (typeof window !== 'undefined') {
      // Check if we're in development mode (Vite dev server)
      // Vite typically uses ports 3000, 3001, etc. and serves from localhost
      const isDevelopment = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') &&
                           (window.location.port.startsWith('30') || window.location.port === '5173'); // 5173 is Vite's default

      if (!isDevelopment) {
        // In production, use relative URLs (nginx will proxy to backend)
        return '/api/v1';
      }

      // In development, construct URL using current host but backend port
      const protocol = window.location.protocol;
      const hostname = window.location.hostname;

      // Use the current hostname but with backend port (8000)
      return `${protocol}//${hostname}:8000/api/v1`;
    }

    // 4. Fallback for server-side rendering or other edge cases
    return '/api/v1';
  }

  private createURL(urlString: string): URL {
    // If the URL is already absolute, use it directly
    if (urlString.startsWith('http://') || urlString.startsWith('https://')) {
      return new URL(urlString);
    }

    // For relative URLs, use the current window location as base
    if (typeof window !== 'undefined') {
      return new URL(urlString, window.location.origin);
    }

    // Fallback for server-side rendering - assume localhost
    return new URL(urlString, 'http://localhost:3000');
  }

  async submitTriageRequest(
    message: string,
    userId: string,
    sessionId?: string,
    priority: number = 0,
    tags?: string[],
    instanceId?: string
  ): Promise<TriageResponse> {
    const response = await fetch(`${this.tasksBaseUrl}/triage`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        query: message,
        user_id: userId,
        session_id: sessionId,
        priority,
        tags,
        ...(instanceId && { instance_id: instanceId })
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP ${response.status}: ${errorText}`);
    }

    return response.json();
  }

  async continueConversation(
    threadId: string,
    message: string,
    userId: string,
    context?: Record<string, any>
  ): Promise<TriageResponse> {
    const response = await fetch(`${this.tasksBaseUrl}/tasks/${threadId}/continue`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        query: message,
        user_id: userId,
        context,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP ${response.status}: ${errorText}`);
    }

    return response.json();
  }

  async getTaskStatus(threadId: string): Promise<TaskStatusResponse> {
    const response = await fetch(`${this.tasksBaseUrl}/tasks/${threadId}`);

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP ${response.status}: ${errorText}`);
    }

    return response.json();
  }

  async listTasks(
    userId?: string,
    statusFilter?: string,
    limit: number = 50
  ): Promise<TaskStatusResponse[]> {
    const baseUrl = `${this.tasksBaseUrl}/tasks`;
    const url = this.createURL(baseUrl);
    if (userId) url.searchParams.append('user_id', userId);
    if (statusFilter) url.searchParams.append('status_filter', statusFilter);
    url.searchParams.append('limit', limit.toString());

    const response = await fetch(url.toString());

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP ${response.status}: ${errorText}`);
    }

    return response.json();
  }

  async cancelTask(threadId: string, deleteThread: boolean = false): Promise<void> {
    const baseUrl = `${this.tasksBaseUrl}/tasks/${threadId}`;
    const url = this.createURL(baseUrl);
    if (deleteThread) {
      url.searchParams.set('delete', 'true');
    }

    const response = await fetch(url.toString(), {
      method: 'DELETE',
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP ${response.status}: ${errorText}`);
    }
  }

  // Polling utility for waiting for task completion
  async pollTaskUntilComplete(
    threadId: string,
    maxWaitMs: number = 300000, // 5 minutes
    pollIntervalMs: number = 2000 // 2 seconds
  ): Promise<TaskStatusResponse> {
    const startTime = Date.now();

    while (Date.now() - startTime < maxWaitMs) {
      const status = await this.getTaskStatus(threadId);

      if (status.status === 'completed' || status.status === 'failed' || status.status === 'cancelled') {
        return status;
      }

      await new Promise(resolve => setTimeout(resolve, pollIntervalMs));
    }

    throw new Error(`Task ${threadId} did not complete within ${maxWaitMs}ms`);
  }

  // Legacy method - now uses task-based approach
  async sendChatMessage(
    message: string,
    threadId: string,
    userId: string,
    _maxIterations: number = 10
  ): Promise<{ response: string; thread_id: string }> {
    // For existing threads, continue the conversation
    const triageResponse = await this.continueConversation(threadId, message, userId);

    // Poll for completion
    const finalStatus = await this.pollTaskUntilComplete(triageResponse.thread_id);

    if (finalStatus.status === 'failed') {
      throw new Error(finalStatus.error_message || 'Task failed');
    }

    // Extract the response from the final result or latest update
    let response = 'No response available';
    if (finalStatus.result && finalStatus.result.response) {
      response = finalStatus.result.response;
    } else if (finalStatus.updates.length > 0) {
      // Find the last assistant response
      const assistantUpdates = finalStatus.updates.filter(u => u.type === 'response' || u.type === 'completion');
      if (assistantUpdates.length > 0) {
        response = assistantUpdates[assistantUpdates.length - 1].message;
      }
    }

    return {
      response,
      thread_id: finalStatus.thread_id,
    };
  }

  async getConversationHistory(threadId: string, _userId?: string): Promise<{ messages: ChatMessage[] }> {
    try {
      const status = await this.getTaskStatus(threadId);

      // Convert updates to chat messages
      const messages: ChatMessage[] = [];

      // Add original query if available
      if (status.metadata.subject) {
        messages.push({
          role: 'user',
          content: status.metadata.subject,
          timestamp: status.metadata.created_at,
        });
      }

      // Convert updates to messages
      for (const update of status.updates) {
        if (update.type === 'response' || update.type === 'completion') {
          messages.push({
            role: 'assistant',
            content: update.message,
            timestamp: update.timestamp,
          });
        } else if (update.type === 'user_message') {
          messages.push({
            role: 'user',
            content: update.message,
            timestamp: update.timestamp,
          });
        }
      }

      return { messages };
    } catch (error) {
      // Return empty history if thread doesn't exist
      return { messages: [] };
    }
  }

  async clearConversation(threadId: string): Promise<{ session_id: string; cleared: boolean; message: string }> {
    try {
      await this.cancelTask(threadId, true); // Pass true to delete the thread
      return {
        session_id: threadId,
        cleared: true,
        message: 'Conversation cleared successfully',
      };
    } catch (error) {
      return {
        session_id: threadId,
        cleared: false,
        message: `Failed to clear conversation: ${error}`,
      };
    }
  }

  async getAgentStatus(): Promise<AgentStatus> {
    // Use the /health endpoint instead of the removed /agent/status
    const response = await fetch(`${this.tasksBaseUrl}/health`);

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP ${response.status}: ${errorText}`);
    }

    const healthData = await response.json();

    // Transform health endpoint response to AgentStatus format
    return {
      agent_available: healthData.status === 'healthy' || healthData.status === 'degraded',
      workers_available: healthData.components?.workers === 'available',
      system_health: {
        redis_connection: healthData.components?.redis_connection === 'available',
        vectorizer: healthData.components?.vectorizer === 'available',
        vector_search: healthData.components?.vector_search === 'available',
        task_queue: healthData.components?.task_system === 'available',
      },
      tools_available: [], // Not provided by health endpoint
      version: healthData.version || '0.1.0',
      status: healthData.status,
    };
  }

  async checkHealth(): Promise<boolean> {
    try {
      const status = await this.getAgentStatus();
      return status.agent_available;
    } catch {
      return false;
    }
  }

  // Utility method to create a new thread and submit initial message
  async startNewConversation(
    message: string,
    userId: string,
    priority: number = 0,
    tags?: string[],
    instanceId?: string
  ): Promise<string> {
    const triageResponse = await this.submitTriageRequest(message, userId, undefined, priority, tags, instanceId);
    return triageResponse.thread_id;
  }

  // Instance Management Methods
  async listInstances(): Promise<RedisInstance[]> {
    const response = await fetch(`${this.tasksBaseUrl}/instances`);
    if (!response.ok) {
      throw new Error(`Failed to list instances: ${response.statusText}`);
    }
    return response.json();
  }

  async createInstance(request: CreateInstanceRequest): Promise<RedisInstance> {
    const response = await fetch(`${this.tasksBaseUrl}/instances`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || `Failed to create instance: ${response.statusText}`);
    }

    return response.json();
  }

  async getInstance(instanceId: string): Promise<RedisInstance> {
    const response = await fetch(`${this.tasksBaseUrl}/instances/${instanceId}`);
    if (!response.ok) {
      throw new Error(`Failed to get instance: ${response.statusText}`);
    }
    return response.json();
  }

  async updateInstance(instanceId: string, request: UpdateInstanceRequest): Promise<RedisInstance> {
    const response = await fetch(`${this.tasksBaseUrl}/instances/${instanceId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || `Failed to update instance: ${response.statusText}`);
    }

    return response.json();
  }

  async deleteInstance(instanceId: string): Promise<{ message: string }> {
    const response = await fetch(`${this.tasksBaseUrl}/instances/${instanceId}`, {
      method: 'DELETE',
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || `Failed to delete instance: ${response.statusText}`);
    }

    return response.json();
  }

  async testInstanceConnection(instanceId: string): Promise<ConnectionTestResult> {
    const response = await fetch(`${this.tasksBaseUrl}/instances/${instanceId}/test-connection`, {
      method: 'POST',
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || `Failed to test connection: ${response.statusText}`);
    }

    return response.json();
  }

  async testConnectionUrl(connectionUrl: string): Promise<ConnectionTestResult> {
    const response = await fetch(`${this.tasksBaseUrl}/instances/test-connection-url`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ connection_url: connectionUrl }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || `Failed to test connection URL: ${response.statusText}`);
    }

    return response.json();
  }

  async testAdminApiConnection(
    adminUrl: string,
    adminUsername: string,
    adminPassword: string
  ): Promise<{
    success: boolean;
    message: string;
    host?: string;
    port?: number;
    cluster_name?: string;
    tested_at: string;
  }> {
    const response = await fetch(`${this.tasksBaseUrl}/instances/test-admin-api`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        admin_url: adminUrl,
        admin_username: adminUsername,
        admin_password: adminPassword,
      }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || `Failed to test admin API connection: ${response.statusText}`);
    }

    return response.json();
  }
}

// Export singleton instance
export const sreAgentApi = new SREAgentAPI();
export default sreAgentApi;
