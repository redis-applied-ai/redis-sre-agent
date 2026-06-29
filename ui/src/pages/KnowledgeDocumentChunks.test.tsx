import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getKnowledgeDocumentChunks: vi.fn(),
}));

vi.mock("../services/sreAgentApi", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../services/sreAgentApi")>();
  return {
    ...actual,
    default: {
      ...actual.default,
      getKnowledgeDocumentChunks: mocks.getKnowledgeDocumentChunks,
    },
  };
});

vi.mock("../components/MarkdownRenderer", () => ({
  default: ({ content }: { content: string }) => (
    <div data-testid="markdown">{content}</div>
  ),
}));

import KnowledgeDocumentChunks from "./KnowledgeDocumentChunks";

const renderDocumentChunksRoute = (initialEntry: string) => {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route
          path="/knowledge/document-chunks/:documentHash"
          element={<KnowledgeDocumentChunks />}
        />
      </Routes>
    </MemoryRouter>,
  );
};

describe("KnowledgeDocumentChunks", () => {
  beforeEach(() => {
    mocks.getKnowledgeDocumentChunks.mockReset();
    Object.defineProperty(window.HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(),
    });
  });

  it("sorts chunks, renders metadata, and shows empty chunk fallback", async () => {
    mocks.getKnowledgeDocumentChunks.mockResolvedValueOnce({
      document_hash: "doc-123",
      index_type: "knowledge",
      chunk_count: 3,
      title: "Memory Runbook",
      metadata: { source_document_path: "shared/memory.md" },
      chunks: [
        {
          chunk_index: 2,
          content: "## Final step",
          title: "Memory Runbook",
          total_chunks: 3,
          version: "8.0",
        },
        {
          chunk_index: 0,
          content: "Initial checks",
          title: "Memory Runbook",
          total_chunks: 3,
          version: "8.0",
        },
        {
          chunk_index: 1,
          content: "   ",
          title: "Memory Runbook",
          total_chunks: 3,
          version: "8.0",
        },
      ],
    });

    renderDocumentChunksRoute(
      "/knowledge/document-chunks/doc-123?version=8.0&index_type=knowledge#chunk-2",
    );

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Memory Runbook" }),
      ).toBeInTheDocument();
    });

    expect(mocks.getKnowledgeDocumentChunks).toHaveBeenCalledWith("doc-123", {
      version: "8.0",
      indexType: "knowledge",
    });
    expect(screen.getByText("shared/memory.md")).toBeInTheDocument();
    expect(
      screen
        .getAllByRole("link", { name: /Chunk \d/ })
        .map((link) => link.textContent),
    ).toEqual(["Chunk 0", "Chunk 1", "Chunk 2"]);
    expect(
      screen.getByText("This chunk has no renderable content."),
    ).toBeInTheDocument();
    expect(screen.getByText("Initial checks")).toBeInTheDocument();
    expect(screen.getByText("## Final step")).toBeInTheDocument();
  });
});
