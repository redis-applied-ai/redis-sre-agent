import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Card,
  CardHeader,
  CardContent,
  Button,
  Loader,
  ErrorMessage,
  Tooltip,
} from "@radar/ui-kit";
import {
  sreAgentApi,
  type TaskStatusResponse,
  type RedisInstance,
} from "../services/sreAgentApi";
import { maskRedisUrl } from "../utils/urlMasking";

interface KnowledgeStats {
  total_documents: number;
  total_chunks: number;
  last_ingestion: string | null;
  ingestion_status: "idle" | "running" | "error";
  document_types: Record<string, number>;
  storage_size_mb: number;
}

interface SystemHealth {
  status: string;
  components: {
    redis_connection: string;
    vectorizer: string;
    indices_created: string;
    vector_search: string;
    task_system: string;
    workers: string;
  };
  timestamp: string;
  version: string;
}

interface ConversationThread {
  id: string;
  name: string;
  subject: string;
  lastMessage: string;
  timestamp: string;
  messageCount: number;
  status: string;
}

const Dashboard = () => {
  const navigate = useNavigate();
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  // Data states
  const [conversations, setConversations] = useState<ConversationThread[]>([]);
  const [instances, setInstances] = useState<RedisInstance[]>([]);
  const [knowledgeStats, setKnowledgeStats] = useState<KnowledgeStats | null>(
    null,
  );
  const [systemHealth, setSystemHealth] = useState<SystemHealth | null>(null);

  const loadDashboardData = async () => {
    setError("");

    const threadsPromise = sreAgentApi.listThreads(undefined, 10, 0);
    const instancesPromise = sreAgentApi.listInstances();
    const knowledgePromise = sreAgentApi.getKnowledgeStats();
    const healthPromise = sreAgentApi.getSystemHealth();

    const [threadsRes, instancesRes, knowledgeRes, healthRes] =
      await Promise.allSettled([
        threadsPromise,
        instancesPromise,
        knowledgePromise,
        healthPromise,
      ]);

    // Threads -> conversations (graceful if unavailable)
    if (threadsRes.status === "fulfilled") {
      const threadsData = threadsRes.value;
      const conversationThreads: ConversationThread[] = threadsData.map(
        (t) => ({
          id: t.thread_id,
          name: t.subject || "Untitled Conversation",
          subject: t.subject || "Untitled Conversation",
          lastMessage: t.latest_message || "No updates",
          timestamp: t.updated_at || t.created_at,
          messageCount: 0,
          status: "unknown",
        }),
      );
      setConversations(conversationThreads);
    } else {
      console.warn("Conversations unavailable:", threadsRes.reason);
      setConversations([]);
    }

    // Instances
    if (instancesRes.status === "fulfilled") {
      setInstances(instancesRes.value.instances);
    } else {
      console.warn("Instances unavailable:", instancesRes.reason);
      setInstances([]);
    }

    // Knowledge
    if (knowledgeRes.status === "fulfilled") {
      setKnowledgeStats(knowledgeRes.value);
    } else {
      console.warn("Knowledge stats unavailable:", knowledgeRes.reason);
      setKnowledgeStats(null);
    }

    // Health
    if (healthRes.status === "fulfilled") {
      setSystemHealth(healthRes.value);
    } else {
      console.warn("Health unavailable:", healthRes.reason);
      setSystemHealth(null);
    }

    // Surface a soft error if any failed
    const anyFailed = [threadsRes, instancesRes, knowledgeRes, healthRes].some(
      (r) => r.status === "rejected",
    );
    if (anyFailed) {
      setError(
        "Some dashboard data failed to load. Functionality may be limited.",
      );
    }

    setIsLoading(false);
  };

  useEffect(() => {
    loadDashboardData();
  }, []);

  const handleRefresh = async () => {
    setIsLoading(true);
    await loadDashboardData();
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case "done":
      case "completed":
      case "healthy":
      case "available":
        return "text-redis-green";
      case "failed":
      case "error":
      case "unhealthy":
        return "text-redis-red";
      case "in_progress":
      case "queued":
      case "running":
        return "text-redis-yellow-500";
      default:
        return "text-redis-dusk-04";
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status.toLowerCase()) {
      case "done":
      case "completed":
      case "healthy":
      case "available":
        return "✅";
      case "failed":
      case "error":
      case "unhealthy":
        return "❌";
      case "in_progress":
      case "queued":
      case "running":
        return "⏳";
      default:
        return "⚪";
    }
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <Loader size="lg" />
          <p className="text-redis-sm text-redis-dusk-04 mt-2">
            Loading dashboard...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-redis-xl font-bold text-redis-dusk-01">
            SRE Dashboard
          </h1>
          <p className="text-redis-sm text-redis-dusk-04 mt-1">
            Monitor triage tasks, knowledge base, and Redis instances.
          </p>
        </div>
        <div className="flex gap-2">
          <Tooltip content="Refresh all dashboard data">
            <Button
              variant="outline"
              onClick={handleRefresh}
              isLoading={isLoading}
            >
              {isLoading ? <Loader size="sm" /> : "Refresh"}
            </Button>
          </Tooltip>
          <Button variant="primary" onClick={() => navigate("/triage")}>
            Start Triage
          </Button>
        </div>
      </div>

      {/* Error Message */}
      {error && <ErrorMessage message={error} title="Dashboard Error" />}

      {/* Overview Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* Agent Status */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-redis-sm text-redis-dusk-04">SRE Agent</p>
                <p
                  className={`text-redis-2xl font-bold ${
                    systemHealth?.status === "unhealthy"
                      ? "text-redis-red"
                      : systemHealth?.status === "degraded"
                        ? "text-redis-yellow-500"
                        : "text-redis-green"
                  }`}
                >
                  {systemHealth?.status === "unhealthy"
                    ? "❌ Offline"
                    : systemHealth?.status === "degraded"
                      ? "🟡 Degraded"
                      : "✅ Online"}
                </p>
              </div>
              <div className="text-redis-xs text-redis-dusk-04">
                {systemHealth?.timestamp
                  ? formatTimestamp(systemHealth.timestamp)
                  : "N/A"}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Redis Instances */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-redis-sm text-redis-dusk-04">
                  Redis Instances
                </p>
                <p className="text-redis-2xl font-bold text-redis-dusk-01">
                  {instances.length}
                </p>
              </div>
              <div className="text-redis-xs text-redis-dusk-04">
                {instances.length > 0 ? "configured" : "none"}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Knowledge Base */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-redis-sm text-redis-dusk-04">
                  Knowledge Base
                </p>
                <p className="text-redis-2xl font-bold text-redis-dusk-01">
                  {knowledgeStats?.total_documents || 0}
                </p>
              </div>
              <div className="text-redis-xs text-redis-dusk-04">documents</div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Recent Triage - Full Width */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <h3 className="text-redis-lg font-semibold text-redis-dusk-01">
              Recent Triage
            </h3>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => navigate("/triage")}
              >
                View All
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => navigate("/triage")}
              >
                Triage Now
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {conversations.length === 0 ? (
              <div className="text-center py-6 text-redis-dusk-04">
                <div className="text-lg mb-2">💬</div>
                <div className="text-sm mb-3">No recent conversations</div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => navigate("/triage")}
                >
                  Start First Triage
                </Button>
              </div>
            ) : (
              conversations.slice(0, 3).map((conversation) => (
                <div
                  key={conversation.id}
                  className="flex items-center justify-between p-3 rounded-redis-sm bg-redis-dusk-09 hover:bg-redis-dusk-08 cursor-pointer transition-colors"
                  onClick={() => navigate(`/triage?thread=${conversation.id}`)}
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={`h-2 w-2 rounded-full ${
                        conversation.status === "done"
                          ? "bg-redis-green"
                          : conversation.status === "failed"
                            ? "bg-redis-red"
                            : "bg-redis-yellow-500"
                      }`}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-redis-sm font-medium text-redis-dusk-01 truncate">
                        {conversation.name}
                      </p>
                      <p className="text-redis-xs text-redis-dusk-04 truncate">
                        {conversation.lastMessage}
                      </p>
                    </div>
                  </div>
                  <span className="text-redis-xs text-redis-dusk-04">
                    {formatTimestamp(conversation.timestamp)}
                  </span>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>

      {/* Bottom Section - Knowledge and Instances */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Knowledge Highlights */}
        <Card>
          <CardHeader>
            <h3 className="text-redis-lg font-semibold text-redis-dusk-01">
              Knowledge Highlights
            </h3>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {knowledgeStats ? (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="text-center p-2 rounded bg-redis-dusk-09">
                      <div className="text-redis-md font-bold text-redis-dusk-01">
                        {knowledgeStats.total_documents}
                      </div>
                      <div className="text-redis-xs text-redis-dusk-04">
                        Documents
                      </div>
                    </div>
                    <div className="text-center p-2 rounded bg-redis-dusk-09">
                      <div className="text-redis-md font-bold text-redis-dusk-01">
                        {knowledgeStats.total_chunks || 0}
                      </div>
                      <div className="text-redis-xs text-redis-dusk-04">
                        Chunks
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-redis-sm text-redis-dusk-04">
                      Status
                    </span>
                    <span
                      className={`text-redis-sm font-medium ${
                        knowledgeStats.ingestion_status === "idle"
                          ? "text-redis-green"
                          : knowledgeStats.ingestion_status === "running"
                            ? "text-redis-yellow-500"
                            : "text-redis-red"
                      }`}
                    >
                      {knowledgeStats.ingestion_status === "idle"
                        ? "✅ Ready"
                        : knowledgeStats.ingestion_status === "running"
                          ? "⏳ Processing"
                          : "❌ Error"}
                    </span>
                  </div>

                  <div className="space-y-2">
                    <label className="text-redis-sm font-medium text-redis-dusk-01">
                      Quick Search
                    </label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        placeholder="Search knowledge base..."
                        className="flex-1 px-3 py-2 text-redis-sm border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            const query = (
                              e.target as HTMLInputElement
                            ).value.trim();
                            if (query) {
                              navigate(
                                `/knowledge?search=${encodeURIComponent(query)}`,
                              );
                            }
                          }
                        }}
                      />
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={(e) => {
                          const input = (
                            e.target as HTMLElement
                          ).parentElement?.querySelector(
                            "input",
                          ) as HTMLInputElement;
                          const query = input?.value.trim();
                          if (query) {
                            navigate(
                              `/knowledge?search=${encodeURIComponent(query)}`,
                            );
                          } else {
                            navigate("/knowledge");
                          }
                        }}
                      >
                        🔍
                      </Button>
                    </div>
                  </div>
                </>
              ) : (
                <div className="text-center py-4 text-redis-dusk-04">
                  <div className="text-lg mb-2">📚</div>
                  <div className="text-sm">Loading knowledge base...</div>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Instances */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <h3 className="text-redis-lg font-semibold text-redis-dusk-01">
                Instances
              </h3>
              <Button
                variant="outline"
                size="sm"
                onClick={() => navigate("/settings?section=instances")}
              >
                View All
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {instances.length === 0 ? (
              <div className="text-center py-6 text-redis-dusk-04">
                <div className="text-lg mb-2">🗄️</div>
                <div className="text-sm mb-3">No instances configured</div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => navigate("/settings?section=instances")}
                >
                  Add Instance
                </Button>
              </div>
            ) : (
              <div className="space-y-3">
                {instances.slice(0, 3).map((instance) => (
                  <div
                    key={instance.id}
                    className="p-3 rounded-redis-sm bg-redis-dusk-09"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="text-redis-sm font-medium text-redis-dusk-01 truncate">
                        {instance.name}
                      </h4>
                      <span
                        className={`text-redis-xs px-2 py-1 rounded ${
                          instance.connection_url
                            ? "bg-redis-green text-white"
                            : "bg-redis-dusk-06 text-redis-dusk-04"
                        }`}
                      >
                        {instance.connection_url ? "configured" : "incomplete"}
                      </span>
                    </div>
                    <div className="space-y-1">
                      <p className="text-redis-xs text-redis-dusk-04 truncate">
                        {maskRedisUrl(instance.connection_url)}
                      </p>
                      <p className="text-redis-xs text-redis-dusk-04">
                        {instance.environment} • {instance.usage}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default Dashboard;
