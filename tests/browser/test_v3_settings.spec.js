/**
 * Phase 3d — Settings tab audit + V3 refinement.
 *
 * Coverage (per the Phase 3d brief):
 *   1. Smoke — each of the 8 Settings sections is reachable via the
 *      left-rail TOC and renders into the page.
 *   2. Domains / Secrets / Infrastructure Services sections render as
 *      .spec-list (regression on the D8 settings-*-row cards).
 *   3. Cost Tracker summary uses .spec-list (when data is present).
 *   4. Deployment Preferences exposes a .seg-control mirror over the
 *      hidden <select>.
 *   5. Layer-aware contrast in BOTH themes for every section that
 *      renders — extends the Phase 2a sweep to lazy-loaded subtrees
 *      that the original full-page sweep missed.
 *
 * The contrast bits piggyback on the same WCAG walk-up logic used in
 * tests/browser/test_contrast_invariants.spec.js so the methodology
 * stays consistent.
 */

import { test, expect } from '@playwright/test';

const SECTION_IDS = [
    'settings-general',
    'settings-prereqs',
    'settings-domains',
    'settings-secrets',
    'settings-services',
    'settings-cost',
    'settings-prefs',
    'settings-roadmap',
];

// ─────────────────────────────────────────────────────────────────────
// WCAG helpers (sRGB → relative luminance → contrast ratio). Identical
// to test_contrast_invariants.spec.js so failures from this file are
// directly comparable to the global sweep.
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
function contrast(a, b) {
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
    // Settles V3 motion transitions before reading colours.
    await page.waitForTimeout(320);
}

async function navigateToSettings(page) {
    await page.goto('/');
    await page.locator('button.tab-btn[data-target="settings"]').waitFor({ timeout: 5000 });
    await page.click('button.tab-btn[data-target="settings"]');
    // Allow lazy loaders (domains/secrets/services) to fire — these are
    // skeleton-then-async, and the contrast sweep needs the final DOM,
    // not the skeleton placeholders.
    await page.waitForTimeout(1100);
}

// ─────────────────────────────────────────────────────────────────────
// 1. Smoke — every section is reachable from the TOC and renders
// ─────────────────────────────────────────────────────────────────────

test('Settings TOC has all 8 section anchors', async ({ page }) => {
    await navigateToSettings(page);
    for (const id of SECTION_IDS) {
        const tocLink = page.locator(`.settings-toc a[href="#${id}"]`);
        await expect(tocLink, `TOC link for #${id} missing`).toHaveCount(1);
    }
});

for (const id of SECTION_IDS) {
    test(`Settings section #${id} renders`, async ({ page }) => {
        await navigateToSettings(page);
        const section = page.locator(`#${id}`);
        await expect(section, `#${id} not found`).toHaveCount(1);
        // Header tri-stack must be present and non-empty.
        await expect(section.locator('.settings-section__eyebrow')).toBeVisible();
        await expect(section.locator('.settings-section__title')).toBeVisible();
        await expect(section.locator('.settings-section__description')).toBeVisible();
    });
}

// ─────────────────────────────────────────────────────────────────────
// 2. D8 inventory sections render as .spec-list (regression on cards)
// ─────────────────────────────────────────────────────────────────────

test('Domains & DNS section uses .spec-list (not legacy .settings-domain-row)', async ({ page }) => {
    await navigateToSettings(page);
    // Wait up to 3s for the lazy-loader to complete (or fail and fall
    // back to empty/error state — both of which use spec-list-compatible
    // markup, just without spec-rows).
    await page.waitForTimeout(2000);
    const legacyCount = await page.locator('#settings-domains-list .settings-domain-row').count();
    expect(legacyCount, 'legacy .settings-domain-row must not be present').toBe(0);
    // Either we have a .spec-list (data) OR an .settings-spec-empty /
    // .settings-spec-error placeholder. Whichever, no legacy card.
    const specOrEmpty = await page.locator(
        '#settings-domains-list .spec-list, #settings-domains-list .settings-spec-empty, #settings-domains-list .settings-spec-error'
    ).count();
    expect(specOrEmpty, 'Domains list must use spec-list or settings-spec-empty/error').toBeGreaterThanOrEqual(1);
});

test('Secrets Manager section uses .spec-list', async ({ page }) => {
    await navigateToSettings(page);
    await page.waitForTimeout(2000);
    const legacy = await page.locator('#settings-secrets-list .settings-secret-row').count();
    expect(legacy).toBe(0);
    const specOrEmpty = await page.locator(
        '#settings-secrets-list .spec-list, #settings-secrets-list .settings-spec-empty, #settings-secrets-list .settings-spec-error'
    ).count();
    expect(specOrEmpty).toBeGreaterThanOrEqual(1);
});

test('Infrastructure Services section uses .spec-list', async ({ page }) => {
    await navigateToSettings(page);
    await page.waitForTimeout(2000);
    const legacy = await page.locator('#settings-services-list .settings-service-row').count();
    expect(legacy).toBe(0);
    const specOrEmpty = await page.locator(
        '#settings-services-list .spec-list, #settings-services-list .settings-spec-empty, #settings-services-list .settings-spec-error'
    ).count();
    expect(specOrEmpty).toBeGreaterThanOrEqual(1);
});

// ─────────────────────────────────────────────────────────────────────
// 3. Cost Tracker summary renders into the spec-list when data present
// ─────────────────────────────────────────────────────────────────────

