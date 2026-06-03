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
import { railNavigate } from './helpers/nav.js';

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
        await railNavigate(page, 'settings');
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
        await railNavigate(page, 'dashboard');
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
        // Visit Settings so its DOM is in the inspected tree.
        await railNavigate(page, 'settings');
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

// ─────────────────────────────────────────────────────────────────────
// Test: Modal / overlay-aware contrast sweep (Polish A — 2026-05-18)
//
//   The Dashboard-snapshot sweep above only visits elements that are
//   visible at the moment it runs. Modals, popovers, and the journey
//   takeover all start `hidden`, so any contrast failure inside them
//   slipped through silently.
//
//   The `.btn-primary` regression (burgundy fill + gold text at 2.54:1)
//   is a concrete example: it's used 15+ times across modal footers,
//   the "+ Add operator" affordance, the operator-management Save /
//   Delete buttons, and the journey Deploy button. The default sweep
//   never caught it because every one of those mount points is offscreen
//   until an operator interacts.
//
//   This block enumerates the known overlay surfaces, opens each in
//   turn via its real trigger, runs the same WCAG audit over its
//   interior, then closes the overlay before moving on. Failures are
//   tagged with the surface they came from so a regression is
//   immediately identifiable.
// ─────────────────────────────────────────────────────────────────────

/**
 * In-browser audit helper. Given a root element, walks every visible
 * descendant with direct text content and returns AA failures.
 * Mirrors the full-page sweep above but scoped to the overlay surface.
 */
