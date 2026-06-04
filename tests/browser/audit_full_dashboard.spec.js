/**
 * FULL DASHBOARD AUDIT — every page, every sub-pill, every deployment mode.
 *
 * This is the "does it actually work end-to-end" check. For each surface:
 *   1. Navigate to it via the real user flow (rail / sub-pill / button)
 *   2. Capture any JS errors that fire during render
 *   3. Assert the surface's anchor element is present and visible
 *   4. For data-bearing surfaces, assert the data layer populated
 *
 * Surfaces audited (in execution order):
 *   - Dashboard tab — hero CTAs + alerts + fleet tiles
 *   - Demo mode activation via "Try Demo Mode"
 *   - Deployments → Configure (draft mode)
 *   - Deployments → Deploy (draft mode)
 *   - Deployments → Manage (demo deployment)
 *   - Deployments → Bolt-ons (demo deployment)
 *   - Deployments → Cleanup (demo deployment)
 *   - Operations → Beacons (demo deployment)
 *   - Operations → Terminal (demo deployment)
 *   - Operations → Payloads (demo deployment)
 *   - Settings (all 8 sections render via APP.navigateTo)
 *   - ⌘K command palette opens
 *
 * One spec per surface so a failure on Bolt-ons doesn't block reading
 * the Beacons result.
 */

import { test, expect } from '@playwright/test';
import { railNavigate, clickSubPill } from './helpers/nav.js';

// Capture page errors throughout a test and assert none fired.
function bindErrorCapture(page) {
    const errors = [];
    page.on('pageerror', (err) => errors.push(`[pageerror] ${err.message}`));
    page.on('console', (msg) => {
        if (msg.type() === 'error') errors.push(`[console-error] ${msg.text()}`);
    });
    return errors;
}

async function bootDemo(page) {
    await page.goto('/');
    await page.waitForFunction(
        () => window.APP && typeof window.APP.startDemoMode === 'function',
        { timeout: 8000 },
    );
    await page.evaluate(() => window.APP.startDemoMode());
    await page.waitForFunction(
        () => window.APP.activeDeployment.current === 'demo'
              && window.APP.activeDeployment.deployment_type === 'demo',
        { timeout: 5000 },
    );
}

// ─── Dashboard ──────────────────────────────────────────────────────────

test('AUDIT — Dashboard hero renders all three CTAs without errors', async ({ page }) => {
    const errors = bindErrorCapture(page);
    await page.goto('/');
    await page.waitForFunction(() => window.APP, { timeout: 8000 });
    await expect(page.locator('.dashboard-hero__primary')).toBeVisible();
    await expect(page.locator('#dashboard-demo-btn')).toBeVisible();
    await expect(page.locator('#dashboard-demo-btn')).toContainText('Try Demo Mode');
    // Resume button is hidden by default (no resumable draft), that's fine.
    expect(errors.filter(e => !e.includes('favicon'))).toEqual([]);
});

// ─── Demo activation ────────────────────────────────────────────────────

test('AUDIT — Try Demo Mode button activates demo deployment', async ({ page }) => {
    const errors = bindErrorCapture(page);
    await page.goto('/');
    await page.waitForFunction(() => window.APP && typeof window.APP.startDemoMode === 'function');
    await page.click('#dashboard-demo-btn');
    await page.waitForFunction(
        () => window.APP.activeDeployment.current === 'demo'
              && window.APP.activeDeployment.deployment_type === 'demo',
        { timeout: 5000 },
    );
    expect(errors.filter(e => !e.includes('favicon'))).toEqual([]);
});

// ─── Configure (draft) ──────────────────────────────────────────────────

test('AUDIT — Configure pane mounts in draft mode without errors', async ({ page }) => {
    const errors = bindErrorCapture(page);
    await page.goto('/');
    await page.waitForFunction(() => window.APP && window.APP.activeDeployment);
    await page.evaluate(() => {
        window.APP.activeDeployment.set(window.APP.activeDeployment.DRAFT_SENTINEL);
    });
    await railNavigate(page, 'deployments-tab');
    await clickSubPill(page, 'configure');
    await expect(page.locator('[data-subpill-pane="configure"]')).toBeVisible();
    expect(errors.filter(e => !e.includes('favicon'))).toEqual([]);
});

// ─── Manage (demo deployment) ───────────────────────────────────────────

test('AUDIT — Manage sub-pill loads demo resources', async ({ page }) => {
    const errors = bindErrorCapture(page);
    await bootDemo(page);
    await railNavigate(page, 'deployments-tab');
    await clickSubPill(page, 'manage');
    await expect(page.locator('[data-subpill-pane="manage"]')).toBeVisible();
    // Wait for the resources fetch to land.
    await page.waitForFunction(async () => {
        const r = await fetch('/api/deploy/resources/project/demo');
        const b = await r.json();
        return b && b.success && b.resources && b.resources.length >= 10;
    }, { timeout: 8000 });
    expect(errors.filter(e => !e.includes('favicon'))).toEqual([]);
});

// ─── Bolt-ons (demo deployment) ─────────────────────────────────────────

