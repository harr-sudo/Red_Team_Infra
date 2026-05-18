/**
 * Phase 3B — Operations tab interiors (Beacons + Terminal + Payloads).
 *
 * Scope (per the phase brief):
 *   1. Beacons sub-pill: spec-list renders, row click opens the detail
 *      panel, "driven by" attribution surfaces when audit has data.
 *   2. Terminal sub-pill: tab strip renders with operator color dots.
 *   3. Payloads sub-pill: two-column layout renders + spec-list summary.
 *   4. Layer-aware contrast clean in both themes for the visible
 *      Operations surface.
 *
 * The Flask backend is expected on http://127.0.0.1:5050. CS REST API
 * connectivity is NOT required — tests that need beacons inject
 * synthetic beacons via BEACON.cachedBeacons + BEACON.renderBeaconSpecList.
 */

import { test, expect } from '@playwright/test';

const SUBPILL_BEACONS  = '#subpill-beacons';
const SUBPILL_TERMINAL = '#subpill-terminal';
const SUBPILL_PAYLOADS = '#subpill-payloads';

async function setTheme(page, theme) {
    await page.evaluate((t) => {
        if (t === 'light') document.documentElement.setAttribute('data-theme', 'light');
        else document.documentElement.removeAttribute('data-theme');
    }, theme);
    await page.waitForTimeout(280);
}

async function gotoOperations(page, subpill = 'beacons') {
    await page.goto('/');
    await page.locator('button.tab-btn[data-target="operations-tab"]').waitFor({ timeout: 5000 });
    await page.click('button.tab-btn[data-target="operations-tab"]');
    await page.waitForTimeout(150);
    const map = { beacons: SUBPILL_BEACONS, terminal: SUBPILL_TERMINAL, payloads: SUBPILL_PAYLOADS };
    await page.locator(map[subpill]).click();
    await page.waitForTimeout(250);
}

// Inject a synthetic beacon list and trigger the V3 render. The
// production code path reaches here via BEACON.refreshBeacons() →
// renderBeaconTable() → renderBeaconSpecList(). We call the public
// render method directly so the test doesn't depend on CS REST API.
async function injectFakeBeacons(page, beacons) {
    await page.evaluate((bs) => {
        BEACON.cachedBeacons = bs.map(b => Object.assign({
            alive: true, sleep: 60000, jitter: 5, lastCheckinMs: 0,
            fetchedAt: Date.now(), os: 'Windows 10', arch: 'x64',
        }, b));
        // Force parent containers visible so the spec-list is in the
        // visible viewport. The production code path makes these visible
        // when BEACON.connect() succeeds; in tests we short-circuit.
        const noDep   = document.getElementById('beacon-no-deployment');
        const notEn   = document.getElementById('beacon-not-enabled');
        const main    = document.getElementById('beacon-main-content');
        const sec     = document.getElementById('beacon-table-section');
        const empty   = document.getElementById('beacon-empty-state');
        if (noDep)  noDep.style.display = 'none';
        if (notEn)  notEn.style.display = 'none';
        if (main)   main.style.display = 'block';
        if (sec)    sec.style.display  = 'block';
        if (empty)  empty.style.display = 'none';
        BEACON.renderBeaconTable(BEACON.cachedBeacons);
        BEACON.renderBeaconSpecList(BEACON.cachedBeacons);
    }, beacons);
}

// ── 1. Beacons sub-pill ───────────────────────────────────────────────

test('Beacons: V3 spec-list renders rows for active beacons', async ({ page }) => {
    await gotoOperations(page, 'beacons');
    await injectFakeBeacons(page, [
        { bid: 'b1', user: 'alice', computer: 'WS-01', internal: '10.0.1.5', pid: 4711 },
        { bid: 'b2', user: 'bob',   computer: 'DC-01', internal: '10.0.1.2', pid: 8123, isAdmin: true },
    ]);
    const list = page.locator('#beacons-spec-list');
    await expect(list).toBeVisible();
    const rows = list.locator('li.spec-row');
    await expect(rows).toHaveCount(2);
    await expect(rows.first().locator('.ops-beacons-row__bid')).toContainText('b1');
    await expect(rows.first().locator('.spec-pill')).toBeVisible();
});

