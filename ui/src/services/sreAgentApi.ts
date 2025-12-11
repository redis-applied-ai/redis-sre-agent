// SRE Agent API service - Task-based implementation
export interface ChatMessage {
  role: "user" | "assistant" | "tool" | "system";
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
  status:
    | "queued"
    | "in_progress"
    | "completed"
    | "done"
    | "failed"
    | "cancelled";
  updates: TaskUpdate[];
  result?: Record<string, any>;
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
  subject: string;
  created_at: string;
  updated_at: string;
  user_id?: string;
  latest_message: string;
  tags: string[];
  priority: number;
  instance_id?: string;
  // Optional count of user/assistant messages, provided by backend when available
  message_count?: number;
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
  // Redis Cloud identifiers
  redis_cloud_subscription_id?: number;
  redis_cloud_database_id?: number;
  // Redis Cloud metadata
  redis_cloud_subscription_type?: "pro" | "essentials";
  redis_cloud_database_name?: string;
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
  // Redis Cloud identifiers
  redis_cloud_subscription_id?: number;
  redis_cloud_database_id?: number;
  // Redis Cloud metadata
  redis_cloud_subscription_type?: "pro" | "essentials";
  redis_cloud_database_name?: string;
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
  // Redis Cloud identifiers
  redis_cloud_subscription_id?: number;
  redis_cloud_database_id?: number;
  // Redis Cloud metadata
  redis_cloud_subscription_type?: "pro" | "essentials";
  redis_cloud_database_name?: string;
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
    if (
      typeof import.meta !== "undefined" &&
      import.meta.env?.VITE_API_BASE_URL
    ) {
      return import.meta.env.VITE_API_BASE_URL;
    }

    // 3. In production builds or when using nginx proxy, use relative URLs
    if (typeof window !== "undefined") {
      // Check if we're in development mode (Vite dev server)
      // Vite typically uses ports 3000, 3001, etc. and serves from localhost
      const isDevelopment =
        (window.location.hostname === "localhost" ||
          window.location.hostname === "127.0.0.1") &&
        (window.location.port.startsWith("30") ||
          window.location.port === "5173"); // 5173 is Vite's default

      if (!isDevelopment) {
        // In production, use relative URLs (nginx will proxy to backend)
        return "/api/v1";
      }

      // In development, construct URL using current host but backend port
      const protocol = window.location.protocol;
      const hostname = window.location.hostname;

      // Use the current hostname but with backend port (8000)
      return `${protocol}//${hostname}:8000/api/v1`;
    }

