/**
 * Phase 2a.4 — Contrast invariants regression net.
 *
 * Asserts that key text elements in the dashboard meet WCAG AA contrast
 * (>= 4.5:1 for normal body text, >= 3:1 for large/bold display text)
 * against their IMMEDIATE rendered ancestor surface — not against the
 * page background. The "layer-aware" rule:
 *
 *   When evaluating text contrast, walk up the DOM until we hit an
 *   ancestor with a non-transparent background-color. THAT is the
 *   contrast baseline, regardless of what theoretically sits behind it.
 *
 * Specific regression coverage:
 *   1. D8 Settings section headers (eyebrow / title / description)
 *      in BOTH themes — fixes 2026-05-18 bug where global
 *      `header { background: var(--burgundy); }` was applying to
 *      <header class="settings-section__header">.
 *   2. Dashboard widget titles in both themes.
 *   3. Global header chip text in both themes.
 *
 * Plus a smoke run of the comprehensive page-wide audit script
 * `scripts/utilities/contrast_audit.js`, which is also runnable
 * standalone via the test runner output.
 */

import { test, expect } from '@playwright/test';

// ─────────────────────────────────────────────────────────────────────
// WCAG helpers (sRGB → relative luminance → contrast ratio)
// ─────────────────────────────────────────────────────────────────────

function parseRgb(s) {
    // "rgb(14, 31, 39)" / "rgba(14, 31, 39, 0.55)" → [r,g,b,a]
    const m = s.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const parts = m[1].split(',').map(p => parseFloat(p.trim()));
    const [r, g, b] = parts;
    const a = parts.length === 4 ? parts[3] : 1;
    return [r, g, b, a];
}

function srgbChannelToLinear(c) {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
}

function relativeLuminance([r, g, b]) {
    const R = srgbChannelToLinear(r);
    const G = srgbChannelToLinear(g);
    const B = srgbChannelToLinear(b);
    return 0.2126 * R + 0.7152 * G + 0.0722 * B;
}

function contrastRatio(rgbA, rgbB) {
    const L1 = relativeLuminance(rgbA);
    const L2 = relativeLuminance(rgbB);
    const lighter = Math.max(L1, L2);
    const darker = Math.min(L1, L2);
    return (lighter + 0.05) / (darker + 0.05);
}

/**
 * In-browser: walk up from `el` until we find an ancestor with a
 * SUBSTANTIALLY-opaque background-color (alpha >= 0.7).
 * For partly-transparent backgrounds (e.g. rgba(255,255,255,0.06)
 * decorative tints), we composite them with the surface beneath and
 * return the perceived color.
 *
 * Returns an "rgb(r, g, b)" string.
 */
const WALK_TO_SURFACE_FN = function walkToSurface(el) {
    function parseRgba(s) {
        const m = s.match(/rgba?\(([^)]+)\)/);
        if (!m) return null;
        const parts = m[1].split(',').map((p) => parseFloat(p.trim()));
        return [parts[0], parts[1], parts[2], parts.length === 4 ? parts[3] : 1];
    }
    // Collect overlays (top-down). We walk up, recording any
    // non-transparent bg; then composite from the deepest opaque
    // ancestor downward to the element.
    const stack = [];
    let cur = el;
    while (cur && cur !== document.documentElement) {
        const cs = window.getComputedStyle(cur);
        const parsed = parseRgba(cs.backgroundColor);
        if (parsed && parsed[3] > 0.01) {
            stack.push(parsed);
            if (parsed[3] >= 0.99) break; // opaque, stop
        }
        cur = cur.parentElement;
    }
    // If nothing opaque found, fall back to body bg.
    if (stack.length === 0 || stack[stack.length - 1][3] < 0.99) {
        const bodyBg = parseRgba(window.getComputedStyle(document.body).backgroundColor) || [255, 255, 255, 1];
        stack.push(bodyBg);
    }
    // Composite bottom (opaque ancestor) up through the overlays.
    let [r, g, b] = stack[stack.length - 1].slice(0, 3);
    for (let i = stack.length - 2; i >= 0; i--) {
        const [or, og, ob, oa] = stack[i];
        r = or * oa + r * (1 - oa);
        g = og * oa + g * (1 - oa);
        b = ob * oa + b * (1 - oa);
    }
    return `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`;
};

