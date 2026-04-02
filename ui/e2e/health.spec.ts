import { test, expect } from '@playwright/test';

// Basic health and app boot smoke
// Supports either a local Vite dev server or the compose-backed UI/API stack.

test('dashboard shows agent status when backend is up', async ({ page }) => {
  await page.goto('/');

  // Header loads
  await expect(page.getByText('Redis SRE Agent')).toBeVisible();

  // Agent status card renders a status text like Online/Degraded/Offline.
  // Allow some time for the dashboard to fetch data.
  await expect(page.getByText(/Online|Degraded|Offline|Available|Unavailable/i)).toBeVisible({ timeout: 30_000 });
});
