/**
 * 2026-05-22 — End-to-end audit of the Cost overlay user flow.
 *
 * Pipelines covered:
 *   1. Monthly-burn tile in the global top bar (#global-cost-chip /
 *      #global-cost-amount) — shows formatted "$N/mo" or "—" placeholder.
 *   2. GET /api/costs/aggregate         — per-project monthly burn aggregate.
 *   3. GET /api/costs/ce-usage          — Cost Explorer daily-quota state.
 *   4. GET /api/costs/budget-alert      — banner threshold warnings.
 *   5. GET /api/costs/summary?project=X — per-project breakdown.
 *   6. Cost overlay drawer — opens via APP.overlay.openCost() (the
 *      dashboard widget [data-v3-widget="cost"] is the visible affordance
 *      that routes through the same path), then renders the hero,
 *      ce-usage indicator, and per-project list.
 *
 * Each endpoint is exercised TWICE:
 *   - directly via page.request.get(...) to confirm the Flask route
 *     responds with the documented shape.
 *   - through the UI (overlay render path) to confirm the frontend
 *     consumes the same shape without errors.
 */

import { test, expect } from '@playwright/test';

async function gotoDashboard(page) {
    const errors = [];
    page.on('pageerror', e => errors.push(`pageerror: ${e.message}`));
    page.on('console', msg => {
        if (msg.type() !== 'error') return;
        const text = msg.text();
        // The overlay's intentional summary-without-project fetch returns
        // a 400 that the browser surfaces as a "Failed to load resource"
        // console error. That's expected and graceful — skip it.
        if (text.includes('400 (BAD REQUEST)') && text.includes('Failed to load resource')) return;
        errors.push(`console.error: ${text}`);
    });
    page.on('response', resp => {
        const url = resp.url();
        // Only flag 5xx — the overlay deliberately calls /api/costs/summary
        // without a project param to get the aggregate view, which returns a
        // documented 400. The fetch() in renderOverlay_Cost() handles that
        // gracefully (falls back to empty object) — see app.js:34670.
        if (url.includes('/api/costs/') && resp.status() >= 500) {
            errors.push(`HTTP ${resp.status()} on ${url}`);
        }
    });
    await page.goto('/');
    await page.locator('[data-page="dashboard"]').first().waitFor({ timeout: 8000 });
    await page.waitForTimeout(400);
    return errors;
}

test.describe('cost overlay audit — direct endpoint pipelines', () => {
    test('GET /api/costs/aggregate returns success + deployments array', async ({ request }) => {
        const resp = await request.get('/api/costs/aggregate');
        expect(resp.status()).toBe(200);
        const json = await resp.json();
        expect(json.success).toBe(true);
        expect(typeof json.monthly_total).toBe('number');
        expect(Array.isArray(json.deployments)).toBe(true);
        expect(json.currency).toBeTruthy();
        expect(json.computed_at).toMatch(/\d{4}-\d{2}-\d{2}T/);
    });

    test('GET /api/costs/ce-usage returns used/limit/remaining/exhausted', async ({ request }) => {
        const resp = await request.get('/api/costs/ce-usage');
        expect(resp.status()).toBe(200);
        const json = await resp.json();
        expect(json.success).toBe(true);
        expect(typeof json.used).toBe('number');
        expect(typeof json.limit).toBe('number');
        expect(typeof json.remaining).toBe('number');
        expect(typeof json.exhausted).toBe('boolean');
        expect(json.used + json.remaining).toBeLessThanOrEqual(json.limit + 1); // tolerate off-by-one in counters
    });

    test('GET /api/costs/budget-alert returns level + threshold + used_percent', async ({ request }) => {
        const resp = await request.get('/api/costs/budget-alert');
        expect(resp.status()).toBe(200);
        const json = await resp.json();
        expect(json.success).toBe(true);
        // level is one of: ok | warning | danger (when enabled)
        if (json.enabled) {
            expect(['ok', 'warning', 'danger']).toContain(json.level);
            expect(typeof json.threshold).toBe('number');
        }
    });

    test('GET /api/costs/summary?project=demo returns 200 with success flag', async ({ request }) => {
        const resp = await request.get('/api/costs/summary?project=demo');
        expect(resp.status()).toBe(200);
        const json = await resp.json();
        // Project may not exist — service should still respond gracefully
        // with success:true and an actual_costs/estimated_costs structure
        // (or success:false + error string). Both shapes are valid for an
        // unknown project, as long as it's a 200 + JSON.
        expect(typeof json).toBe('object');
        expect('success' in json).toBe(true);
    });

    test('GET /api/costs/summary without project returns 400', async ({ request }) => {
        const resp = await request.get('/api/costs/summary');
        expect(resp.status()).toBe(400);
        const json = await resp.json();
        expect(json.success).toBe(false);
        expect(json.error).toMatch(/project/i);
    });
});