const AUDIT_SUBTREE_FN = function auditSubtree(root, walkToSurface) {
    function parseRgba(s) {
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
    // Include the root itself plus every descendant.
    const els = [root, ...root.querySelectorAll('*')];
    for (const el of els) {
        const cs = window.getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0') continue;
        if (el.getAttribute('aria-hidden') === 'true') continue;
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;
        let hasText = false;
        for (const child of el.childNodes) {
            if (child.nodeType === 3 && child.textContent.trim().length > 0) {
                hasText = true;
                break;
            }
        }
        if (!hasText) continue;
        // Skip terminal/code areas and preview tree (same as full-page sweep).
        if (el.closest('.terminal, .beacon-console, .code-preview, pre, code, .preview-tab.active')) continue;
        if (el.closest('.preview, [data-preview]')) continue;
        if (el.closest('.arch-diagram-frame')) continue;

        const fg = parseRgba(cs.color);
        if (!fg) continue;
        const surface = walkToSurface(el);
        const bg = parseRgba(surface);
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
};

/**
 * Each entry describes one overlay surface:
 *   label    — human-readable surface identifier (used in failure output)
 *   open     — async callback receiving the page; opens the overlay
 *   selector — selector for the overlay root once visible (audit scope)
 *   close    — async callback receiving the page; closes the overlay
 *
 * Add new entries here whenever a new modal/overlay ships so the audit
 * doesn't fall behind the UI.
 */
const OVERLAY_SCENARIOS = [
    {
        label: 'version-modal (footer-triggered)',
        open: async (page) => {
            await page.locator('#app-version-footer').click();
            await page.locator('#version-modal').waitFor({ state: 'visible', timeout: 3000 });
        },
        selector: '#version-modal',
        close: async (page) => {
            await page.locator('#version-modal .modal__close').click();
            await page.waitForTimeout(150);
        },
    },
    {
        label: 'add-operator-modal (+ Add operator from chip menu)',
        open: async (page) => {
            await page.locator('#operator-chip').click();
            await page.locator('#operator-menu-add').click();
            await page.locator('#add-operator-modal').waitFor({ state: 'visible', timeout: 3000 });
        },
        selector: '#add-operator-modal',
        close: async (page) => {
            await page.locator('#add-operator-modal .modal__close').click();
            await page.waitForTimeout(150);
        },
    },
    {
        label: 'operator-management-modal (Manage… from chip menu)',
        open: async (page) => {
            // Seed a second operator so the list has at least two rows for the
            // inline-editor expansion step.
            await page.evaluate(async () => {
                try {
                    await fetch('/api/operators', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ id: 'contrast_pw', display: 'Contrast Pw', color: '#65a30d' }),
                    });
                } catch (_) { /* idempotent */ }
            });
            await page.locator('#operator-chip').click();
            await page.locator('#operator-menu-manage').click();
            await page.locator('#operator-management-modal').waitFor({ state: 'visible', timeout: 3000 });
        },
        selector: '#operator-management-modal',
        close: async (page) => {
            await page.locator('#operator-management-modal .modal__close').click();
            await page.waitForTimeout(150);
        },
    },
    {
        label: 'operator-management-modal :: inline editor expanded',
        open: async (page) => {
            await page.evaluate(async () => {
                try {
                    await fetch('/api/operators', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ id: 'contrast_pw', display: 'Contrast Pw', color: '#65a30d' }),
                    });
                } catch (_) { /* idempotent */ }
            });
            await page.locator('#operator-chip').click();
            await page.locator('#operator-menu-manage').click();
            await page.locator('#operator-management-modal').waitFor({ state: 'visible', timeout: 3000 });
            // Expand the first row's editor.
            await page.locator('#operator-management-list [data-mgmt-edit]').first().click();
            // Wait for editor to render its Save/Delete buttons.
            await page.locator('#operator-management-modal [data-mgmt-save], #operator-management-modal button:has-text("Save")').first().waitFor({ timeout: 2000 }).catch(() => {});
            await page.waitForTimeout(150);
        },
        selector: '#operator-management-modal',
        close: async (page) => {
            await page.locator('#operator-management-modal .modal__close').click();
            await page.waitForTimeout(150);
        },
    },
    {
        label: 'journey-takeover (+ New Deployment)',
        open: async (page) => {
            await openJourney(page);
        },
        selector: '#journey-takeover',
        close: async (page) => {
            await closeJourney(page);
        },
    },
    {
        label: 'journey-takeover :: review phase (Step 5 / spec-edit)',
        open: async (page) => {
            await openJourney(page);
            // Jump straight to the review phase via the public API. This is
            // "Step 5" in operator-facing terms (steps 1-4 are wizard, then
            // the review/spec-edit phase).
            await page.evaluate(() => {
                if (window.APP && window.APP.journey && typeof window.APP.journey.goToReview === 'function') {
                    window.APP.journey.goToReview();
                }
            });
            await page.waitForTimeout(200);
            // Expand the first editable spec-row's inline editor so the
            // editor surface is part of the audit.
            const firstPencil = page.locator('#journey-takeover .spec-row[data-review-row]:not([data-readonly]) .spec-row__action').first();
            if (await firstPencil.count()) {
                await firstPencil.click();
                await page.waitForTimeout(200);
            }
        },
        selector: '#journey-takeover',
        close: async (page) => {
            await closeJourney(page);
        },
    },
];

/**
 * Open the journey takeover. Idempotent — if it's already open, just
 * waits for it to settle.
 */
async function openJourney(page) {
    // Force a clean scrim state before opening. The journey's close()
    // schedules `hidden = true` via a 300ms setTimeout — even when we wait
    // for that to settle in closeJourney(), browser-side state can drift
    // (focus restore, animation frame) and the next open can race against
    // a stale data-open="true" on the scrim. This synchronous reset
    // guarantees the next open starts from a clean slate.
    await page.evaluate(() => {
        const scrim = document.getElementById('journey-scrim');
        const card = document.getElementById('journey-takeover');
        if (scrim && !scrim.hidden) {
            scrim.hidden = true;
            scrim.removeAttribute('data-open');
            scrim.setAttribute('aria-hidden', 'true');
            if (card) {
                card.hidden = true;
                card.removeAttribute('data-open');
            }
            document.body.removeAttribute('data-journey-open');
        }
    });
    await page.locator('#global-new-deployment-btn').click();
    await page.locator('#journey-takeover').waitFor({ state: 'visible', timeout: 3000 });
    await page.waitForTimeout(150);
}

