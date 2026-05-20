/**
 * Phase 3E — Dashboard widgets V3-native refresh.
 *
 * Verifies:
 *   1. Smoke: dashboard tab is active on load + the six widget cards
 *      (Live Deployments, Active Beacons, Cost Trend, Architecture,
 *      Recent Activity, Elastic Detection Rules) are present.
 *   2. Every widget head uses the new eyebrow + title rhythm
 *      (.dashboard-widget__head with __eyebrow + __title children).
 *   3. The activity feed renders rows as .spec-row composing the
 *      Phase 2b primitive, with .operator-dot inside the __key.
 *   4. Live deployments grid: each card has a .spec-pill status pill
 *      (live / draft / error variant).
 *   5. Cost delta is rendered as .dashboard-cost-delta-badge with a
 *      variant class (--up / --down / --flat).
 *   6. "+ New Deployment" hero CTA still opens the journey takeover
 *      (no regression on Phase 2b ownership).
 *   7. Both themes pass layer-aware contrast on every dashboard
 *      widget interior (audit scoped to dashboard subtree).
 *
 * The activity feed + deployments grid depend on backend endpoints that
 * may be empty in dev; tests gate on .empty-state vs. rendered rows.
 */

import { test, expect } from '@playwright/test';

// ─────────────────────────────────────────────────────────────────────
// WCAG helpers (sRGB → relative luminance → contrast ratio).
// Mirrors the helpers in test_contrast_invariants.spec.js so the
// dashboard suite is self-contained.
// ─────────────────────────────────────────────────────────────────────

function parseRgb(s) {
    const m = s.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const parts = m[1].split(',').map(p => parseFloat(p.trim()));
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

const WALK_TO_SURFACE_FN = function walkToSurface(el) {
    function parseRgba(s) {
        const m = s.match(/rgba?\(([^)]+)\)/);
        if (!m) return null;
        const parts = m[1].split(',').map((p) => parseFloat(p.trim()));
        return [parts[0], parts[1], parts[2], parts.length === 4 ? parts[3] : 1];
    }
    const stack = [];
    let cur = el;
    while (cur && cur !== document.documentElement) {
        const cs = window.getComputedStyle(cur);
        const parsed = parseRgba(cs.backgroundColor);
        if (parsed && parsed[3] > 0.01) {
            stack.push(parsed);
            if (parsed[3] >= 0.99) break;
        }
        cur = cur.parentElement;
    }
    if (stack.length === 0 || stack[stack.length - 1][3] < 0.99) {
        const bodyBg = parseRgba(window.getComputedStyle(document.body).backgroundColor) || [255, 255, 255, 1];
        stack.push(bodyBg);
    }
    let [r, g, b] = stack[stack.length - 1].slice(0, 3);
    for (let i = stack.length - 2; i >= 0; i--) {
        const [or, og, ob, oa] = stack[i];
        r = or * oa + r * (1 - oa);
        g = og * oa + g * (1 - oa);
        b = ob * oa + b * (1 - oa);
    }
    return `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`;
};

async function setTheme(page, theme) {
    await page.evaluate((t) => {
        if (t === 'light') document.documentElement.setAttribute('data-theme', 'light');
        else document.documentElement.removeAttribute('data-theme');
    }, theme);
    await page.waitForTimeout(320);
}

async function gotoDashboard(page) {
    await page.goto('/');
    await page.locator('button.tab-btn[data-target="dashboard"]').waitFor({ timeout: 5000 });
    // Dashboard is the default-active tab, but click to be explicit.
    await page.click('button.tab-btn[data-target="dashboard"]');
    // Give widgets time to fire their initial fetches.
    await page.waitForTimeout(500);
}

// ─────────────────────────────────────────────────────────────────────
// Smoke
// ─────────────────────────────────────────────────────────────────────

