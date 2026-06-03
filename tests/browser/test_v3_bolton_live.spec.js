/**
 * v3 BOLT-ON LIVE (Agent D) — Deployments → Bolt-ons live UI tests.
 *
 * Verifies the live wiring of the Bolt-ons sub-pill to /api/bolton/*:
 *
 *   1. Rail entry for Bolt-ons exists under Deployments
 *   2. Activating Bolt-ons via the rail mounts the live UI
 *   3. Host selector populates from /api/bolton/labs/<lab>/hosts
 *   4. Selecting a host renders the 6-section spec-list (or empty state
 *      with at least the section scaffolding visible)
 *   5. APP.bolton dispatches Install / Patch / Uninstall via the same
 *      POST endpoints + opens the progress overlay
 *   6. Both themes pass layer-aware contrast on the live UI chrome
 */

import { test, expect } from '@playwright/test';
import { seedDeployment } from './helpers/seed-deployment.js';
import { railNavigate, clickSubPill } from './helpers/nav.js';

// ─── WCAG helpers ───────────────────────────────────────────────────────

function parseRgb(s) {
    const m = s.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const parts = m[1].split(',').map((p) => parseFloat(p.trim()));
    return [parts[0], parts[1], parts[2], parts.length === 4 ? parts[3] : 1];
}
function lin(c) {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
}
function lum([r, g, b]) {
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}
function ratio(a, b) {
    const L1 = lum(a);
    const L2 = lum(b);
    return (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
}

async function setTheme(page, theme) {
    await page.evaluate((t) => {
        if (t === 'light') document.documentElement.setAttribute('data-theme', 'light');
        else document.documentElement.removeAttribute('data-theme');
    }, theme);
    await page.waitForTimeout(120);
}

async function gotoBoltons(page) {
    // Seed a goad-mini deployment so the Bolt-ons sub-pill is visible.
    // The visibility gates require deployment_type ∈ goad-*/combined-*/c2-* +
    // (for c2-*) enable_test_lab. goad-mini always shows Bolt-ons.
    await seedDeployment(page, { type: 'goad-mini', name: 'goad_test_alpha' });
    await page.goto('/');
    await railNavigate(page, 'deployments-tab');
    await clickSubPill(page, 'bolt-ons');
}

// ─────────────────────────────────────────────────────────────────────────
// 1. MARKUP — rail entry + pane
// ─────────────────────────────────────────────────────────────────────────

test.describe('v3 bolt-on live — markup', () => {
    test('rail entry for Bolt-ons exists under Deployments', async ({ page }) => {
        await seedDeployment(page, { type: 'goad-mini', name: 'goad_test_alpha' });
        await page.goto('/');
        await railNavigate(page, 'deployments-tab');
        const child = page.locator('.app-rail__child[data-rail-subpill="bolt-ons"]');
        await expect(child).toHaveCount(1, { timeout: 5000 });
        await expect(child).toContainText('Bolt-ons');
    });

    test('clicking Bolt-ons shows the pane', async ({ page }) => {
        await gotoBoltons(page);
        await expect(page.locator('#subpill-pane-bolt-ons')).toBeVisible();
        await expect(page.locator('.bolton-live')).toBeVisible();
        await expect(page.locator('#bolton-host-select')).toBeVisible();
    });

    test('all 6 catalog sections are present in the DOM', async ({ page }) => {
        await gotoBoltons(page);
        const sections = page.locator('#bolton-sections .bt-section');
        const want = ['installed', 'available', 'incompatible', 'conflicts', 'already-elsewhere', 'patched'];
        for (const name of want) {
            await expect(page.locator(`#bolton-sections .bt-section[data-section="${name}"]`)).toHaveCount(1);
        }
    });
});

// ─────────────────────────────────────────────────────────────────────────
// 2. JS NAMESPACE — APP.bolton
// ─────────────────────────────────────────────────────────────────────────

test.describe('v3 bolt-on live — JS namespace', () => {
    test('APP.bolton exposes the documented surface area', async ({ page }) => {
        await gotoBoltons(page);
        const surface = await page.evaluate(() => ({
            init: typeof window.APP.bolton.init,
            loadHosts: typeof window.APP.bolton.loadHosts,
            selectHost: typeof window.APP.bolton.selectHost,
            applyFilter: typeof window.APP.bolton.applyFilter,
            install: typeof window.APP.bolton.install,
            uninstall: typeof window.APP.bolton.uninstall,
            patch: typeof window.APP.bolton.patch,
            patchRevert: typeof window.APP.bolton.patchRevert,
            invokeAgent: typeof window.APP.bolton.invokeAgent,
        }));
        for (const [k, t] of Object.entries(surface)) {
            expect(t).toBe('function');
        }
    });
});

// ─────────────────────────────────────────────────────────────────────────
// 3. HOST SELECTOR — populates from API
// ─────────────────────────────────────────────────────────────────────────

test.describe('v3 bolt-on live — host selector', () => {
    test('host selector eventually has a non-loading option list', async ({ page }) => {
        await page.route('**/api/bolton/labs/**/hosts', (route) => {
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    success: true,
                    lab: 'goad-light',
                    hosts: [
                        { name: 'dc01', role: 'dc', installed_count: 2 },
                        { name: 'ws01', role: 'workstation', installed_count: 0 },
                    ],
                }),
            });
        });
        await gotoBoltons(page);
        const sel = page.locator('#bolton-host-select');
        await expect(sel.locator('option')).not.toHaveCount(1, { timeout: 5000 });
        const optionText = await sel.locator('option').allTextContents();
        expect(optionText.some((t) => t.includes('dc01'))).toBe(true);
    });
});