    // 4. Fallback for server-side rendering or other edge cases
    return "/api/v1";
  }

  private createURL(urlString: string): URL {
    // If the URL is already absolute, use it directly
    if (urlString.startsWith("http://") || urlString.startsWith("https://")) {
      return new URL(urlString);
    }

    // For relative URLs, use the current window location as base
    if (typeof window !== "undefined") {
      return new URL(urlString, window.location.origin);
    }

    // Fallback for server-side rendering - assume localhost
    return new URL(urlString, "http://localhost:3000");
  }

  async submitTriageRequest(
    message: string,
    userId: string,
    sessionId?: string,
    priority: number = 0,
    tags?: string[],
    instanceId?: string,
  ): Promise<TriageResponse> {
    const response = await fetch(`${this.tasksBaseUrl}/tasks`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message,
        context: {
          user_id: userId,
          session_id: sessionId,
          priority,
          tags,
          ...(instanceId && { instance_id: instanceId }),
        },
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP ${response.status}: ${errorText}`);
    }

    const data = await response.json(); // TaskCreateResponse
    return {
      thread_id: data.thread_id,
      status: data.status,
      message: data.message,
    } as TriageResponse;
  }

  async continueConversation(
    threadId: string,
    message: string,
    userId: string,
    context?: Record<string, any>,
  ): Promise<TriageResponse> {
    const response = await fetch(`${this.tasksBaseUrl}/tasks`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message,
        thread_id: threadId,
        context: { user_id: userId, ...(context || {}) },
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP ${response.status}: ${errorText}`);
    }

    const data = await response.json(); // TaskCreateResponse
    return {
      thread_id: data.thread_id,
      status: data.status,
      message: data.message,
    } as TriageResponse;
  }

  async getTaskStatus(threadId: string): Promise<TaskStatusResponse> {
    // Threads endpoint returns full thread state (messages, updates, result)
    const response = await fetch(`${this.tasksBaseUrl}/threads/${threadId}`);

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP ${response.status}: ${errorText}`);
    }

    const thread = await response.json();
    // Derive a task-like status from thread data
    const status = thread?.error_message
      ? "failed"
      : thread?.result
        ? "completed"
        : "in_progress";

    return {
      thread_id: thread.thread_id,
      status,
      updates: Array.isArray(thread.updates)
        ? thread.updates.map((u: any) => ({
            timestamp: u.timestamp,
            message: u.message,
            type: u.update_type,
            metadata: u.metadata || {},
          }))
        : [],
      result: thread.result,
      error_message: thread.error_message,
      metadata: {
        created_at: thread?.metadata?.created_at,
        updated_at: thread?.metadata?.updated_at,
        user_id: thread?.metadata?.user_id,
        session_id: thread?.metadata?.session_id,
        priority: thread?.metadata?.priority ?? 0,
        tags: thread?.metadata?.tags ?? [],
        subject: thread?.metadata?.subject,
      },
      context: thread.context || {},
    } as TaskStatusResponse;
  }

  async listTasks(
    userId?: string,
    statusFilter?: string,
    limit: number = 50,
  ): Promise<TaskStatusResponse[]> {
    try {
      const baseUrl = `${this.tasksBaseUrl}/tasks`;
      const url = this.createURL(baseUrl);
      if (userId) url.searchParams.append("user_id", userId);
      if (statusFilter) url.searchParams.append("status_filter", statusFilter);
      url.searchParams.append("limit", limit.toString());

      const response = await fetch(url.toString());

      if (!response.ok) {
        // If listing is not supported, return empty without throwing
        if (response.status === 405 || response.status === 404) {
          return [];
        }
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }

      return response.json();
    } catch (e) {
      // Graceful fallback: no conversations
      return [];
    }
  }
  async listThreads(
    userId?: string,
    limit: number = 50,
    offset: number = 0,
  ): Promise<ThreadSummary[]> {
    try {
      const baseUrl = `${this.tasksBaseUrl}/threads`;
      const url = this.createURL(baseUrl);
      if (userId) url.searchParams.append("user_id", userId);
      url.searchParams.append("limit", String(limit));
      url.searchParams.append("offset", String(offset));

      const response = await fetch(url.toString());
      if (!response.ok) {
        // Gracefully handle missing list endpoint
        if (response.status === 405 || response.status === 404) return [];
        const text = await response.text();
        throw new Error(`HTTP ${response.status}: ${text}`);
      }

      const data = await response.json();
      // Ensure shape matches ThreadSummary
      return (data || []).map((t: any) => ({
        thread_id: t.thread_id,
        subject: t.subject || "Untitled",
        created_at: t.created_at,
        updated_at: t.updated_at,
        user_id: t.user_id,
        latest_message: t.latest_message || "No updates",
        tags: Array.isArray(t.tags) ? t.tags : [],
        priority: typeof t.priority === "number" ? t.priority : 0,
        instance_id: t.instance_id,
        message_count:
          typeof t.message_count === "number" ? t.message_count : undefined,
      })) as ThreadSummary[];
    } catch {
      return [];
    }
  }

  async cancelTask(
    threadId: string,
    deleteThread: boolean = false,
  ): Promise<void> {
    if (deleteThread) {
      // Deleting a conversation maps to deleting the thread
      const response = await fetch(`${this.tasksBaseUrl}/threads/${threadId}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }
      return;
    }

    // Cancelling an in-flight task by thread is not yet supported by the backend.
    // No-op for now to avoid accidental deletions on Stop.
    return;
  }

  // Polling utility for waiting for task completion
  async pollTaskUntilComplete(
    threadId: string,
    maxWaitMs: number = 300000, // 5 minutes
    pollIntervalMs: number = 2000, // 2 seconds
  ): Promise<TaskStatusResponse> {
    const startTime = Date.now();

    while (Date.now() - startTime < maxWaitMs) {
      const status = await this.getTaskStatus(threadId);

      if (
        status.status === "completed" ||
        status.status === "failed" ||
        status.status === "cancelled"
      ) {
        return status;
      }

      await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
    }

    throw new Error(`Task ${threadId} did not complete within ${maxWaitMs}ms`);
  }

  // Legacy method - now uses task-based approach
  async sendChatMessage(
    message: string,
    threadId: string,
    userId: string,
    _maxIterations: number = 10,
  ): Promise<{ response: string; thread_id: string }> {
    // For existing threads, continue the conversation
    const triageResponse = await this.continueConversation(
      threadId,
      message,
      userId,
    );

    // Poll for completion
    const finalStatus = await this.pollTaskUntilComplete(
      triageResponse.thread_id,
    );

    if (finalStatus.status === "failed") {
      throw new Error(finalStatus.error_message || "Task failed");
    }

    // Extract the response from the final result or latest update
    let response = "No response available";
    if (finalStatus.result && finalStatus.result.response) {
      response = finalStatus.result.response;
    } else if (finalStatus.updates.length > 0) {
      // Find the last assistant response
      const assistantUpdates = finalStatus.updates.filter(
        (u) => u.type === "response" || u.type === "completion",
      );
      if (assistantUpdates.length > 0) {
        response = assistantUpdates[assistantUpdates.length - 1].message;
      }
    }

    return {
      response,
      thread_id: finalStatus.thread_id,
    };
  }

  // Unified transcript helper: prefer context.messages; fallback to updates
  async getTranscript(threadId: string): Promise<ChatMessage[]> {
    const status = await this.getTaskStatus(threadId);

    // Preferred: context.messages contains the entire transcript
    const ctxMsgs = Array.isArray(status?.context?.messages)
      ? status.context.messages
      : [];
    if (ctxMsgs.length > 0) {
      return ctxMsgs.map((msg: any) => ({
        role: msg.role,
        content: msg.content,
        timestamp: msg.timestamp,
      })) as ChatMessage[];
    }

    // Fallback: reconstruct from updates and metadata
    const messages: ChatMessage[] = [];
    const initial =
      (status.context as any)?.original_query || status.metadata.subject;
    if (initial) {
      messages.push({
        role: "user",
        content: initial,
        timestamp: status.metadata.created_at,
      });
    }

    for (const update of status.updates) {
      if (
        (update.type === "response" || update.type === "completion") &&
        update.message
      ) {
        messages.push({
          role: "assistant",
          content: update.message,
          timestamp: update.timestamp,
        });
      } else if (update.type === "user_message" && update.message) {
        messages.push({
          role: "user",
          content: update.message,
          timestamp: update.timestamp,
        });
      } else if (
        (update.type === "agent_reflection" ||
          update.type === "agent_processing" ||
          update.type === "agent_start") &&
        update.message &&
        update.message.length > 10 &&
        !/completed/i.test(update.message)
      ) {
        messages.push({
          role: "assistant",
          content: update.message,
          timestamp: update.timestamp,
        });
      }
    }

    if (
      (status.status === "done" || status.status === "completed") &&
      (status as any).result?.response
    ) {
      messages.push({
        role: "assistant",
        content: (status as any).result.response,
        timestamp:
          (status as any).result.turn_completed_at ||
          status.metadata.updated_at,
      });
    }
    if (status.status === "failed" && status.error_message) {
      messages.push({
        role: "assistant",
        content: `❌ ${status.error_message}`,
        timestamp: status.metadata.updated_at,
      });
    }

    return messages;
  }

  async getConversationHistory(
    threadId: string,
    _userId?: string,
  ): Promise<{ messages: ChatMessage[] }> {
    try {
      const status = await this.getTaskStatus(threadId);

      // Convert updates to chat messages
      const messages: ChatMessage[] = [];

      // Add original query if available
      if (status.metadata.subject) {
        messages.push({
          role: "user",
          content: status.metadata.subject,
          timestamp: status.metadata.created_at,
        });
      }

      // Convert updates to messages
      for (const update of status.updates) {
        if (update.type === "response" || update.type === "completion") {
          messages.push({
            role: "assistant",
            content: update.message,
            timestamp: update.timestamp,
          });
        } else if (update.type === "user_message") {
          messages.push({
            role: "user",
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

  async clearConversation(
    threadId: string,
  ): Promise<{ session_id: string; cleared: boolean; message: string }> {
    try {
      await this.cancelTask(threadId, true); // Pass true to delete the thread
      return {
        session_id: threadId,
        cleared: true,
        message: "Conversation cleared successfully",
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
      agent_available:
        healthData.status === "healthy" || healthData.status === "degraded",
      workers_available: healthData.components?.workers === "available",
      system_health: {
        redis_connection:
          healthData.components?.redis_connection === "available",
        vectorizer: healthData.components?.vectorizer === "available",
        vector_search: healthData.components?.vector_search === "available",
        task_queue: healthData.components?.task_system === "available",
      },
      tools_available: [], // Not provided by health endpoint
      version: healthData.version || "0.1.0",
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
    instanceId?: string,
  ): Promise<string> {
    const triageResponse = await this.submitTriageRequest(
      message,
      userId,
      undefined,
      priority,
      tags,
      instanceId,
    );
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
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(
        error.detail || `Failed to create instance: ${response.statusText}`,
      );
    }

    return response.json();
  }

  async getInstance(instanceId: string): Promise<RedisInstance> {
    const response = await fetch(
      `${this.tasksBaseUrl}/instances/${instanceId}`,
    );
    if (!response.ok) {
      throw new Error(`Failed to get instance: ${response.statusText}`);
    }
    return response.json();
  }

  async updateInstance(
    instanceId: string,
    request: UpdateInstanceRequest,
  ): Promise<RedisInstance> {
    const response = await fetch(
      `${this.tasksBaseUrl}/instances/${instanceId}`,
      {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(request),
      },
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(
        error.detail || `Failed to update instance: ${response.statusText}`,
      );
    }

    return response.json();
  }

  async deleteInstance(instanceId: string): Promise<{ message: string }> {
    const response = await fetch(
      `${this.tasksBaseUrl}/instances/${instanceId}`,
      {
        method: "DELETE",
      },
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(
        error.detail || `Failed to delete instance: ${response.statusText}`,
      );
    }

    return response.json();
  }

  async testInstanceConnection(
    instanceId: string,
  ): Promise<ConnectionTestResult> {
    const response = await fetch(
      `${this.tasksBaseUrl}/instances/${instanceId}/test-connection`,
      {
        method: "POST",
      },
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(
        error.detail || `Failed to test connection: ${response.statusText}`,
      );
    }

    return response.json();
  }

  async testConnectionUrl(
    connectionUrl: string,
  ): Promise<ConnectionTestResult> {
    const response = await fetch(
      `${this.tasksBaseUrl}/instances/test-connection-url`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ connection_url: connectionUrl }),
      },
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(
        error.detail || `Failed to test connection URL: ${response.statusText}`,
      );
    }

    return response.json();
  }

  async testAdminApiConnection(
    adminUrl: string,
    adminUsername: string,
    adminPassword: string,
  ): Promise<{
    success: boolean;
    message: string;
    host?: string;
    port?: number;
    cluster_name?: string;
    tested_at: string;
  }> {
    const response = await fetch(
      `${this.tasksBaseUrl}/instances/test-admin-api`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          admin_url: adminUrl,
          admin_username: adminUsername,
          admin_password: adminPassword,
        }),
      },
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(
        error.detail ||
          `Failed to test admin API connection: ${response.statusText}`,
      );
    }

    return response.json();
  }

  // Knowledge Base Methods
  async getKnowledgeStats(): Promise<{
    total_documents: number;
    total_chunks: number;
    last_ingestion: string | null;
  }> {
    const response = await fetch(`${this.tasksBaseUrl}/knowledge/stats`);
    if (!response.ok) {
      throw new Error(`Failed to get knowledge stats: ${response.statusText}`);
    }
    return response.json();
  }

  async getKnowledgeJobs(): Promise<any[]> {
    const response = await fetch(`${this.tasksBaseUrl}/knowledge/jobs`);
    if (!response.ok) {
      throw new Error(`Failed to get knowledge jobs: ${response.statusText}`);
    }
    return response.json();
  }

  async searchKnowledge(
    query: string,
    limit: number = 10,
    category?: string,
  ): Promise<{
    query: string;
    results: Array<{
      id: string;
      title: string;
      content: string;
      source: string;
      category: string;
      score: number;
    }>;
    total_results: number;
  }> {
    const params = new URLSearchParams();
    params.append("query", query);
    params.append("limit", String(limit));
    if (category) {
      params.append("category", category);
    }

    const response = await fetch(
      `${this.tasksBaseUrl}/knowledge/search?${params}`,
    );
    if (!response.ok) {
      throw new Error(
        `Failed to search knowledge base: ${response.statusText}`,
      );
    }
    return response.json();
  }

  async ingestDocument(
    title: string,
    content: string,
    category: string = "general",
    docType: string = "runbook",
    severity: string = "info",
  ): Promise<{ message: string; document_id?: string }> {
    const response = await fetch(
      `${this.tasksBaseUrl}/knowledge/ingest/document`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          content,
          category,
          doc_type: docType,
          severity,
        }),
      },
    );

    if (!response.ok) {
      throw new Error(`Failed to ingest document: ${response.statusText}`);
    }
    return response.json();
  }

  // System Health Methods
  async getSystemHealth(): Promise<{
    status: string;
    components: Record<string, string>;
    version?: string;
  }> {
    const response = await fetch(`${this.tasksBaseUrl}/health`);
    if (!response.ok) {
      throw new Error(`Failed to get system health: ${response.statusText}`);
    }
    return response.json();
  }

  // Schedule Methods
  async listSchedules(): Promise<any[]> {
    const response = await fetch(`${this.tasksBaseUrl}/schedules/`);
    if (!response.ok) {
      throw new Error(`Failed to list schedules: ${response.statusText}`);
    }
    return response.json();
  }

  async createSchedule(scheduleData: {
    name: string;
    cron_expression: string;
    redis_instance_id?: string;
    instructions: string;
    enabled: boolean;
  }): Promise<any> {
    const response = await fetch(`${this.tasksBaseUrl}/schedules/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(scheduleData),
    });
    if (!response.ok) {
      throw new Error(`Failed to create schedule: ${response.statusText}`);
    }
    return response.json();
  }

  async updateSchedule(
    scheduleId: string,
    updateData: {
      name?: string;
      cron_expression?: string;
      redis_instance_id?: string;
      instructions?: string;
      enabled?: boolean;
    },
  ): Promise<any> {
    const response = await fetch(
      `${this.tasksBaseUrl}/schedules/${scheduleId}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updateData),
      },
    );
    if (!response.ok) {
      throw new Error(`Failed to update schedule: ${response.statusText}`);
    }
    return response.json();
  }

  async deleteSchedule(scheduleId: string): Promise<void> {
    const response = await fetch(
      `${this.tasksBaseUrl}/schedules/${scheduleId}`,
      {
        method: "DELETE",
      },
    );
    if (!response.ok) {
      throw new Error(`Failed to delete schedule: ${response.statusText}`);
    }
  }

  async triggerSchedule(scheduleId: string): Promise<any> {
    const response = await fetch(
      `${this.tasksBaseUrl}/schedules/${scheduleId}/trigger`,
      { method: "POST" },
    );
    if (!response.ok) {
      throw new Error(`Failed to trigger schedule: ${response.statusText}`);
    }
    return response.json();
  }

  async getScheduleRuns(scheduleId: string): Promise<any[]> {
    const response = await fetch(
      `${this.tasksBaseUrl}/schedules/${scheduleId}/runs`,
    );
    if (!response.ok) {
      throw new Error(`Failed to get schedule runs: ${response.statusText}`);
    }
    return response.json();
  }

  // Knowledge Settings Methods
  async getKnowledgeSettings(): Promise<{
    chunk_size: number;
    chunk_overlap: number;
    splitting_strategy: string;
    embedding_model: string;
  }> {
    const response = await fetch(`${this.tasksBaseUrl}/knowledge/settings`);
    if (!response.ok) {
      throw new Error(
        `Failed to get knowledge settings: ${response.statusText}`,
      );
    }
    return response.json();
  }

  async updateKnowledgeSettings(settings: {
    chunk_size?: number;
    chunk_overlap?: number;
    splitting_strategy?: string;
    embedding_model?: string;
  }): Promise<any> {
    const response = await fetch(`${this.tasksBaseUrl}/knowledge/settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    });
    if (!response.ok) {
      throw new Error(
        `Failed to update knowledge settings: ${response.statusText}`,
      );
    }
    return response.json();
  }

  async resetKnowledgeSettings(): Promise<any> {
    const response = await fetch(
      `${this.tasksBaseUrl}/knowledge/settings/reset`,
      {
        method: "POST",
      },
    );
    if (!response.ok) {
      throw new Error(
        `Failed to reset knowledge settings: ${response.statusText}`,
      );
    }
    return response.json();
  }
}

// Export singleton instance
export const sreAgentApi = new SREAgentAPI();
export default sreAgentApi;
