import { useState, useEffect, useRef, useCallback } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Card, CardHeader, CardContent, Button } from "@radar/ui-kit";
import { ConfirmDialog } from "../components/Modal";
import MarkdownRenderer from "../components/MarkdownRenderer";
import MemoryPanel from "../components/MemoryPanel";
import TaskMonitor from "../components/TaskMonitor";
import ToolCallsAccordion, {
  normalizeToolCalls,
} from "../components/ToolCallsAccordion";
import sreAgentApi, {
  type ApprovalRecord,
  type CitationGroup,
  type FeedbackRecord,
  type FeedbackVerdict,
  type PendingApprovalSummary,
  type RedisCluster,
  type RedisInstance,
  type TaskToolCall,
} from "../services/sreAgentApi";

// Simple fallback components for missing UI kit components
const Loader = ({ size = "md" }: { size?: "sm" | "md" | "lg" }) => (
  <div
    className={`animate-spin rounded-full border-2 border-gray-300 border-t-blue-600 ${
      size === "sm" ? "h-4 w-4" : size === "lg" ? "h-8 w-8" : "h-6 w-6"
    }`}
  />
);

const ErrorMessage = ({ message }: { message: string }) => (
  <div className="bg-red-50 border border-red-200 text-red-600 px-4 py-3 rounded-md">
    {message}
  </div>
);

interface FeedbackButtonsProps {
  taskId: string;
  initialVerdict?: FeedbackVerdict | null;
  onError: (msg: string) => void;
}

const FeedbackButtons = ({
  taskId,
  initialVerdict,
  onError,
}: FeedbackButtonsProps) => {
  const [verdict, setVerdict] = useState<FeedbackVerdict | null>(
    initialVerdict ?? null,
  );
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!isSubmitting) {
      setVerdict(initialVerdict ?? null);
    }
  }, [initialVerdict, taskId]);

  const handleClick = useCallback(
    async (clicked: "up" | "down") => {
      if (isSubmitting) return;
      // Clicking the already-active verdict withdraws it
      const nextVerdict: FeedbackVerdict =
        verdict === clicked ? "withdrawn" : clicked;
      const optimistic = nextVerdict === "withdrawn" ? null : nextVerdict;
      const previous = verdict;
      setVerdict(optimistic);
      setIsSubmitting(true);
      try {
        const record = await sreAgentApi.submitFeedback(taskId, nextVerdict);
        setVerdict(record.verdict === "withdrawn" ? null : record.verdict);
      } catch (err) {
        setVerdict(previous);
        onError(
          `Failed to submit feedback: ${err instanceof Error ? err.message : "Unknown error"}`,
        );
      } finally {
        setIsSubmitting(false);
      }
    },
    [taskId, verdict, isSubmitting, onError],
  );

  return (
    <div className="flex items-center gap-2 mt-2">
      <button
        data-testid="feedback-up"
        data-active={verdict === "up" ? "true" : "false"}
        onClick={() => handleClick("up")}
        disabled={isSubmitting}
        title="Helpful"
        className={`text-lg px-2 py-1 rounded transition-colors ${
          isSubmitting ? "opacity-40 cursor-not-allowed" : "cursor-pointer"
        } ${
          verdict === "up"
            ? "bg-green-100 text-green-700 border border-green-300"
            : "hover:bg-redis-dusk-08 text-redis-dusk-04"
        }`}
      >
        👍
      </button>
      <button
        data-testid="feedback-down"
        data-active={verdict === "down" ? "true" : "false"}
        onClick={() => handleClick("down")}
        disabled={isSubmitting}
        title="Not helpful"
        className={`text-lg px-2 py-1 rounded transition-colors ${
          isSubmitting ? "opacity-40 cursor-not-allowed" : "cursor-pointer"
        } ${
          verdict === "down"
            ? "bg-red-100 text-red-700 border border-red-300"
            : "hover:bg-redis-dusk-08 text-redis-dusk-04"
        }`}
      >
        👎
      </button>
    </div>
  );
};

const buildKnowledgeDocumentPath = (
  documentHash: unknown,
  chunkIndex?: unknown,
  version?: unknown,
) => {
  const docHash = String(documentHash || "").trim();
  if (!docHash) return undefined;

  const query = new URLSearchParams();
  const chunk = String(chunkIndex ?? "").trim();
  const versionText = String(version ?? "").trim();
  if (versionText) query.set("version", versionText);

  const suffix = query.toString() ? `?${query.toString()}` : "";
  const anchor = chunk ? `#chunk-${encodeURIComponent(chunk)}` : "";
  return `/knowledge/document-chunks/${encodeURIComponent(docHash)}${suffix}${anchor}`;
};

interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "tool" | "system" | "status";
  content: string;
  timestamp: string;
  metadata?: Record<string, any>;
}

interface CitationDisplayItem {
  key: string;
  title: string;
  to?: string;
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
  instanceName?: string;
  clusterId?: string;
  clusterName?: string;
}

interface SessionDetailsPanelProps {
  thread: ChatThread | undefined;
  threadId: string;
  taskId: string | null;
  status: string;
  isThreadBusy: boolean;
  pendingApproval: PendingApprovalSummary | null;
  feedback: FeedbackRecord | null;
  toolCallCount: number;
  onClose: () => void;
}

const DetailRow = ({
  label,
  value,
}: {
  label: string;
  value: string | number | null | undefined;
}) => (
  <div className="border-b border-redis-dusk-08 py-3 last:border-b-0">
    <dt className="text-redis-xs font-semibold uppercase tracking-wide text-redis-dusk-04">
      {label}
    </dt>
    <dd className="mt-1 break-all text-redis-sm text-foreground">
      {value == null || value === "" ? "Not available" : value}
    </dd>
  </div>
);

const SessionDetailsPanel = ({
  thread,
  threadId,
  taskId,
  status,
  isThreadBusy,
  pendingApproval,
  feedback,
  toolCallCount,
  onClose,
}: SessionDetailsPanelProps) => {
  const targetLabel =
    thread?.instanceName ||
    thread?.instanceId ||
    thread?.clusterName ||
    thread?.clusterId ||
    "General Q&A";

  return (
    <Card className="h-full flex flex-col" padding="none">
      <CardHeader className="flex-shrink-0 p-4 border-b border-redis-dusk-08">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-redis-lg font-semibold text-foreground">
              Session Details
            </h3>
            <p className="mt-1 text-redis-xs text-redis-dusk-04">
              Current chat routing and task state.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 overflow-y-auto p-4">
        <dl>
          <DetailRow label="Thread ID" value={threadId} />
          <DetailRow label="Task ID" value={taskId} />
          <DetailRow label="Status" value={status || "unknown"} />
          <DetailRow label="Busy" value={isThreadBusy ? "Yes" : "No"} />
          <DetailRow label="Subject" value={thread?.subject || thread?.name} />
          <DetailRow label="Target" value={targetLabel} />
          <DetailRow label="Messages" value={thread?.messageCount ?? 0} />
          <DetailRow label="Tool calls loaded" value={toolCallCount} />
          <DetailRow
            label="Feedback"
            value={feedback?.verdict ? feedback.verdict : "None"}
          />
          <DetailRow
            label="Pending approval"
            value={pendingApproval?.status || "None"}
          />
          <DetailRow label="Last updated" value={thread?.timestamp} />
        </dl>
      </CardContent>
    </Card>
  );
};

