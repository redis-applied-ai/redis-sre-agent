import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getKnowledgeStats: vi.fn(),
  getKnowledgeJobs: vi.fn(),
  searchKnowledge: vi.fn(),
  ingestDocument: vi.fn(),
}));

vi.mock("../services/sreAgentApi", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../services/sreAgentApi")>();
  return {
    ...actual,
    sreAgentApi: {
      ...actual.sreAgentApi,
      getKnowledgeStats: mocks.getKnowledgeStats,
      getKnowledgeJobs: mocks.getKnowledgeJobs,
      searchKnowledge: mocks.searchKnowledge,
      ingestDocument: mocks.ingestDocument,
    },
  };
});

vi.mock("../components/MarkdownRenderer", () => ({
  default: ({ content }: { content: string }) => (
    <div data-testid="markdown">{content}</div>
  ),
}));

import Knowledge from "./Knowledge";

const stats = {
  total_documents: 2,
  total_chunks: 4,
  last_ingestion: null,
  ingestion_status: "idle",
  document_types: { runbook: 2 },
  storage_size_mb: 0.2,
};

const renderKnowledgeRoute = (initialEntry = "/knowledge") => {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/knowledge" element={<Knowledge />} />
      </Routes>
    </MemoryRouter>,
  );
};

describe("Knowledge", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getKnowledgeStats.mockResolvedValue(stats);
    mocks.getKnowledgeJobs.mockResolvedValue({ jobs: [] });
  });

  it("searches with category filters and renders source/version chunk links", async () => {
    const user = userEvent.setup();
    mocks.searchKnowledge.mockResolvedValueOnce({
      results: [
        {
          id: "fragment-1",
          document_hash: "doc-1",
          chunk_index: 1,
          title: "Memory Tuning Guide",
          content: "Use maxmemory with an eviction policy.",
          source: "redis-docs",
          category: "performance",
          doc_type: "runbook",
          version: "8.0",
          summary: "Memory pressure guidance.",
        },
      ],
    });

    renderKnowledgeRoute();

    await screen.findByRole("heading", { name: "Knowledge Base" });
    await user.type(
      screen.getByPlaceholderText("Search knowledge base..."),
      "maxmemory",
    );
    await user.selectOptions(screen.getByRole("combobox"), "performance");
    await user.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => {
      expect(mocks.searchKnowledge).toHaveBeenCalledWith(
        "maxmemory",
        10,
        "performance",
      );
    });
    expect(screen.getByText('Found 1 results for "maxmemory"')).toBeVisible();
    expect(screen.getByText("Memory Tuning Guide")).toBeVisible();
    expect(screen.getByText("Source: redis-docs")).toBeVisible();
    expect(screen.getByText("8.0")).toBeVisible();
    expect(screen.getByRole("link", { name: "Open document" })).toHaveAttribute(
      "href",
      "/knowledge/document-chunks/doc-1?version=8.0#chunk-1",
    );
  });

  it("shows empty search results", async () => {
    const user = userEvent.setup();
    mocks.searchKnowledge.mockResolvedValueOnce({ results: [] });

    renderKnowledgeRoute();

    await screen.findByRole("heading", { name: "Knowledge Base" });
    await user.type(
      screen.getByPlaceholderText("Search knowledge base..."),
      "missing exact runbook",
    );
    await user.click(screen.getByRole("button", { name: "Search" }));

    await screen.findByText('No results found for "missing exact runbook"');
  });

  it("shows search errors from the API", async () => {
    const user = userEvent.setup();
    mocks.searchKnowledge.mockRejectedValueOnce(
      new Error("Embedding provider unavailable for general semantic search"),
    );

    renderKnowledgeRoute();

    await screen.findByRole("heading", { name: "Knowledge Base" });
    await user.type(
      screen.getByPlaceholderText("Search knowledge base..."),
      "how do I tune memory",
    );
    await user.click(screen.getByRole("button", { name: "Search" }));

    await screen.findByText("Knowledge Base Error");
    expect(
      screen.getByText(
        "Embedding provider unavailable for general semantic search",
      ),
    ).toBeVisible();
  });
});
