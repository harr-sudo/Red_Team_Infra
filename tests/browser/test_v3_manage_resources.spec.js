/**
 * Phase 3a.2 — Manage sub-pill: "All Deployed Resources" + "Deployment
 * History & Logs" V3-native restyle.
 *
 * User feedback called out two saturated visual elements that needed
 * removal:
 *   1. Per-resource-type AWS-icon ribbons (orange #d86613 EC2, purple
 *      #693cc5 VPC, etc.) on the far left of every resource row.
 *   2. Full-height saturated left strip on every deployment-history
 *      card (border-left: 5px solid var(--success-text)/danger-text/...).
 *
 * This spec verifies the V3-native replacement:
 *   - Resource rows render a neutral .spec-pill type badge + .spec-pill--*
 *     state pill — no saturated background colour per type.
 *   - Deployment history cards have no full-height saturated left strip;
 *     status is communicated via .spec-pill in the header.
 *   - Both themes contrast clean inside both sections.
 *
 * Skips gracefully when no project is selected / no audit data exists
 * (contrast assertions still run on the empty state).
 */

import { test, expect } from '@playwright/test';

async function setTheme(page, theme) {
    await page.evaluate((t) => {
        if (t === 'light') document.documentElement.setAttribute('data-theme', 'light');
        else document.documentElement.removeAttribute('data-theme');
    }, theme);
    await page.waitForTimeout(320);
}

async function navigateToManageSubPill(page) {
    await page.goto('/');
    await page.locator('button.tab-btn[data-target="deployments-tab"]').waitFor({ timeout: 5000 });
    await page.click('button.tab-btn[data-target="deployments-tab"]');
    await page.waitForTimeout(150);
    await page.locator('#subpill-manage').click();
    // APP.manage.render() + the resource list / timeline renders fan out async.
    await page.waitForTimeout(1100);
}

async function pickFirstAvailableProject(page) {
    const project = await page.evaluate(() => {
        if (window.APP && window.APP.activeDeployment) {
            const cur = window.APP.activeDeployment.current;
            if (cur) return cur;
        }
        const sel = document.querySelector('#header-deployment-select, #project-name');
        if (sel && sel.tagName === 'SELECT') {
            const first = Array.from(sel.options).map(o => o.value).filter(Boolean)[0];
            if (first) return first;
        }
        return null;
    });
    if (project) {
        await page.evaluate((p) => {
            if (window.APP && window.APP.activeDeployment) window.APP.activeDeployment.set(p);
        }, project);
        await page.waitForTimeout(700);
    }
    return project;
}

test('Resource list: details-card V3 chrome (chevron + caps eyebrow) is mounted', async ({ page }) => {
    await navigateToManageSubPill(page);
    const card = page.locator('#resource-list-section details.details-card--v3');
    await expect(card).toHaveCount(1);
    // Chevron is a real SVG (not a unicode triangle).
    await expect(card.locator('.details-card__chevron')).toHaveCount(1);
    // Eyebrow caps label sits above the title text.
    await expect(card.locator('.details-card__eyebrow')).toContainText(/DEPLOYED INVENTORY/i);
    await expect(card.locator('.details-card__title')).toContainText(/All Deployed Resources/i);
});

test('Resource list: chevron rotates on expand (motion behaviour confirmed)', async ({ page }) => {
    await navigateToManageSubPill(page);
    const summary = page.locator('#resource-list-section details.details-card--v3 > summary');
    const chevron = page.locator('#resource-list-section .details-card__chevron');
    const transformClosed = await chevron.evaluate(el => window.getComputedStyle(el).transform);
    await summary.click();
    await page.waitForTimeout(320); // 280ms transition + buffer
    const transformOpen = await chevron.evaluate(el => window.getComputedStyle(el).transform);
    // The rotate-from -90deg to 0deg → transforms must differ (matrix(...)
    // strings are different between closed/open states).
    expect(transformOpen).not.toBe(transformClosed);
});

test('Resource rows: NO saturated background colour on row ::before / type pill', async ({ page }) => {
    await navigateToManageSubPill(page);
    const project = await pickFirstAvailableProject(page);
    // Open the details card so rows render.
    const summary = page.locator('#resource-list-section details.details-card--v3 > summary');
    if (await summary.count()) {
        await summary.click();
        await page.waitForTimeout(400);
    }
    // Wait for rows or empty state.
    await page.waitForTimeout(900);
    const rows = page.locator('.resource-row-v3');
    const rowCount = await rows.count();
    if (rowCount === 0) {
        test.skip(true, `no resources rendered (project=${project}) — skipping ribbon-removal assertions`);
        return;
    }

    // SATURATED-COLOUR forbidden hex list (the actual AWS Architecture
    // Icons fill values that drove the original ribbons):
    //   EC2 #d86613, VPC #693cc5, S3 #e7157b-ish, Lambda #e7157b, etc.
    // We assert that the row ::before and the type pill background never
    // resolves to one of those — they should be transparent / brand-light /
    // bg-input only.
    const banned = ['216, 102, 19', '105, 60, 197', '231, 21, 123', '231, 165, 33'];

    const firstRow = rows.first();
    // Row ::before — query via getComputedStyle on ::before pseudo.
    const beforeBg = await firstRow.evaluate(el => {
        return window.getComputedStyle(el, '::before').backgroundColor;
    });
    for (const b of banned) {
        expect(beforeBg, `row ::before must not be a saturated AWS-icon hex (got ${beforeBg})`).not.toContain(b);
    }

    // Type pill on the row must use the neutral .resource-row-v3__type-pill
    // chrome (--bg-input surface).
    const pill = firstRow.locator('.resource-row-v3__type-pill').first();
    await expect(pill).toHaveCount(1);
    const pillBg = await pill.evaluate(el => window.getComputedStyle(el).backgroundColor);
    for (const b of banned) {
        expect(pillBg, `type pill must not have a saturated background (got ${pillBg})`).not.toContain(b);
    }

    // The legacy <img src="...ec2.svg"> AWS architecture icons must NOT
    // appear inside resource rows any more.
    await expect(firstRow.locator('img[src*="aws-icons"]')).toHaveCount(0);
});

