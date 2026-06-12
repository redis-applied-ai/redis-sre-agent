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
  taskResponses?: Record<string, unknown>;
  feedbackResponses?: Record<string, unknown>;
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
  const taskResponses: Record<string, unknown> = options.taskResponses || {};
  const feedbackResponses: Record<string, unknown> =
    options.feedbackResponses || {};
  let latestTaskBody: unknown = null;
  const knowledgeSearchQueries: string[] = [];
  const feedbackRequestIds: string[] = [];

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

    if (
      method === "GET" &&
      path.startsWith("/api/v1/tasks/") &&
      path.endsWith("/approvals")
    ) {
      const parts = path.split("/");
      return json({ task_id: parts[parts.length - 2], approvals: [] });
    }

    if (
      method === "GET" &&
      path.startsWith("/api/v1/tasks/") &&
      path.endsWith("/feedback")
    ) {
      const parts = path.split("/");
      const taskId = parts[parts.length - 2] || "";
      feedbackRequestIds.push(taskId);
      if (feedbackResponses[taskId]) {
        return json(feedbackResponses[taskId]);
      }
      return json({ error: "No feedback" }, 404);
    }

    if (method === "GET" && path.startsWith("/api/v1/tasks/")) {
      const taskId = path.split("/").pop() || "";
      if (taskResponses[taskId]) {
        return json(taskResponses[taskId]);
      }
      return json({ error: "Task not found" }, 404);
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
    feedbackRequestIds: () => [...feedbackRequestIds],
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

  const targetAccordion = page.getByTestId("chat-target-accordion");
  await expect(targetAccordion).not.toHaveAttribute("open", "");
  await expect(targetAccordion.locator("summary")).toContainText(
    "General troubleshooting",
  );
  await expect(
    page.getByText("No specific instance", { exact: false }),
  ).not.toBeVisible();
  await targetAccordion.locator("summary").click();
  await targetAccordion.getByLabel("Target").selectOption("cluster:cluster-1");
  await expect(targetAccordion.locator("summary")).toContainText(
    "Prod RE Cluster",
  );
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
  const api = await mockApi(page, {
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
        task_id: "task-markdown",
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
            content: "I'm running the memory diagnostics now...",
            metadata: {
              timestamp: now,
              update_type: "agent_processing",
            },
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
    taskResponses: {
      "task-markdown": {
        task_id: "task-markdown",
        thread_id: "thread-markdown",
        status: "done",
        updates: [],
        result: null,
        tool_calls: [
          {
            id: "call-1",
            name: "redis_sre_123abc_get_metric_window",
            args: { metric: "used_memory" },
            result: { samples: 12 },
          },
          {
            id: "call-2",
            name: "knowledge_search",
            args: { query: "memory pressure" },
            result: { results_count: 1 },
          },
        ],
        citation_groups: [
          {
            group_key: "startup_context_loaded",
            label: "Startup context loaded",
            count: 1,
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
        ],
        feedback: {
          task_id: "task-markdown",
          verdict: "down",
          comment: null,
          created_at: now,
          updated_at: now,
        },
      },
    },
    feedbackResponses: {
      "task-markdown": {
        feedback: {
          task_id: "task-markdown",
          verdict: "down",
          comment: null,
          created_at: now,
          updated_at: now,
        },
        task: {
          task_id: "task-markdown",
          status: "done",
        },
      },
    },
  });

  await page.goto("/chat?thread=thread-markdown");

  await expect(
    page.getByRole("heading", { name: "SRE Agent Chat" }),
  ).toBeVisible();
  expect(api.feedbackRequestIds()).toEqual([]);
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
  ).not.toBeVisible();
  await expect(
    page.getByText("Chat agent processing your question...", { exact: true }),
  ).not.toBeVisible();
  await expect(
    page.getByText("I'm running the memory diagnostics now...", {
      exact: true,
    }),
  ).not.toBeVisible();
  await expect(page.getByText("Knowledge loaded at startup")).toBeVisible();
  const toolCallsAccordion = page.getByTestId("tool-calls-accordion");
  await expect(toolCallsAccordion).toBeVisible();
  await expect(toolCallsAccordion).not.toHaveAttribute("open", "");
  await expect(toolCallsAccordion.getByTestId("tool-call-item")).toHaveCount(2);
  await toolCallsAccordion.locator("summary").first().click();
  await expect(toolCallsAccordion).toHaveAttribute("open", "");
  await expect(toolCallsAccordion.getByText("get_metric_window")).toBeVisible();
  await expect(toolCallsAccordion.getByText("knowledge_search")).toBeVisible();
  await toolCallsAccordion
    .getByTestId("tool-call-item")
    .first()
    .locator("summary")
    .click();
  await expect(toolCallsAccordion.getByText("used_memory")).toBeVisible();
  await expect(page.getByTestId("feedback-down")).toHaveAttribute(
    "data-active",
    "true",
  );
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
    /\/knowledge\/document-chunks\/doc-1\?version=8\.0#chunk-0$/,
  );
  await expect(startupAccordion.getByText("redis-docs")).not.toBeVisible();
  await expect(startupAccordion.getByText("doc-1")).not.toBeVisible();

  const answerBox = await page
    .getByRole("heading", { name: "Findings" })
    .boundingBox();
  const userBox = await page.getByText("show a report").boundingBox();
  const startupBox = await page
    .getByText("Knowledge loaded at startup")
    .boundingBox();
  const toolCallsBox = await toolCallsAccordion.boundingBox();
  const feedbackBox = await page.getByTestId("feedback-down").boundingBox();
  const answerMarkdown = page
    .locator(".markdown-content.text-redis-sm")
    .filter({ hasText: "Memory pressure is elevated" })
    .first();
  const answerMarkdownBox = await answerMarkdown.boundingBox();
  const answerBubbleWidth = await answerMarkdown.evaluate(
    (element) => element.parentElement?.getBoundingClientRect().width || 0,
  );

  expect(userBox).not.toBeNull();
  expect(answerBox).not.toBeNull();
  expect(startupBox).not.toBeNull();
  expect(toolCallsBox).not.toBeNull();
  expect(feedbackBox).not.toBeNull();
  expect(answerMarkdownBox).not.toBeNull();
  expect(userBox!.y).toBeLessThan(startupBox!.y);
  expect(startupBox!.y).toBeLessThan(toolCallsBox!.y);
  expect(toolCallsBox!.y).toBeLessThan(answerBox!.y);
  expect(answerBox!.y).toBeLessThan(feedbackBox!.y);
  expect(Math.abs(answerBubbleWidth - toolCallsBox!.width)).toBeLessThanOrEqual(
    2,
  );
  expect(answerMarkdownBox!.width).toBeGreaterThan(toolCallsBox!.width - 40);
});

