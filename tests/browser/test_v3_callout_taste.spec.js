/**
 * V3 callout TASTE migration regression net.
 *
 * Asserts the legacy `.callout` + `.callout--<tone>` markup has been fully
 * retired from the live dashboard in favor of the TASTE primitive
 * (`.cfg-callout` + `.cfg-callout--<tone>`). Specifically:
 *
 *   1. No element on the rendered SPA carries `class="callout callout--*"`
 *      or `class="callout--*"` (legacy left-ribbon pattern).
 *      `webapp/frontend/preview/` is design history — we don't touch it,
 *      but we also never serve it as part of the live SPA, so the
 *      assertion runs against the rendered DOM which excludes preview
 *      automatically. We still scope the audit defensively below.
 *
 *   2. Every `.cfg-callout` resolves to `border-radius: 8px` — a sanity
 *      check that the TASTE class is actually applied (catches a missing
 *      stylesheet link or a typo in the class name).
 *
 *   3. The warning callout's text meets WCAG AA contrast (>= 4.5:1)
 *      against its composited parent surface in BOTH dark and light
 *      themes. We re-use the layer-aware walkToSurface helper from
 *      test_contrast_invariants.spec.js so the assertion mirrors how the
 *      existing contrast invariants are computed.
 *
 * Picks the Configure tab (deployments-tab) since 14 of the 16 migrated
 * callouts live there, including the warning variants.
 */

import { test, expect } from '@playwright/test';

// ─────────────────────────────────────────────────────────────────────
// Layer-aware contrast helpers (mirrored from
// test_contrast_invariants.spec.js so this spec is self-contained).
// ─────────────────────────────────────────────────────────────────────

function parseRgb(s) {
    const m = s.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const parts = m[1].split(',').map((p) => parseFloat(p.trim()));
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
        if (t === 'light') {
            document.documentElement.setAttribute('data-theme', 'light');
        } else {
            document.documentElement.removeAttribute('data-theme');
        }
    }, theme);
    await page.waitForTimeout(320);
}

// ─────────────────────────────────────────────────────────────────────
// Test 1: No legacy `.callout--*` markup in the live SPA.
// ─────────────────────────────────────────────────────────────────────

