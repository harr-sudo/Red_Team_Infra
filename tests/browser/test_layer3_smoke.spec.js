/**
 * Layer 3 smoke test — Playwright + Chromium (headless).
 *
 * Purpose: prove the browser-based test layer is wired:
 *   1. Chromium launches
 *   2. Can navigate to Flask running on 127.0.0.1:5050
 *   3. enforce_loopback() at webapp/backend/app.py:35-39 lets us through
 *      (Playwright's chromium connects FROM localhost, so it's loopback-OK)
 *   4. The /api/ contract responds correctly
 *
 * Real DOM tests (tab navigation, snapshot guard, etc.) land in later
 * commits (T0.9 + the D-phase snapshot guards).
 */

import { test, expect } from '@playwright/test';

test('Flask is reachable from headless Chromium and returns expected JSON', async ({ page }) => {
    // Navigate to /api/ — should return JSON, not the SPA HTML
    const response = await page.goto('/api/');
    expect(response.status()).toBe(200);

    const body = await response.json();
    expect(body).toHaveProperty('name');
    expect(body).toHaveProperty('version');
    expect(body).toHaveProperty('endpoints');
    expect(body.endpoints).toHaveProperty('config');
    expect(body.endpoints).toHaveProperty('deploy');
});

test('loopback guard does not block Playwright Chromium', async ({ page }) => {
    // Playwright connects from 127.0.0.1; enforce_loopback() should pass.
    // If this 403s, the test framework is fundamentally broken — every
    // future browser test will fail.
    const response = await page.goto('/api/');
    expect(response.status()).not.toBe(403);
});

test('dashboard SPA loads and has expected nav buttons', async ({ page }) => {
    // Smoke check that the main UI renders.
    await page.goto('/');
    // Wait for the nav to be visible (any tab button is enough)
    await page.locator('button.tab-btn[data-target="dashboard"]').waitFor({ timeout: 5000 });

    // D2 — "Pre Reqs" tab was lifted into Settings as a section card, so the
    // nav row had 9 tabs. Cross-tab links to APP.navigateTo('aws-check')
    // still work via the NAVIGATE_ALIASES redirect (app.js).
    // D3.1 — New merged "Deployments" tab added (Configure/Deploy/Manage sub-
    // pills scaffold).
    // D3.6 — The 3 legacy buttons (Configuration / Deploy / Deployment
    // Manager) were removed from the DOM along with the ?legacyTabs=1
    // feature flag. Remaining tabs: Dashboard / Deployments / Tools /
    // Architecture / Beacon / Terminal / Settings = 7.
    // D4.1 — New merged "Operations" tab added (Beacons/Terminal/Payloads
    // sub-pills scaffold). During the transition the 3 Operations-related
    // legacy buttons (Beacon / Terminal / Tools) coexisted, hidden via
    // data-legacy="true" + the ?legacyTabs=1 flag — DOM count was 8.
    // D4.6 — Final 5-tab layout after M-Operations completes. The 3 legacy
    // Operations buttons were deleted along with the feature flag. Legacy
    // navigateTo('beacon'|'terminal'|'tools') still works via NAVIGATE_ALIASES.
    // Tabs: Dashboard / Deployments / Operations / Architecture / Settings = 5.
    const tabCount = await page.locator('button.tab-btn[data-target]').count();
    expect(tabCount).toBe(5);
});
