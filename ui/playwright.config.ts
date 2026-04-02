import { defineConfig, devices } from '@playwright/test';

const useExistingServer = process.env.PLAYWRIGHT_USE_EXISTING_SERVER === '1';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  retries: 1,
  reporter: 'list',
  globalSetup: './e2e/support/global-setup.mjs',
  globalTeardown: './e2e/support/global-teardown.mjs',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3002',
    trace: 'on-first-retry',
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: useExistingServer
    ? undefined
    : {
        command: 'npm run dev',
        port: 3000,
        reuseExistingServer: true,
        timeout: 120_000,
        env: {
          VITE_API_URL: process.env.VITE_API_URL || 'http://localhost:8080',
          VITE_API_BASE_URL:
            process.env.VITE_API_BASE_URL || 'http://localhost:8080/api/v1',
        },
    },
});