// ─────────────────────────────────────────────────────────────────────────
// 4. ACTION DISPATCH — install / patch / uninstall
// ─────────────────────────────────────────────────────────────────────────

test.describe('v3 bolt-on live — action dispatch', () => {
    test('install POST is fired and progress overlay opens', async ({ page }) => {
        let installCalls = 0;
        await page.route('**/api/bolton/labs/**/hosts/**/install/**', (route) => {
            installCalls += 1;
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    success: true,
                    job_id: 'j_test_install',
                    action: 'bolton.install',
                }),
            });
        });
        await page.route('**/api/bolton/jobs/j_test_install', (route) => {
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    success: true,
                    job_id: 'j_test_install',
                    status: 'SUCCEEDED',
                    log_tail: '[STUB] done',
                }),
            });
        });

        await gotoBoltons(page);
        // Direct-dispatch via APP.bolton so we don't depend on a populated row.
        await page.evaluate(() => {
            window.APP.bolton.state.lab = 'goad-light';
            window.APP.bolton.install('bolton.identity.kerb', 'dc01');
        });
        await page.waitForTimeout(200);
        expect(installCalls).toBe(1);
        // Either Agent C's overlay (mounted under #app-overlay-root with
        // data-overlay-id="bolton-progress") or the fallback scrim must be present.
        const overlayCount = await page.evaluate(() => {
            const fallback = document.getElementById('bolton-progress-fallback');
            const overlay = document.querySelector('[data-overlay-id="bolton-progress"]');
            return (fallback ? 1 : 0) + (overlay ? 1 : 0);
        });
        expect(overlayCount).toBeGreaterThanOrEqual(1);
    });

    test('uninstall + patch + patch-revert dispatchers each POST correctly', async ({ page }) => {
        const calls = { uninstall: 0, patch: 0, patchRevert: 0 };
        await page.route('**/api/bolton/labs/**/hosts/**/uninstall/**', (route) => {
            calls.uninstall += 1;
            route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, job_id: 'j_u' }) });
        });
        await page.route('**/api/bolton/labs/**/hosts/**/patch/**', (route) => {
            calls.patch += 1;
            route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, job_id: 'j_p' }) });
        });
        await page.route('**/api/bolton/labs/**/hosts/**/patch-revert/**', (route) => {
            calls.patchRevert += 1;
            route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, job_id: 'j_r' }) });
        });
        await page.route('**/api/bolton/jobs/**', (route) => {
            route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, status: 'SUCCEEDED' }) });
        });

        await gotoBoltons(page);
        await page.evaluate(() => {
            window.APP.bolton.state.lab = 'goad-light';
            window.APP.bolton.uninstall('bolton.x', 'dc01');
            window.APP.bolton.patch('bolton.y', 'dc01');
            window.APP.bolton.patchRevert('bolton.z', 'dc01');
        });
        await page.waitForTimeout(250);
        expect(calls.uninstall).toBe(1);
        expect(calls.patch).toBe(1);
        expect(calls.patchRevert).toBe(1);
    });
});

// ─────────────────────────────────────────────────────────────────────────
// 5. CONTRAST — both themes
// ─────────────────────────────────────────────────────────────────────────

test.describe('v3 bolt-on live — contrast', () => {
    for (const theme of ['dark', 'light']) {
        test(`title + description meet WCAG AA in ${theme} mode`, async ({ page }) => {
            await gotoBoltons(page);
            await setTheme(page, theme);
            const samples = await page.evaluate(() => {
                const out = [];
                const probe = (selector) => {
                    const el = document.querySelector(selector);
                    if (!el) return;
                    const cs = window.getComputedStyle(el);
                    let bg = null;
                    let cur = el;
                    while (cur && cur !== document.documentElement) {
                        const c = window.getComputedStyle(cur);
                        const m = c.backgroundColor.match(/rgba?\(([^)]+)\)/);
                        if (m) {
                            const parts = m[1].split(',').map((s) => parseFloat(s.trim()));
                            if (parts.length === 3 || (parts.length === 4 && parts[3] > 0.5)) {
                                bg = c.backgroundColor;
                                break;
                            }
                        }
                        cur = cur.parentElement;
                    }
                    out.push({ selector, fg: cs.color, bg: bg || window.getComputedStyle(document.body).backgroundColor });
                };
                probe('.bolton-live__title');
                probe('.bolton-live__description');
                probe('.bolton-live__summary-label');
                return out;
            });
            for (const s of samples) {
                const fg = parseRgb(s.fg);
                const bg = parseRgb(s.bg);
                if (!fg || !bg) continue;
                const r = ratio(fg.slice(0, 3), bg.slice(0, 3));
                expect.soft(r, `${s.selector} contrast in ${theme}`).toBeGreaterThanOrEqual(4.5);
            }
        });
    }
});
