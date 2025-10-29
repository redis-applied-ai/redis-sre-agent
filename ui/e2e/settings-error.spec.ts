import { test, expect } from '@playwright/test';

// Exercise an error path via Settings > Instances by testing the Admin API
// with obviously invalid credentials. This calls the real backend
// /api/v1/instances/test-admin-api and should surface an error message in the UI.

test('instances: invalid admin API credentials show an error result', async ({ page }) => {
  await page.goto('/settings?section=instances');

  // Open Add Instance form
  await page.getByRole('button', { name: 'Add Instance' }).click();

  // Fill minimal required fields (use placeholders because labels are not programmatically associated)
  await page.getByPlaceholder('e.g., Production Cache').fill(`E2E Admin API Test ${Date.now()}`);
  await page.getByPlaceholder('redis://localhost:6379 or redis://user:pass@host:port/db').fill('redis://localhost:6379');

  // Select instance type = Redis Enterprise to reveal Admin API fields
  const instanceTypeSelect = page.locator('xpath=//label[normalize-space(.)="Instance Type"]/following-sibling::select[1]');
  await instanceTypeSelect.selectOption('redis_enterprise');

  // Fill invalid admin API info (intentionally bogus host)
  await page.getByPlaceholder('https://redis-enterprise:9443').fill('https://not-a-real-host.invalid:9443');
  await page.getByPlaceholder('admin@redis.com').fill('admin');
  await page.getByPlaceholder('••••••••').fill('wrongpassword');

  // Trigger test
  await page.getByRole('button', { name: 'Test Admin API Connection' }).click();

  // Expect an error result box to appear (red-styled). We assert by text prefix ❌
  await expect(page.getByText('❌', { exact: false })).toBeVisible({ timeout: 30_000 });
});