async function getContrastForSelector(page, selector) {
    const result = await page.evaluate(
        ({ sel, walkSrc }) => {
            // eslint-disable-next-line no-new-func
            const walkToSurface = new Function('return ' + walkSrc)();
            const el = document.querySelector(sel);
            if (!el) return { found: false };
            const cs = window.getComputedStyle(el);
            return {
                found: true,
                color: cs.color,
                surface: walkToSurface(el),
                fontSize: parseFloat(cs.fontSize),
                fontWeight: parseInt(cs.fontWeight, 10) || 400,
            };
        },
        { sel: selector, walkSrc: WALK_TO_SURFACE_FN.toString() }
    );
    if (!result.found) return null;
    const fg = parseRgb(result.color);
    const bg = parseRgb(result.surface);
    if (!fg || !bg) return null;
    return {
        ratio: contrastRatio(fg.slice(0, 3), bg.slice(0, 3)),
        fg: result.color,
        bg: result.surface,
        fontSize: result.fontSize,
        fontWeight: result.fontWeight,
    };
}

function aaThreshold(fontSize, fontWeight) {
    // WCAG: "large text" = 18pt (~24px) or 14pt bold (~18.66px bold).
    // We approximate generously.
    const isLarge =
        fontSize >= 24 ||
        (fontSize >= 18.66 && fontWeight >= 700);
    return isLarge ? 3.0 : 4.5;
}

async function setTheme(page, theme) {
    await page.evaluate((t) => {
        if (t === 'light') {
            document.documentElement.setAttribute('data-theme', 'light');
        } else {
            document.documentElement.removeAttribute('data-theme');
        }
    }, theme);
    // Allow CSS transition to settle (V3 motion is 280ms).
    await page.waitForTimeout(320);
}

// ─────────────────────────────────────────────────────────────────────
// Test: Settings section header — D8 regression
// ─────────────────────────────────────────────────────────────────────

const SETTINGS_HEADER_SELECTORS = [
    '#settings-domains .settings-section__eyebrow',
    '#settings-domains .settings-section__title',
    '#settings-domains .settings-section__description',
    '#settings-secrets .settings-section__eyebrow',
    '#settings-secrets .settings-section__title',
    '#settings-secrets .settings-section__description',
    '#settings-services .settings-section__eyebrow',
    '#settings-services .settings-section__title',
    '#settings-services .settings-section__description',
];

for (const theme of ['dark', 'light']) {
    test(`Settings section headers pass contrast (${theme} theme) — D8 regression`, async ({ page }) => {
        await page.goto('/');
        await page.locator('button.tab-btn[data-target="settings"]').waitFor({ timeout: 5000 });
        // Navigate to Settings tab so the section is rendered visible
        await page.click('button.tab-btn[data-target="settings"]');
        await page.waitForTimeout(200);
        await setTheme(page, theme);

        for (const sel of SETTINGS_HEADER_SELECTORS) {
            const r = await getContrastForSelector(page, sel);
            if (r === null) continue; // selector not in DOM in this build
            const threshold = aaThreshold(r.fontSize, r.fontWeight);
            expect(
                r.ratio,
                `${sel} (${theme}): contrast ${r.ratio.toFixed(2)}:1, fg=${r.fg}, bg=${r.bg}, threshold=${threshold}`
            ).toBeGreaterThanOrEqual(threshold);
        }
    });
}

// ─────────────────────────────────────────────────────────────────────
// Test: Dashboard widget titles
// ─────────────────────────────────────────────────────────────────────

for (const theme of ['dark', 'light']) {
    test(`Dashboard widget titles pass contrast (${theme} theme)`, async ({ page }) => {
        await page.goto('/');
        await page.locator('button.tab-btn[data-target="dashboard"]').waitFor({ timeout: 5000 });
        await page.click('button.tab-btn[data-target="dashboard"]');
        await page.waitForTimeout(200);
        await setTheme(page, theme);

        // Page title is the most visible candidate.
        const r = await getContrastForSelector(
            page,
            '.tab-page[data-page="dashboard"] .page-title'
        );
        if (r) {
            const threshold = aaThreshold(r.fontSize, r.fontWeight);
            expect(
                r.ratio,
                `dashboard page-title (${theme}): ${r.ratio.toFixed(2)}:1 fg=${r.fg} bg=${r.bg}`
            ).toBeGreaterThanOrEqual(threshold);
        }
    });
}

// ─────────────────────────────────────────────────────────────────────
// Test: Global header chip labels
// ─────────────────────────────────────────────────────────────────────

