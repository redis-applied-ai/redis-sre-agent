import { SREAgentAPI } from "./sreAgentApi";

describe("SREAgentAPI UI enhancement calls", () => {
  beforeEach(() => {
    global.fetch = vi.fn();
  });

  it("passes cluster_id when starting a cluster-scoped conversation", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        thread_id: "thread-1",
        status: "queued",
        message: "queued",
      }),
    });

    const api = new SREAgentAPI("http://localhost:8080/api/v1");
    const threadId = await api.startNewConversation(
      "inspect cluster",
      "user-1",
      0,
      ["triage"],
      undefined,
      "cluster-1",
    );

    expect(threadId).toBe("thread-1");
    const request = (fetch as unknown as ReturnType<typeof vi.fn>).mock
      .calls[0];
    expect(request[0]).toBe("http://localhost:8080/api/v1/tasks");
    expect(JSON.parse(request[1].body)).toEqual({
      message: "inspect cluster",
      context: {
        user_id: "user-1",
        priority: 0,
        tags: ["triage"],
        cluster_id: "cluster-1",
      },
    });
  });

  it("loads knowledge document chunks from a document hash", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        document_hash: "hash/with space",
        chunk_count: 1,
        chunks: [{ content: "chunk" }],
      }),
    });

    const api = new SREAgentAPI("http://localhost:8080/api/v1");
    const result = await api.getKnowledgeDocumentChunks("hash/with space", {
      version: "8.0",
      includeMetadata: true,
    });

    expect(result.document_hash).toBe("hash/with space");
    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8080/api/v1/knowledge/document-chunks/hash%2Fwith%20space?include_metadata=true&version=8.0",
    );
  });

  it("preserves citation metadata when loading a transcript", async () => {
    const citationMetadata = {
      timestamp: "2026-06-04T18:00:00Z",
      metadata: {
        message_type: "citations",
        citations: [
          {
            title: "Memory Tuning Guide",
            document_hash: "doc-1",
            chunk_index: 0,
          },
        ],
      },
    };

    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        thread_id: "thread-1",
        status: "done",
        messages: [
          {
            role: "system",
            content: "**Discovered context**",
            metadata: citationMetadata,
          },
        ],
        updates: [],
        metadata: {
          created_at: "2026-06-04T18:00:00Z",
          updated_at: "2026-06-04T18:00:00Z",
          priority: 0,
          tags: [],
        },
        context: {},
        resume_supported: false,
      }),
    });

    const api = new SREAgentAPI("http://localhost:8080/api/v1");
    const transcript = await api.getTranscript("thread-1");

    expect(transcript[0].metadata).toEqual(citationMetadata);
  });
});
