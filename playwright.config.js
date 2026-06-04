// Playwright config for the Red Team Infra dashboard.
//
// IMPORTANT — TEST ISOLATION (task #54):
// The operator must start Flask with DASHBOARD_STATE_DIR pointing at an
// isolated tmpdir before running the browser suite. Otherwise the live
// ~/.dashboard/operators.json + ~/.dashboard/audit.log + the in-tree
// webapp/state/presence/ directory will be polluted by spec runs.
//
//   export DASHBOARD_STATE_DIR=/tmp/playwright-dashboard-state
//   rm -rf "$DASHBOARD_STATE_DIR"
//   source venv/bin/activate && PYTHONPATH=. \
//     python3 -m flask --app webapp.backend.app run --port 5050 --host 127.0.0.1
//
// Then in another shell:
//   npm run test:browser
//
// A `globalSetup` hook below also wipes the tmpdir at suite start so
// stale state from a previous run never bleeds into the next run.
// `webServer` is intentionally null — operators control the Flask
// process directly to keep iteration loops fast.

import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  testMatch: '**/*.spec.js',
  // Exclude the snapshot-capture script from the regular browser-test
  // suite — it's a baseline generator, run on-demand via
  // `make snapshot-bless` (which sets CAPTURE_SNAPSHOTS=1). See T0.9
  // / §21.5.
  testIgnore: process.env.CAPTURE_SNAPSHOTS ? [] : ['**/fixtures/**'],
  globalSetup: './tests/browser/global-setup.js',
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
