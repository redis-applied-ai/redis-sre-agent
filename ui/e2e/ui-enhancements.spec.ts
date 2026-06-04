import { expect, test, type Page } from "@playwright/test";

const now = "2026-06-03T17:00:00Z";

const instance = {
  id: "instance-1",
  name: "Cache Primary",
  connection_url: "redis://cache.example.com:6379",
  environment: "production",
  usage: "cache",
  description: "Primary cache",
  created_at: now,
  updated_at: now,
};

const cluster = {
  id: "cluster-1",
  name: "Prod RE Cluster",
  cluster_type: "redis_enterprise",
  environment: "production",
  description: "Production Redis Enterprise cluster",
  admin_url: "https://prod-re.example.com:9443",
  version: "7.22",
  created_at: now,
  updated_at: now,
};

const knowledgeStats = {
  total_documents: 1,
  total_chunks: 2,
  last_ingestion: null,
  ingestion_status: "idle",
  document_types: { runbook: 1 },
  storage_size_mb: 0.01,
};

const knowledgeResult = {
  id: "fragment-1",
  document_hash: "doc-1",
  chunk_index: 0,
  title: "Memory Tuning Guide",
  content: "### Fragment\n\nUse **maxmemory** to cap memory usage.",
  source: "redis-docs",
  category: "performance",
  doc_type: "runbook",
  version: "8.0",
  summary: "Tuning memory pressure in Redis.",
};

interface MockApiOptions {
  threads?: unknown[];
  threadResponses?: Record<string, unknown>;
  knowledgeSearchDelayMs?: number;
}

const delay = (ms: number) =>
  new Promise((resolve) => {
    setTimeout(resolve, ms);
  });

async function mockApi(page: Page, options: MockApiOptions = {}) {
  const clusters = [cluster];
  const threadResponses: Record<string, unknown> = {
    "thread-cluster": {
      thread_id: "thread-cluster",
      status: "queued",
      messages: [],
      updates: [],
      result: null,
      metadata: {
        created_at: now,
        updated_at: now,
        priority: 0,
        tags: [],
        subject: "inspect cluster",
      },
      context: { original_query: "inspect cluster", cluster_id: "cluster-1" },
      resume_supported: false,
    },
    ...(options.threadResponses || {}),
  };
  let latestTaskBody: unknown = null;
  const knowledgeSearchQueries: string[] = [];

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    const json = async (body: unknown, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });

    if (method === "GET" && path === "/api/v1/health") {
      return json({
        status: "healthy",
        components: {
          redis_connection: "available",
          vectorizer: "available",
          vector_search: "available",
          task_system: "available",
          workers: "available",
        },
        version: "test",
        timestamp: now,
      });
    }

    if (method === "GET" && path === "/api/v1/threads") {
      return json(options.threads || []);
    }

    if (method === "GET" && path.startsWith("/api/v1/threads/")) {
      const threadId = path.split("/").pop() || "";
      if (threadResponses[threadId]) {
        return json(threadResponses[threadId]);
      }
      return json({ error: "Thread not found" }, 404);
    }

    if (method === "GET" && path === "/api/v1/instances") {
      return json({ instances: [instance], total: 1, limit: 1000, offset: 0 });
    }

    if (method === "GET" && path === "/api/v1/clusters") {
      return json({
        clusters,
        total: clusters.length,
        limit: 1000,
        offset: 0,
      });
    }

    if (method === "POST" && path === "/api/v1/clusters") {
      const body = await request.postDataJSON();
      clusters.unshift({
        ...cluster,
        ...body,
        id: "cluster-created",
        created_at: now,
        updated_at: now,
      });
      return json(clusters[0]);
    }

    if (method === "POST" && path === "/api/v1/tasks") {
      latestTaskBody = await request.postDataJSON();
      return json({
        thread_id: "thread-cluster",
        status: "queued",
        message: "queued",
      });
    }

    if (method === "GET" && path === "/api/v1/knowledge/stats") {
      return json(knowledgeStats);
    }

    if (method === "GET" && path === "/api/v1/knowledge/jobs") {
      return json([]);
    }

    if (method === "GET" && path === "/api/v1/knowledge/search") {
      knowledgeSearchQueries.push(url.searchParams.get("query") || "");
      if (options.knowledgeSearchDelayMs) {
        await delay(options.knowledgeSearchDelayMs);
      }
      return json({
        query: url.searchParams.get("query") || "",
        category_filter: null,
        doc_type_filter: null,
        results_count: 1,
        results: [knowledgeResult],
        formatted_output: "",
      });
    }

    if (
      method === "GET" &&
      path === "/api/v1/knowledge/document-chunks/doc-1"
    ) {
      return json({
        document_hash: "doc-1",
        title: "Memory Tuning Guide",
        source: "redis-docs",
        category: "performance",
        doc_type: "runbook",
        summary: "Tuning memory pressure in Redis.",
        chunk_count: 2,
        metadata: {
          source_pack: "redis-docs",
          source_pack_version: "2026.06",
          source_document_path: "docs/latest/develop/reference/eviction.md",
          product_labels: ["redis"],
        },
        chunks: [
          {
            chunk_index: 0,
            title: "Memory Tuning Guide",
            content:
              "# Full Guide\n\nUse **maxmemory** with a matching policy.",
            source: "redis-docs",
            category: "performance",
            doc_type: "runbook",
            version: "8.0",
          },
          {
            chunk_index: 1,
            content: "Review eviction metrics before changing production.",
            version: "8.0",
          },
        ],
      });
    }

    return json({ error: `Unhandled ${method} ${path}` }, 404);
  });

  return {
    latestTaskBody: () => latestTaskBody,
    knowledgeSearchQueries: () => [...knowledgeSearchQueries],
  };
}

