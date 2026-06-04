import { useEffect, useMemo, useState } from "react";
import {
  Link,
  useLocation,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { Button, Card, CardContent, CardHeader } from "@radar/ui-kit";
import MarkdownRenderer from "../components/MarkdownRenderer";
import sreAgentApi, {
  KnowledgeDocumentChunk,
  KnowledgeDocumentChunksResponse,
} from "../services/sreAgentApi";

const metadataLabels: Record<string, string> = {
  document_hash: "Document Hash",
  title: "Title",
  name: "Name",
  source: "Source",
  category: "Category",
  doc_type: "Document Type",
  version: "Version",
  priority: "Priority",
  pinned: "Pinned",
  source_pack: "Source Pack",
  source_pack_version: "Source Pack Version",
  source_document_path: "Source Path",
  product_labels: "Product Labels",
  chunk_id: "Chunk ID",
  chunk_index: "Chunk Index",
  total_chunks: "Total Chunks",
};

const getChunkVersion = (chunk?: KnowledgeDocumentChunk) => {
  return typeof chunk?.version === "string" && chunk.version.trim()
    ? chunk.version
    : undefined;
};

const formatMetadataValue = (value: unknown): string => {
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (value == null || value === "") return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
};

const getChunkAnchorId = (chunkIndex: unknown) => {
  const value = String(chunkIndex ?? "").trim();
  return value ? `chunk-${value}` : undefined;
};

const getChunkIndexFromHash = (hash: string) => {
  const match = hash.match(/^#chunk-(.+)$/);
  if (!match) return undefined;

  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
};

const KnowledgeDocumentChunks = () => {
  const { documentHash } = useParams();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [documentChunks, setDocumentChunks] =
    useState<KnowledgeDocumentChunksResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const version = searchParams.get("version") || undefined;
  const indexType = searchParams.get("index_type") || "knowledge";
  const targetChunkIndex =
    searchParams.get("chunk") ||
    getChunkIndexFromHash(location.hash) ||
    undefined;

  useEffect(() => {
    const loadDocumentChunks = async () => {
      if (!documentHash) {
        setError("Missing document hash.");
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      setError("");
      try {
        const result = await sreAgentApi.getKnowledgeDocumentChunks(
          documentHash,
          {
            version,
            indexType,
          },
        );
        setDocumentChunks(result);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Failed to load knowledge document chunks.",
        );
      } finally {
        setIsLoading(false);
      }
    };

    loadDocumentChunks();
  }, [documentHash, indexType, version]);

  const chunks = useMemo(() => {
    return [...(documentChunks?.chunks || [])].sort((a, b) => {
      const left = Number(a.chunk_index ?? 0);
      const right = Number(b.chunk_index ?? 0);
      return left - right;
    });
  }, [documentChunks]);

  const hasRenderableChunks = useMemo(() => {
    return chunks.some((chunk) => Boolean(chunk.content?.trim()));
  }, [chunks]);

  useEffect(() => {
    if (isLoading || !targetChunkIndex) return;

    const targetId = getChunkAnchorId(targetChunkIndex);
    if (!targetId) return;

    window.setTimeout(() => {
      document.getElementById(targetId)?.scrollIntoView({
        block: "start",
        behavior: "smooth",
      });
    }, 0);
  }, [chunks.length, isLoading, targetChunkIndex]);

  const metadataRows = useMemo(() => {
    if (!documentChunks) return [];
    const sample = chunks[0];
    const metadata = documentChunks.metadata || {};
    const values: Record<string, unknown> = {
      title: documentChunks.title || sample?.title,
      name: documentChunks.name,
      document_hash: documentChunks.document_hash,
      total_chunks: sample?.total_chunks ?? documentChunks.chunk_count,
      source: documentChunks.source || sample?.source,
      category: documentChunks.category || sample?.category,
      doc_type: documentChunks.doc_type || sample?.doc_type,
      version: version || getChunkVersion(sample),
      priority: documentChunks.priority,
      pinned: documentChunks.pinned,
      source_pack: metadata.source_pack,
      source_pack_version: metadata.source_pack_version,
      source_document_path: metadata.source_document_path,
      product_labels: metadata.product_labels,
    };

    return Object.entries(values)
      .map(([key, value]) => ({
        key,
        label: metadataLabels[key] || key,
        value: formatMetadataValue(value),
      }))
      .filter((row) => row.value);
  }, [documentChunks, chunks, version]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-redis-blue-03 mx-auto"></div>
          <p className="mt-2 text-redis-dusk-04">Loading document chunks...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="text-redis-sm text-redis-red mb-4">{error}</div>
          <Link to="/knowledge">
            <Button variant="outline">Back to Knowledge</Button>
          </Link>
        </CardContent>
      </Card>
    );
  }

  if (!documentChunks) return null;

  const title =
    documentChunks.title ||
    documentChunks.name ||
    chunks[0]?.title ||
    `Document chunks ${documentChunks.document_hash}`;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <Link
            to="/knowledge"
            className="text-redis-sm text-redis-blue-03 hover:underline"
          >
            Back to Knowledge
          </Link>
          <h1 className="text-redis-xl font-bold text-foreground mt-2 truncate">
            {title}
          </h1>
          {documentChunks.summary && (
            <p className="text-redis-sm text-redis-dusk-04 mt-1">
              {documentChunks.summary}
            </p>
          )}
          <p className="text-redis-sm text-redis-dusk-04 mt-2">
            This page assembles indexed chunks that share the same document
            hash. It is not the original source document body.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <h2 className="text-redis-lg font-semibold text-foreground">
            Document Chunks Metadata
          </h2>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-redis-sm">
              <tbody>
                {metadataRows.map((row) => (
                  <tr key={row.key} className="border-t border-redis-dusk-08">
                    <th className="w-48 py-2 pr-4 font-medium text-redis-dusk-04">
                      {row.label}
                    </th>
                    <td className="py-2 text-foreground break-all">
                      {row.value}
                    </td>
                  </tr>
                ))}
                <tr className="border-t border-redis-dusk-08">
                  <th className="w-48 py-2 pr-4 font-medium text-redis-dusk-04">
                    Chunks
                  </th>
                  <td className="py-2 text-foreground">
                    {documentChunks.chunk_count ?? chunks.length}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-redis-lg font-semibold text-foreground">
            Assembled Document
          </h2>
        </CardHeader>
        <CardContent>
          {hasRenderableChunks ? (
            <div className="space-y-8">
              {chunks.map((chunk) => {
                const chunkIndex = String(chunk.chunk_index ?? "").trim();
                const anchorId = getChunkAnchorId(chunkIndex);
                const isTargetChunk =
                  Boolean(targetChunkIndex) && chunkIndex === targetChunkIndex;

                return (
                  <section
                    key={`${documentChunks.document_hash}-${chunkIndex || "unknown"}`}
                    className={`scroll-mt-24 border-t border-redis-dusk-08 pt-6 first:border-t-0 first:pt-0 ${
                      isTargetChunk
                        ? "rounded-redis-sm bg-redis-dusk-09 p-3"
                        : ""
                    }`}
                  >
                    <h3
                      id={anchorId}
                      className="scroll-mt-24 text-redis-md font-semibold text-foreground"
                    >
                      {anchorId ? (
                        <a
                          href={`#${anchorId}`}
                          className="hover:text-redis-blue-03 hover:underline"
                        >
                          Chunk {chunkIndex}
                        </a>
                      ) : (
                        "Chunk"
                      )}
                    </h3>
                    {chunk.content?.trim() ? (
                      <MarkdownRenderer
                        content={chunk.content}
                        className="mt-3"
                      />
                    ) : (
                      <p className="mt-3 text-redis-sm text-redis-dusk-04">
                        This chunk has no renderable content.
                      </p>
                    )}
                  </section>
                );
              })}
            </div>
          ) : (
            <p className="text-redis-sm text-redis-dusk-04">
              These document chunks have no renderable content.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default KnowledgeDocumentChunks;
