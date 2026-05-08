import { useEffect, useState } from "react";
import { Card, CardHeader, CardContent, Button } from "@radar/ui-kit";
import sreAgentApi, {
  ThreadMemoryItem,
  ThreadMemoryResponse,
  ThreadMemorySection,
} from "../services/sreAgentApi";

interface MemoryPanelProps {
  threadId: string | null;
  onClose: () => void;
  refreshKey?: number | string;
}

const PAGE_SIZE = 50;

const formatDate = (iso: string | null): string => {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString([], {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
};

const MemoryItem = ({ item }: { item: ThreadMemoryItem }) => {
  const tags = [...item.topics, ...item.entities];
  return (
    <li className="border border-redis-dusk-08 rounded-md p-3 bg-redis-dusk-09">
      <p className="text-redis-sm text-foreground whitespace-pre-wrap break-words">
        {item.text || <span className="italic text-redis-dusk-04">(empty)</span>}
      </p>
      <div className="flex flex-wrap items-center gap-2 mt-2 text-redis-xs text-redis-dusk-04">
        {item.created_at && <span>{formatDate(item.created_at)}</span>}
        {tags.length > 0 && (
          <>
            {item.created_at && <span>·</span>}
            <span className="flex flex-wrap gap-1">
              {tags.slice(0, 6).map((tag, idx) => (
                <span
                  key={`${tag}-${idx}`}
                  className="px-1.5 py-0.5 rounded bg-redis-dusk-08 text-redis-dusk-03"
                >
                  {tag}
                </span>
              ))}
            </span>
          </>
        )}
      </div>
    </li>
  );
};

interface SectionViewProps {
  label: string;
  count: number;
  section: ThreadMemorySection | null;
  loadingMore: boolean;
  onLoadMore: () => void;
}

const SectionView = ({
  label,
  count,
  section,
  loadingMore,
  onLoadMore,
}: SectionViewProps) => {
  const [expanded, setExpanded] = useState(true);

  if (!section) {
    return null;
  }
  const items = section.long_term.items;
  const hasMore = section.long_term.next_offset != null;

  return (
    <div className="border-b border-redis-dusk-08 last:border-b-0">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-redis-dusk-09"
      >
        <span className="text-redis-sm font-semibold text-foreground">
          {label}
        </span>
        <span className="flex items-center gap-2 text-redis-xs text-redis-dusk-04">
          <span>
            {count} {count === 1 ? "memory" : "memories"}
          </span>
          <span
            className={`transform transition-transform ${expanded ? "rotate-180" : ""}`}
          >
            ▼
          </span>
        </span>
      </button>
      {expanded && (
        <div className="px-4 pb-4 space-y-3">
          {section.working_memory_context && (
            <div className="text-redis-xs">
              <p className="font-medium text-redis-dusk-03 mb-1">
                Working context
              </p>
              <p className="text-redis-dusk-04 whitespace-pre-wrap bg-redis-dusk-09 border border-redis-dusk-08 rounded-md p-2">
                {section.working_memory_context}
              </p>
            </div>
          )}
          {items.length === 0 ? (
            <p className="text-redis-xs text-redis-dusk-04 italic">
              No memories yet for this scope. Memories are extracted as
              conversations conclude.
            </p>
          ) : (
            <ul className="space-y-2">
              {items.map((item, idx) => (
                <MemoryItem key={item.id ?? idx} item={item} />
              ))}
            </ul>
          )}
          {hasMore && (
            <Button
              variant="outline"
              size="sm"
              onClick={onLoadMore}
              disabled={loadingMore}
            >
              {loadingMore ? "Loading…" : "Load more"}
            </Button>
          )}
        </div>
      )}
    </div>
  );
};

const MemoryPanel = ({ threadId, onClose, refreshKey }: MemoryPanelProps) => {
  const [data, setData] = useState<ThreadMemoryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMoreUser, setLoadingMoreUser] = useState(false);
  const [loadingMoreAsset, setLoadingMoreAsset] = useState(false);

  useEffect(() => {
    if (!threadId) {
      setData(null);
      return;
    }
    let cancelled = false;
    const fetchInitial = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await sreAgentApi.getThreadMemory(threadId, {
          userLimit: PAGE_SIZE,
          userOffset: 0,
          assetLimit: PAGE_SIZE,
          assetOffset: 0,
        });
        if (!cancelled) setData(response);
      } catch (err: any) {
        if (!cancelled) setError(err?.message ?? "Failed to load memory");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchInitial();
    return () => {
      cancelled = true;
    };
  }, [threadId, refreshKey]);

  const loadMoreUser = async () => {
    if (!threadId || !data?.user_scope) return;
    const offset = data.user_scope.long_term.next_offset;
    if (offset == null) return;
    setLoadingMoreUser(true);
    try {
      const next = await sreAgentApi.getThreadMemory(threadId, {
        userLimit: PAGE_SIZE,
        userOffset: offset,
        assetLimit: 0,
        assetOffset: 0,
      });
      setData((prev) => {
        if (!prev || !prev.user_scope || !next.user_scope) return prev;
        return {
          ...prev,
          user_scope: {
            ...prev.user_scope,
            long_term: {
              items: [
                ...prev.user_scope.long_term.items,
                ...next.user_scope.long_term.items,
              ],
              total: next.user_scope.long_term.total,
              next_offset: next.user_scope.long_term.next_offset,
            },
          },
        };
      });
    } catch (err: any) {
      setError(err?.message ?? "Failed to load more memories");
    } finally {
      setLoadingMoreUser(false);
    }
  };

  const loadMoreAsset = async () => {
    if (!threadId || !data?.asset_scope) return;
    const offset = data.asset_scope.long_term.next_offset;
    if (offset == null) return;
    setLoadingMoreAsset(true);
    try {
      const next = await sreAgentApi.getThreadMemory(threadId, {
        userLimit: 0,
        userOffset: 0,
        assetLimit: PAGE_SIZE,
        assetOffset: offset,
      });
      setData((prev) => {
        if (!prev || !prev.asset_scope || !next.asset_scope) return prev;
        return {
          ...prev,
          asset_scope: {
            ...prev.asset_scope,
            long_term: {
              items: [
                ...prev.asset_scope.long_term.items,
                ...next.asset_scope.long_term.items,
              ],
              total: next.asset_scope.long_term.total,
              next_offset: next.asset_scope.long_term.next_offset,
            },
          },
        };
      });
    } catch (err: any) {
      setError(err?.message ?? "Failed to load more memories");
    } finally {
      setLoadingMoreAsset(false);
    }
  };

  const renderBody = () => {
    if (!threadId) {
      return (
        <p className="text-redis-sm text-redis-dusk-04 p-4">
          Select a conversation to view its memory.
        </p>
      );
    }
    if (loading && !data) {
      return (
        <p className="text-redis-sm text-redis-dusk-04 p-4">Loading memory…</p>
      );
    }
    if (error) {
      return (
        <div className="p-4">
          <p className="text-redis-sm text-redis-red">
            Failed to load memory: {error}
          </p>
        </div>
      );
    }
    if (!data) {
      return null;
    }
    if (!data.enabled) {
      return (
        <div className="p-4">
          <p className="text-redis-sm text-redis-dusk-04">
            Agent Memory Server is not configured. Set{" "}
            <code className="bg-redis-dusk-08 px-1 py-0.5 rounded">
              AGENT_MEMORY_ENABLED
            </code>{" "}
            and{" "}
            <code className="bg-redis-dusk-08 px-1 py-0.5 rounded">
              AGENT_MEMORY_BASE_URL
            </code>{" "}
            to enable.
          </p>
        </div>
      );
    }
    if (data.status === "missing_scope") {
      return (
        <p className="text-redis-sm text-redis-dusk-04 p-4">
          This thread has no user or asset scope, so no memory is associated
          with it.
        </p>
      );
    }
    if (data.status === "error") {
      return (
        <div className="p-4">
          <p className="text-redis-sm text-redis-red">
            Memory server unreachable: {data.error}
          </p>
          <p className="text-redis-xs text-redis-dusk-04 mt-2">
            The agent continues to function without memory.
          </p>
        </div>
      );
    }

    const userTotal = data.user_scope?.long_term.total ?? 0;
    const assetTotal = data.asset_scope?.long_term.total ?? 0;
    const scopeBits: string[] = [];
    if (data.scope.user_id) scopeBits.push(`user · ${data.scope.user_id}`);
    if (data.scope.instance_id)
      scopeBits.push(`instance · ${data.scope.instance_id}`);
    if (data.scope.cluster_id)
      scopeBits.push(`cluster · ${data.scope.cluster_id}`);

    return (
      <>
        {scopeBits.length > 0 && (
          <div className="px-4 py-3 border-b border-redis-dusk-08 bg-redis-dusk-09">
            <p className="text-redis-xs uppercase tracking-wide text-redis-dusk-04 mb-1">
              Scope
            </p>
            <div className="flex flex-col gap-0.5 text-redis-xs text-foreground">
              {scopeBits.map((bit) => (
                <span key={bit}>{bit}</span>
              ))}
            </div>
          </div>
        )}
        {data.user_scope && (
          <SectionView
            label="User-scoped memory"
            count={userTotal}
            section={data.user_scope}
            loadingMore={loadingMoreUser}
            onLoadMore={loadMoreUser}
          />
        )}
        {data.asset_scope && (
          <SectionView
            label="Asset-scoped memory"
            count={assetTotal}
            section={data.asset_scope}
            loadingMore={loadingMoreAsset}
            onLoadMore={loadMoreAsset}
          />
        )}
      </>
    );
  };

  return (
    <Card className="flex-1 flex flex-col h-full" padding="none">
      <CardHeader className="flex-shrink-0 p-4 pb-3 border-b border-redis-dusk-08">
        <div className="flex items-center justify-between">
          <h3 className="text-redis-lg font-semibold text-foreground">
            Memory
          </h3>
          <Button variant="outline" size="sm" onClick={onClose}>
            ✕
          </Button>
        </div>
      </CardHeader>
      <CardContent className="flex-1 overflow-y-auto p-0">
        {renderBody()}
      </CardContent>
    </Card>
  );
};

export default MemoryPanel;