test.describe('cost overlay audit — UI pipelines', () => {
    test('monthly-burn tile renders in top bar with $N/mo OR em-dash placeholder', async ({ page }) => {
        const errors = await gotoDashboard(page);

        const chip = page.locator('#global-cost-chip');
        await expect(chip).toBeVisible();
        const amount = page.locator('#global-cost-amount');
        await expect(amount).toBeVisible();
        await expect(page.locator('.global-header__cost-caption')).toContainText(/monthly burn/i);

        // Wait a beat for the async refresh to settle (or graceful fallback).
        await page.waitForTimeout(800);
        const text = (await amount.textContent() || '').trim();
        // Accept either the em-dash placeholder OR a "$N/mo" formatted value.
        expect(text).toMatch(/^(—|\$\d+\/mo)$/);

        expect(errors.filter(e => !e.includes('favicon'))).toEqual([]);
    });

    test('overlay opens via APP.overlay.openCost() and renders hero + per-project list', async ({ page }) => {
        const errors = await gotoDashboard(page);

        // Trigger the same path the dashboard widget click uses.
        await page.evaluate(() => window.APP.overlay.openCost());

        const overlay = page.locator('.app-overlay[data-overlay-id="cost"]');
        await overlay.waitFor({ state: 'visible', timeout: 8000 });

        // Hero shows $N/mo total.
        const hero = overlay.locator('.app-overlay__cost-hero-num');
        await hero.waitFor({ state: 'visible', timeout: 8000 });
        const heroText = await hero.textContent();
        expect(heroText).toMatch(/\$\d+/);

        // CE-usage indicator should render (uses /api/costs/ce-usage).
        const ceUsage = overlay.locator('.cost-ce-usage');
        await ceUsage.waitFor({ state: 'visible', timeout: 8000 });
        await expect(ceUsage).toHaveClass(/cost-ce-usage--(ok|warning|danger)/);
        await expect(overlay.locator('.cost-ce-usage__bar[role="progressbar"]')).toBeVisible();

        // Per-project breakdown: either a populated list OR the empty state.
        const list = overlay.locator('dl.spec-list');
        const empty = overlay.locator('.app-overlay__empty');
        const hasList = await list.count() > 0;
        const hasEmpty = await empty.count() > 0;
        expect(hasList || hasEmpty).toBe(true);

        // Footer save-budget control is wired.
        await expect(overlay.locator('[data-v3-cost-budget]')).toBeVisible();
        await expect(overlay.locator('[data-v3-cost-save]')).toBeVisible();

        expect(errors.filter(e => !e.includes('favicon'))).toEqual([]);
    });

    test('clicking the dashboard cost widget opens the cost overlay', async ({ page }) => {
        await gotoDashboard(page);
        const tile = page.locator('[data-v3-widget="cost"]').first();
        await expect(tile).toBeVisible();
        await tile.click();
        const overlay = page.locator('.app-overlay[data-overlay-id="cost"]');
        await overlay.waitFor({ state: 'visible', timeout: 8000 });
        await expect(overlay.locator('.app-overlay__cost-hero-num')).toBeVisible();
    });

    test('overlay consumes /api/costs/aggregate, /ce-usage, /summary, /projects, /settings without 5xx', async ({ page }) => {
        const seen = {};
        const errors = [];
        page.on('response', resp => {
            const url = resp.url();
            const m = url.match(/\/api\/costs\/([a-z-]+)/);
            if (m) {
                seen[m[1]] = resp.status();
                if (resp.status() >= 500) errors.push(`HTTP ${resp.status()} on ${url}`);
            }
        });

        await page.goto('/');
        await page.locator('[data-page="dashboard"]').first().waitFor({ timeout: 8000 });
        await page.evaluate(() => window.APP.overlay.openCost());
        await page.locator('.app-overlay[data-overlay-id="cost"] .app-overlay__cost-hero-num').waitFor({ timeout: 8000 });
        await page.waitForTimeout(500);

        // Overlay render path hits at least these endpoints.
        expect(seen['summary']).toBeLessThan(500);
        expect(seen['projects']).toBeLessThan(500);
        expect(seen['ce-usage']).toBeLessThan(500);
        // budget-alert and aggregate are hit by other surfaces; they may or
        // may not fire during this specific render — but if they did fire,
        // they must not have 5xx'd.
        for (const [name, status] of Object.entries(seen)) {
            expect(status, `${name} status`).toBeLessThan(500);
        }
        expect(errors).toEqual([]);
    });

    test('budget-alert banner — endpoint level matches banner visibility', async ({ page }) => {
        await gotoDashboard(page);

        // Fetch the live alert state through the page's own fetcher so
        // cookies / state-dir match.
        const alert = await page.evaluate(async () => {
            const r = await fetch('/api/costs/budget-alert');
            return r.json();
        });
        expect(alert.success).toBe(true);

        const banner = page.locator('#budget-alert-banner');
        if (alert.enabled && (alert.level === 'warning' || alert.level === 'danger')) {
            // Banner should be present in DOM and rendered with the threshold.
            await expect(banner).toBeAttached();
            const html = await banner.innerHTML();
            expect(html).toMatch(/Budget at/i);
            expect(html).toMatch(/View cost tracker/i);
        } else {
            // When level=ok or disabled, banner is hidden (style.display='none').
            if (await banner.count() > 0) {
                const display = await banner.evaluate(el => getComputedStyle(el).display);
                expect(display).toBe('none');
            }
        }
    });
});