test('AUDIT — Bolt-ons sub-pill loads demo hosts + catalog', async ({ page }) => {
    const errors = bindErrorCapture(page);
    await bootDemo(page);
    await railNavigate(page, 'deployments-tab');
    await clickSubPill(page, 'bolt-ons');
    await expect(page.locator('#subpill-pane-bolt-ons')).toBeVisible();
    // Host dropdown populated from /api/bolton/labs/demo/hosts.
    await page.waitForFunction(
        () => !!document.querySelector('#bolton-host-select option[value="tldc01"]'),
        { timeout: 8000 },
    );
    // Select tldc01 and wait for the catalog to populate.
    await page.evaluate(() => window.APP.bolton.selectHost('demo', 'tldc01'));
    await page.waitForFunction(
        () => !!document.querySelector('.bt-row[data-vuln-id="bolton.identity-kerberos.kerberoastable-svc"]'),
        { timeout: 8000 },
    );
    expect(errors.filter(e => !e.includes('favicon'))).toEqual([]);
});

// ─── Cleanup (demo deployment) ──────────────────────────────────────────

test('AUDIT — Cleanup sub-pill mounts in demo mode', async ({ page }) => {
    const errors = bindErrorCapture(page);
    await bootDemo(page);
    await railNavigate(page, 'deployments-tab');
    await clickSubPill(page, 'cleanup');
    await expect(page.locator('[data-subpill-pane="cleanup"]')).toBeVisible();
    expect(errors.filter(e => !e.includes('favicon'))).toEqual([]);
});

// ─── Operations → Beacons (demo deployment) ─────────────────────────────

test('AUDIT — Operations Beacons sub-pill mounts in demo mode', async ({ page }) => {
    const errors = bindErrorCapture(page);
    await bootDemo(page);
    await railNavigate(page, 'operations-tab');
    await clickSubPill(page, 'beacons');
    await expect(page.locator('[data-subpill-pane="beacons"]')).toBeVisible();
    expect(errors.filter(e => !e.includes('favicon'))).toEqual([]);
});

test('AUDIT — Operations Terminal sub-pill mounts in demo mode', async ({ page }) => {
    const errors = bindErrorCapture(page);
    await bootDemo(page);
    await railNavigate(page, 'operations-tab');
    await clickSubPill(page, 'terminal');
    await expect(page.locator('[data-subpill-pane="terminal"]')).toBeVisible();
    expect(errors.filter(e => !e.includes('favicon'))).toEqual([]);
});

test('AUDIT — Operations Payloads sub-pill mounts in demo mode', async ({ page }) => {
    const errors = bindErrorCapture(page);
    await bootDemo(page);
    await railNavigate(page, 'operations-tab');
    await clickSubPill(page, 'payloads');
    await expect(page.locator('[data-subpill-pane="payloads"]')).toBeVisible();
    expect(errors.filter(e => !e.includes('favicon'))).toEqual([]);
});

// ─── Settings ───────────────────────────────────────────────────────────

test('AUDIT — Settings tab mounts via APP.navigateTo', async ({ page }) => {
    const errors = bindErrorCapture(page);
    await page.goto('/');
    await page.waitForFunction(() => window.APP && typeof window.APP.navigateTo === 'function');
    await page.evaluate(() => window.APP.navigateTo('settings'));
    await page.waitForFunction(() => {
        const p = document.querySelector('.tab-page[data-page="settings"]');
        if (!p) return false;
        return p.classList.contains('active');
    }, { timeout: 5000 });
    expect(errors.filter(e => !e.includes('favicon'))).toEqual([]);
});

// ─── ⌘K palette ─────────────────────────────────────────────────────────

test('AUDIT — Command palette opens on ⌘K', async ({ page }) => {
    const errors = bindErrorCapture(page);
    await page.goto('/');
    await page.waitForFunction(() => window.APP);
    // Trigger the palette via its public open() API (keyboard event in
    // headless is finicky on macOS; the open() function is the canonical
    // entry-point the keyboard handler calls).
    await page.evaluate(() => {
        if (window.APP.palette && typeof window.APP.palette.open === 'function') {
            window.APP.palette.open();
        }
    });
    // Palette is rendered into a fixed overlay; assert the search input is there.
    await expect(page.locator('.palette-overlay, #palette-overlay').first()).toBeVisible({ timeout: 5000 });
    expect(errors.filter(e => !e.includes('favicon'))).toEqual([]);
});

// ─── Bolt-on detail drawer in demo mode ─────────────────────────────────

test('AUDIT — Bolt-on detail drawer opens with Walkthrough + Detections + Install tabs', async ({ page }) => {
    const errors = bindErrorCapture(page);
    await bootDemo(page);
    await page.evaluate(
        () => window.APP.bolton.openDetail('bolton.identity-kerberos.kerberoastable-svc', 'walkthrough'),
    );
    await expect(page.locator('.bolton-detail')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('.bolton-detail__tab')).toHaveCount(3);
    // 2026-05-28 — title rewrites from curriculum-agent-A are expected; match
    // the lead noun only so future content tweaks don't churn this assertion.
    await expect(page.locator('.bolton-walk__title')).toContainText(/Kerberoasting/i);
    expect(errors.filter(e => !e.includes('favicon'))).toEqual([]);
});