test('legacy `.callout--<tone>` markup is fully retired from live SPA', async ({ page }) => {
    await page.goto('/');
    await page.locator('button.tab-btn[data-target="deployments-tab"]').waitFor({ timeout: 5000 });
    await page.click('button.tab-btn[data-target="deployments-tab"]');
    await page.waitForTimeout(300);

    // Enumerate every element that carries any of the legacy callout
    // tone classes. The preview/ tree is shipped as static markdown +
    // standalone HTML files under /preview/* and is never injected into
    // the SPA's DOM, but we filter defensively just in case a future
    // change starts iframing it. The matcher uses raw className tokens
    // (not Tailwind-style transformations) so `.callout--info` etc.
    // are caught exactly.
    const offenders = await page.evaluate(() => {
        const tones = ['info', 'warning', 'success', 'danger'];
        const out = [];
        for (const el of document.querySelectorAll('*')) {
            // Skip anything inside a preview wrapper (matches both
            // .preview class and [data-preview] attribute, consistent
            // with the global contrast sweep).
            if (el.closest && el.closest('.preview, [data-preview]')) continue;
            // Also skip anything served from /preview/ via an iframe src
            // — currently no such iframe ships, but future-proof.
            if (el.tagName === 'IFRAME' && el.src && el.src.includes('/preview/')) continue;
            const cls = el.className;
            if (typeof cls !== 'string') continue;
            for (const tone of tones) {
                // Look for the legacy class token specifically. Token
                // boundary check avoids false-positives on `cfg-callout--info`.
                const re = new RegExp(`(^|\\s)callout--${tone}(\\s|$)`);
                if (re.test(cls)) {
                    out.push({
                        tag: el.tagName.toLowerCase(),
                        id: el.id || null,
                        cls,
                        tone,
                    });
                    break;
                }
            }
        }
        return out;
    });

    expect(
        offenders,
        `Expected zero legacy .callout--<tone> elements in the live SPA, found ${offenders.length}:\n` +
            offenders
                .slice(0, 20)
                .map((o) => `  <${o.tag}${o.id ? `#${o.id}` : ''}> .callout--${o.tone} (full class: "${o.cls}")`)
                .join('\n')
    ).toEqual([]);
});

// ─────────────────────────────────────────────────────────────────────
// Test 2: Every `.cfg-callout` has the TASTE border-radius applied.
// ─────────────────────────────────────────────────────────────────────

test('every `.cfg-callout` resolves to border-radius: 8px (TASTE class applied)', async ({ page }) => {
    await page.goto('/');
    await page.locator('button.tab-btn[data-target="deployments-tab"]').waitFor({ timeout: 5000 });
    await page.click('button.tab-btn[data-target="deployments-tab"]');
    await page.waitForTimeout(300);

    // Pull every cfg-callout's computed border-radius. We expect 8px
    // uniformly — the class sets it, and no inline `border-radius`
    // override exists in the migrated markup. If a callout reports
    // anything else, either the class is missing or the inline style
    // got an override that needs to be stripped.
    const results = await page.evaluate(() => {
        const els = document.querySelectorAll('.cfg-callout');
        return Array.from(els).map((el) => ({
            id: el.id || null,
            cls: el.className,
            borderRadius: window.getComputedStyle(el).borderTopLeftRadius,
        }));
    });

    expect(results.length, 'expected at least one .cfg-callout on the configure page').toBeGreaterThan(0);

    const wrong = results.filter((r) => r.borderRadius !== '8px');
    expect(
        wrong,
        `Some .cfg-callout elements do not resolve to border-radius 8px:\n` +
            wrong
                .slice(0, 10)
                .map((r) => `  ${r.id ? `#${r.id}` : '(anon)'} radius=${r.borderRadius} class="${r.cls}"`)
                .join('\n')
    ).toEqual([]);
});

// ─────────────────────────────────────────────────────────────────────
// Test 3: Warning callout passes WCAG AA contrast in both themes.
// ─────────────────────────────────────────────────────────────────────

for (const theme of ['dark', 'light']) {
    test(`warning cfg-callout passes >= 4.5:1 contrast in ${theme} theme`, async ({ page }) => {
        await page.goto('/');
        await page.locator('button.tab-btn[data-target="deployments-tab"]').waitFor({ timeout: 5000 });
        await page.click('button.tab-btn[data-target="deployments-tab"]');
        await page.waitForTimeout(300);
        await setTheme(page, theme);

        // The Domain Setup Steps callout (line 1470+) and several other
        // warning callouts live inside data-config-section parents that
        // are display:none until a deployment_type is picked in the
        // journey takeover. For the contrast check we don't need the
        // full user flow — just any rendered warning callout. We
        // force-show every config section + the warning callouts'
        // ancestor chain so at least one warning callout is visible.
        await page.evaluate(() => {
            // Reveal all hidden ancestors of every warning callout.
            const callouts = document.querySelectorAll('.cfg-callout.cfg-callout--warning');
            for (const c of callouts) {
                let cur = c;
                while (cur && cur !== document.body) {
                    if (cur.style && cur.style.display === 'none') {
                        cur.style.display = '';
                    }
                    if (cur.hasAttribute && cur.hasAttribute('hidden')) {
                        cur.removeAttribute('hidden');
                    }
                    cur = cur.parentElement;
                }
            }
            // Expand any <details> inside the first visible warning
            // callout so the full body counts toward the audit.
            const candidate = Array.from(document.querySelectorAll('.cfg-callout.cfg-callout--warning')).find(
                (el) => {
                    const cs = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return cs.display !== 'none' && rect.width > 0 && rect.height > 0;
                }
            );
            if (candidate) {
                for (const d of candidate.querySelectorAll('details')) {
                    d.open = true;
                }
            }
        });
        await page.waitForTimeout(120);

        const audit = await page.evaluate((walkSrc) => {
            // eslint-disable-next-line no-new-func
            const walkToSurface = new Function('return ' + walkSrc)();

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
                return (
                    (Math.max(lum(a), lum(b)) + 0.05) / (Math.min(lum(a), lum(b)) + 0.05)
                );
            }

            const candidates = Array.from(document.querySelectorAll('.cfg-callout.cfg-callout--warning')).filter(
                (el) => {
                    const cs = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return cs.display !== 'none' && rect.width > 0 && rect.height > 0;
                }
            );
            if (candidates.length === 0) return { found: false };

            // Audit the first visible warning callout's text-bearing
            // descendants. We deliberately skip <pre>/<code> children
                // because the TASTE class re-skins those to the dark
                // terminal palette (terminal-safe variables); they're
                // never measured against the callout surface.
            const root = candidates[0];
            const failures = [];
            let checked = 0;
            const els = [root, ...root.querySelectorAll('*')];
            for (const el of els) {
                const cs = window.getComputedStyle(el);
                if (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0') continue;
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
                if (el.closest('pre, code')) continue;

                const fg = parseRgba(cs.color);
                if (!fg || fg[3] < 0.5) continue;
                const bg = parseRgba(walkToSurface(el));
                if (!bg) continue;

                const fontSize = parseFloat(cs.fontSize);
                const fontWeight = parseInt(cs.fontWeight, 10) || 400;
                const isLarge = fontSize >= 24 || (fontSize >= 18.66 && fontWeight >= 700);
                const threshold = isLarge ? 3.0 : 4.5;
                const r = ratio(fg.slice(0, 3), bg.slice(0, 3));
                checked++;
                if (r < threshold) {
                    failures.push({
                        tag: el.tagName.toLowerCase(),
                        text: (el.textContent || '').trim().slice(0, 60),
                        ratio: Number(r.toFixed(2)),
                        fg: cs.color,
                        bg: walkToSurface(el),
                        threshold,
                    });
                }
            }
            return { found: true, checked, failures, rootId: root.id || null, rootCls: root.className };
        }, WALK_TO_SURFACE_FN.toString());

        expect(audit.found, 'no visible .cfg-callout--warning on the Configure page').toBe(true);
        expect(audit.checked, 'audit must inspect at least one text node').toBeGreaterThan(0);
        expect(
            audit.failures,
            `${audit.failures.length} WCAG AA contrast failures inside .cfg-callout--warning (${theme} theme):\n` +
                audit.failures
                    .slice(0, 10)
                    .map((f) => `  <${f.tag}> "${f.text}" — ${f.ratio}:1 (need ${f.threshold}) fg=${f.fg} bg=${f.bg}`)
                    .join('\n')
        ).toEqual([]);
    });
}
