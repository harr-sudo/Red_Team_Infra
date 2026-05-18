import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  testMatch: '**/*.spec.js',
  // Exclude the snapshot-capture script from the regular browser-test
  // suite — it's a baseline generator, run on-demand via
  // `make snapshot-bless` (which sets CAPTURE_SNAPSHOTS=1). See T0.9
  // / §21.5.
  testIgnore: process.env.CAPTURE_SNAPSHOTS ? [] : ['**/fixtures/**'],
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],
  use: {
    baseURL: 'http://127.0.0.1:5050',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: null,
});
