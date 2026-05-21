/**
 * v3 — Operations sub-pill REACTIVITY + "All deployments" fleet mode
 * (2026-05-19).
 *
 * Two coupled fixes verified here:
 *
 *  A. Switching the top-bar deployment dropdown WHILE an Operations sub-pill
 *     (Beacons / Terminal / Payloads) is open triggers a reload of the
 *     underlying namespace's init() function.
 *
 *  B. "All deployments" mode (sentinel value `__all__` set via
 *     APP.activeDeployment.set) shows the per-surface empty state on every
 *     per-deployment surface, and renders the fleet table on Manage.
 *     Clicking a fleet row switches the dropdown back to that project.
 *
 * Both themes contrast clean.
 */

import { test, expect } from '@playwright/test';

const ALL_SENTINEL = '__all__';

async function gotoRoot(page) {
    await page.goto('/');
    // Wait for the global listbox to either populate with at least one row
    // or render the empty-state row — both of which complete the deferred
    // _refreshGlobalDeployments() call. We need this before any set() so
    // the deferred set inside _refreshGlobalDeployments() doesn't clobber.
    await page.waitForFunction(
        () => {
            const lb = document.getElementById('global-deploy-listbox');
            return lb && lb.children.length > 0;
        },
        null,
        { timeout: 5000 }
    );
}

async function gotoSubpill(page, parent, subpill) {
    const railItem = page.locator(`.app-rail__item[data-rail-target="${parent}"]`);
    await railItem.click();
    const child = page.locator(`.app-rail__child[data-rail-subpill="${subpill}"]`);
    await child.waitFor({ timeout: 5000 });
    await child.click();
    await page.locator(`#subpill-pane-${subpill}`).waitFor({ state: 'visible', timeout: 5000 });
}

async function setTheme(page, theme) {
    await page.evaluate((t) => {
        if (t === 'light') document.documentElement.setAttribute('data-theme', 'light');
        else document.documentElement.removeAttribute('data-theme');
    }, theme);
    await page.waitForTimeout(120);
}

// ─── WCAG helpers (re-implemented locally so the spec is self-contained) ──

function parseRgb(s) {
    const m = s.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const parts = m[1].split(',').map((p) => parseFloat(p.trim()));
    return [parts[0], parts[1], parts[2]];
}
function lin(c) { const v = c / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }
function lum([r, g, b]) { return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b); }
function ratio(a, b) { const L1 = lum(a); const L2 = lum(b); return (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05); }

// Inject synthetic /api/deploy/active so the dropdown shows reliable
// project names regardless of the host's tfstate.
async function mockActiveDeployments(page, deployments, opts = {}) {
    const _deps = deployments;
    await page.route('**/api/deploy/active**', async (route) => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                success: true,
                deployments: _deps,
            }),
        });
    });
    // Costs aggregate — used by fleet table.
    await page.route('**/api/costs/aggregate**', async (route) => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                success: true,
                deployments: _deps.map((d) => ({ project_name: d.project_name || d._filename, monthly: 123 })),
                total_monthly: 123 * _deps.length,
            }),
        });
    });
    // 2026-05-19 — Operations aggregate endpoints. Tests that don't pass
    // explicit overrides get an empty fleet (which falls back to the
    // empty-state CTA the existing All-mode tests already assert against).
    const beaconAll = opts.beaconAll || { success: true, beacons: [], errors: [], deployments_polled: 0 };
    const payloadsAll = opts.payloadsAll || { success: true, payloads: [], errors: [] };
    await page.route('**/api/beacon/all', async (route) => {
        await route.fulfill({
            status: 200, contentType: 'application/json',
            body: JSON.stringify(beaconAll),
        });
    });
    await page.route('**/api/tools/payloads/all', async (route) => {
        await route.fulfill({
            status: 200, contentType: 'application/json',
            body: JSON.stringify(payloadsAll),
        });
    });
}

// ─────────────────────────────────────────────────────────────────────────
// PART A — Operations sub-pill REACTIVITY
// ─────────────────────────────────────────────────────────────────────────