const Triage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [agentStatus, setAgentStatus] = useState<
    "unknown" | "available" | "unavailable"
  >("unknown");
  const [isPolling, setIsPolling] = useState(false);

  const [showNewConversation, setShowNewConversation] = useState(false);
  const [showSidebar, setShowSidebar] = useState(true);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [threadToDelete, setThreadToDelete] = useState<string | null>(null);
  const [instances, setInstances] = useState<RedisInstance[]>([]);
  const [clusters, setClusters] = useState<RedisCluster[]>([]);
  const [selectedInstanceId, setSelectedInstanceId] = useState<string>("");
  const [selectedClusterId, setSelectedClusterId] = useState<string>("");
  const [isThinking, setIsThinking] = useState(false);
  const [showWebSocketMonitor, setShowWebSocketMonitor] = useState(false);
  const [isThreadBusy, setIsThreadBusy] = useState(false);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [activeThreadStatus, setActiveThreadStatus] =
    useState<string>("unknown");
  const [pendingApproval, setPendingApproval] =
    useState<PendingApprovalSummary | null>(null);
  const [resumeSupported, setResumeSupported] = useState(false);
  const [approvalHistory, setApprovalHistory] = useState<ApprovalRecord[]>([]);
  const [approvalComment, setApprovalComment] = useState("");
  const [isSubmittingApproval, setIsSubmittingApproval] = useState(false);

  const [liveModeLocked, setLiveModeLocked] = useState(false);
  const [expandedCitations, setExpandedCitations] = useState<Set<string>>(
    new Set(),
  );
  const [showSessionDetailsPanel, setShowSessionDetailsPanel] =
    useState<boolean>(() => {
      if (typeof window === "undefined") return false;
      return (
        window.localStorage.getItem("triage.showSessionDetailsPanel") === "1"
      );
    });
  const [showMemoryPanel, setShowMemoryPanel] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem("triage.showMemoryPanel") === "1";
  });
  const [memoryRefreshKey, setMemoryRefreshKey] = useState(0);
  const [threadFeedback, setThreadFeedback] = useState<FeedbackRecord | null>(
    null,
  );
  const [threadToolCalls, setThreadToolCalls] = useState<TaskToolCall[]>([]);
  const [threadCitationGroups, setThreadCitationGroups] = useState<
    CitationGroup[]
  >([]);
  const [turnToolCallsByTaskId, setTurnToolCallsByTaskId] = useState<
    Record<string, TaskToolCall[]>
  >({});
  const [turnCitationGroupsByTaskId, setTurnCitationGroupsByTaskId] = useState<
    Record<string, CitationGroup[]>
  >({});

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(
      "triage.showMemoryPanel",
      showMemoryPanel ? "1" : "0",
    );
  }, [showMemoryPanel]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(
      "triage.showSessionDetailsPanel",
      showSessionDetailsPanel ? "1" : "0",
    );
  }, [showSessionDetailsPanel]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const newConversationInputRef = useRef<HTMLTextAreaElement>(null);
  const hydratedToolCallTaskIdsRef = useRef<Set<string>>(new Set());

  const isCitationMessage = (content: string) => {
    return /^\*\*(Sources for previous response|Discovered context|Startup context loaded|Knowledge loaded at startup)\*\*/.test(
      content,
    );
  };
  const isStartupCitationMessage = (message: ChatMessage) => {
    return (
      message.role === "system" &&
      /^\*\*(Startup context loaded|Knowledge loaded at startup)\*\*/.test(
        message.content,
      )
    );
  };
  const citationHeading = (content: string) => {
    const match = content.match(/^\*\*([^*]+)\*\*/);
    const heading = match?.[1] || "Sources";
    return heading === "Startup context loaded"
      ? "Knowledge loaded at startup"
      : heading;
  };
  const citationBody = (content: string) =>
    content.replace(
      /^\*\*(Sources for previous response|Discovered context|Startup context loaded|Knowledge loaded at startup)\*\*\n?/,
      "",
    );
  const citationGroupToMessage = (
    group: CitationGroup,
    taskId?: string,
  ): ChatMessage => {
    const label = String(group.label || "Sources").trim() || "Sources";
    const citations = Array.isArray(group.citations) ? group.citations : [];

    return {
      role: "system",
      content: `**${label}**`,
      metadata: {
        message_type: "citations",
        citation_group: group.group_key,
        citation_group_label: label,
        citations,
        count: group.count ?? citations.length,
        synthetic: true,
        ...(taskId ? { task_id: taskId } : {}),
      },
    };
  };
  const sortCitationMessages = (citationMessages: ChatMessage[]) =>
    [...citationMessages].sort((a, b) => {
      const aStartup = isStartupCitationMessage(a);
      const bStartup = isStartupCitationMessage(b);
      if (aStartup === bStartup) return 0;
      return aStartup ? -1 : 1;
    });

  const getCitationItems = (message: ChatMessage): CitationDisplayItem[] => {
    const metadata = message.metadata || {};
    const nestedMetadata =
      metadata.metadata && typeof metadata.metadata === "object"
        ? metadata.metadata
        : {};
    const structuredCitations = Array.isArray(nestedMetadata.citations)
      ? nestedMetadata.citations
      : Array.isArray(metadata.citations)
        ? metadata.citations
        : [];

    if (structuredCitations.length > 0) {
      return structuredCitations.map((citation: Record<string, any>, index) => {
        const title =
          String(citation.title || citation.name || "").trim() ||
          String(citation.document_hash || citation.id || "Untitled chunk");
        const documentHash = citation.document_hash;
        const chunkIndex = citation.chunk_index;
        return {
          key: String(
            citation.id ||
              `${documentHash || "citation"}-${chunkIndex ?? index}`,
          ),
          title,
          to: buildKnowledgeDocumentPath(
            documentHash,
            chunkIndex,
            citation.version,
          ),
        };
      });
    }

    return citationBody(message.content)
      .split("\n")
      .map((line, index) => {
        const trimmed = line.trim();
        if (!trimmed) return null;
        const quotedMatch = trimmed.match(
          /^[•*-]\s*"([^"]+)"(?:\s*\(([^)]*)\))?(?:\s*\[hash:([^\]]+)])?/,
        );
        const fallbackMatch = trimmed.match(
          /^[•*-]\s*([^\[(]+?)(?:\s*\(([^)]*)\))?(?:\s*\[hash:([^\]]+)])?$/,
        );
        const match = quotedMatch || fallbackMatch;
        if (!match) return null;
        const title = match[1]?.trim();
        const documentHash = match[3]?.trim();
        if (!title) return null;
        return {
          key: `${documentHash || title}-${index}`,
          title,
          to: buildKnowledgeDocumentPath(documentHash),
        };
      })
      .filter((item): item is CitationDisplayItem => Boolean(item));
  };

  const isAssistantStatusContent = (content: string) => {
    const text = content.trim();
    return [
      /^processing query with chat agent$/i,
      /^chat agent processing your question/i,
      /^processing query\b/i,
      /^i['’]m running\b/i,
      /^i am running\b/i,
      /^running (?:tool|query|analysis|diagnostic)\b/i,
      /^executing tool\b/i,
      /^calling tool\b/i,
      /^using tool\b/i,
      /^tool call\b/i,
    ].some((pattern) => pattern.test(text));
  };

  const isProgressUpdateType = (updateType: string | undefined) => {
    return Boolean(
      updateType &&
        [
          "agent_reflection",
          "agent_processing",
          "agent_start",
          "agent_status",
          "status_update",
          "tool_call",
          "tool_result",
          "task_queued",
          "task_started",
          "task_completed",
        ].includes(updateType),
    );
  };

  const getMessageUpdateType = (message: ChatMessage) => {
    const metadata = message.metadata || {};
    const nestedMetadata =
      metadata.metadata && typeof metadata.metadata === "object"
        ? metadata.metadata
        : {};
    const updateType =
      metadata.type ||
      metadata.update_type ||
      nestedMetadata.type ||
      nestedMetadata.update_type;
    return typeof updateType === "string" ? updateType : undefined;
  };

  const shouldHideTranscriptMessage = (message: ChatMessage) => {
    if (message.role === "status") return true;
    if (message.role !== "assistant") return false;
    return (
      isAssistantStatusContent(message.content) ||
      isProgressUpdateType(getMessageUpdateType(message))
    );
  };

  const getMessageTaskId = (message: ChatMessage) => {
    const metadata = message.metadata || {};
    const nestedMetadata =
      metadata.metadata && typeof metadata.metadata === "object"
        ? metadata.metadata
        : {};
    const taskId = metadata.task_id || nestedMetadata.task_id;
    return typeof taskId === "string" && taskId ? taskId : undefined;
  };

  const rememberTurnToolCalls = (
    taskId: string | null | undefined,
    toolCalls: TaskToolCall[],
    citationGroups: CitationGroup[] = [],
  ) => {
    setThreadToolCalls(toolCalls);
    setThreadCitationGroups(citationGroups);
    if (!taskId || (toolCalls.length === 0 && citationGroups.length === 0)) {
      return;
    }

    hydratedToolCallTaskIdsRef.current.add(taskId);
    setTurnToolCallsByTaskId((prev) => ({
      ...prev,
      [taskId]: toolCalls,
    }));
    setTurnCitationGroupsByTaskId((prev) => ({
      ...prev,
      [taskId]: citationGroups,
    }));
  };

  const clearTurnToolCalls = () => {
    hydratedToolCallTaskIdsRef.current = new Set();
    setThreadToolCalls([]);
    setThreadCitationGroups([]);
    setTurnToolCallsByTaskId({});
    setTurnCitationGroupsByTaskId({});
  };

  const hydrateTranscriptToolCalls = async (
    transcriptMessages: ChatMessage[],
    latestTaskId: string | null | undefined,
    latestToolCalls: TaskToolCall[],
    latestCitationGroups: CitationGroup[] = [],
  ) => {
    const taskIds = Array.from(
      new Set(
        transcriptMessages
          .filter(
            (message) =>
              message.role === "assistant" &&
              !shouldHideTranscriptMessage(message),
          )
          .map(getMessageTaskId)
          .filter((taskId): taskId is string => Boolean(taskId)),
      ),
    );
    const taskIdsToFetch = taskIds.filter(
      (taskId) =>
        taskId !== latestTaskId &&
        !hydratedToolCallTaskIdsRef.current.has(taskId),
    );

    if (
      latestTaskId &&
      (latestToolCalls.length > 0 || latestCitationGroups.length > 0)
    ) {
      hydratedToolCallTaskIdsRef.current.add(latestTaskId);
    }

    if (
      taskIdsToFetch.length === 0 &&
      latestToolCalls.length === 0 &&
      latestCitationGroups.length === 0
    ) {
      return;
    }

    const fetchedEntries = await Promise.all(
      taskIdsToFetch.map(async (taskId) => {
        try {
          const evidence = await sreAgentApi.getTaskEvidence(taskId);
          return {
            taskId,
            toolCalls: evidence.toolCalls,
            citationGroups: evidence.citationGroups,
          };
        } catch (err) {
          console.error(`Failed to load task evidence for ${taskId}:`, err);
          return { taskId, toolCalls: [], citationGroups: [] };
        }
      }),
    );

    setTurnToolCallsByTaskId((prev) => {
      const next = { ...prev };

      if (latestTaskId && latestToolCalls.length > 0) {
        next[latestTaskId] = latestToolCalls;
      }

      fetchedEntries.forEach(({ taskId, toolCalls }) => {
        hydratedToolCallTaskIdsRef.current.add(taskId);
        if (toolCalls.length > 0) {
          next[taskId] = toolCalls;
        }
      });

      return next;
    });
    setTurnCitationGroupsByTaskId((prev) => {
      const next = { ...prev };

      if (latestTaskId && latestCitationGroups.length > 0) {
        next[latestTaskId] = latestCitationGroups;
      }

      fetchedEntries.forEach(({ taskId, citationGroups }) => {
        if (citationGroups.length > 0) {
          next[taskId] = citationGroups;
        }
      });

      return next;
    });
  };

  const shouldDisplayBeforeGeneratedAnswer = (message: ChatMessage) => {
    return (
      message.role === "status" ||
      (message.role === "system" && isCitationMessage(message.content)) ||
      (message.role === "assistant" &&
        isAssistantStatusContent(message.content))
    );
  };

  const orderMessagesForDisplay = (items: ChatMessage[]) => {
    const generatedAnswerIndex = items.findLastIndex(
      (message) =>
        message.role === "assistant" &&
        !isAssistantStatusContent(message.content),
    );

    if (generatedAnswerIndex < 0) return items;

    const generatedAnswer = items[generatedAnswerIndex];
    const beforeAnswer = items.slice(0, generatedAnswerIndex);
    const afterAnswer = items.slice(generatedAnswerIndex + 1);
    const lateStatusMessages = afterAnswer.filter(
      shouldDisplayBeforeGeneratedAnswer,
    );

    if (lateStatusMessages.length === 0) return items;

    const remainingAfterAnswer = afterAnswer.filter(
      (message) => !shouldDisplayBeforeGeneratedAnswer(message),
    );

    return [
      ...beforeAnswer,
      ...lateStatusMessages,
      generatedAnswer,
      ...remainingAfterAnswer,
    ];
  };
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(
    null,
  );
  const approvalBlocked = Boolean(pendingApproval && resumeSupported);

  const userId = "sre-user-1"; // In a real app, this would come from auth

  const resetApprovalState = () => {
    setActiveTaskId(null);
    setPendingApproval(null);
    setResumeSupported(false);
    setApprovalHistory([]);
    setApprovalComment("");
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const focusNewConversationInput = () => {
    window.setTimeout(() => {
      newConversationInputRef.current?.focus();
    }, 0);
  };

  const syncThreadSearchParam = (
    threadId: string | null,
    options: { replace?: boolean } = {},
  ) => {
    try {
      const params = new URLSearchParams(window.location.search);
      if (threadId) {
        params.set("thread", threadId);
      } else {
        params.delete("thread");
      }

      const nextSearch = params.toString() ? `?${params.toString()}` : "";
      if (window.location.search === nextSearch) return;
      setSearchParams(params, { replace: options.replace ?? false });
    } catch {
      // URL sync is helpful for reload/linking, but chat state should still
      // work if browser history APIs are unavailable.
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    // Check agent status and load threads on component mount
    const initializeComponent = async () => {
      try {
        const isHealthy = await sreAgentApi.checkHealth();
        setAgentStatus(isHealthy ? "available" : "unavailable");

        // Load existing threads
        await loadThreads();

        // Load available instances
        await loadInstances();
        // Load available clusters
        await loadClusters();
      } catch {
        setAgentStatus("unavailable");
      }
    };

    initializeComponent();
  }, []);

  const loadInstances = async () => {
    try {
      const response = await sreAgentApi.listInstances();
      setInstances(response.instances);
    } catch (err) {
      console.error("Failed to load instances:", err);
      // Don't show error to user, just log it
    }
  };

  const loadClusters = async () => {
    try {
      const response = await sreAgentApi.listClusters();
      setClusters(response.clusters);
    } catch (err) {
      console.error("Failed to load clusters:", err);
      // Don't show error to user, just log it
    }
  };

  // Handle URL parameters to auto-select thread
  useEffect(() => {
    const threadParam = searchParams.get("thread");
    if (threadParam && threads.length > 0 && activeThreadId !== threadParam) {
      // Check if the thread exists in our loaded threads
      const threadExists = threads.some((thread) => thread.id === threadParam);
      if (threadExists) {
        selectThread(threadParam, { syncUrl: false });
      }
    }
  }, [threads, searchParams, activeThreadId]);

  // Auto-show new conversation when landing on the page or when threads exist but none selected
  useEffect(() => {
    const threadParam = searchParams.get("thread");
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
      // Prefer native threads listing; gracefully handle backends without it
      const summaries = await sreAgentApi.listThreads(undefined, 50, 0);

      const threadList: ChatThread[] = summaries.map((t) => {
        const subject = t.subject && t.subject.trim() ? t.subject : "Untitled";
        const tags = Array.isArray((t as any).tags)
          ? ((t as any).tags as string[])
          : [];
        const isScheduled =
          tags.includes("scheduled") || t.user_id === "scheduler";
        return {
          id: t.thread_id,
          name: subject,
          subject,
          lastMessage: t.latest_message || "No updates",
          timestamp: t.updated_at || t.created_at,
          messageCount:
            typeof (t as any).message_count === "number"
              ? (t as any).message_count
              : 0,
          status: "unknown", // precise status derived when the thread is loaded in the monitor
          isScheduled,
          instanceId: t.instance_id,
          clusterId: (t as any).cluster_id,
          instanceName: undefined,
          clusterName: undefined,
        };
      });

      setThreads(threadList);
    } catch (err) {
      console.error("Failed to load threads:", err);
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
        rememberTurnToolCalls(
          status.task_id,
          normalizeToolCalls(status.tool_calls, status.updates),
          status.citation_groups || [],
        );
        setActiveThreadStatus(status.status || "unknown");

        // Update messages from task updates
        const newMessages: ChatMessage[] = [];

        // Add original query if available (use original_query from context, not the rewritten subject)
        if (status.context?.original_query) {
          newMessages.push({
            id: `initial-${threadId}`,
            role: "user",
            content: status.context.original_query,
            timestamp: status.metadata.created_at,
          });
        }

        // Convert task updates to messages (reverse to show oldest first)
        const sortedUpdates = [...status.updates].reverse();
        sortedUpdates.forEach((update, index) => {
          // Filter out technical/internal messages that users shouldn't see
          const technicalMessageTypes = [
            "turn_complete",
            "agent_complete",
            "completion",
            "agent_init",
            "turn_start",
            "queued",
            "triage",
            "agent_status",
            "task_queued",
            "task_started",
            "task_completed",
            "task_failed",
            "status_update",
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
            /task.*processing/i,
          ];

          const updateType =
            (update as any).type || (update as any).update_type;

          // Skip technical messages
          if (technicalMessageTypes.includes(updateType)) {
            return;
          }

          // Skip messages with technical patterns
          if (
            update.message &&
            technicalMessagePatterns.some((pattern) =>
              pattern.test(update.message),
            )
          ) {
            return;
          }

          if (updateType === "response") {
            newMessages.push({
              id: `update-${index}`,
              role: "assistant",
              content: update.message,
              timestamp: update.timestamp,
            });
          } else if (updateType === "user_message") {
            newMessages.push({
              id: `update-${index}`,
              role: "user",
              content: update.message,
              timestamp: update.timestamp,
            });
          }
        });

        // Add the final agent response if task is complete and has a result
        if (
          (status.status === "done" || status.status === "completed") &&
          status.result?.response
        ) {
          newMessages.push({
            id: `result-${status.thread_id}`,
            role: "assistant",
            content: status.result.response,
            timestamp:
              status.result.turn_completed_at || status.metadata.updated_at,
          });
        }

        // Add error message if task failed
        if (status.status === "failed") {
          const resultError =
            typeof status.result?.error === "string"
              ? status.result.error
              : undefined;
          const resultMessage =
            typeof status.result?.message === "string"
              ? status.result.message
              : undefined;
          const failureDetail =
            status.error_message || resultError || resultMessage;
          newMessages.push({
            id: `error-${status.thread_id}`,
            role: "assistant",
            content: failureDetail
              ? `Chat failed: ${failureDetail}`
              : `Chat failed. Please try again or contact support if the issue persists.`,
            timestamp: status.metadata.updated_at,
          });
        }

        setMessages(orderMessagesForDisplay(newMessages));

        // Stop polling if task is complete
        if (
          status.status === "done" ||
          status.status === "completed" ||
          status.status === "failed" ||
          status.status === "cancelled"
        ) {
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
        console.error("Polling error:", err);
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
    setActiveThreadStatus("unknown");
    // Reload the thread to show the completed conversation
    if (activeThreadId) {
      selectThread(activeThreadId);
    }
  };

  const handleStop = async () => {
    if (!activeThreadId) return;
    try {
      await sreAgentApi.cancelTask(activeThreadId);
      setIsThreadBusy(false);
      setActiveThreadStatus("cancelled");
      setLiveModeLocked(false);
      setShowWebSocketMonitor(false);
      // Refresh thread list and reload current thread transcript
      await loadThreads();
      await selectThread(activeThreadId);
    } catch (err) {
      console.error("Failed to cancel task:", err);
      setError(
        `Failed to stop: ${err instanceof Error ? err.message : "Unknown error"}`,
      );
    }
  };

  const createNewThread = async () => {
    // Clear current conversation and prepare for new one
    // Don't create placeholder threads - just clear the UI state
    setActiveThreadId(null);
    setMessages([]);
    setError("");
    setShowNewConversation(true);
    setShowWebSocketMonitor(false);
    setThreadFeedback(null);
    setActiveThreadStatus("unknown");
    clearTurnToolCalls();
    resetApprovalState();
    syncThreadSearchParam(null);

    // On mobile only, switch to chat view
    if (window.innerWidth < 768) {
      // md breakpoint
      setShowSidebar(false);
    }

    // Stop any existing polling
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
    setIsPolling(false);
    focusNewConversationInput();
  };

  const selectThread = async (
    threadId: string,
    options: { syncUrl?: boolean } = {},
  ) => {
    // Stop any existing polling
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }

    // Determine if thread is likely active from sidebar data to avoid initial flip
    const sidebarThread = threads.find((t) => t.id === threadId);
    const isSameThread = activeThreadId === threadId;
    const sidebarActive = sidebarThread
      ? ["queued", "in_progress", "running"].includes(
          sidebarThread.status as any,
        )
      : false;

    // Reset state and optimistically set live view based on sidebar status
    setActiveThreadId(threadId);
    if (options.syncUrl !== false) {
      syncThreadSearchParam(threadId);
    }
    setMessages([]);
    setError("");
    setIsPolling(false);
    setShowNewConversation(false);
    setLiveModeLocked(sidebarActive);
    setShowWebSocketMonitor(sidebarActive);
    setThreadFeedback(null);
    setActiveThreadStatus(sidebarThread?.status || "unknown");
    if (!isSameThread) {
      clearTurnToolCalls();
    } else {
      setThreadToolCalls([]);
    }
    resetApprovalState();

    // On mobile only, switch to chat view
    if (window.innerWidth < 768) {
      // md breakpoint
      setShowSidebar(false);
    }

    // Load conversation transcript and set view mode based on status
    try {
      const status = await sreAgentApi.getTaskStatus(threadId);
      const transcript = await sreAgentApi.getTranscript(threadId);
      const latestToolCalls = normalizeToolCalls(
        status.tool_calls,
        status.updates,
      );
      rememberTurnToolCalls(
        status.task_id,
        latestToolCalls,
        status.citation_groups || [],
      );

      const newMessages: ChatMessage[] = transcript.map((m, idx) => ({
        id: `m-${idx}-${m.role}-${m.timestamp || idx}`,
        role: m.role as any,
        content: m.content,
        timestamp: m.timestamp || new Date().toISOString(),
        metadata: m.metadata,
      }));
      const latestPreviewMessage = [...newMessages]
        .reverse()
        .find(
          (message) =>
            !shouldHideTranscriptMessage(message) &&
            !(message.role === "system" && isCitationMessage(message.content)),
        );

      setMessages(orderMessagesForDisplay(newMessages));
      await hydrateTranscriptToolCalls(
        newMessages,
        status.task_id,
        latestToolCalls,
        status.citation_groups || [],
      );

      // Update message count and last message in sidebar for this thread
      setThreads((prev) =>
        prev.map((t) =>
          t.id === threadId
            ? {
                ...t,
                messageCount: newMessages.length,
                lastMessage: latestPreviewMessage?.content || t.lastMessage,
                timestamp: new Date().toISOString(),
                instanceId:
                  (status.context as any)?.instance_id || t.instanceId,
                clusterId: (status.context as any)?.cluster_id || t.clusterId,
                instanceName: (status.context as any)?.instance_id
                  ? instances.find(
                      (i) => i.id === (status.context as any)?.instance_id,
                    )?.name || t.instanceName
                  : t.instanceName,
                clusterName: (status.context as any)?.cluster_id
                  ? clusters.find(
                      (c) => c.id === (status.context as any)?.cluster_id,
                    )?.name || t.clusterName
                  : t.clusterName,
              }
            : t,
        ),
      );

      const active = ["queued", "in_progress", "running"].includes(
        status.status as any,
      );
      setIsThreadBusy(active);
      setActiveTaskId(status.task_id || null);
      setActiveThreadStatus(status.status || "unknown");
      setPendingApproval(status.pending_approval || null);
      setResumeSupported(Boolean(status.resume_supported));
      if (status.task_id) {
        const approvals = await sreAgentApi.getTaskApprovals(status.task_id);
        setApprovalHistory(approvals);
        setThreadFeedback(status.feedback ?? null);
      } else {
        setApprovalHistory([]);
        setThreadFeedback(null);
        setThreadToolCalls([]);
      }
      if (!liveModeLocked) setShowWebSocketMonitor(active);
    } catch (err) {
      console.warn("Could not load thread status:", err);
      setIsThreadBusy(false);
      setActiveThreadStatus("unknown");
      setThreadToolCalls([]);
      resetApprovalState();
    }
  };

  const handleApprovalDecision = async (decision: "approved" | "rejected") => {
    if (!activeTaskId || !pendingApproval || !resumeSupported) {
      return;
    }

    setIsSubmittingApproval(true);
    setError("");

    try {
      await sreAgentApi.resumeTask(activeTaskId, {
        approval_id: pendingApproval.approval_id,
        decision,
        decision_by: userId,
        decision_comment: approvalComment.trim() || undefined,
      });

      setPendingApproval(null);
      setResumeSupported(false);
      setApprovalComment("");
      await loadThreads();
      if (activeThreadId) {
        await selectThread(activeThreadId);
      }
    } catch (err) {
      setError(
        `Failed to submit approval decision: ${err instanceof Error ? err.message : "Unknown error"}`,
      );
    } finally {
      setIsSubmittingApproval(false);
    }
  };

  const hasStructuredCitationGroups =
    threadCitationGroups.length > 0 ||
    Object.values(turnCitationGroupsByTaskId).some(
      (groups) => groups.length > 0,
    );
  const displayMessages = orderMessagesForDisplay(messages).filter(
    (message) =>
      !shouldHideTranscriptMessage(message) &&
      !(
        hasStructuredCitationGroups &&
        message.role === "system" &&
        isCitationMessage(message.content)
      ),
  );
  const displayRows = (() => {
    const rows: Array<
      | { kind: "message"; message: ChatMessage }
      | { kind: "tool-calls"; id: string; toolCalls: TaskToolCall[] }
    > = [];
    const insertedTaskIds = new Set<string>();
    const insertedCitationTaskIds = new Set<string>();
    const citationMessagesByTaskId: Record<string, ChatMessage[]> = {};
    Object.entries(turnCitationGroupsByTaskId).forEach(([taskId, groups]) => {
      if (groups.length === 0) return;
      citationMessagesByTaskId[taskId] = sortCitationMessages(
        groups.map((group) => citationGroupToMessage(group, taskId)),
      );
    });
    if (
      activeTaskId &&
      threadCitationGroups.length > 0 &&
      !citationMessagesByTaskId[activeTaskId]
    ) {
      citationMessagesByTaskId[activeTaskId] = sortCitationMessages(
        threadCitationGroups.map((group) =>
          citationGroupToMessage(group, activeTaskId),
        ),
      );
    }
    const legacyCitationMessages = hasStructuredCitationGroups
      ? []
      : sortCitationMessages(
          displayMessages.filter(
            (message) =>
              message.role === "system" && isCitationMessage(message.content),
          ),
        );
    const transcriptMessages = displayMessages.filter(
      (message) =>
        !(message.role === "system" && isCitationMessage(message.content)),
    );
    let insertedLegacyCitations = false;

    const insertLegacyCitations = () => {
      if (insertedLegacyCitations) return;
      legacyCitationMessages.forEach((message) => {
        rows.push({ kind: "message", message });
      });
      insertedLegacyCitations = true;
    };

    transcriptMessages.forEach((message) => {
      if (
        message.role === "assistant" &&
        legacyCitationMessages.length > 0 &&
        !insertedLegacyCitations
      ) {
        insertLegacyCitations();
      }

      if (
        message.role === "assistant" &&
        !isAssistantStatusContent(message.content)
      ) {
        const taskId = getMessageTaskId(message);
        const fallbackTaskId =
          !taskId &&
          activeTaskId &&
          (threadToolCalls.length > 0 || threadCitationGroups.length > 0) &&
          !insertedTaskIds.has(activeTaskId)
            ? activeTaskId
            : undefined;
        const resolvedTaskId = taskId || fallbackTaskId;
        const citationMessages = resolvedTaskId
          ? citationMessagesByTaskId[resolvedTaskId] || []
          : [];
        if (
          resolvedTaskId &&
          citationMessages.length > 0 &&
          !insertedCitationTaskIds.has(resolvedTaskId)
        ) {
          citationMessages.forEach((citationMessage) => {
            rows.push({ kind: "message", message: citationMessage });
          });
          insertedCitationTaskIds.add(resolvedTaskId);
        }
        const toolCalls = taskId
          ? turnToolCallsByTaskId[taskId] || []
          : fallbackTaskId
            ? threadToolCalls
            : [];
        if (
          resolvedTaskId &&
          toolCalls.length > 0 &&
          !insertedTaskIds.has(resolvedTaskId)
        ) {
          rows.push({
            kind: "tool-calls",
            id: `tool-calls-${resolvedTaskId}`,
            toolCalls,
          });
          insertedTaskIds.add(resolvedTaskId);
        }
      }

      rows.push({ kind: "message", message });
      if (message.role === "user" && legacyCitationMessages.length > 0) {
        insertLegacyCitations();
      }
    });

    if (legacyCitationMessages.length > 0) {
      insertLegacyCitations();
    }

    if (
      activeTaskId &&
      threadCitationGroups.length > 0 &&
      !insertedCitationTaskIds.has(activeTaskId)
    ) {
      const citationMessages = citationMessagesByTaskId[activeTaskId] || [];
      citationMessages.forEach((citationMessage) => {
        rows.push({ kind: "message", message: citationMessage });
      });
    }

    if (
      activeTaskId &&
      threadToolCalls.length > 0 &&
      !insertedTaskIds.has(activeTaskId)
    ) {
      rows.push({
        kind: "tool-calls",
        id: `tool-calls-${activeTaskId}`,
        toolCalls: threadToolCalls,
      });
    }

    return rows;
  })();

  const sendMessage = async () => {
    if (!inputMessage.trim() || isLoading) return;

    const userMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: "user",
      content: inputMessage.trim(),
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    const messageContent = inputMessage.trim();
    setInputMessage("");
    setIsLoading(true);
    setError("");

    try {
      let threadId = activeThreadId;

      // Block sending if the thread is busy (user should press Stop)
      if (activeThreadId && isThreadBusy) {
        setIsLoading(false);
        return;
      }

      if (activeThreadId && approvalBlocked) {
        setError(
          "This task is waiting for human approval. Use the approval controls above to approve or reject it before continuing.",
        );
        setIsLoading(false);
        return;
      }

      // If no active thread, create a new one
      if (!activeThreadId) {
        const triageResponse = await sreAgentApi.startNewConversation(
          messageContent,
          userId,
          0,
          undefined,
          selectedInstanceId || undefined,
          selectedClusterId || undefined,
        );
        threadId = triageResponse;

        // Update the active thread ID
        setActiveThreadId(threadId);
        syncThreadSearchParam(threadId);
        setShowNewConversation(false);
        clearTurnToolCalls();

        // Store the initial query for WebSocket display and show live monitor
        sessionStorage.setItem(`thread-${threadId}-query`, messageContent);
        setShowWebSocketMonitor(true);
        setIsThreadBusy(true);
        setActiveThreadStatus("queued");
        resetApprovalState();

        // Add new thread to the list
        const resolvedInstanceName = selectedInstanceId
          ? instances.find((i) => i.id === selectedInstanceId)?.name ||
            undefined
          : undefined;
        const resolvedClusterName = selectedClusterId
          ? clusters.find((c) => c.id === selectedClusterId)?.name || undefined
          : undefined;
        const newThread: ChatThread = {
          id: threadId,
          name:
            messageContent.substring(0, 30) +
            (messageContent.length > 30 ? "..." : ""),
          subject:
            messageContent.substring(0, 50) +
            (messageContent.length > 50 ? "..." : ""),
          lastMessage: "Agent is thinking...",
          timestamp: new Date().toISOString(),
          messageCount: 1,
          status: "queued",
          instanceId: selectedInstanceId || undefined,
          instanceName: resolvedInstanceName,
          clusterId: selectedClusterId || undefined,
          clusterName: resolvedClusterName,
        };
        setThreads((prev) => [newThread, ...prev]);

        // Refresh threads to replace placeholder title with backend-provided subject
        await loadThreads();
      } else {
        // Continue existing conversation: switch to live WebSocket monitor
        await sreAgentApi.continueConversation(
          threadId!,
          messageContent,
          userId,
        );
        sessionStorage.setItem(`thread-${threadId}-query`, messageContent);

        // Refresh threads to replace placeholder title with backend-provided subject
        await loadThreads();

        setShowWebSocketMonitor(true);
        setIsThreadBusy(true);
        setLiveModeLocked(true);
        setActiveThreadStatus("queued");
        setThreadToolCalls([]);
        resetApprovalState();
      }

      // WebSocket will handle updates - reset loading state after API call succeeds
      setIsLoading(false);
    } catch (err) {
      setError(
        `Failed to send message: ${err instanceof Error ? err.message : "Unknown error"}`,
      );
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
        setError("");
        setIsPolling(false);
        setThreadFeedback(null);
        setActiveThreadStatus("unknown");
        syncThreadSearchParam(null);
        clearTurnToolCalls();
        resetApprovalState();

        // Stop polling
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
        }
      }

      // Remove from threads list
      setThreads((prev) =>
        prev.filter((thread) => thread.id !== threadToDelete),
      );
    } catch (err) {
      console.error("Failed to delete thread:", err);
      setError(
        `Failed to delete conversation: ${err instanceof Error ? err.message : "Unknown error"}`,
      );
    } finally {
      setThreadToDelete(null);
    }
  };

  const handleComposerKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const activeThread = activeThreadId
    ? threads.find((thread) => thread.id === activeThreadId)
    : undefined;
  const loadedToolCallCount = Array.from(
    new Map(
      [...Object.values(turnToolCallsByTaskId).flat(), ...threadToolCalls].map(
        (toolCall, index) => [
          toolCall.id || `${toolCall.name || "tool"}-${index}`,
          toolCall,
        ],
      ),
    ).values(),
  ).length;
  const targetSelectionValue = selectedClusterId
    ? `cluster:${selectedClusterId}`
    : selectedInstanceId
      ? `instance:${selectedInstanceId}`
      : "";
  const targetSelectionLabel = selectedClusterId
    ? clusters.find((cluster) => cluster.id === selectedClusterId)?.name ||
      "Selected cluster"
    : selectedInstanceId
      ? instances.find((instance) => instance.id === selectedInstanceId)
          ?.name || "Selected instance"
      : "General troubleshooting";
  const hasTargetOptions = instances.length > 0 || clusters.length > 0;
  const handleTargetSelectionChange = (value: string) => {
    if (value.startsWith("instance:")) {
      setSelectedInstanceId(value.slice("instance:".length));
      setSelectedClusterId("");
      return;
    }

    if (value.startsWith("cluster:")) {
      setSelectedClusterId(value.slice("cluster:".length));
      setSelectedInstanceId("");
      return;
    }

    setSelectedInstanceId("");
    setSelectedClusterId("");
  };
  const targetSelectionAccordion = hasTargetOptions ? (
    <details
      data-testid="chat-target-accordion"
      className="mt-3 overflow-hidden rounded-redis-sm border border-redis-dusk-08 bg-redis-dusk-09 text-redis-sm"
    >
      <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 text-left font-medium text-foreground transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-redis-blue-03">
        <span
          aria-hidden="true"
          className="accordion-chevron flex h-3 w-3 flex-shrink-0 items-center justify-center"
        >
          <span className="h-1.5 w-1.5 border-b border-r border-current" />
        </span>
        <span className="min-w-0 flex-1 truncate">Troubleshooting target</span>
        <span className="max-w-[220px] truncate text-redis-xs font-normal text-redis-dusk-04">
          {targetSelectionLabel}
        </span>
      </summary>
      <div className="border-t border-redis-dusk-08 px-3 py-3">
        <label
          htmlFor="chat-target-select"
          className="block text-redis-xs font-semibold uppercase tracking-wide text-redis-dusk-04"
        >
          Target
        </label>
        <select
          id="chat-target-select"
          value={targetSelectionValue}
          onChange={(e) => handleTargetSelectionChange(e.target.value)}
          className="mt-1 w-full rounded-redis-sm border border-redis-dusk-06 px-3 py-2 text-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
          disabled={isLoading || agentStatus !== "available"}
        >
          <option value="">General troubleshooting</option>
          {instances.length > 0 && (
            <optgroup label="Instances">
              {instances.map((instance) => (
                <option key={instance.id} value={`instance:${instance.id}`}>
                  {instance.name} - {instance.environment}
                </option>
              ))}
            </optgroup>
          )}
          {clusters.length > 0 && (
            <optgroup label="Clusters">
              {clusters.map((cluster) => (
                <option key={cluster.id} value={`cluster:${cluster.id}`}>
                  {cluster.name} - {cluster.environment}
                </option>
              ))}
            </optgroup>
          )}
        </select>
      </div>
    </details>
  ) : null;

  return (
    <div className="flex min-h-0 flex-1 flex-col space-y-6">
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
            <h1 className="text-redis-xl font-bold text-foreground">
              SRE Agent Chat
            </h1>
            <p className="text-redis-sm text-redis-dusk-04 mt-1">
              {activeThreadId
                ? "Chat with the Redis SRE Agent for troubleshooting and support"
                : "Describe your Redis issue or ask a question to get started"}
            </p>
          </div>
        </div>
        {activeThreadId && (
          <div className="flex items-center gap-2">
            <Button
              variant={showSessionDetailsPanel ? "primary" : "outline"}
              size="sm"
              onClick={() => setShowSessionDetailsPanel((v) => !v)}
              title={
                showSessionDetailsPanel
                  ? "Hide session details"
                  : "Show session details"
              }
            >
              Session Details
            </Button>
            <Button
              variant={showMemoryPanel ? "primary" : "outline"}
              size="sm"
              onClick={() => setShowMemoryPanel((v) => !v)}
              title={
                showMemoryPanel ? "Hide memory panel" : "Show memory panel"
              }
            >
              Memory
            </Button>
          </div>
        )}
      </div>

      {/* Main Content Area */}
      <div className="flex gap-4 min-h-0 flex-1">
        {/* Thread Sidebar - Responsive visibility */}
        <div
          className={`${showSidebar ? "flex" : "hidden"} md:flex w-full md:w-80 md:min-w-80 max-w-80 flex-col h-full`}
        >
          <Card className="flex-1 flex flex-col h-full" padding="none">
            <CardHeader className="flex-shrink-0 p-4 pb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <h3 className="text-redis-lg font-semibold text-foreground">
                    Conversations
                  </h3>
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
                  <div
                    className={`h-2 w-2 rounded-full ${
                      agentStatus === "available"
                        ? "bg-redis-green"
                        : agentStatus === "unavailable"
                          ? "bg-redis-red"
                          : "bg-redis-yellow-500"
                    }`}
                  />
                  <span className="text-redis-xs text-redis-dusk-04">
                    Agent{" "}
                    {agentStatus === "available"
                      ? "Online"
                      : agentStatus === "unavailable"
                        ? "Offline"
                        : "Checking..."}
                  </span>
                </div>
              </div>
            </CardHeader>
            <div className="overflow-y-auto min-h-0 flex-1">
              <div className="space-y-1 p-0">
                {threads
                  .filter((thread) => {
                    // Always show non-scheduled tasks
                    if (!thread.isScheduled) return true;

                    // For scheduled tasks, hide if they're just queued and waiting
                    // (no user interaction yet)
                    if (
                      thread.status === "queued" &&
                      thread.lastMessage === "No updates"
                    ) {
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
                          ? "bg-redis-blue-03 border-redis-blue-03 text-white"
                          : "hover:bg-redis-dusk-09 border-transparent"
                      }`}
                      onClick={() => selectThread(thread.id)}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex flex-col gap-1 flex-1 min-w-0">
                          <div
                            className={`font-medium text-redis-sm truncate ${
                              activeThreadId === thread.id
                                ? "text-white"
                                : "text-foreground"
                            }`}
                          >
                            {thread.name}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {thread.isScheduled && (
                            <div
                              className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap ${
                                activeThreadId === thread.id
                                  ? "bg-blue-600 text-white"
                                  : "bg-blue-100 text-blue-700"
                              }`}
                            >
                              <svg
                                className="w-3 h-3"
                                fill="currentColor"
                                viewBox="0 0 20 20"
                              >
                                <path
                                  fillRule="evenodd"
                                  d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z"
                                  clipRule="evenodd"
                                />
                              </svg>
                              Scheduled
                            </div>
                          )}
                        </div>
                        <button
                          onClick={(e) => showDeleteConfirmation(thread.id, e)}
                          className={`opacity-0 group-hover:opacity-100 flex items-center justify-center w-5 h-5 rounded transition-all ${
                            activeThreadId === thread.id
                              ? "text-blue-200 hover:text-white hover:bg-white hover:bg-opacity-20"
                              : "text-redis-dusk-04 hover:text-redis-red hover:bg-redis-red hover:bg-opacity-10"
                          }`}
                          title="Delete conversation"
                        >
                          <svg
                            className="w-3 h-3"
                            fill="currentColor"
                            viewBox="0 0 20 20"
                          >
                            <path
                              fillRule="evenodd"
                              d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                              clipRule="evenodd"
                            />
                          </svg>
                        </button>
                      </div>
                      <div
                        className={`text-redis-xs truncate mt-1 ${
                          activeThreadId === thread.id
                            ? "text-blue-100"
                            : "text-redis-dusk-04"
                        }`}
                      >
                        {thread.lastMessage}
                      </div>
                      <div
                        className={`text-redis-xs mt-1 flex items-center gap-2 ${
                          activeThreadId === thread.id
                            ? "text-blue-200"
                            : "text-redis-dusk-05"
                        }`}
                      >
                        <span>{formatTimestamp(thread.timestamp)}</span>
                        <span>•</span>
                        <span>{thread.messageCount} messages</span>
                        <>
                          <span>•</span>
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 max-w-[140px] truncate">
                            {thread.instanceName ||
                              (thread.instanceId
                                ? instances.find(
                                    (i) => i.id === thread.instanceId,
                                  )?.name
                                : undefined) ||
                              thread.clusterName ||
                              (thread.clusterId
                                ? clusters.find(
                                    (c) => c.id === thread.clusterId,
                                  )?.name
                                : undefined) ||
                              "General Q&A"}
                          </span>
                        </>
                      </div>
                    </div>
                  ))}
                {threads.length === 0 && (
                  <div className="p-6 text-center text-redis-dusk-04">
                    <p className="text-redis-sm">No conversations yet.</p>
                    <p className="text-redis-xs mt-1">
                      Click "New Chat" above to start troubleshooting with the
                      SRE Agent.
                    </p>
                  </div>
                )}
              </div>
            </div>
          </Card>
        </div>

        {/* Chat Area */}
        <div
          className={`${showSidebar && !activeThreadId && !showNewConversation ? "hidden" : "flex"} md:flex flex-1 flex-col h-full`}
        >
          <Card className="flex-1 flex flex-col h-full">
            {activeThreadId ? (
              <>
                {/* Chat Header with Target Info */}
                {(() => {
                  const activeInstance = activeThread?.instanceId
                    ? instances.find((i) => i.id === activeThread.instanceId)
                    : undefined;
                  const activeCluster = activeThread?.clusterId
                    ? clusters.find((c) => c.id === activeThread.clusterId)
                    : undefined;

                  if (activeInstance) {
                    return (
                      <div className="px-4 py-3 border-b border-redis-dusk-08 bg-redis-dusk-09">
                        <div className="flex items-center gap-2 text-redis-sm">
                          <span className="text-redis-dusk-04">
                            Redis Instance:
                          </span>
                          <span className="font-medium text-foreground">
                            {activeInstance.name}
                          </span>
                          <span className="text-redis-dusk-05">•</span>
                          <span className="text-redis-dusk-04">
                            {activeInstance.environment}
                          </span>
                        </div>
                      </div>
                    );
                  }

                  if (activeCluster) {
                    return (
                      <div className="px-4 py-3 border-b border-redis-dusk-08 bg-redis-dusk-09">
                        <div className="flex items-center gap-2 text-redis-sm">
                          <span className="text-redis-dusk-04">
                            Redis Cluster:
                          </span>
                          <span className="font-medium text-foreground">
                            {activeCluster.name}
                          </span>
                          <span className="text-redis-dusk-05">•</span>
                          <span className="text-redis-dusk-04">
                            {activeCluster.environment}
                          </span>
                        </div>
                      </div>
                    );
                  }

                  return null;
                })()}

                {/* Chat Content Area */}
                <CardContent className="flex-1 min-h-0 overflow-hidden">
                  {showWebSocketMonitor && (
                    <TaskMonitor
                      threadId={activeThreadId}
                      renderTranscript={false}
                      initialQuery={
                        sessionStorage.getItem(
                          `thread-${activeThreadId}-query`,
                        ) || undefined
                      }
                      onSnapshot={(snapshot) => {
                        const snapshotMessages = orderMessagesForDisplay(
                          snapshot.messages.map((message) => ({
                            ...message,
                            role: message.role as ChatMessage["role"],
                          })),
                        );
                        setMessages(snapshotMessages);
                        setActiveThreadStatus(snapshot.status || "unknown");
                        if (snapshot.taskId) {
                          setActiveTaskId(snapshot.taskId);
                          rememberTurnToolCalls(
                            snapshot.taskId,
                            snapshot.toolCalls,
                            snapshot.citationGroups,
                          );
                        }
                        void hydrateTranscriptToolCalls(
                          snapshotMessages,
                          snapshot.taskId,
                          snapshot.toolCalls,
                          snapshot.citationGroups,
                        );
                      }}
                      onStatusChange={(status) => {
                        setActiveThreadStatus(status || "unknown");
                        const active = [
                          "queued",
                          "in_progress",
                          "running",
                        ].includes(status as any);
                        setIsThreadBusy(active);
                        // Only ever turn ON live view from status; do not turn OFF here
                        if (active) {
                          setShowWebSocketMonitor(true);
                          setLiveModeLocked(true);
                        } else if (status === "awaiting_approval") {
                          setIsThreadBusy(false);
                          setShowWebSocketMonitor(false);
                          setLiveModeLocked(false);
                        }
                      }}
                      onApprovalStateChange={async (
                        nextPendingApproval,
                        nextResumeSupported,
                      ) => {
                        setPendingApproval(nextPendingApproval);
                        setResumeSupported(nextResumeSupported);
                        if (nextPendingApproval && nextResumeSupported) {
                          setIsThreadBusy(false);
                          setShowWebSocketMonitor(false);
                          setLiveModeLocked(false);
                          await loadThreads();
                          if (activeThreadId) {
                            await selectThread(activeThreadId);
                          }
                        }
                      }}
                      onCompleted={async () => {
                        setIsThreadBusy(false);
                        setActiveThreadStatus("done");
                        setLiveModeLocked(false);
                        setShowWebSocketMonitor(false);
                        resetApprovalState();
                        await loadThreads();
                        if (activeThreadId) {
                          await selectThread(activeThreadId);
                        }
                        setMemoryRefreshKey((k) => k + 1);
                      }}
                    />
                  )}
                  <div className="h-full min-h-0 overflow-y-auto p-4 space-y-4">
                    {approvalBlocked && pendingApproval && (
                      <div className="rounded-redis-md border border-amber-300 bg-amber-50 px-4 py-3 text-amber-950">
                        <div className="text-redis-sm font-semibold">
                          Approval required
                        </div>
                        <div className="mt-1 text-redis-sm">
                          This task is paused waiting for human approval to
                          continue: {pendingApproval.summary}
                        </div>
                        <div className="mt-2 text-redis-xs text-amber-900">
                          Requested{" "}
                          {new Date(
                            pendingApproval.requested_at,
                          ).toLocaleString()}
                          {pendingApproval.expires_at
                            ? ` • Expires ${new Date(
                                pendingApproval.expires_at,
                              ).toLocaleString()}`
                            : ""}
                        </div>
                        <div className="mt-2 text-redis-xs text-amber-900">
                          Review the pending action, optionally add a comment,
                          then approve or reject it here to resume the task.
                        </div>
                        {activeTaskId && (
                          <>
                            {approvalHistory.length > 0 && (
                              <div className="mt-3 rounded-redis-sm border border-amber-200 bg-white/60 p-3">
                                <div className="text-redis-xs font-semibold uppercase tracking-wide text-amber-900">
                                  Approval history
                                </div>
                                <div className="mt-2 space-y-2">
                                  {approvalHistory.map((approval) => (
                                    <div
                                      key={approval.approval_id}
                                      className="text-redis-xs text-amber-950"
                                    >
                                      <div className="font-medium">
                                        {approval.tool_name}
                                      </div>
                                      <div>
                                        Status: {approval.status}
                                        {approval.decision?.decision_by
                                          ? ` • By ${approval.decision.decision_by}`
                                          : ""}
                                      </div>
                                      <div>
                                        Requested{" "}
                                        {new Date(
                                          approval.requested_at,
                                        ).toLocaleString()}
                                      </div>
                                      {approval.decision?.decision_comment && (
                                        <div>
                                          Comment:{" "}
                                          {approval.decision.decision_comment}
                                        </div>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                            <div className="mt-3 space-y-2">
                              <label className="block text-redis-xs font-semibold uppercase tracking-wide text-amber-900">
                                Decision comment
                              </label>
                              <textarea
                                value={approvalComment}
                                onChange={(e) =>
                                  setApprovalComment(e.target.value)
                                }
                                placeholder="Optional comment for the approval record"
                                className="w-full rounded-redis-sm border border-amber-300 bg-white px-3 py-2 text-redis-sm text-foreground focus:outline-none focus:ring-2 focus:ring-amber-400"
                                rows={3}
                                disabled={isSubmittingApproval}
                              />
                              <div className="flex gap-2">
                                <Button
                                  variant="primary"
                                  onClick={() =>
                                    handleApprovalDecision("approved")
                                  }
                                  disabled={isSubmittingApproval}
                                >
                                  {isSubmittingApproval
                                    ? "Submitting..."
                                    : "Approve and Resume"}
                                </Button>
                                <Button
                                  variant="outline"
                                  onClick={() =>
                                    handleApprovalDecision("rejected")
                                  }
                                  disabled={isSubmittingApproval}
                                >
                                  Reject
                                </Button>
                              </div>
                            </div>
                          </>
                        )}
                      </div>
                    )}
                    {displayRows.length === 0 ? (
                      <div className="text-redis-sm text-redis-dusk-04">
                        No messages yet for this conversation.
                      </div>
                    ) : (
                      displayRows.map((row) => {
                        if (row.kind === "tool-calls") {
                          return (
                            <div key={row.id} className="flex justify-start">
                              <ToolCallsAccordion toolCalls={row.toolCalls} />
                            </div>
                          );
                        }

                        const msg = row.message;
                        return (
                          <div
                            key={msg.id}
                            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                          >
                            {msg.role === "system" &&
                            isCitationMessage(msg.content) ? (
                              // Citation accordion
                              <details
                                data-testid="citation-accordion"
                                open={expandedCitations.has(msg.id)}
                                onToggle={(event) => {
                                  const isExpanded = event.currentTarget.open;
                                  setExpandedCitations((prev) => {
                                    const next = new Set(prev);
                                    if (isExpanded) {
                                      next.add(msg.id);
                                    } else {
                                      next.delete(msg.id);
                                    }
                                    return next;
                                  });
                                }}
                                className="citation-accordion w-full max-w-3xl overflow-hidden rounded-redis-sm text-redis-sm"
                                title={new Date(msg.timestamp).toLocaleString()}
                              >
                                <summary className="citation-accordion-summary group flex cursor-pointer items-center gap-2 px-3 py-2 text-left font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-redis-blue-03">
                                  <span
                                    aria-hidden="true"
                                    className="flex h-3 w-3 flex-shrink-0 items-center justify-center transition-colors"
                                  >
                                    <span
                                      className={`h-1.5 w-1.5 border-b border-r border-current transition-transform ${expandedCitations.has(msg.id) ? "translate-y-[-1px] rotate-45" : "-rotate-45"}`}
                                    />
                                  </span>
                                  <span>{citationHeading(msg.content)}</span>
                                </summary>
                                {expandedCitations.has(msg.id) && (
                                  <div className="citation-accordion-body px-3 py-2 pl-8">
                                    {(() => {
                                      const citationItems =
                                        getCitationItems(msg);
                                      if (citationItems.length === 0) {
                                        return (
                                          <div className="markdown-content">
                                            <MarkdownRenderer
                                              content={citationBody(
                                                msg.content,
                                              )}
                                            />
                                          </div>
                                        );
                                      }

                                      return (
                                        <ul className="citation-link-list">
                                          {citationItems.map((item) => (
                                            <li key={item.key}>
                                              {item.to ? (
                                                <Link to={item.to}>
                                                  {item.title}
                                                </Link>
                                              ) : (
                                                <span>{item.title}</span>
                                              )}
                                            </li>
                                          ))}
                                        </ul>
                                      );
                                    })()}
                                  </div>
                                )}
                              </details>
                            ) : (
                              <div
                                className={`${
                                  msg.role === "assistant"
                                    ? "w-full max-w-3xl"
                                    : "max-w-[80%]"
                                } rounded-redis-md px-3 py-2 break-words ${
                                  msg.role === "user"
                                    ? "bg-redis-blue-03 text-white text-redis-sm"
                                    : msg.role === "assistant"
                                      ? "bg-redis-dusk-09 text-foreground"
                                      : msg.role === "tool"
                                        ? "bg-amber-50 text-amber-900 border border-amber-200 text-redis-sm"
                                        : "bg-redis-dusk-09 text-redis-dusk-03 text-redis-sm"
                                }`}
                                title={new Date(msg.timestamp).toLocaleString()}
                              >
                                {msg.role === "assistant" ? (
                                  <MarkdownRenderer
                                    content={msg.content}
                                    className="text-redis-sm"
                                  />
                                ) : (
                                  <div className="text-redis-sm whitespace-pre-wrap">
                                    {msg.content}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })
                    )}
                    {!isThreadBusy &&
                      !showWebSocketMonitor &&
                      activeTaskId &&
                      messages.some((m) => m.role === "assistant") && (
                        <div className="flex justify-start pl-0">
                          <FeedbackButtons
                            taskId={activeTaskId}
                            initialVerdict={threadFeedback?.verdict ?? null}
                            onError={(msg) => setError(msg)}
                          />
                        </div>
                      )}
                    {isThreadBusy && (
                      <div className="text-redis-xs text-redis-dusk-04">
                        Task is running. Press Stop to cancel before sending a
                        new message.
                      </div>
                    )}
                    <div ref={messagesEndRef} />
                  </div>
                </CardContent>

                {/* Input Area for Follow-up Messages */}
                <div className="p-4 border-t border-redis-dusk-08">
                  <div className="flex gap-2">
                    <textarea
                      value={inputMessage}
                      onChange={(e) => setInputMessage(e.target.value)}
                      onKeyDown={handleComposerKeyDown}
                      placeholder={
                        approvalBlocked
                          ? "Approval required before this conversation can continue"
                          : "Continue the conversation..."
                      }
                      className="flex-1 p-3 border border-redis-dusk-06 rounded-redis-sm resize-none focus:outline-none focus:ring-2 focus:ring-redis-blue-03 focus:border-transparent min-h-[60px]"
                      rows={2}
                      disabled={
                        isLoading ||
                        agentStatus !== "available" ||
                        approvalBlocked
                      }
                    />
                    {isThreadBusy ? (
                      <Button
                        variant="destructive"
                        onClick={handleStop}
                        className="self-end"
                      >
                        Stop
                      </Button>
                    ) : approvalBlocked ? (
                      <Button variant="outline" disabled className="self-end">
                        Use Approval Controls Above
                      </Button>
                    ) : (
                      <Button
                        variant="primary"
                        onClick={sendMessage}
                        disabled={
                          !inputMessage.trim() ||
                          isLoading ||
                          agentStatus !== "available"
                        }
                        className="self-end"
                      >
                        {isLoading ? <Loader size="sm" /> : "Send"}
                      </Button>
                    )}
                  </div>
                  <div className="text-redis-xs text-redis-dusk-04 mt-2">
                    {approvalBlocked
                      ? "This task is paused for approval. Use the approval controls above to approve or reject it."
                      : isThreadBusy
                        ? "Task is running — press Stop to cancel before sending a new message."
                        : agentStatus === "available"
                          ? "Press Enter to send, Shift+Enter for new line"
                          : "Agent is currently unavailable"}
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
                      <div className="text-sm">
                        Select a conversation or start a new one
                      </div>
                    </div>
                  </div>
                </CardContent>

                {/* Input Area */}
                <div className="p-4 border-t border-redis-dusk-08">
                  <div className="flex gap-2">
                    <textarea
                      ref={newConversationInputRef}
                      value={inputMessage}
                      onChange={(e) => setInputMessage(e.target.value)}
                      onKeyDown={handleComposerKeyDown}
                      placeholder="Describe your Redis issue or ask a question..."
                      className="flex-1 p-3 border border-redis-dusk-06 rounded-redis-sm resize-none focus:outline-none focus:ring-2 focus:ring-redis-blue-03 focus:border-transparent min-h-[80px] lg:min-h-[60px]"
                      rows={window.innerWidth < 1024 ? 2 : 3}
                      disabled={isLoading || agentStatus !== "available"}
                    />
                    <Button
                      variant="primary"
                      onClick={sendMessage}
                      disabled={
                        !inputMessage.trim() ||
                        isLoading ||
                        agentStatus !== "available"
                      }
                      className="self-end"
                    >
                      {isLoading ? <Loader size="sm" /> : "Send"}
                    </Button>
                  </div>
                  {targetSelectionAccordion}
                  <div className="text-redis-xs text-redis-dusk-04 mt-2">
                    {agentStatus === "available"
                      ? "Press Enter to send, Shift+Enter for new line"
                      : agentStatus === "unavailable"
                        ? "SRE Agent is currently offline. Please check the backend service."
                        : "Checking agent status..."}
                  </div>
                </div>
              </>
            )}
          </Card>
        </div>

        {/* Session Details Panel - right rail */}
        {activeThreadId && showSessionDetailsPanel && (
          <div
            data-testid="session-details-panel"
            className="flex w-full md:w-96 md:min-w-96 md:max-w-96 flex-col h-full"
          >
            <SessionDetailsPanel
              thread={activeThread}
              threadId={activeThreadId}
              taskId={activeTaskId}
              status={activeThreadStatus}
              isThreadBusy={isThreadBusy}
              pendingApproval={pendingApproval}
              feedback={threadFeedback}
              toolCallCount={loadedToolCallCount}
              onClose={() => setShowSessionDetailsPanel(false)}
            />
          </div>
        )}

        {/* Memory Panel - right rail */}
        {activeThreadId && showMemoryPanel && (
          <div className="flex w-full md:w-96 md:min-w-96 md:max-w-96 flex-col h-full">
            <MemoryPanel
              threadId={activeThreadId}
              onClose={() => setShowMemoryPanel(false)}
              refreshKey={memoryRefreshKey}
            />
          </div>
        )}
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