test("dashboard shows clusters alongside instances", async ({ page }) => {
  await mockApi(page);

  await page.goto("/");

  await expect(
    page.getByRole("heading", { name: "SRE Dashboard" }),
  ).toBeVisible();
  const shellHeight = await page
    .locator(".app-content-shell")
    .evaluate((element) => element.getBoundingClientRect().height);
  expect(shellHeight).toBeGreaterThanOrEqual(
    (page.viewportSize()?.height || 720) - 90,
  );
  await expect(
    page.getByText("Redis Instances", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Redis Clusters", { exact: true })).toBeVisible();
  await expect(page.getByText("Prod RE Cluster")).toBeVisible();
  await expect(
    page.getByText("Redis Enterprise", { exact: true }),
  ).toBeVisible();
});

test("settings lets users configure a Redis cluster", async ({ page }) => {
  await mockApi(page);

  await page.goto("/settings?section=clusters");

  await expect(
    page.getByRole("heading", { name: "Redis Clusters" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Add Cluster" }).first().click();

  await page
    .locator(
      'xpath=//label[normalize-space(.)="Cluster Name"]/following-sibling::input[1]',
    )
    .fill("QA Redis Cloud");
  await page
    .locator(
      'xpath=//label[normalize-space(.)="Environment"]/following-sibling::select[1]',
    )
    .selectOption("staging");
  await page
    .locator(
      'xpath=//label[normalize-space(.)="Cluster Type"]/following-sibling::select[1]',
    )
    .selectOption("redis_cloud");
  await page
    .locator(
      'xpath=//label[normalize-space(.)="Description"]/following-sibling::textarea[1]',
    )
    .fill("QA cluster used for chat diagnostics.");

  await page
    .locator("form")
    .getByRole("button", { name: "Add Cluster" })
    .click();

  await expect(page.getByText("QA Redis Cloud")).toBeVisible();
});

test("chat can start a cluster-scoped agent task", async ({ page }) => {
  const api = await mockApi(page);

  await page.goto("/triage");

  await expect(page).toHaveURL(/\/chat$/);
  await expect(
    page.getByRole("heading", { name: "SRE Agent Chat" }),
  ).toBeVisible();

  await page
    .locator("select")
    .filter({ hasText: "Prod RE Cluster - production" })
    .selectOption("cluster-1");
  await page
    .getByPlaceholder("Describe your Redis issue or ask a question...")
    .fill("inspect cluster");
  await page.getByRole("button", { name: "Send" }).click();

  await expect
    .poll(() => api.latestTaskBody())
    .toMatchObject({
      message: "inspect cluster",
      context: {
        user_id: "sre-user-1",
        priority: 0,
        cluster_id: "cluster-1",
      },
    });
});

test("chat New Chat focuses the empty-state composer", async ({ page }) => {
  await mockApi(page);

  await page.goto("/chat");

  const composer = page.getByPlaceholder(
    "Describe your Redis issue or ask a question...",
  );
  await expect(composer).toBeVisible();

  await page.getByRole("button", { name: "New Chat" }).click();

  await expect(composer).toBeFocused();
});

test("chat submits the empty-state composer with Command Enter", async ({
  page,
}) => {
  const api = await mockApi(page);

  await page.goto("/chat");

  const composer = page.getByPlaceholder(
    "Describe your Redis issue or ask a question...",
  );
  await composer.fill("check memory pressure");
  await composer.press("Meta+Enter");

  await expect
    .poll(() => api.latestTaskBody())
    .toMatchObject({
      message: "check memory pressure",
      context: {
        user_id: "sre-user-1",
        priority: 0,
      },
    });
});

test("chat renders Markdown in completed assistant messages", async ({
  page,
}) => {
  await mockApi(page, {
    threads: [
      {
        thread_id: "thread-markdown",
        subject: "Markdown answer",
        created_at: now,
        updated_at: now,
        user_id: "sre-user-1",
        latest_message: "Rendered report",
        tags: [],
        priority: 0,
      },
    ],
    threadResponses: {
      "thread-markdown": {
        thread_id: "thread-markdown",
        status: "done",
        messages: [
          {
            role: "user",
            content: "show a report",
            metadata: { timestamp: now },
          },
          {
            role: "assistant",
            content:
              "## Findings\n\n- Memory pressure is elevated\n\n| Metric | Value |\n| --- | --- |\n| used_memory | 12mb |",
            metadata: { timestamp: now },
          },
          {
            role: "assistant",
            content: "Processing query with chat agent",
            metadata: { timestamp: now },
          },
          {
            role: "assistant",
            content: "Chat agent processing your question...",
            metadata: { timestamp: now },
          },
          {
            role: "system",
            content:
              '**Startup context loaded**\n\n• "Memory Tuning Guide" (redis-docs) [hash:doc-1]',
            metadata: {
              timestamp: now,
              metadata: {
                message_type: "citations",
                citations: [
                  {
                    id: "sre_knowledge:doc-1:chunk:0",
                    title: "Memory Tuning Guide",
                    document_hash: "doc-1",
                    chunk_index: 0,
                    version: "8.0",
                  },
                ],
              },
            },
          },
        ],
        updates: [],
        result: null,
        metadata: {
          created_at: now,
          updated_at: now,
          priority: 0,
          tags: [],
          subject: "Markdown answer",
        },
        context: {},
        resume_supported: false,
      },
    },
  });

  await page.goto("/chat?thread=thread-markdown");

  await expect(
    page.getByRole("heading", { name: "SRE Agent Chat" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Memory" })).toHaveClass(
    /redis-button-base/,
  );
  await expect(page.getByRole("heading", { name: "Findings" })).toBeVisible();
  await expect(
    page.getByText("Memory pressure is elevated", { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("table")).toBeVisible();
  await expect(
    page.getByText("Processing query with chat agent", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Chat agent processing your question...", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Knowledge loaded at startup")).toBeVisible();
  const startupAccordion = page
    .getByTestId("citation-accordion")
    .filter({ hasText: "Knowledge loaded at startup" });
  const startupToggle = startupAccordion.locator("summary");
  await expect(startupAccordion).not.toHaveAttribute("open", "");
  await expect(startupToggle).not.toHaveClass(/redis-button-base/);
  await expect(startupToggle.locator('[aria-hidden="true"]')).toHaveCount(1);
  await startupToggle.click();
  await expect(startupAccordion).toHaveAttribute("open", "");
  const startupLink = startupAccordion.getByRole("link", {
    name: "Memory Tuning Guide",
  });
  await expect(startupLink).toBeVisible();
  await expect(startupLink).toHaveAttribute(
    "href",
    /\/knowledge\/document-chunks\/doc-1\?chunk=0&version=8\.0$/,
  );
  await expect(startupAccordion.getByText("redis-docs")).not.toBeVisible();
  await expect(startupAccordion.getByText("doc-1")).not.toBeVisible();

  const answerBox = await page
    .getByRole("heading", { name: "Findings" })
    .boundingBox();
  const processingBox = await page
    .getByText("Processing query with chat agent", { exact: true })
    .boundingBox();
  const chatProcessingBox = await page
    .getByText("Chat agent processing your question...", { exact: true })
    .boundingBox();
  const startupBox = await page
    .getByText("Knowledge loaded at startup")
    .boundingBox();

  expect(answerBox).not.toBeNull();
  expect(processingBox).not.toBeNull();
  expect(chatProcessingBox).not.toBeNull();
  expect(startupBox).not.toBeNull();
  expect(processingBox!.y).toBeLessThan(answerBox!.y);
  expect(chatProcessingBox!.y).toBeLessThan(answerBox!.y);
  expect(startupBox!.y).toBeLessThan(answerBox!.y);
});

test("knowledge search renders fragments and opens the selected chunk", async ({
  page,
}) => {
  await mockApi(page);

  await page.goto("/knowledge?search=maxmemory");

  await expect(page.getByText("Memory Tuning Guide")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Fragment" })).toBeVisible();
  await expect(page.getByText("maxmemory", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Memory Tuning Guide" }).click();

  await expect(page).toHaveURL(
    /\/knowledge\/document-chunks\/doc-1\?chunk=0&version=8\.0$/,
  );
  await expect(
    page.getByRole("heading", { name: "Memory Tuning Guide chunk 0" }),
  ).toBeVisible();
  await expect(page.getByText("Document Chunks Metadata")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Knowledge Chunk", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("8.0")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Full Guide" })).toBeVisible();
  await expect(
    page.getByText("Review eviction metrics before changing production."),
  ).not.toBeVisible();
  await expect(
    page.getByRole("link", { name: "View all chunks for this document" }),
  ).toBeVisible();
});

test("knowledge search chunk prefix opens a selected chunk", async ({
  page,
}) => {
  await mockApi(page);

  await page.goto("/knowledge");

  const input = page.getByPlaceholder("Search knowledge base...");
  await input.fill("chunk:doc-1:1");
  await input.press("Enter");

  await expect(page).toHaveURL(/\/knowledge\/document-chunks\/doc-1\?chunk=1$/);
  await expect(
    page.getByRole("heading", { name: "Memory Tuning Guide chunk 1" }),
  ).toBeVisible();
  await expect(
    page.getByText("Review eviction metrics before changing production."),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Full Guide" }),
  ).not.toBeVisible();
});

test("knowledge search runs after four idle characters or Enter", async ({
  page,
}) => {
  const api = await mockApi(page);

  await page.goto("/knowledge");

  const input = page.getByPlaceholder("Search knowledge base...");
  await input.fill("abc");
  await page.waitForTimeout(1100);
  expect(api.knowledgeSearchQueries()).toEqual([]);

  await input.type("d");
  await page.waitForTimeout(600);
  expect(api.knowledgeSearchQueries()).toEqual([]);

  await expect.poll(() => api.knowledgeSearchQueries().length).toBe(1);
  expect(api.knowledgeSearchQueries()).toEqual(["abcd"]);

  await input.type("f");
  await page.waitForTimeout(600);
  expect(api.knowledgeSearchQueries()).toEqual(["abcd"]);

  await expect.poll(() => api.knowledgeSearchQueries().length).toBe(2);
  expect(api.knowledgeSearchQueries()).toEqual(["abcd", "abcdf"]);
});

test("knowledge search Enter does not duplicate pending or active searches", async ({
  page,
}) => {
  const api = await mockApi(page, { knowledgeSearchDelayMs: 500 });

  await page.goto("/knowledge");

  const input = page.getByPlaceholder("Search knowledge base...");
  await input.fill("redis");
  await input.press("Enter");
  await expect.poll(() => api.knowledgeSearchQueries().length).toBe(1);
  await page.waitForTimeout(1200);
  expect(api.knowledgeSearchQueries()).toEqual(["redis"]);

  await input.fill("cluster");
  await expect.poll(() => api.knowledgeSearchQueries().length).toBe(2);
  await input.press("Enter");
  await page.waitForTimeout(700);
  expect(api.knowledgeSearchQueries()).toEqual(["redis", "cluster"]);
});