test('Beacons: clicking a row opens the detail panel (interact)', async ({ page }) => {
    await gotoOperations(page, 'beacons');
    await injectFakeBeacons(page, [
        { bid: 'b9', user: 'eve', computer: 'WS-09', internal: '10.0.2.9', pid: 1234 },
    ]);
    await page.locator('#beacons-spec-list li.spec-row[data-bid="b9"] .spec-row__head').click();
    await page.waitForTimeout(250);
    const panel = page.locator('#beacon-interact-panel');
    await expect(panel).toBeVisible();
    // Detail spec-list emitted
    const detail = page.locator('#beacon-detail-spec-list');
    await expect(detail).toBeVisible();
    const detailRows = detail.locator('.spec-row');
    await expect(detailRows).not.toHaveCount(0);
    // Selected state mirrored
    await expect(page.locator('#beacons-spec-list li.spec-row[data-bid="b9"]'))
        .toHaveAttribute('data-selected', 'true');
});

test('Beacons: "driven by" attribution surfaces when audit returns a match', async ({ page }) => {
    await gotoOperations(page, 'beacons');
    // Stub /api/audit so fetchDrivenBy resolves with a known operator
    await page.route('**/api/audit**', async (route) => {
        const url = new URL(route.request().url());
        if (url.searchParams.get('action_prefix') === 'beacon.exec') {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    success: true,
                    entries: [
                        { ts: new Date().toISOString(), op: 'op-test', action: 'beacon.exec',
                          target: 'driven-bid', details: { command: 'ls' } },
                    ],
                }),
            });
            return;
        }
        await route.continue();
    });

    // Seed an operator profile so the dot color resolves
    await page.evaluate(() => {
        APP.operator.all = [{ id: 'op-test', display: 'Test Op', color: '#a31621' }];
    });

    await injectFakeBeacons(page, [
        { bid: 'driven-bid', user: 'alice', computer: 'WS-DRIVEN', internal: '10.0.0.1', pid: 5 },
    ]);
    await page.locator('#beacons-spec-list li.spec-row[data-bid="driven-bid"] .spec-row__head').click();
    await page.waitForTimeout(400);

    const pill = page.locator('[data-driven-by-pill]');
    await expect(pill).toBeVisible();
    await expect(pill).toContainText(/Test Op/i);
});

// ── 2. Terminal sub-pill ──────────────────────────────────────────────

test('Terminal: tab strip renders with operator color dots', async ({ page }) => {
    await gotoOperations(page, 'terminal');

    // Seed APP.operator so the dot color resolves
    await page.evaluate(() => {
        APP.operator.current = { id: 'op-yellow', display: 'Yellow', color: '#65a30d' };
        APP.operator.all = [
            { id: 'op-yellow', display: 'Yellow', color: '#65a30d' },
            { id: 'op-blue',   display: 'Blue',   color: '#3b82f6' },
        ];
    });

    // Add a tab directly via TERMINAL._addTab — exercises the V3 chrome
    // render path without depending on xterm.js / websocket.
    await page.evaluate(() => {
        TERMINAL._addTab('term_test_yellow', 'Local Shell', 'op-yellow');
        TERMINAL._addTab('term_test_blue',   'SSH ▸ bastion', 'op-blue');
    });

    const tab1 = page.locator('#terminal-tab-bar .terminal-tab[data-term-id="term_test_yellow"]');
    const tab2 = page.locator('#terminal-tab-bar .terminal-tab[data-term-id="term_test_blue"]');
    await expect(tab1).toBeVisible();
    await expect(tab2).toBeVisible();

    // Operator dot is the right color (computed style)
    const dot1Bg = await tab1.locator('.terminal-tab__op-dot').evaluate(el => getComputedStyle(el).backgroundColor);
    const dot2Bg = await tab2.locator('.terminal-tab__op-dot').evaluate(el => getComputedStyle(el).backgroundColor);
    // #65a30d → rgb(101, 163, 13); #3b82f6 → rgb(59, 130, 246)
    expect(dot1Bg).toBe('rgb(101, 163, 13)');
    expect(dot2Bg).toBe('rgb(59, 130, 246)');

    // V3 SVG close affordance exists
    await expect(tab1.locator('.terminal-tab__close svg use[href="#icon-x"]')).toHaveCount(1);

    // "+" new-tab button is still last
    const newTab = page.locator('#terminal-tab-bar .terminal-tab.terminal-tab-new');
    await expect(newTab).toBeVisible();
});

