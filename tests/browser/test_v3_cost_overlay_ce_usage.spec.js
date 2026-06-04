/**
 * 2026-05-20 — Cost overlay CE-usage indicator (audit Journey #13).
 *
 * Verifies the Cost Explorer daily API usage indicator renders inside
 * the Cost overlay with the three tone variants based on
 * /api/costs/ce-usage response shape:
 *
 *   used <= limit - 3 → tone 'ok'      (no special class beyond base)
 *   remaining <= 2     → tone 'warning'
 *   exhausted: true    → tone 'danger'
 *
 * Response shape (per webapp/backend/routes/costs.py:118-126):
 *   { success: true, used, limit, remaining, exhausted, cache_ttl_hours, resets_at }
 *
 * The indicator surface lives inside the Cost overlay handle. We
 * trigger the overlay via APP.overlay.openCost() and inspect the
 * .cost-ce-usage element + its tone class.
 */

import { test, expect } from '@playwright/test';

async function gotoDashboard(page) {
    await page.goto('/');
    await page.evaluate(() => { window.confirm = () => true; });
    await page.locator('[data-page="dashboard"]').first().waitFor({ timeout: 5000 });
    await page.waitForTimeout(300);
}

async function mockCostEndpoints(page, ceUsage) {
    await page.route('**/api/costs/summary**', async (route) => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                success: true,
                monthly_total: 120,
                estimated_costs: { estimated_monthly: 120 },
            }),
        });
    });
    await page.route('**/api/costs/projects', async (route) => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ projects: [] }),
        });
    });
    await page.route('**/api/costs/settings', async (route) => {
        if (route.request().method() === 'GET') {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({ monthly_budget: 200 }),
            });
        } else {
            await route.continue();
        }
    });
    await page.route('**/api/costs/ce-usage', async (route) => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ success: true, ...ceUsage }),
        });
    });
}

test.describe('v3 cost overlay — CE usage indicator', () => {
    test('renders ok tone when usage is well below limit', async ({ page }) => {
        await mockCostEndpoints(page, {
            used: 1,
            limit: 10,
            remaining: 9,
            exhausted: false,
            cache_ttl_hours: 24,
            resets_at: '2026-05-21T00:00:00Z',
        });
        await gotoDashboard(page);
        await page.evaluate(() => window.APP.overlay.openCost());

        const usage = page.locator('.app-overlay[data-overlay-id="cost"] .cost-ce-usage');
        await usage.waitFor({ state: 'visible', timeout: 8000 });
        await expect(usage).toHaveClass(/cost-ce-usage--ok/);
        const countText = await usage.locator('.cost-ce-usage__count').textContent();
        expect(countText).toMatch(/1\s*\/\s*10/);
    });

    test('renders warning tone when remaining <= 2', async ({ page }) => {
        await mockCostEndpoints(page, {
            used: 8,
            limit: 10,
            remaining: 2,
            exhausted: false,
            cache_ttl_hours: 24,
            resets_at: '2026-05-21T00:00:00Z',
        });
        await gotoDashboard(page);
        await page.evaluate(() => window.APP.overlay.openCost());

        const usage = page.locator('.app-overlay[data-overlay-id="cost"] .cost-ce-usage');
        await usage.waitFor({ state: 'visible', timeout: 8000 });
        await expect(usage).toHaveClass(/cost-ce-usage--warning/);
        const countText = await usage.locator('.cost-ce-usage__count').textContent();
        expect(countText).toMatch(/2 of 10/);
    });

    test('renders danger tone when exhausted', async ({ page }) => {
        await mockCostEndpoints(page, {
            used: 10,
            limit: 10,
            remaining: 0,
            exhausted: true,
            cache_ttl_hours: 24,
            resets_at: '2026-05-21T00:00:00Z',
        });
        await gotoDashboard(page);
        await page.evaluate(() => window.APP.overlay.openCost());

        const usage = page.locator('.app-overlay[data-overlay-id="cost"] .cost-ce-usage');
        await usage.waitFor({ state: 'visible', timeout: 8000 });
        await expect(usage).toHaveClass(/cost-ce-usage--danger/);
        const countText = await usage.locator('.cost-ce-usage__count').textContent();
        expect(countText).toMatch(/limit reached/i);
    });

    test('progress bar fill % reflects used/limit ratio', async ({ page }) => {
        await mockCostEndpoints(page, {
            used: 5,
            limit: 10,
            remaining: 5,
            exhausted: false,
            cache_ttl_hours: 24,
            resets_at: '2026-05-21T00:00:00Z',
        });
        await gotoDashboard(page);
        await page.evaluate(() => window.APP.overlay.openCost());

        const fill = page.locator('.app-overlay[data-overlay-id="cost"] .cost-ce-usage__bar-fill');
        await fill.waitFor({ state: 'visible', timeout: 8000 });
        const width = await fill.evaluate(el => el.style.width);
        // 5/10 = 50%.
        expect(width).toBe('50%');
    });

    test('aria-valuenow + aria-valuemax wired correctly', async ({ page }) => {
        await mockCostEndpoints(page, {
            used: 3,
            limit: 10,
            remaining: 7,
            exhausted: false,
            cache_ttl_hours: 24,
            resets_at: '2026-05-21T00:00:00Z',
        });
        await gotoDashboard(page);
        await page.evaluate(() => window.APP.overlay.openCost());

        const bar = page.locator('.app-overlay[data-overlay-id="cost"] .cost-ce-usage__bar[role="progressbar"]');
        await bar.waitFor({ state: 'visible', timeout: 8000 });
        await expect(bar).toHaveAttribute('aria-valuenow', '3');
        await expect(bar).toHaveAttribute('aria-valuemax', '10');
    });
});