test('Resource rows: state badges use .spec-pill primitives (live/draft/error)', async ({ page }) => {
    await navigateToManageSubPill(page);
    await pickFirstAvailableProject(page);
    const summary = page.locator('#resource-list-section details.details-card--v3 > summary');
    if (await summary.count()) {
        await summary.click();
        await page.waitForTimeout(400);
    }
    await page.waitForTimeout(900);
    const rows = page.locator('.resource-row-v3');
    if ((await rows.count()) === 0) {
        test.skip(true, 'no resources rendered — skipping spec-pill assertion');
        return;
    }
    // At least one state pill exists; it must carry a .spec-pill--*
    // variant class. (RUNNING / AVAILABLE resources → spec-pill--live.)
    const pills = rows.locator('.spec-pill');
    const pillCount = await pills.count();
    expect(pillCount).toBeGreaterThan(0);
    const cls = await pills.first().getAttribute('class');
    const hasVariant =
        cls.includes('spec-pill--live') ||
        cls.includes('spec-pill--draft') ||
        cls.includes('spec-pill--error');
    expect(hasVariant, `expected a spec-pill--* variant, got "${cls}"`).toBe(true);
});

test('Deployment History card: no saturated full-height left strip', async ({ page }) => {
    await navigateToManageSubPill(page);
    // Allow timeline to render.
    await page.waitForTimeout(900);
    const cards = page.locator('#deployment-timeline .history-card-v3');
    const count = await cards.count();
    if (count === 0) {
        test.skip(true, 'no deployment history entries — skipping history-card chrome assertions');
        return;
    }
    const first = cards.first();
    // Border-left must be a 1px hairline (var(--border-subtle)) — NOT a
    // 4-5px saturated --success-text / --danger-text strip.
    const borderLeftWidth = await first.evaluate(el => window.getComputedStyle(el).borderLeftWidth);
    const borderLeftWidthPx = parseFloat(borderLeftWidth);
    expect(borderLeftWidthPx, `history card border-left must be a hairline (1px), got ${borderLeftWidth}`).toBeLessThanOrEqual(1.5);

    // Status is communicated via a .spec-pill--* variant in the title row.
    // The neutral type pill (.history-card-v3__type-pill) carries .spec-pill
    // chrome but no variant — find the variant-bearing one.
    const pills = await first.locator('.spec-pill').all();
    expect(pills.length, 'history card must include at least one .spec-pill').toBeGreaterThan(0);
    let variantPillClass = null;
    for (const p of pills) {
        const cls = await p.getAttribute('class');
        if (cls && (cls.includes('spec-pill--live') || cls.includes('spec-pill--draft') || cls.includes('spec-pill--error'))) {
            variantPillClass = cls;
            break;
        }
    }
    expect(variantPillClass, `expected a .spec-pill--{live|draft|error} status pill in history card head`).not.toBeNull();
});

// ── Layer-aware contrast (both themes) on the two restyled sections ──
function _contrastFailures(page, rootSel) {
    return page.evaluate(({ rootSel }) => {
        function parseRgb(s) {
            const m = s.match(/rgba?\(([^)]+)\)/);
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
        const root = document.querySelector(rootSel);
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
                    cls: typeof el.className === 'string' ? el.className : '',
                    text: (el.textContent || '').trim().slice(0, 40),
                    ratio: Number(r.toFixed(2)),
                    threshold,
                    fg: cs.color,
                    bg: `rgb(${bg.join(', ')})`,
                });
            }
        });
        return failures;
    }, { rootSel });
}

for (const theme of ['dark', 'light']) {
    test(`Resource list contrast clean (${theme} theme)`, async ({ page }) => {
        await navigateToManageSubPill(page);
        await setTheme(page, theme);
        // Open the details card so child contrast is exercised.
        const summary = page.locator('#resource-list-section details.details-card--v3 > summary');
        if (await summary.count()) {
            await summary.click();
            await page.waitForTimeout(400);
        }
        await page.waitForTimeout(500);
        const failures = await _contrastFailures(page, '#resource-list-section');
        if (failures.length) {
            // eslint-disable-next-line no-console
            console.log(`Resource list (${theme}) contrast failures:`, JSON.stringify(failures, null, 2));
        }
        expect(failures, `${failures.length} AA failures in ${theme}`).toEqual([]);
    });
}

for (const theme of ['dark', 'light']) {
    test(`Deployment history contrast clean (${theme} theme)`, async ({ page }) => {
        await navigateToManageSubPill(page);
        await setTheme(page, theme);
        await page.waitForTimeout(500);
        const failures = await _contrastFailures(page, '#deployment-history-section');
        if (failures.length) {
            // eslint-disable-next-line no-console
            console.log(`Deployment history (${theme}) contrast failures:`, JSON.stringify(failures, null, 2));
        }
        expect(failures, `${failures.length} AA failures in ${theme}`).toEqual([]);
    });
}
