import { test, expect } from '@playwright/test';

// Chat happy-path against a running local Python backend.
// Assumes Vite dev server proxies /api and /health to http://localhost:8000

const uniqueMessage = `E2E hello ${Date.now()}`;

test('send a message on Triage and see live processing', async ({ page }) => {
  let threadId: string | undefined;
  await page.goto('/triage');

  // New-conversation textarea (initial input)
  const newConversationTextarea = page.getByPlaceholder('Describe your Redis issue or ask a question...');
  await newConversationTextarea.waitFor({ state: 'visible' });

  // Type and send
  await newConversationTextarea.fill(uniqueMessage);
  await page.getByRole('button', { name: 'Send' }).click();

  // Capture created thread id
  const resp = await page.waitForResponse((r) => r.url().includes('/api/v1/tasks') && r.request().method() === 'POST');
  const data = await resp.json();
  threadId = data.thread_id as string;

  try {
    // After sending, UI enters a busy state and shows a Stop button while the task runs.
    await expect(page.getByRole('button', { name: 'Stop' })).toBeVisible({ timeout: 30_000 });

    // The user's message should appear in the transcript area soon after sending.
    // The message may appear both in the sidebar and in the chat bubble; assert the chat bubble copy.
    await expect(page.getByText(uniqueMessage).last()).toBeVisible({ timeout: 30_000 });

    // Optional: stop the task to end the live run and return to transcript view.
    await page.getByRole('button', { name: 'Stop' }).click();
    await expect(page.getByRole('button', { name: 'Stop' })).toBeHidden({ timeout: 30_000 });
  } finally {
    if (threadId) {
      await page.request.delete(`/api/v1/threads/${threadId}`);
    }
  }
});