// ── 3. Payloads sub-pill ──────────────────────────────────────────────

test('Payloads: two-column layout renders with parameter spec-list', async ({ page }) => {
    await gotoOperations(page, 'payloads');
    const grid = page.locator('#ops-payloads-grid');
    await expect(grid).toBeVisible();
    // Both columns mounted
    await expect(grid.locator('#ops-payloads-form')).toBeVisible();
    await expect(grid.locator('#ops-payloads-preview')).toBeVisible();
    // Grid is actually two columns at desktop width (Playwright defaults
    // to ~1280px viewport for Chromium).
    const cols = await grid.evaluate(el => {
        const cs = window.getComputedStyle(el);
        return cs.gridTemplateColumns.split(' ').length;
    });
    expect(cols).toBeGreaterThanOrEqual(2);

    // Parameter spec-list rendered
    const spec = page.locator('#ops-payloads-spec-list .spec-row');
    await expect(spec).not.toHaveCount(0);
    // Pill present (DRAFT until something is staged)
    await expect(page.locator('#ops-payloads-spec-pill')).toBeVisible();
});

test('Payloads: artifact rows render with Download + View action buttons', async ({ page }) => {
    await gotoOperations(page, 'payloads');
    await page.evaluate(() => {
        APP.payloads.clearArtifacts();
        APP.payloads.addArtifact({ name: 'beacon.x64.exe', size: '262 KB', url: '/static/test.bin' });
        APP.payloads.addArtifact({ name: 'profile.dll',    size: '180 KB' });
    });
    const list = page.locator('#ops-payloads-artifacts-list');
    await expect(list).toBeVisible();
    await expect(list.locator('li.spec-row')).toHaveCount(2);
    // The artifact WITH a url renders both Download + View buttons.
    // (addArtifact unshifts, so the one with url is the second-added but
    // most-recent row in the list after the test seeds both.)
    const rows = list.locator('li.spec-row');
    const totalButtons = await rows.locator('.ops-payloads-artifact__btn').count();
    expect(totalButtons).toBeGreaterThanOrEqual(3);  // 2 on download row + 1 on the no-url row
    // The row with the url has a downloadable <a>
    await expect(list.locator('a.ops-payloads-artifact__btn[download]')).toHaveCount(1);
});

// ── 4. Contrast invariants (layer-aware) ──────────────────────────────

