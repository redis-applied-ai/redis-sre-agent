import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';

// E2E tests for the feedback (thumbs up/down) UI flow.
//
// Seeding strategy: create a thread + task via HTTP (direct to backend), then
// force task status to "done" via redis-cli so the UI renders FeedbackButtons.
// This avoids waiting for the agent worker and is deterministic.

const REDIS_PORT = process.env.REDIS_PORT || '7843';
const BACKEND_URL = process.env.FEEDBACK_TEST_BACKEND_URL || 'http://127.0.0.1:8001';

function redisSet(key: string, value: string) {
  execSync(`redis-cli -p ${REDIS_PORT} SET "${key}" "${value}"`, { stdio: 'pipe' });
}

function redisHSet(key: string, ...fieldValues: string[]) {
  const pairs = fieldValues.join(' ');
  execSync(`redis-cli -p ${REDIS_PORT} HSET "${key}" ${pairs}`, { stdio: 'pipe' });
}

function redisDel(...keys: string[]) {
  try {
    execSync(`redis-cli -p ${REDIS_PORT} DEL ${keys.map((k) => `"${k}"`).join(' ')}`, { stdio: 'pipe' });
  } catch {
    // best-effort cleanup
  }
}

async function apiFetch(path: string, options: RequestInit = {}): Promise<any> {
  const res = await fetch(`${BACKEND_URL}/api/v1${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${options.method || 'GET'} ${path} failed: ${res.status} ${body}`);
  }
  return res.json();
}

interface SeedResult {
  threadId: string;
  taskId: string;
}

async function seedCompletedTask(): Promise<SeedResult> {
  // 1. Create a thread with a user message and an assistant response already in place.
  const thread = await apiFetch('/threads', {
    method: 'POST',
    body: JSON.stringify({
      subject: 'E2E feedback test thread',
      user_id: 'e2e-test',
      messages: [
        { role: 'user', content: 'E2E feedback: what is Redis memory usage?' },
        { role: 'assistant', content: 'E2E feedback: Redis memory usage is 42 MB.' },
      ],
    }),
  });
  const threadId: string = thread.thread_id;

  // 2. Create a task linked to the thread (this writes the status key as "queued").
  const task = await apiFetch('/tasks', {
    method: 'POST',
    body: JSON.stringify({
      message: 'E2E feedback: what is Redis memory usage?',
      thread_id: threadId,
      user_id: 'e2e-test',
    }),
  });
  const taskId: string = task.task_id;

  // 3. Force the task to "done" and write metadata so the feedback module can
  //    resolve the thread_id (needed for stream publish — non-fatal if absent).
  redisSet(`sre:task:${taskId}:status`, 'done');
  redisHSet(`sre:task:${taskId}:metadata`, 'thread_id', threadId, 'user_id', 'e2e-test');

  return { threadId, taskId };
}

async function cleanupTask(threadId: string, taskId: string) {
  redisDel(
    `sre:task:${taskId}:status`,
    `sre:task:${taskId}:metadata`,
    `sre:feedback:task:${taskId}`,
  );
  try {
    await apiFetch(`/threads/${threadId}`, { method: 'DELETE' });
  } catch {
    // best-effort
  }
}

test.describe('Feedback buttons — thumbs up / down flow', () => {
  let threadId: string;
  let taskId: string;

  test.beforeAll(async () => {
    ({ threadId, taskId } = await seedCompletedTask());
  });

  test.afterAll(async () => {
    await cleanupTask(threadId, taskId);
  });

  test('full feedback lifecycle: up → down → withdraw → reload', async ({ page, request }) => {
    // ── Navigate to Triage with the seeded thread ──────────────────────────
    await page.goto(`/triage?thread=${encodeURIComponent(threadId)}`);

    // Wait for the static transcript view (no live WebSocket monitor, no Stop button).
    // The FeedbackButtons appear once the assistant message is rendered.
    const upBtn = page.getByTestId('feedback-up');
    const downBtn = page.getByTestId('feedback-down');
    await expect(upBtn).toBeVisible({ timeout: 30_000 });
    await expect(downBtn).toBeVisible({ timeout: 30_000 });

    // Both buttons should be inactive initially (no prior feedback).
    await expect(upBtn).toHaveAttribute('data-active', 'false');
    await expect(downBtn).toHaveAttribute('data-active', 'false');

    // ── AC-1: Click 👍 — button becomes active ─────────────────────────────
    // Use waitForResponse to confirm the backend POST has settled before querying.
    await Promise.all([
      upBtn.click(),
      page.waitForResponse((r) => r.url().includes(`/tasks/${taskId}/feedback`) && r.request().method() === 'POST'),
    ]);
    await expect(upBtn).toHaveAttribute('data-active', 'true', { timeout: 5_000 });
    await expect(downBtn).toHaveAttribute('data-active', 'false');

    // Verify backend: GET /api/v1/tasks/{taskId}/feedback → verdict "up"
    const afterUp = await request.get(`/api/v1/tasks/${taskId}/feedback`);
    expect(afterUp.ok()).toBe(true);
    const upRecord = await afterUp.json();
    expect(upRecord.verdict).toBe('up');

    // ── AC-2: Click 👎 — switches active state to down ────────────────────
    await Promise.all([
      downBtn.click(),
      page.waitForResponse((r) => r.url().includes(`/tasks/${taskId}/feedback`) && r.request().method() === 'POST'),
    ]);
    await expect(downBtn).toHaveAttribute('data-active', 'true', { timeout: 5_000 });
    await expect(upBtn).toHaveAttribute('data-active', 'false');

    // Verify backend: verdict now "down"
    const afterDown = await request.get(`/api/v1/tasks/${taskId}/feedback`);
    expect(afterDown.ok()).toBe(true);
    const downRecord = await afterDown.json();
    expect(downRecord.verdict).toBe('down');

    // ── AC-3: Click 👎 again (same verdict) — withdraws ───────────────────
    await Promise.all([
      downBtn.click(),
      page.waitForResponse((r) => r.url().includes(`/tasks/${taskId}/feedback`) && r.request().method() === 'POST'),
    ]);
    await expect(downBtn).toHaveAttribute('data-active', 'false', { timeout: 5_000 });
    await expect(upBtn).toHaveAttribute('data-active', 'false');

    // Verify backend: verdict now "withdrawn"
    const afterWithdraw = await request.get(`/api/v1/tasks/${taskId}/feedback`);
    expect(afterWithdraw.ok()).toBe(true);
    const withdrawRecord = await afterWithdraw.json();
    expect(withdrawRecord.verdict).toBe('withdrawn');

    // ── AC-4: Reload — no button active (withdrawn state persists) ─────────
    await page.goto(`/triage?thread=${encodeURIComponent(threadId)}`);
    await expect(upBtn).toBeVisible({ timeout: 30_000 });
    await expect(downBtn).toBeVisible({ timeout: 30_000 });
    await expect(upBtn).toHaveAttribute('data-active', 'false');
    await expect(downBtn).toHaveAttribute('data-active', 'false');
  });
});