/**
 * Close the journey takeover and wait for the scrim to fully unmount
 * (i.e., `hidden` attribute set to true). The journey close removes
 * `data-open` synchronously but defers `hidden = true` by 300ms via
 * setTimeout — clicks that race that timer get intercepted by the
 * still-visible (but transition-fading) scrim.
 */
async function closeJourney(page) {
    await page.evaluate(() => {
        if (window.APP && window.APP.journey && typeof window.APP.journey.close === 'function') {
            window.APP.journey.close({ confirmIfDirty: false });
        }
    });
    // Wait for the deferred unmount: scrim.hidden = true at +300ms.
    await page.locator('#journey-scrim').waitFor({ state: 'hidden', timeout: 2000 }).catch(() => {});
    await page.waitForTimeout(50);
}

for (const theme of ['dark', 'light']) {
    test(`Modal/overlay contrast sweep (${theme} theme) — no AA failures in hidden states`, async ({ page }) => {
        await page.goto('/');
        // Wait for APP to load + rail to be wired so the modal triggers below
        // (which run APP.* function calls) have a fully booted shell.
        await page.waitForFunction(
            () => typeof window.APP !== 'undefined' && typeof window.APP.navigateTo === 'function',
            { timeout: 5000 },
        );
        await setTheme(page, theme);

        const allFailures = [];

        for (const scenario of OVERLAY_SCENARIOS) {
            try {
                await scenario.open(page);
            } catch (err) {
                // If the trigger doesn't exist in this build, skip rather than
                // false-positive — but record the skip so it's visible.
                // eslint-disable-next-line no-console
                console.log(`  [skip] ${scenario.label}: open failed (${err.message})`);
                continue;
            }

            const failures = await page.evaluate(
                ({ sel, walkSrc, auditSrc }) => {
                    // eslint-disable-next-line no-new-func
                    const walkToSurface = new Function('return ' + walkSrc)();
                    // eslint-disable-next-line no-new-func
                    const auditSubtree = new Function('return ' + auditSrc)();
                    const root = document.querySelector(sel);
                    if (!root) return [{ tag: 'missing', text: sel, ratio: 0, threshold: 4.5 }];
                    return auditSubtree(root, walkToSurface);
                },
                {
                    sel: scenario.selector,
                    walkSrc: WALK_TO_SURFACE_FN.toString(),
                    auditSrc: AUDIT_SUBTREE_FN.toString(),
                }
            );

            for (const f of failures) {
                allFailures.push({ ...f, surface: scenario.label });
            }

            try {
                await scenario.close(page);
            } catch (_) {
                // If close fails, force-close every modal so the next scenario
                // starts clean.
                await page.evaluate(() => {
                    if (window.APP && window.APP.modal && typeof window.APP.modal.closeAll === 'function') {
                        window.APP.modal.closeAll();
                    }
                    if (window.APP && window.APP.journey && typeof window.APP.journey.close === 'function') {
                        try { window.APP.journey.close({ confirmIfDirty: false }); } catch (_e) {}
                    }
                });
                await page.waitForTimeout(150);
            }
        }

        if (allFailures.length > 0) {
            // eslint-disable-next-line no-console
            console.log(`\n${theme} theme overlay contrast failures (${allFailures.length}):`);
            for (const f of allFailures.slice(0, 40)) {
                // eslint-disable-next-line no-console
                console.log(
                    `  [${f.surface}] <${f.tag}${f.id ? `#${f.id}` : ''}${f.cls ? `.${String(f.cls).split(' ').join('.')}` : ''}> "${f.text}" — ${f.ratio}:1 (need ${f.threshold}) fg=${f.fg} bg=${f.bg}`
                );
            }
        }
        expect(
            allFailures,
            `${allFailures.length} AA contrast failures across hidden overlay surfaces in ${theme} mode`
        ).toEqual([]);
    });
}