test('Cost Tracker container is wrapped in .cost-tracker-summary', async ({ page }) => {
    await navigateToSettings(page);
    const wrap = await page.locator('#settings-cost .cost-tracker-summary').count();
    expect(wrap, 'Cost summary container must be wrapped in .cost-tracker-summary').toBe(1);
    // The legacy class .lifecycle-card must NOT appear inside the cost
    // summary surface — we replaced the 4-card grid with a spec-list.
    const legacyCards = await page.locator('#cost-summary-cards .lifecycle-card').count();
    expect(legacyCards, 'legacy lifecycle-card 4-up must not be present').toBe(0);
});

// ─────────────────────────────────────────────────────────────────────
// 4. Deployment Preferences uses .seg-control mirror
// ─────────────────────────────────────────────────────────────────────

test('Deployment Preferences uses a seg-control mirror over the select', async ({ page }) => {
    await navigateToSettings(page);
    const seg = page.locator('#auto-refresh-seg');
    await expect(seg).toHaveCount(1);
    await expect(seg.locator('.seg-control__option')).toHaveCount(5);
    // Hidden select still present as state-of-truth.
    const select = page.locator('#auto-refresh-interval');
    await expect(select).toHaveCount(1);
});

test('Seg-control click updates the hidden select + persists', async ({ page }) => {
    await navigateToSettings(page);
    const seg = page.locator('#auto-refresh-seg');
    const select = page.locator('#auto-refresh-interval');
    // Pick the "60s" option (data-value="60")
    await seg.locator('.seg-control__option[data-value="60"]').click();
    await page.waitForTimeout(120);
    const value = await select.inputValue();
    expect(value).toBe('60');
    // The clicked option is now is-active.
    const activeCount = await seg.locator('.seg-control__option.is-active[data-value="60"]').count();
    expect(activeCount).toBe(1);
    // And localStorage carries it.
    const stored = await page.evaluate(() => localStorage.getItem('autoRefreshInterval'));
    expect(stored).toBe('60');
});

// ─────────────────────────────────────────────────────────────────────
// 5. Per-section layer-aware contrast sweep — both themes
//
//   The Phase 2a full-page contrast sweep visits Settings but doesn't
//   scroll-trigger every lazy-loaded sub-section. This test walks
//   every visible text node inside each Settings section ID and runs
//   the layer-aware contrast check. We accept a per-section result so
//   if one section drifts (e.g. someone adds a low-contrast pill in
//   Cost Tracker), we know exactly where without grepping logs.
// ─────────────────────────────────────────────────────────────────────

async function auditSectionContrast(page, sectionId) {
    return page.evaluate(({ sectionId, walkSrc }) => {
        // eslint-disable-next-line no-new-func
        const walkToSurface = new Function('return ' + walkSrc)();
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

        const root = document.getElementById(sectionId);
        if (!root) return { found: false, failures: [] };
        const failures = [];
        const els = root.querySelectorAll('*');
        for (const el of els) {
            const cs = window.getComputedStyle(el);
            if (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0') continue;
            if (el.offsetParent === null && cs.position !== 'fixed') continue;
            if (el.getAttribute('aria-hidden') === 'true') continue;
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) continue;
            // Skip elements with no direct text node.
            let hasText = false;
            for (const child of el.childNodes) {
                if (child.nodeType === 3 && child.textContent.trim().length > 0) {
                    hasText = true;
                    break;
                }
            }
            if (!hasText) continue;
            // Skip terminal/code areas — by-design dark.
            if (el.closest('.terminal, .beacon-console, .code-preview, pre, code, .preview-tab.active')) continue;

            const fg = parseRgb(cs.color);
            if (!fg) continue;
            const surface = walkToSurface(el);
            const bg = parseRgb(surface);
            if (!bg) continue;
            if (fg[3] < 0.5) continue;

            const r = ratio(fg.slice(0, 3), bg.slice(0, 3));
            const fontSize = parseFloat(cs.fontSize);
            const fontWeight = parseInt(cs.fontWeight, 10) || 400;
            const isLarge = fontSize >= 24 || (fontSize >= 18.66 && fontWeight >= 700);
            const threshold = isLarge ? 3.0 : 4.5;
            if (r < threshold) {
                failures.push({
                    tag: el.tagName.toLowerCase(),
                    cls: String(el.className || '').slice(0, 80),
                    text: (el.textContent || '').trim().slice(0, 60),
                    ratio: Number(r.toFixed(2)),
                    fg: cs.color,
                    bg: surface,
                    fontSize,
                    threshold,
                });
            }
        }
        return { found: true, failures };
    }, { sectionId, walkSrc: WALK_TO_SURFACE_FN.toString() });
}

for (const theme of ['dark', 'light']) {
    for (const id of SECTION_IDS) {
        test(`Settings section #${id} contrast (${theme})`, async ({ page }) => {
            await navigateToSettings(page);
            await setTheme(page, theme);
            // Bring the section into view in case the IntersectionObserver
            // is keying lazy loaders off visibility.
            await page.locator(`#${id}`).scrollIntoViewIfNeeded();
            await page.waitForTimeout(450);
            const { found, failures } = await auditSectionContrast(page, id);
            expect(found, `#${id} not in DOM`).toBe(true);
            if (failures.length > 0) {
                // eslint-disable-next-line no-console
                console.log(`\n#${id} (${theme}) — ${failures.length} contrast failures:`);
                for (const f of failures.slice(0, 12)) {
                    // eslint-disable-next-line no-console
                    console.log(`  <${f.tag}.${(f.cls || '').split(' ').join('.')}> "${f.text}" — ${f.ratio}:1 (need ${f.threshold}) fg=${f.fg} bg=${f.bg}`);
                }
            }
            expect(failures, `#${id} (${theme}): ${failures.length} AA failures`).toEqual([]);
        });
    }
}