test.describe('v3 — Operations sub-pill reactivity to top-bar deployment changes', () => {
    test.beforeEach(async ({ page }) => {
        await mockActiveDeployments(page, [
            { project_name: 'lab_alpha',  _filename: 'lab_alpha',  deployment_type: 'c2-adhoc', status: 'success' },
            { project_name: 'lab_bravo',  _filename: 'lab_bravo',  deployment_type: 'c2-purple', status: 'success' },
        ]);
    });

    test('APP.beacons subscribes to top-bar selector and reloads on change', async ({ page }) => {
        await gotoRoot(page);
        await gotoSubpill(page, 'operations-tab', 'beacons');
        // The init() is gated by `_initialized` — verify a subscriber has
        // been added by switching to lab_bravo and seeing BEACON.init fire.
        const initCallCount = await page.evaluate(() => {
            window.__beaconInitCalls = 0;
            const orig = BEACON.init;
            BEACON.init = function () {
                window.__beaconInitCalls += 1;
                // Avoid actually firing the real init (would hit CS REST API).
            };
            return 0;
        });
        await page.evaluate(() => APP.activeDeployment.set('lab_bravo'));
        await page.waitForTimeout(120);
        const after = await page.evaluate(() => window.__beaconInitCalls);
        expect(after).toBeGreaterThanOrEqual(1);
    });

    test('APP.terminal subscribes to top-bar selector and reloads on change', async ({ page }) => {
        await gotoRoot(page);
        await gotoSubpill(page, 'operations-tab', 'terminal');
        await page.evaluate(() => {
            window.__terminalInitCalls = 0;
            TERMINAL.init = function () { window.__terminalInitCalls += 1; };
        });
        await page.evaluate(() => APP.activeDeployment.set('lab_bravo'));
        await page.waitForTimeout(120);
        const after = await page.evaluate(() => window.__terminalInitCalls);
        expect(after).toBeGreaterThanOrEqual(1);
    });

    test('APP.payloads subscribes to top-bar selector and reloads on change', async ({ page }) => {
        await gotoRoot(page);
        await gotoSubpill(page, 'operations-tab', 'payloads');
        await page.evaluate(() => {
            window.__payloadsReloadCalls = 0;
            window.loadToolsPage = function () { window.__payloadsReloadCalls += 1; };
        });
        await page.evaluate(() => APP.activeDeployment.set('lab_bravo'));
        await page.waitForTimeout(120);
        const after = await page.evaluate(() => window.__payloadsReloadCalls);
        expect(after).toBeGreaterThanOrEqual(1);
    });

    test('subscriber does NOT fire reload when the sub-pill pane is hidden', async ({ page }) => {
        await gotoRoot(page);
        await gotoSubpill(page, 'operations-tab', 'beacons');
        // Stub BEACON.init so we can count direct calls.
        await page.evaluate(() => {
            BEACON.init = function () { window.__beaconInitCalls = (window.__beaconInitCalls || 0) + 1; };
        });
        // Navigate to a different sub-pill so beacons pane hides. The
        // rail-click sub-pill switch may itself call BEACON.init via the
        // sub-pill init/cleanup hooks — so we reset the counter AFTER the
        // navigation, just before the deployment-set.
        await gotoSubpill(page, 'operations-tab', 'terminal');
        await page.evaluate(() => { window.__beaconInitCalls = 0; });
        // Verify Beacons pane is actually hidden before the assertion.
        const hidden = await page.evaluate(() => {
            const p = document.getElementById('subpill-pane-beacons');
            return p && p.hidden;
        });
        expect(hidden).toBe(true);
        // Set a different deployment — the Beacons subscriber should NOT
        // fire BEACON.init since the pane is hidden.
        await page.evaluate(() => APP.activeDeployment.set('lab_bravo'));
        await page.waitForTimeout(120);
        const after = await page.evaluate(() => window.__beaconInitCalls || 0);
        expect(after).toBe(0);
    });
});

// ─────────────────────────────────────────────────────────────────────────
// PART B — "All deployments" mode
// ─────────────────────────────────────────────────────────────────────────