const auditScript = `
function parseRgb(s) {
    const m = s.match(/rgba?\\(([^)]+)\\)/);
    if (!m) return null;
    const parts = m[1].split(',').map((p) => parseFloat(p.trim()));
    return [parts[0], parts[1], parts[2], parts.length === 4 ? parts[3] : 1];
}
function lin(c) { const v = c / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }
function lum([r, g, b]) { return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b); }
function ratio(a, b) { const L1 = lum(a); const L2 = lum(b); return (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05); }
function walkToSurface(el) {
    const stack = [];
    let cur = el;
    while (cur && cur !== document.documentElement) {
        const cs = window.getComputedStyle(cur);
        const parsed = parseRgb(cs.backgroundColor);
        if (parsed && parsed[3] > 0.01) {
            stack.push(parsed);
            if (parsed[3] >= 0.99) break;
        }
        cur = cur.parentElement;
    }
    if (stack.length === 0 || stack[stack.length - 1][3] < 0.99) {
        stack.push(parseRgb(window.getComputedStyle(document.body).backgroundColor) || [255, 255, 255, 1]);
    }
    let [r, g, b] = stack[stack.length - 1].slice(0, 3);
    for (let i = stack.length - 2; i >= 0; i--) {
        const [or, og, ob, oa] = stack[i];
        r = or * oa + r * (1 - oa);
        g = og * oa + g * (1 - oa);
        b = ob * oa + b * (1 - oa);
    }
    return [Math.round(r), Math.round(g), Math.round(b)];
}
function auditRoot(sel) {
    const root = document.querySelector(sel);
    if (!root) return [];
    const failures = [];
    root.querySelectorAll('*').forEach(el => {
        const cs = window.getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0') return;
        if (el.getAttribute('aria-hidden') === 'true') return;
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return;
        let hasText = false;
        for (const c of el.childNodes) {
            if (c.nodeType === 3 && c.textContent.trim().length > 0) { hasText = true; break; }
        }
        if (!hasText) return;
        const fg = parseRgb(cs.color);
        if (!fg || fg[3] < 0.5) return;
        const bg = walkToSurface(el);
        const r = ratio(fg.slice(0, 3), bg);
        const fs = parseFloat(cs.fontSize);
        const fw = parseInt(cs.fontWeight, 10) || 400;
        const isLarge = fs >= 24 || (fs >= 18.66 && fw >= 700);
        const threshold = isLarge ? 3.0 : 4.5;
        if (r < threshold) {
            failures.push({
                tag: el.tagName.toLowerCase(),
                cls: el.className,
                text: (el.textContent || '').trim().slice(0, 40),
                ratio: Number(r.toFixed(2)),
                threshold,
                fg: cs.color,
                bg: \`rgb(\${bg.join(', ')})\`,
            });
        }
    });
    return failures;
}
return auditRoot(sel);`;

for (const theme of ['dark', 'light']) {
    test(`Beacons sub-pill passes contrast (${theme} theme)`, async ({ page }) => {
        await gotoOperations(page, 'beacons');
        await injectFakeBeacons(page, [
            { bid: 'cb1', user: 'alice', computer: 'WS-01', internal: '10.0.1.5', pid: 4711, isAdmin: true },
        ]);
        await setTheme(page, theme);
        const failures = await page.evaluate(
            new Function('sel', auditScript),
            '#subpill-pane-beacons'
        );
        if (failures.length) console.log(`Beacons (${theme}):`, JSON.stringify(failures, null, 2));
        expect(failures, `${failures.length} AA failures in ${theme}`).toEqual([]);
    });
}

for (const theme of ['dark', 'light']) {
    test(`Terminal sub-pill passes contrast (${theme} theme)`, async ({ page }) => {
        await gotoOperations(page, 'terminal');
        // Seed operator + add a tab so the chrome is actually painted
        await page.evaluate(() => {
            APP.operator.all = [{ id: 'op-yellow', display: 'Yellow', color: '#65a30d' }];
            APP.operator.current = APP.operator.all[0];
            TERMINAL._addTab('term_contrast', 'Local Shell', 'op-yellow');
        });
        await setTheme(page, theme);
        const failures = await page.evaluate(
            new Function('sel', auditScript),
            '#subpill-pane-terminal'
        );
        if (failures.length) console.log(`Terminal (${theme}):`, JSON.stringify(failures, null, 2));
        expect(failures, `${failures.length} AA failures in ${theme}`).toEqual([]);
    });
}

for (const theme of ['dark', 'light']) {
    test(`Payloads sub-pill passes contrast (${theme} theme)`, async ({ page }) => {
        await gotoOperations(page, 'payloads');
        // Seed an artifact so the artifacts list is painted
        await page.evaluate(() => {
            APP.payloads.clearArtifacts();
            APP.payloads.addArtifact({ name: 'beacon.x64.bin', size: '262 KB', url: '/static/test.bin' });
        });
        await setTheme(page, theme);
        const failures = await page.evaluate(
            new Function('sel', auditScript),
            '#subpill-pane-payloads'
        );
        if (failures.length) console.log(`Payloads (${theme}):`, JSON.stringify(failures, null, 2));
        expect(failures, `${failures.length} AA failures in ${theme}`).toEqual([]);
    });
}