for (const theme of ['dark', 'light']) {
    test(`Global header chip labels pass contrast (${theme} theme)`, async ({ page }) => {
        await page.goto('/');
        await page.locator('.global-header').waitFor({ timeout: 5000 });
        await setTheme(page, theme);

        const chipSelectors = [
            '.global-header__chip-label',
        ];
        for (const sel of chipSelectors) {
            // Just first occurrence — if any present.
            const present = await page.locator(sel).count();
            if (!present) continue;
            const r = await getContrastForSelector(page, sel);
            if (r === null) continue;
            const threshold = aaThreshold(r.fontSize, r.fontWeight);
            expect(
                r.ratio,
                `${sel} (${theme}): ${r.ratio.toFixed(2)}:1 fg=${r.fg} bg=${r.bg}`
            ).toBeGreaterThanOrEqual(threshold);
        }
    });
}

// ─────────────────────────────────────────────────────────────────────
// Test: Full-page sweep smoke test
//   Walks every visible text element on the rendered SPA and reports
//   AA contrast failures. Used as a comprehensive regression net so a
//   future surface or color tweak that breaks contrast somewhere we
//   haven't called out by selector will still fail this suite.
// ─────────────────────────────────────────────────────────────────────

for (const theme of ['dark', 'light']) {
    test(`Full-page contrast sweep (${theme} theme) — no AA failures`, async ({ page }) => {
        await page.goto('/');
        await page.locator('button.tab-btn[data-target="settings"]').waitFor({ timeout: 5000 });
        // Visit Settings so its DOM is in the inspected tree.
        await page.click('button.tab-btn[data-target="settings"]');
        await page.waitForTimeout(300);
        await setTheme(page, theme);

        const failures = await page.evaluate((walkSrc) => {
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
            const failures = [];
            const els = document.querySelectorAll('body *');
            for (const el of els) {
                // Skip non-visible / aria-hidden / display:none.
                // offsetParent === null catches descendants of display:none
                // ancestors (which the element's own computed style won't
                // reflect — it only sees its own display rule).
                const cs = window.getComputedStyle(el);
                if (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0') continue;
                if (el.offsetParent === null && cs.position !== 'fixed') continue;
                if (el.getAttribute('aria-hidden') === 'true') continue;
                // Skip if the element has zero rendered area
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) continue;
                // Only check elements with direct text content (no children eating layout)
                let hasText = false;
                for (const child of el.childNodes) {
                    if (child.nodeType === 3 && child.textContent.trim().length > 0) {
                        hasText = true;
                        break;
                    }
                }
                if (!hasText) continue;
                // Skip terminal/code areas — they're correct by design.
                if (el.closest('.terminal, .beacon-console, .code-preview, pre, code, .preview-tab.active')) {
                    continue;
                }
                // Skip elements inside the legacy/preview hidden tree.
                if (el.closest('.preview, [data-preview]')) continue;
                // Skip the architecture diagram frame (white bg by design)
                if (el.closest('.arch-diagram-frame')) continue;

                const fg = parseRgb(cs.color);
                if (!fg) continue;
                const surface = walkToSurface(el);
                const bg = parseRgb(surface);
                if (!bg) continue;
                // Skip if foreground is fully transparent
                if (fg[3] < 0.5) continue;

                const r = ratio(fg.slice(0, 3), bg.slice(0, 3));
                const fontSize = parseFloat(cs.fontSize);
                const fontWeight = parseInt(cs.fontWeight, 10) || 400;
                const isLarge = fontSize >= 24 || (fontSize >= 18.66 && fontWeight >= 700);
                const threshold = isLarge ? 3.0 : 4.5;
                if (r < threshold) {
                    failures.push({
                        tag: el.tagName.toLowerCase(),
                        cls: el.className,
                        id: el.id,
                        text: (el.textContent || '').trim().slice(0, 60),
                        ratio: Number(r.toFixed(2)),
                        fg: cs.color,
                        bg: surface,
                        fontSize,
                        fontWeight,
                        threshold,
                    });
                }
            }
            return failures;
        }, WALK_TO_SURFACE_FN.toString());

        if (failures.length > 0) {
            // Print a useful diagnostic if this fails.
            // eslint-disable-next-line no-console
            console.log(`\n${theme} theme contrast failures (${failures.length}):`);
            for (const f of failures.slice(0, 30)) {
                // eslint-disable-next-line no-console
                console.log(
                    `  <${f.tag}${f.id ? `#${f.id}` : ''}${f.cls ? `.${String(f.cls).split(' ').join('.')}` : ''}> "${f.text}" — ${f.ratio}:1 (need ${f.threshold}) fg=${f.fg} bg=${f.bg}`
                );
            }
        }
        expect(failures, `${failures.length} AA contrast failures in ${theme} mode`).toEqual([]);
    });
}