test("chat thread selection syncs the URL and shows session details", async ({
  page,
}) => {
  const api = await mockApi(page, {
    threads: [
      {
        thread_id: "thread-details",
        subject: "Session debug details",
        created_at: now,
        updated_at: now,
        user_id: "sre-user-1",
        latest_message: "Details loaded",
        tags: [],
        priority: 0,
      },
    ],
    threadResponses: {
      "thread-details": {
        thread_id: "thread-details",
        task_id: "task-details",
        status: "done",
        messages: [
          {
            role: "user",
            content: "show session details",
            metadata: { timestamp: now },
          },
          {
            role: "assistant",
            content: "Session details are available.",
            metadata: { timestamp: now, task_id: "task-details" },
          },
        ],
        updates: [],
        result: null,
        metadata: {
          created_at: now,
          updated_at: now,
          priority: 0,
          tags: [],
          subject: "Session debug details",
        },
        context: { cluster_id: "cluster-1" },
        resume_supported: false,
      },
    },
    taskResponses: {
      "task-details": {
        task_id: "task-details",
        thread_id: "thread-details",
        status: "done",
        updates: [],
        result: null,
        tool_calls: [
          {
            id: "details-call-1",
            name: "redis_sre_get_cluster_info",
            args: { cluster_id: "cluster-1" },
            result: { nodes: 3 },
          },
        ],
        feedback: {
          task_id: "task-details",
          verdict: "up",
          comment: null,
          created_at: now,
          updated_at: now,
        },
      },
    },
  });

  await page.goto("/chat");

  await page.getByText("Session debug details").click();

  await expect(page).toHaveURL(/\/chat\?thread=thread-details$/);
  await expect(
    page
      .getByRole("paragraph")
      .filter({ hasText: "Session details are available." }),
  ).toBeVisible();
  expect(api.feedbackRequestIds()).toEqual([]);

  await page.getByRole("button", { name: "Session Details" }).click();

  const detailsPanel = page.getByTestId("session-details-panel");
  await expect(
    detailsPanel.getByRole("heading", { name: "Session Details" }),
  ).toBeVisible();
  await expect(detailsPanel.getByText("thread-details")).toBeVisible();
  await expect(detailsPanel.getByText("task-details")).toBeVisible();
  await expect(detailsPanel.getByText("done", { exact: true })).toBeVisible();
  await expect(detailsPanel.getByText("Prod RE Cluster")).toBeVisible();
  await expect(detailsPanel.getByText("Tool calls loaded")).toBeVisible();
  await expect(detailsPanel.getByText("1", { exact: true })).toBeVisible();
  await expect(detailsPanel.getByText("up", { exact: true })).toBeVisible();
});

