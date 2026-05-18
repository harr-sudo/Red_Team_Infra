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
    // nav row now has 9 tabs. Cross-tab links to APP.navigateTo('aws-check')
    // still work via the NAVIGATE_ALIASES redirect (app.js).
    const tabCount = await page.locator('button.tab-btn[data-target]').count();
    expect(tabCount).toBe(9);
});
