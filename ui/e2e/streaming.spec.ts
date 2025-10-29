import { test, expect } from '@playwright/test';

// Verifies the live streaming indicator (Thinking...) appears during a running task.

test('triage shows live Thinking indicator during processing', async ({ page }) => {
  const msg = `E2E streaming ${Date.now()}`;
  let threadId: string | undefined;

  await page.goto('/triage');

  const textarea = page.getByPlaceholder('Describe your Redis issue or ask a question...');
  await textarea.waitFor({ state: 'visible' });
  await textarea.fill(msg);
  await page.getByRole('button', { name: 'Send' }).click();

  // Capture created thread id
  const resp = await page.waitForResponse((r) => r.url().includes('/api/v1/tasks') && r.request().method() === 'POST');
  const data = await resp.json();
  threadId = data.thread_id as string;

  try {
    // When live, the UI shows a Stop button, and TaskMonitor shows a "Thinking..." bubble.
    await expect(page.getByRole('button', { name: 'Stop' })).toBeVisible({ timeout: 30_000 });
    // Disambiguate exact "Thinking..." inside the stream bubble
    await expect(page.getByText('Thinking...', { exact: true })).toBeVisible({ timeout: 30_000 });

    // Clean up to keep test time bounded
    await page.getByRole('button', { name: 'Stop' }).click();
    await expect(page.getByRole('button', { name: 'Stop' })).toBeHidden({ timeout: 30_000 });
  } finally {
    if (threadId) {
      await page.request.delete(`/api/v1/threads/${threadId}`);
    }
  }
});