test("chat shows running tool calls in the standard transcript", async ({
  page,
}) => {
  await mockApi(page, {
    threads: [
      {
        thread_id: "thread-running",
        subject: "Running answer",
        created_at: now,
        updated_at: now,
        user_id: "sre-user-1",
        latest_message: "Agent is working",
        tags: [],
        priority: 0,
      },
    ],
    threadResponses: {
      "thread-running": {
        thread_id: "thread-running",
        task_id: "task-running",
        status: "in_progress",
        messages: [
          {
            role: "user",
            content: "check current ops",
            metadata: { timestamp: now },
          },
          {
            role: "assistant",
            content: "Previous completed answer.",
            metadata: { timestamp: now, task_id: "task-previous" },
          },
        ],
        updates: [
          {
            timestamp: now,
            message: "I'm running redis_sre_get_metric_window now...",
            type: "agent_processing",
          },
          {
            timestamp: now,
            message: "Executing tool: redis_sre_123abc_get_metric_window",
            type: "tool_call",
            metadata: {
              tool_args: { metric: "instantaneous_ops_per_sec" },
            },
          },
        ],
        result: null,
        metadata: {
          created_at: now,
          updated_at: now,
          priority: 0,
          tags: [],
          subject: "Running answer",
        },
        context: {},
        resume_supported: false,
      },
    },
    taskResponses: {
      "task-previous": {
        task_id: "task-previous",
        thread_id: "thread-running",
        status: "done",
        updates: [],
        result: null,
        tool_calls: [
          {
            id: "previous-call-1",
            name: "redis_sre_123abc_get_memory_stats",
            args: { scope: "previous turn" },
            result: { samples: 3 },
          },
        ],
      },
      "task-running": {
        task_id: "task-running",
        thread_id: "thread-running",
        status: "in_progress",
        updates: [],
        result: null,
        tool_calls: null,
      },
    },
  });

  await page.goto("/chat?thread=thread-running");

  await expect(
    page
      .getByRole("paragraph")
      .filter({ hasText: "Previous completed answer." }),
  ).toBeVisible();
  await expect(page.getByText("Task is running.")).toBeVisible();
  await expect(
    page.getByText("Executing tool: redis_sre_123abc_get_metric_window", {
      exact: true,
    }),
  ).not.toBeVisible();
  await expect(
    page.getByText("I'm running redis_sre_get_metric_window now...", {
      exact: true,
    }),
  ).not.toBeVisible();

  const toolCallsAccordions = page.getByTestId("tool-calls-accordion");
  await expect(toolCallsAccordions).toHaveCount(2);

  const previousToolCallsAccordion = toolCallsAccordions.nth(0);
  await expect(previousToolCallsAccordion).toBeVisible();
  await previousToolCallsAccordion.locator("summary").first().click();
  await expect(
    previousToolCallsAccordion.getByText("get_memory_stats"),
  ).toBeVisible();

  const runningToolCallsAccordion = toolCallsAccordions.nth(1);
  await expect(runningToolCallsAccordion).toBeVisible();
  await expect(
    runningToolCallsAccordion.getByText("1", { exact: true }),
  ).toBeVisible();
  await runningToolCallsAccordion.locator("summary").first().click();
  await expect(
    runningToolCallsAccordion.getByText("get_metric_window"),
  ).toBeVisible();
  await runningToolCallsAccordion
    .getByTestId("tool-call-item")
    .first()
    .locator("summary")
    .click();
  await expect(
    runningToolCallsAccordion.getByText("instantaneous_ops_per_sec"),
  ).toBeVisible();
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
    /\/knowledge\/document-chunks\/doc-1\?version=8\.0#chunk-0$/,
  );
  await expect(
    page.getByRole("heading", { name: "Memory Tuning Guide" }),
  ).toBeVisible();
  await expect(page.getByText("Document Chunks Metadata")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Assembled Document", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Chunk 0" })).toBeVisible();
  await expect(page.getByText("8.0")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Full Guide" })).toBeVisible();
  await expect(
    page.getByText("Review eviction metrics before changing production."),
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

  await expect(page).toHaveURL(/\/knowledge\/document-chunks\/doc-1#chunk-1$/);
  await expect(
    page.getByRole("heading", { name: "Memory Tuning Guide" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Chunk 1" })).toBeVisible();
  await expect(
    page.getByText("Review eviction metrics before changing production."),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Full Guide" })).toBeVisible();
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