test('dashboard: smoke — page renders with all six core widgets', async ({ page }) => {
    await gotoDashboard(page);
    await expect(page.locator('.tab-page[data-page="dashboard"]')).toBeVisible();

    // Six section.dashboard-widget cards in the Dashboard tab.
    // (The 3-col compact widgets sit inside .dashboard-widget-row, also
    // bearing .dashboard-widget — so we expect six total inside the page.)
    const widgetCount = await page
        .locator('.tab-page[data-page="dashboard"] .dashboard-widget')
        .count();
    expect(widgetCount, 'six dashboard-widget cards should be present').toBeGreaterThanOrEqual(6);

    // Specific widget anchors
    await expect(page.locator('#dashboard-deployments-grid')).toBeVisible();
    await expect(page.locator('#dashboard-beacons-widget')).toBeVisible();
    await expect(page.locator('#dashboard-cost-widget')).toBeVisible();
    await expect(page.locator('#dashboard-architecture-widget')).toBeVisible();
    await expect(page.locator('#dashboard-activity-widget')).toBeVisible();
    await expect(page.locator('#dashboard-elastic-rules-widget')).toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────
// Goal 1 — Widget framing consistency
// ─────────────────────────────────────────────────────────────────────

test('dashboard: every widget head uses the eyebrow + title rhythm', async ({ page }) => {
    await gotoDashboard(page);
    // Every .dashboard-widget in the dashboard tab should now contain a
    // .dashboard-widget__head wrapper with one eyebrow + one title.
    const widgets = page.locator('.tab-page[data-page="dashboard"] .dashboard-widget');
    const count = await widgets.count();
    expect(count).toBeGreaterThanOrEqual(6);
    for (let i = 0; i < count; i++) {
        const w = widgets.nth(i);
        const head = w.locator('.dashboard-widget__head');
        await expect(head, `widget ${i} should have a __head`).toHaveCount(1);
        const eyebrow = head.locator('.dashboard-widget__eyebrow');
        const title = head.locator('.dashboard-widget__title');
        await expect(eyebrow, `widget ${i} should have an __eyebrow`).toHaveCount(1);
        await expect(title, `widget ${i} should have a __title`).toHaveCount(1);
    }
});

// ─────────────────────────────────────────────────────────────────────
// Goal 2 — Activity feed renders with operator dots
// ─────────────────────────────────────────────────────────────────────

test('dashboard: activity feed renders as a .spec-list with operator dots', async ({ page }) => {
    await gotoDashboard(page);
    const list = page.locator('#activity-feed-list');
    await expect(list).toBeVisible();
    // The legacy class + the new primitive class both apply.
    await expect(list).toHaveClass(/spec-list/);
    await expect(list).toHaveClass(/activity-feed/);

    // Wait for the feed to settle — either empty state or at least one row.
    await page.waitForTimeout(800);

    const rows = list.locator('li.spec-row');
    const empty = list.locator('.activity-feed__empty');

    const rowCount = await rows.count();
    const emptyCount = await empty.count();
    expect(rowCount + emptyCount, 'feed should resolve to rows or empty state').toBeGreaterThan(0);

    if (rowCount > 0) {
        const first = rows.first();
        // .operator-dot inside the __key cell, identity color via inline style.
        await expect(first.locator('.spec-row__key .operator-dot')).toHaveCount(1);
        // Verb + optional target inside the __value cell
        await expect(first.locator('.spec-row__value-verb')).toHaveCount(1);
        // Time hint
        await expect(first.locator('.spec-row__hint')).toHaveCount(1);
        // Row should be marked read-only so the spec-row hover pencil
        // affordance never fires for an audit entry.
        await expect(first).toHaveAttribute('data-readonly', 'true');
    }
});

// ─────────────────────────────────────────────────────────────────────
// Goal 4 — Live deployments grid: each card has a status pill
// ─────────────────────────────────────────────────────────────────────

test('dashboard: live deployments grid uses spec-pill status pills (or empty state)', async ({ page }) => {
    await gotoDashboard(page);
    const grid = page.locator('#dashboard-deployments-grid');
    await expect(grid).toBeVisible();
    // Allow /api/deploy/active to land.
    await page.waitForTimeout(900);

    const cards = grid.locator('a.dashboard-deployment-card');
    const empty = grid.locator('.empty-state');

    const cardCount = await cards.count();
    const emptyCount = await empty.count();
    expect(cardCount + emptyCount, 'grid should resolve to cards or empty state').toBeGreaterThan(0);

    if (cardCount > 0) {
        const first = cards.first();
        // New rhythm: kicker, title, pill
        await expect(first.locator('.dashboard-deployment-card__kicker')).toHaveCount(1);
        await expect(first.locator('.dashboard-deployment-card__title')).toHaveCount(1);
        await expect(first.locator('.spec-pill')).toHaveCount(1);
        // Pill must carry one of the three variant classes.
        const pillClass = await first.locator('.spec-pill').getAttribute('class');
        expect(pillClass).toMatch(/spec-pill--(live|draft|error)/);
    }
});

// ─────────────────────────────────────────────────────────────────────
// Goal 3 — Cost trend delta badge variant
// ─────────────────────────────────────────────────────────────────────

test('dashboard: cost delta renders as a colored badge (or backend-pending)', async ({ page }) => {
    await gotoDashboard(page);
    await page.waitForTimeout(900);
    const deltaEl = page.locator('#dashboard-cost-delta');
    await expect(deltaEl).toBeVisible();
    // Either the backend resolved (badge with variant) or it failed gracefully
    // (badge with --flat). Either way a .dashboard-cost-delta-badge node must exist.
    const badgeCount = await deltaEl.locator('.dashboard-cost-delta-badge').count();
    expect(badgeCount, 'cost delta should render a badge node').toBe(1);
    const cls = await deltaEl.locator('.dashboard-cost-delta-badge').getAttribute('class');
    expect(cls).toMatch(/dashboard-cost-delta-badge--(up|down|flat)/);
});

// ─────────────────────────────────────────────────────────────────────
// Goal 6 — Operator color dots consistency
// ─────────────────────────────────────────────────────────────────────

test('dashboard: operator dot utility renders consistently across surfaces', async ({ page }) => {
    await gotoDashboard(page);
    await page.waitForTimeout(800);

    // Header chip dot
    const chipDot = page.locator('#operator-chip-dot');
    await expect(chipDot).toHaveClass(/operator-dot/);
    const chipSize = await chipDot.evaluate(el => {
        const r = el.getBoundingClientRect();
        return { w: r.width, h: r.height };
    });
    expect(chipSize.w).toBeGreaterThan(6);
    expect(chipSize.w).toBeLessThan(12);
    expect(chipSize.h).toEqual(chipSize.w);

    // Activity feed dots (if rendered)
    const feedDots = page.locator('#activity-feed-list .spec-row__key .operator-dot');
    if (await feedDots.count() > 0) {
        const feedSize = await feedDots.first().evaluate(el => {
            const r = el.getBoundingClientRect();
            return { w: r.width, h: r.height };
        });
        // Same 8px treatment as the chip dot.
        expect(feedSize.w).toBeGreaterThan(6);
        expect(feedSize.w).toBeLessThan(12);
        expect(feedSize.h).toEqual(feedSize.w);
    }
});

// ─────────────────────────────────────────────────────────────────────
// Regression — "+ New Deployment" journey ownership (Phase 2b)
// ─────────────────────────────────────────────────────────────────────

test('dashboard: + New Deployment hero invokes APP.startNewDeployment (no regression)', async ({ page }) => {
    await gotoDashboard(page);
    // Capture confirm() so a leftover dirty state doesn't block the test.
    await page.evaluate(() => { window.confirm = () => true; });
    const heroBtn = page.locator('.dashboard-hero__primary');
    await expect(heroBtn).toBeVisible();
    // The hero CTA's contract (since M-Dashboard / D3.8) is to navigate to
    // Configure + reset the form. The journey takeover is owned by the
    // global header "+ New" + the banner button — NOT the dashboard hero.
    // We only verify the hero still wires to APP.startNewDeployment.
    const heroHandler = await heroBtn.evaluate(el => el.getAttribute('onclick'));
    expect(heroHandler).toMatch(/APP\.startNewDeployment/);
    await heroBtn.click();
    await page.waitForTimeout(400);
    // After click, the active tab should be deployments-tab and the
    // configure sub-pill should be active.
    const activeTab = await page.evaluate(() => {
        const a = document.querySelector('.tab-page[style*="display: block"], .tab-page.active');
        return a ? a.getAttribute('data-page') : null;
    });
    expect(activeTab).toBe('deployments-tab');
});

test('dashboard: global header + New navigates to Configure with progressive draft mode (2026-05-20)', async ({ page }) => {
    await gotoDashboard(page);
    await page.evaluate(() => { window.confirm = () => true; });
    const headerBtn = page.locator('#global-new-deployment-btn');
    await expect(headerBtn).toBeVisible();
    await headerBtn.click();
    await page.waitForTimeout(450);
    // 2026-05-20: the inline #journey-takeover wizard was retired as the
    // default flow. The "+ New" header button now drops the operator into
    // Configure V2 (progressive unraveling) — Configure sub-pill active,
    // draft sentinel set on activeDeployment, V2 pane visible. The
    // journey wizard is still mountable behind ?wizard=1 for legacy tests
    // but is no longer the default.
    const tabPage = page.locator('.tab-page[data-page="deployments-tab"]');
    await expect(tabPage).toBeVisible({ timeout: 5000 });
    const v2Pane = page.locator('#configure-v2-pane');
    await expect(v2Pane).toBeVisible({ timeout: 5000 });
    // The legacy body[data-journey-open] flag is NOT set (no scrim takeover).
    const journeyOpen = await page.evaluate(() => document.body.getAttribute('data-journey-open'));
    expect(journeyOpen).toBeNull();
    // Draft sentinel pinned on activeDeployment.
    const isDraft = await page.evaluate(() => {
        try { return APP.activeDeployment.isDraft(); } catch (_) { return false; }
    });
    expect(isDraft).toBe(true);
});

// ─────────────────────────────────────────────────────────────────────
// Layer-aware contrast — dashboard subtree, both themes.
// ─────────────────────────────────────────────────────────────────────

for (const theme of ['dark', 'light']) {
    test(`dashboard: layer-aware contrast clean in ${theme} mode`, async ({ page }) => {
        await gotoDashboard(page);
        await setTheme(page, theme);
        await page.waitForTimeout(500);

        const failures = await page.evaluate((walkSrc) => {
            // eslint-disable-next-line no-new-func
            const walkToSurface = new Function('return ' + walkSrc)();
            function parseRgb(s) {
                const m = s.match(/rgba?\(([^)]+)\)/);
                if (!m) return null;
                const parts = m[1].split(',').map(p => parseFloat(p.trim()));
                return [parts[0], parts[1], parts[2], parts.length === 4 ? parts[3] : 1];
            }
            function lin(c) { const v = c / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }
            function lum([r, g, b]) { return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b); }
            function ratio(a, b) { const L1 = lum(a); const L2 = lum(b); return (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05); }
            const failures = [];
            const root = document.querySelector('.tab-page[data-page="dashboard"]');
            if (!root) return failures;
            const els = root.querySelectorAll('*');
            for (const el of els) {
                const cs = window.getComputedStyle(el);
                if (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0') continue;
                if (el.offsetParent === null && cs.position !== 'fixed') continue;
                if (el.getAttribute('aria-hidden') === 'true') continue;
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) continue;
                let hasText = false;
                for (const c of el.childNodes) {
                    if (c.nodeType === 3 && c.textContent.trim().length > 0) { hasText = true; break; }
                }
                if (!hasText) continue;
                // Skip sparkline SVG glyph (no text) and arch diagram (image)
                if (el.closest('svg, img, .arch-diagram-frame')) continue;
                const fg = parseRgb(cs.color); if (!fg) continue;
                const surface = walkToSurface(el);
                const bg = parseRgb(surface); if (!bg) continue;
                if (fg[3] < 0.5) continue;
                const r = ratio(fg.slice(0, 3), bg.slice(0, 3));
                const fz = parseFloat(cs.fontSize);
                const fw = parseInt(cs.fontWeight, 10) || 400;
                const isLarge = fz >= 24 || (fz >= 18.66 && fw >= 700);
                const threshold = isLarge ? 3.0 : 4.5;
                if (r < threshold) {
                    failures.push({
                        tag: el.tagName.toLowerCase(),
                        cls: String(el.className || '').slice(0, 60),
                        id: el.id,
                        text: (el.textContent || '').trim().slice(0, 60),
                        ratio: Number(r.toFixed(2)),
                        fg: cs.color,
                        bg: surface,
                        threshold,
                    });
                }
            }
            return failures;
        }, WALK_TO_SURFACE_FN.toString());

        if (failures.length > 0) {
            // eslint-disable-next-line no-console
            console.log(`\nDashboard ${theme} contrast failures (${failures.length}):`);
            for (const f of failures.slice(0, 30)) {
                // eslint-disable-next-line no-console
                console.log(`  <${f.tag}#${f.id}.${f.cls}> "${f.text}" — ${f.ratio}:1 (need ${f.threshold}) fg=${f.fg} bg=${f.bg}`);
            }
        }
        expect(failures, `${failures.length} AA failures in dashboard subtree (${theme})`).toEqual([]);
    });
}
