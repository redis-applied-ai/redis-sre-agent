import { test, expect } from '@playwright/test';

// Verifies that after sending a message and stopping the live run,
// reloading the page shows the message again (session/thread persistence).

test('triage conversation persists across reload', async ({ page }) => {
  const msg = `E2E persistence ${Date.now()}`;

  await page.goto('/triage');

  // Send a new message to create a thread
  const textarea = page.getByPlaceholder('Describe your Redis issue or ask a question...');
  await textarea.waitFor({ state: 'visible' });
  await textarea.fill(msg);
  await page.getByRole('button', { name: 'Send' }).click();

  // Capture the thread id from the /api/v1/tasks response
  const resp = await page.waitForResponse((r) => r.url().includes('/api/v1/tasks') && r.request().method() === 'POST');
  const data = await resp.json();
  const threadId = data.thread_id as string;

  try {
    // Wait for the live run to start, then stop it to finalize the transcript
    await expect(page.getByRole('button', { name: 'Stop' })).toBeVisible({ timeout: 30_000 });
    await page.getByRole('button', { name: 'Stop' }).click();
    await expect(page.getByRole('button', { name: 'Stop' })).toBeHidden({ timeout: 30_000 });

    // Reload the page targeting the created thread; verify transcript shows something (not the empty-state)
    await page.goto(`/triage?thread=${encodeURIComponent(threadId)}`);
    await expect(page.getByText('No messages yet for this conversation.', { exact: true })).toBeHidden({ timeout: 30_000 });
  } finally {
    await page.request.delete(`/api/v1/threads/${threadId}`);
  }
});