test.describe('v3 — "All deployments" sentinel + fleet view', () => {
    test.beforeEach(async ({ page }) => {
        await mockActiveDeployments(page, [
            { project_name: 'lab_alpha',  _filename: 'lab_alpha',  deployment_type: 'c2-adhoc',   status: 'success', owner: 'alice' },
            { project_name: 'lab_bravo',  _filename: 'lab_bravo',  deployment_type: 'c2-purple',  status: 'success', owner: 'harris' },
            { project_name: 'lab_charlie',_filename: 'lab_charlie',deployment_type: 'goad-mini',  status: 'draft',   owner: 'harris' },
        ]);
    });

    test('top-bar dropdown contains the "All deployments" sentinel entry', async ({ page }) => {
        await gotoRoot(page);
        // Open the listbox.
        await page.locator('#global-deploy-trigger').click();
        const allOption = page.locator('#global-deploy-listbox .deploy-option--all');
        await expect(allOption).toHaveCount(1);
        await expect(allOption).toContainText('All deployments');
        await expect(allOption).toContainText('Fleet view');
        // Verify the divider is present.
        await expect(page.locator('#global-deploy-listbox .deploy-option-divider')).toHaveCount(1);
        // Sentinel sits at the top of the listbox.
        const firstChildIsAll = await page.evaluate(() => {
            const lb = document.getElementById('global-deploy-listbox');
            return lb.children[0] && lb.children[0].classList.contains('deploy-option--all');
        });
        expect(firstChildIsAll).toBe(true);
    });

    test('ALL_SENTINEL constant + isAll() helper exposed', async ({ page }) => {
        await gotoRoot(page);
        const { sentinel, isAll } = await page.evaluate(() => ({
            sentinel: APP.activeDeployment.ALL_SENTINEL,
            isAll: APP.activeDeployment.isAll(),
        }));
        expect(sentinel).toBe(ALL_SENTINEL);
        expect(typeof isAll).toBe('boolean');
    });

    test('selecting "All deployments" sets the sentinel + updates trigger label', async ({ page }) => {
        await gotoRoot(page);
        await page.locator('#global-deploy-trigger').click();
        await page.locator('#global-deploy-listbox .deploy-option--all').click();
        const v = await page.evaluate(() => APP.activeDeployment.current);
        expect(v).toBe(ALL_SENTINEL);
        await expect(page.locator('#global-deploy-value')).toHaveText('All deployments');
        const isAll = await page.evaluate(() => APP.activeDeployment.isAll());
        expect(isAll).toBe(true);
    });

    // 2026-05-20 (test-fix sweep) — Bug 1: computeOperationsVisible was
    // relaxed to return true for isAll(), so the Operations top-tab + its
    // sub-pills are reachable in All-mode again. renderFleet() paints into
    // #beacons-all-mode-empty / #payloads-all-mode-empty. Terminal in
    // All-mode keeps its per-surface empty state (sessions per-server).
    test('All mode on Beacons → renders per-surface empty state', async ({ page }) => {
        await gotoRoot(page);
        await gotoSubpill(page, 'operations-tab', 'beacons');
        await page.evaluate(() => APP.activeDeployment.set('__all__'));
        await page.waitForTimeout(120);
        const empty = page.locator('#beacons-all-mode-empty .empty-state--all-mode');
        await expect(empty).toBeVisible();
        await expect(empty).toContainText(/Pick a C2 deployment|Pick a deployment/);
        const scoped = page.locator('#beacons-scoped-content');
        await expect(scoped).toBeHidden();
    });

    // 2026-05-20 (test-fix sweep) — Bug 1: now reachable in All-mode.
    test('All mode on Terminal → renders per-surface empty state', async ({ page }) => {
        await gotoRoot(page);
        await gotoSubpill(page, 'operations-tab', 'terminal');
        await page.evaluate(() => APP.activeDeployment.set('__all__'));
        await page.waitForTimeout(120);
        const empty = page.locator('#terminal-all-mode-empty .empty-state--all-mode');
        await expect(empty).toBeVisible();
        await expect(empty).toContainText(/Terminal sessions|Pick a deployment/);
        await expect(page.locator('#terminal-scoped-content')).toBeHidden();
    });

    // 2026-05-20 (test-fix sweep) — Bug 1: now reachable in All-mode.
    test('All mode on Payloads → renders per-surface empty state', async ({ page }) => {
        await gotoRoot(page);
        await gotoSubpill(page, 'operations-tab', 'payloads');
        await page.evaluate(() => APP.activeDeployment.set('__all__'));
        await page.waitForTimeout(120);
        const empty = page.locator('#payloads-all-mode-empty .empty-state--all-mode');
        await expect(empty).toBeVisible();
        await expect(empty).toContainText(/Payloads|Pick a deployment/);
        await expect(page.locator('#payloads-scoped-content')).toBeHidden();
    });

    // 2026-05-21 — Deleted: "All mode on Configure / Deploy / Bolt-ons →
    // renders empty states". Was test.skip'd because computeVisibleSubPills()
    // returns just ['manage','cleanup'] in All mode, so those three sub-pill
    // panes are unreachable. The feature is intentionally retired — Configure
    // / Deploy / Bolt-ons are inherently per-deployment surfaces; the Manage
    // fleet table at #manage-all-mode is the canonical All-mode view. The
    // associated #configure-all-mode-empty / #deploy-all-mode-empty /
    // #bolt-ons-all-mode-empty containers and the _paintAllModeEmpty() helper
    // were removed from app.js + index.html in the same commit.

    test('All mode on Manage → renders the fleet table with one row per project', async ({ page }) => {
        await gotoRoot(page);
        await gotoSubpill(page, 'deployments-tab', 'manage');
        await page.evaluate(() => APP.activeDeployment.set('__all__'));
        await page.waitForTimeout(250);
        await expect(page.locator('#manage-all-mode .manage-fleet')).toBeVisible();
        const rows = page.locator('.manage-fleet__row');
        await expect(rows).toHaveCount(3);
        await expect(rows.first()).toContainText('lab_alpha');
        await expect(page.locator('#manage-scoped-content')).toBeHidden();
    });

    test('clicking a fleet table row switches the dropdown back to that project', async ({ page }) => {
        await gotoRoot(page);
        await gotoSubpill(page, 'deployments-tab', 'manage');
        await page.evaluate(() => APP.activeDeployment.set('__all__'));
        await page.waitForTimeout(250);
        // Click the row for lab_bravo.
        const bravoRow = page.locator('.manage-fleet__row[data-fleet-project="lab_bravo"]');
        await expect(bravoRow).toBeVisible();
        await bravoRow.click();
        const v = await page.evaluate(() => APP.activeDeployment.current);
        expect(v).toBe('lab_bravo');
        // Fleet view should have hidden, scoped view visible.
        await expect(page.locator('#manage-all-mode')).toBeHidden();
        await expect(page.locator('#manage-scoped-content')).toBeVisible();
    });

    test('Cleanup pane shows the "Showing all labs" badge in All mode', async ({ page }) => {
        await gotoRoot(page);
        await gotoSubpill(page, 'deployments-tab', 'cleanup');
        await page.evaluate(() => APP.activeDeployment.set('__all__'));
        await page.waitForTimeout(120);
        const badge = page.locator('#cleanup-all-badge');
        await expect(badge).toBeVisible();
        await expect(badge).toContainText('Showing all labs');
    });

    // 2026-05-20 (test-fix sweep) — Bug 1: Operations reachable in All-mode again.
    test('"Pick a deployment" CTA opens the top-bar dropdown', async ({ page }) => {
        await gotoRoot(page);
        await gotoSubpill(page, 'operations-tab', 'beacons');
        await page.evaluate(() => APP.activeDeployment.set('__all__'));
        await page.waitForTimeout(120);
        await page.locator('#beacons-all-mode-empty [data-action="open-global-deployment-dropdown"]').click();
        await page.waitForTimeout(120);
        const expanded = await page.locator('#global-deploy-trigger').getAttribute('aria-expanded');
        expect(expanded).toBe('true');
    });

    // 2026-05-20 (test-fix sweep) — Bug 1: Operations reachable in All-mode again,
    // so the scoped-content vs all-mode-empty flip on Beacons is live too.
    test('exiting All mode (selecting a real deployment) restores scoped content', async ({ page }) => {
        await gotoRoot(page);
        await gotoSubpill(page, 'operations-tab', 'beacons');
        await page.evaluate(() => APP.activeDeployment.set('__all__'));
        await page.waitForTimeout(120);
        await expect(page.locator('#beacons-all-mode-empty')).toBeVisible();
        await page.evaluate(() => APP.activeDeployment.set('lab_alpha'));
        await page.waitForTimeout(120);
        await expect(page.locator('#beacons-all-mode-empty')).toBeHidden();
        await expect(page.locator('#beacons-scoped-content')).toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────────────
// THEME CONTRAST — verify both themes render the All-mode chrome cleanly
// ─────────────────────────────────────────────────────────────────────────

test.describe('v3 — All-mode contrast in both themes', () => {
    test.beforeEach(async ({ page }) => {
        await mockActiveDeployments(page, [
            { project_name: 'lab_alpha',  _filename: 'lab_alpha',  deployment_type: 'c2-adhoc', status: 'success' },
        ]);
    });

    for (const theme of ['dark', 'light']) {
        test(`empty-state title vs background contrast ≥ 4.5:1 — ${theme}`, async ({ page }) => {
            // 2026-05-20 — Operations sub-pills are no longer reachable
            // when __all__ is selected (see app.js:2275 +
            // computeOperationsVisible). The only All-mode empty-state
            // title that's still operator-visible is the Manage fleet
            // header (.manage-fleet__title.empty-state__title — see
            // app.js:30779), so the contrast assertion targets that.
            await gotoRoot(page);
            await setTheme(page, theme);
            await gotoSubpill(page, 'deployments-tab', 'manage');
            await page.evaluate(() => APP.activeDeployment.set('__all__'));
            await page.waitForTimeout(280);
            const titleEl = page.locator('#manage-all-mode .manage-fleet__title.empty-state__title');
            await expect(titleEl).toBeVisible();
            const { fg, bg } = await titleEl.evaluate((el) => {
                const fg = getComputedStyle(el).color;
                let bg = '';
                let p = el.parentElement;
                while (p) {
                    const c = getComputedStyle(p).backgroundColor;
                    if (c && c !== 'rgba(0, 0, 0, 0)' && c !== 'transparent') { bg = c; break; }
                    p = p.parentElement;
                }
                return { fg, bg };
            });
            const fgRgb = parseRgb(fg);
            const bgRgb = parseRgb(bg);
            if (!fgRgb || !bgRgb) {
                expect(fgRgb).not.toBeNull();
                return;
            }
            const r = ratio(fgRgb, bgRgb);
            expect(r).toBeGreaterThanOrEqual(4.5);
        });

        test(`fleet table row text vs row background contrast ≥ 4.5:1 — ${theme}`, async ({ page }) => {
            await gotoRoot(page);
            await setTheme(page, theme);
            await gotoSubpill(page, 'deployments-tab', 'manage');
            await page.evaluate(() => APP.activeDeployment.set('__all__'));
            await page.waitForTimeout(300);
            const nameEl = page.locator('.manage-fleet__name').first();
            await expect(nameEl).toBeVisible();
            // Walk up the DOM until we find a non-transparent backgroundColor.
            // The fleet row at rest has no bg of its own — it sits on
            // .manage-fleet which uses var(--bg-card).
            const { fg, bg } = await nameEl.evaluate((el) => {
                const fg = getComputedStyle(el).color;
                let bg = '';
                let p = el.parentElement;
                while (p) {
                    const c = getComputedStyle(p).backgroundColor;
                    if (c && c !== 'rgba(0, 0, 0, 0)' && c !== 'transparent') {
                        bg = c;
                        break;
                    }
                    p = p.parentElement;
                }
                return { fg, bg };
            });
            const fgRgb = parseRgb(fg);
            const bgRgb = parseRgb(bg);
            if (!fgRgb || !bgRgb) {
                expect(fgRgb).not.toBeNull();
                return;
            }
            const r = ratio(fgRgb, bgRgb);
            expect(r).toBeGreaterThanOrEqual(4.5);
        });
    }
});

// ─────────────────────────────────────────────────────────────────────────
// 2026-05-19 — Fix 1: per-pane selectors respect the top-bar dropdown on
// FIRST RENDER (not just on subsequent dropdown changes).
// ─────────────────────────────────────────────────────────────────────────

test.describe('v3 — Operations per-pane selectors sync on first render', () => {
    test.beforeEach(async ({ page, context }) => {
        // Each test in this describe needs a clean activeDeployment state
        // — sibling tests that set `__all__` in localStorage would otherwise
        // bleed into our first-render assertions through the shared browser
        // context that Playwright reuses across tests in a file.
        await context.clearCookies();
        await page.addInitScript(() => {
            try { localStorage.clear(); sessionStorage.clear(); } catch (e) { /* private mode */ }
        });
        await mockActiveDeployments(page, [
            { project_name: 'lab_alpha',  _filename: 'lab_alpha',  deployment_type: 'c2-adhoc',
              status: 'success',
              output: { cs_connection_info: { value: { rest_api_enabled: true, host: '10.0.0.5' } } } },
            { project_name: 'lab_bravo',  _filename: 'lab_bravo',  deployment_type: 'c2-purple',
              status: 'success',
              output: { cs_connection_info: { value: { rest_api_enabled: true, host: '10.0.0.6' } } } },
        ]);
        // Stub /api/tools/projects so the payloads selector populates.
        await page.route('**/api/tools/projects**', async (route) => {
            await route.fulfill({
                status: 200, contentType: 'application/json',
                body: JSON.stringify({
                    success: true,
                    projects: [
                        { name: 'lab_alpha', deployment_type: 'c2-adhoc' },
                        { name: 'lab_bravo', deployment_type: 'c2-purple' },
                    ],
                }),
            });
        });
    });

    test('Beacons sub-pill: per-pane selector aligns to top-bar on activation', async ({ page }) => {
        await gotoRoot(page);
        // Set top-bar dropdown BEFORE entering the Beacons sub-pill — this
        // is the bug condition. With the fix, first-render must sync the
        // per-pane selector to the global value.
        await page.evaluate(() => APP.activeDeployment.set('lab_bravo'));
        await page.waitForTimeout(60);
        await gotoSubpill(page, 'operations-tab', 'beacons');
        // Wait for the per-pane selector to match the global. The polling
        // helper retries for ~1.5s after BEACON.init populates options;
        // the wait below covers both the populate + sync.
        await page.waitForFunction(() => {
            const el = document.getElementById('beacon-deployment-select');
            if (!el || !el.options || el.options.length < 2) return false;
            const opt = el.options[el.selectedIndex];
            return opt && (opt.dataset.filename === 'lab_bravo' || opt.value === 'lab_bravo');
        }, null, { timeout: 5000 });
        const filename = await page.evaluate(() => {
            const el = document.getElementById('beacon-deployment-select');
            const opt = el.options[el.selectedIndex];
            return opt ? (opt.dataset.filename || opt.value) : '';
        });
        expect(filename).toBe('lab_bravo');
    });

    test('Payloads sub-pill: per-pane selector aligns to top-bar on activation', async ({ page }) => {
        await gotoRoot(page);
        await page.evaluate(() => APP.activeDeployment.set('lab_bravo'));
        await page.waitForTimeout(60);
        await gotoSubpill(page, 'operations-tab', 'payloads');
        await page.waitForFunction(() => {
            const el = document.getElementById('tools-project-select');
            return el && el.value === 'lab_bravo';
        }, null, { timeout: 5000 });
        const v = await page.evaluate(() =>
            document.getElementById('tools-project-select').value
        );
        expect(v).toBe('lab_bravo');
    });

    test('Local override is respected — operator pick stays sticky', async ({ page }) => {
        await gotoRoot(page);
        await page.evaluate(() => APP.activeDeployment.set('lab_alpha'));
        await page.waitForTimeout(60);
        await gotoSubpill(page, 'operations-tab', 'payloads');
        await page.waitForFunction(() => {
            const el = document.getElementById('tools-project-select');
            return el && el.options && el.options.length > 1;
        }, null, { timeout: 5000 });
        // Operator picks lab_bravo from inside the pane.
        await page.evaluate(() => {
            const el = document.getElementById('tools-project-select');
            el.value = 'lab_bravo';
            el.dispatchEvent(new Event('change', { bubbles: true }));
        });
        await page.waitForTimeout(60);
        // Global goes to lab_alpha — the per-pane selector should NOT follow
        // (operator override wins).
        await page.evaluate(() => APP.activeDeployment.set('lab_alpha'));
        await page.waitForTimeout(120);
        const v = await page.evaluate(() =>
            document.getElementById('tools-project-select').value
        );
        expect(v).toBe('lab_bravo');
    });
});

// ─────────────────────────────────────────────────────────────────────────
// 2026-05-19 — Fix 2: aggregate fleet views for Beacons + Payloads in
// "All deployments" mode.
// ─────────────────────────────────────────────────────────────────────────

// 2026-05-20 (test-fix sweep) — Bug 1: APP.computeOperationsVisible() now
// returns true for isAll() so the aggregate fleet views are reachable.
// APP.beacons.renderFleet() / APP.payloads.renderFleet() paint into
// #beacons-all-mode-empty / #payloads-all-mode-empty when the operator
// is on the relevant sub-pill and the dropdown flips to __all__.
test.describe('v3 — Operations All-mode aggregate fleet views', () => {
    test.beforeEach(async ({ context, page }) => {
        await context.clearCookies();
        await page.addInitScript(() => {
            try { localStorage.clear(); sessionStorage.clear(); } catch (e) { /* private mode */ }
        });
    });

    test('Beacons All mode: renders aggregate table with one row per beacon', async ({ page }) => {
        await mockActiveDeployments(page, [
            { project_name: 'lab_alpha', _filename: 'lab_alpha', deployment_type: 'c2-adhoc', status: 'success' },
            { project_name: 'lab_bravo', _filename: 'lab_bravo', deployment_type: 'c2-purple', status: 'success' },
        ], {
            beaconAll: {
                success: true,
                beacons: [
                    { deployment: 'lab_alpha', id: 'b1001', operator: 'alice', host: 'WIN-01', pid: 4242, last: 1716100000, is_dead: false },
                    { deployment: 'lab_bravo', id: 'b2002', operator: 'harris', host: 'WIN-02', pid: 5151, last: 1716100123, is_dead: false },
                ],
                errors: [],
                deployments_polled: 2,
            },
        });
        await gotoRoot(page);
        await gotoSubpill(page, 'operations-tab', 'beacons');
        await page.evaluate(() => APP.activeDeployment.set('__all__'));
        await page.waitForTimeout(200);
        await expect(page.locator('#beacons-all-mode-empty .ops-fleet--beacons')).toBeVisible();
        const rows = page.locator('#beacons-all-mode-empty .ops-fleet__row');
        await expect(rows).toHaveCount(2);
        await expect(rows.first()).toContainText('b1001');
        await expect(rows.first()).toContainText('lab_alpha');
        await expect(rows.last()).toContainText('b2002');
    });

    test('Beacons All mode: row click deep-links to the deployment', async ({ page }) => {
        await mockActiveDeployments(page, [
            { project_name: 'lab_alpha', _filename: 'lab_alpha', deployment_type: 'c2-adhoc',  status: 'success' },
            { project_name: 'lab_bravo', _filename: 'lab_bravo', deployment_type: 'c2-purple', status: 'success' },
        ], {
            beaconAll: {
                success: true,
                beacons: [
                    { deployment: 'lab_bravo', id: 'b2002', operator: 'harris', host: 'WIN-02', pid: 5151, last: 1716100123, is_dead: false },
                ],
                errors: [], deployments_polled: 2,
            },
        });
        await gotoRoot(page);
        await gotoSubpill(page, 'operations-tab', 'beacons');
        await page.evaluate(() => APP.activeDeployment.set('__all__'));
        await page.waitForTimeout(200);
        await page.locator('#beacons-all-mode-empty .ops-fleet__row').first().click();
        await page.waitForTimeout(120);
        const v = await page.evaluate(() => APP.activeDeployment.current);
        expect(v).toBe('lab_bravo');
    });

    test('Beacons All mode: zero beacons falls back to empty state with fleet copy', async ({ page }) => {
        await mockActiveDeployments(page, [
            { project_name: 'lab_alpha', _filename: 'lab_alpha', deployment_type: 'c2-adhoc', status: 'success' },
        ]);
        await gotoRoot(page);
        await gotoSubpill(page, 'operations-tab', 'beacons');
        await page.evaluate(() => APP.activeDeployment.set('__all__'));
        await page.waitForTimeout(200);
        const empty = page.locator('#beacons-all-mode-empty .empty-state--all-mode');
        await expect(empty).toBeVisible();
        await expect(empty).toContainText(/No active beacons across the fleet|No team server/);
    });

    test('Payloads All mode: renders aggregate read-only history with sticky banner', async ({ page }) => {
        // The mock returns the payloads in the order the backend would
        // emit them — newest first (the route sorts by generated_at desc).
        await mockActiveDeployments(page, [
            { project_name: 'lab_alpha', _filename: 'lab_alpha', deployment_type: 'c2-adhoc', status: 'success' },
        ], {
            payloadsAll: {
                success: true,
                payloads: [
                    { name: 'beacon.dll',   type: 'dll', deployment: 'lab_alpha', generated_by: 'harris', generated_at: 1716101000, status: 'success', size_mb: 0.8, download: null, transfer_id: 'abc2' },
                    { name: 'loader.exe',   type: 'exe', deployment: 'lab_alpha', generated_by: 'alice',  generated_at: 1716100000, status: 'success', size_mb: 1.4, download: null, transfer_id: 'abc1' },
                ],
                errors: [],
            },
        });
        await gotoRoot(page);
        await gotoSubpill(page, 'operations-tab', 'payloads');
        await page.evaluate(() => APP.activeDeployment.set('__all__'));
        await page.waitForTimeout(200);
        const fleet = page.locator('#payloads-all-mode-empty .ops-fleet--payloads');
        await expect(fleet).toBeVisible();
        await expect(fleet.locator('.ops-fleet__banner-text')).toContainText(/picking a specific deployment/);
        const rows = page.locator('#payloads-all-mode-empty .ops-fleet__row');
        await expect(rows).toHaveCount(2);
        await expect(rows.first()).toContainText('beacon.dll');
        await expect(rows.last()).toContainText('loader.exe');
        // Scoped content (generator form) hidden in All mode.
        await expect(page.locator('#payloads-scoped-content')).toBeHidden();
    });

    test('Aggregate endpoint errors surface as a footnote', async ({ page }) => {
        await mockActiveDeployments(page, [
            { project_name: 'lab_alpha', _filename: 'lab_alpha', deployment_type: 'c2-adhoc',  status: 'success' },
            { project_name: 'lab_bravo', _filename: 'lab_bravo', deployment_type: 'c2-purple', status: 'success' },
        ], {
            beaconAll: {
                success: true,
                beacons: [
                    { deployment: 'lab_alpha', id: 'b1001', operator: 'alice', host: 'WIN-01', pid: 4242, last: 1716100000, is_dead: false },
                ],
                errors: [{ deployment: 'lab_bravo', error: 'REST API unreachable' }],
                deployments_polled: 2,
            },
        });
        await gotoRoot(page);
        await gotoSubpill(page, 'operations-tab', 'beacons');
        await page.evaluate(() => APP.activeDeployment.set('__all__'));
        await page.waitForTimeout(200);
        const errLine = page.locator('#beacons-all-mode-empty [data-fleet-errors]');
        await expect(errLine).toBeVisible();
        await expect(errLine).toContainText('lab_bravo');
    });
});
