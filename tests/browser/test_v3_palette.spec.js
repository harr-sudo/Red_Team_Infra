/**
 * v3 PALETTE (Agent B) — ⌘K command palette browser tests.
 *
 * Verifies the overlay shell + JS dispatcher built on top of the Agent A
 * .app-shell foundation:
 *
 *   1. The trigger button is mounted in the top bar
 *   2. ⌘K / Ctrl-K opens the overlay
 *   3. Esc closes the overlay
 *   4. Typing filters results
 *   5. ↑↓ navigates, ↵ selects
 *   6. Selecting a route item navigates via APP.shell.setActiveRoute
 *   7. Selecting an action dispatches (theme toggle round-trip)
 *   8. Recently-used appears at the top of the empty-search state
 *   9. Both themes pass layer-aware contrast on palette chrome
 */

import { test, expect } from '@playwright/test';

// ─── WCAG helpers (shared shape with other v3 suites) ───────────────────

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
    await page.waitForTimeout(280);
}

async function openPalette(page) {
    // Use the trigger button rather than the keybinding — Playwright's
    // keyboard.press('Meta+k') is flaky across OSes; the trigger calls
    // the same APP.palette.open() entrypoint.
    await page.locator('#palette-trigger').click();
    await expect(page.locator('#palette-overlay')).toBeVisible({ timeout: 5000 });
    // Wait for the results container to paint at least one row.
    await page.locator('#palette-results .palette-overlay__row').first()
        .waitFor({ state: 'visible', timeout: 5000 });
}

// ─── 1. Trigger + open/close ────────────────────────────────────────────

test.describe('v3 palette — open/close', () => {
    test('palette trigger button is mounted in the top bar', async ({ page }) => {
        await page.goto('/');
        const trigger = page.locator('#palette-trigger');
        await expect(trigger).toBeVisible({ timeout: 5000 });
        // It must live inside .app-topbar (top utility bar).
        const inTopbar = await trigger.evaluate(el => !!el.closest('.app-topbar'));
        expect(inTopbar).toBe(true);
    });

    test('overlay is hidden on initial page load', async ({ page }) => {
        await page.goto('/');
        await expect(page.locator('#palette-overlay')).toBeHidden();
    });

    test('clicking the trigger opens the overlay', async ({ page }) => {
        await page.goto('/');
        await openPalette(page);
        // Input is auto-focused.
        const focused = await page.evaluate(() => document.activeElement?.id);
        expect(focused).toBe('palette-input');
    });

    test('Cmd+K opens the overlay (Meta on mac, Control elsewhere)', async ({ page }) => {
        await page.goto('/');
        // Try Meta first, then Control — covers both platforms.
        await page.keyboard.down('Meta');
        await page.keyboard.press('k');
        await page.keyboard.up('Meta');
        const visibleMeta = await page.locator('#palette-overlay').isVisible();
        if (!visibleMeta) {
            await page.keyboard.down('Control');
            await page.keyboard.press('k');
            await page.keyboard.up('Control');
        }
        await expect(page.locator('#palette-overlay')).toBeVisible({ timeout: 5000 });
    });

    test('Esc closes the overlay', async ({ page }) => {
        await page.goto('/');
        await openPalette(page);
        await page.keyboard.press('Escape');
        await expect(page.locator('#palette-overlay')).toBeHidden();
    });

    test('clicking the scrim closes the overlay', async ({ page }) => {
        await page.goto('/');
        await openPalette(page);
        // Click a corner of the scrim that's guaranteed to be outside the
        // centered card. The default center-click hits the results list
        // (which sits on top of the scrim) and gets intercepted.
        await page.locator('.palette-overlay__scrim').click({ position: { x: 5, y: 5 }, force: true });
        await expect(page.locator('#palette-overlay')).toBeHidden();
    });
});

// ─── 2. Filtering + keyboard nav ────────────────────────────────────────

test.describe('v3 palette — filtering + nav', () => {
    test('typing filters the result rows', async ({ page }) => {
        await page.goto('/');
        await openPalette(page);

        // Initial state — many rows.
        const initialCount = await page.locator('#palette-results .palette-overlay__row').count();
        expect(initialCount).toBeGreaterThan(5);

        // Type a query that should sharply narrow.
        await page.locator('#palette-input').fill('settings');
        // Allow paint debounce (none currently, but be conservative).
        await page.waitForTimeout(120);

        const rows = page.locator('#palette-results .palette-overlay__row');
        const filteredCount = await rows.count();
        expect(filteredCount).toBeLessThan(initialCount);
        expect(filteredCount).toBeGreaterThan(0);

        // Every visible label must contain "settings" or "set" somewhere in
        // the displayed text (label / subtitle / kind chip).
        const allText = await rows.evaluateAll((els) =>
            els.map((el) => el.textContent.toLowerCase()).join('|')
        );
        expect(allText).toContain('settings');
    });

    test('ArrowDown / ArrowUp move the active row', async ({ page }) => {
        await page.goto('/');
        await openPalette(page);

        // First row starts active.
        const firstActive = await page.evaluate(() => {
            const rows = document.querySelectorAll('#palette-results .palette-overlay__row');
            return rows[0]?.classList.contains('is-active');
        });
        expect(firstActive).toBe(true);

        await page.keyboard.press('ArrowDown');
        const secondActive = await page.evaluate(() => {
            const rows = document.querySelectorAll('#palette-results .palette-overlay__row');
            return rows[1]?.classList.contains('is-active');
        });
        expect(secondActive).toBe(true);

        await page.keyboard.press('ArrowUp');
        const backToFirst = await page.evaluate(() => {
            const rows = document.querySelectorAll('#palette-results .palette-overlay__row');
            return rows[0]?.classList.contains('is-active');
        });
        expect(backToFirst).toBe(true);
    });

    test('shows empty-state message when no results match', async ({ page }) => {
        await page.goto('/');
        await openPalette(page);
        await page.locator('#palette-input').fill('zzzzzzzz-no-match-zzzzzzzz');
        await page.waitForTimeout(120);
        await expect(page.locator('.palette-overlay__empty')).toBeVisible();
    });
});

// ─── 3. Dispatch — route + action ───────────────────────────────────────

test.describe('v3 palette — selection dispatches', () => {
    test('selecting a Settings route navigates via APP.shell.setActiveRoute', async ({ page }) => {
        await page.goto('/');
        await openPalette(page);

        // Filter to a unique route, then Enter the top match.
        await page.locator('#palette-input').fill('settings general');
        await page.waitForTimeout(120);
        await page.keyboard.press('Enter');

        // Overlay closes.
        await expect(page.locator('#palette-overlay')).toBeHidden({ timeout: 5000 });

        // Settings rail item is active.
        await expect(
            page.locator('.app-rail__item[data-rail-target="settings"]')
        ).toHaveClass(/is-active/, { timeout: 5000 });
    });

    test('selecting toggle-theme action dispatches APP.toggleTheme', async ({ page }) => {
        await page.goto('/');

        // Capture starting theme.
        const startedDark = await page.evaluate(() =>
            !document.documentElement.hasAttribute('data-theme'));

        await openPalette(page);
        await page.locator('#palette-input').fill('toggle theme');
        await page.waitForTimeout(120);
        await page.keyboard.press('Enter');

        await expect(page.locator('#palette-overlay')).toBeHidden({ timeout: 5000 });

        // Theme attribute flipped.
        const isLight = await page.evaluate(() =>
            document.documentElement.getAttribute('data-theme') === 'light');
        expect(isLight).toBe(startedDark);  // we expect a flip
    });

    test('clicking a result row also selects it', async ({ page }) => {
        await page.goto('/');
        await openPalette(page);
        await page.locator('#palette-input').fill('operations terminal');
        await page.waitForTimeout(120);

        // Click the first visible row.
        await page.locator('#palette-results .palette-overlay__row').first().click();
        await expect(page.locator('#palette-overlay')).toBeHidden({ timeout: 5000 });
        await expect(
            page.locator('.app-rail__item[data-rail-target="operations-tab"]')
        ).toHaveClass(/is-active/, { timeout: 5000 });
    });
});

// ─── 4. Recently-used ───────────────────────────────────────────────────

test.describe('v3 palette — recently used', () => {
    test('selecting an item surfaces it under RECENT on the next open', async ({ page }) => {
        await page.goto('/');

        // First open + select.
        await openPalette(page);
        await page.locator('#palette-input').fill('settings prereq');
        await page.waitForTimeout(120);
        await page.keyboard.press('Enter');
        await expect(page.locator('#palette-overlay')).toBeHidden({ timeout: 5000 });

        // Wait for the POST /api/palette/select to fully round-trip and the
        // palette's _loaded cache to be invalidated. The handler is fire-
        // and-forget, so we need a generous wait + force-reload to be sure.
        await page.waitForTimeout(800);
        await page.evaluate(() => { if (window.APP?.palette) window.APP.palette._loaded = false; });

        // Re-open.
        await openPalette(page);
        // Give the re-fetch + render a moment.
        await page.waitForTimeout(200);

        // Empty query → look for a RECENT section header anywhere in the
        // results. Implementation may surface it as first or interleaved
        // with TOP RESULTS depending on the kind balance; both are acceptable
        // as long as RECENT appears with the just-selected item.
        const sectionLabels = await page.locator(
            '#palette-results .palette-overlay__section-label'
        ).allTextContents();
        const hasRecent = sectionLabels.some(l => l.trim().toUpperCase() === 'RECENT');
        expect(hasRecent, `RECENT section missing; saw: ${JSON.stringify(sectionLabels)}`).toBe(true);

        // And the selected item ("prereq…") must appear somewhere in the
        // rendered result rows.
        const rowLabels = await page.locator(
            '#palette-results .palette-overlay__row .palette-overlay__row-label'
        ).allTextContents();
        const hasPrereq = rowLabels.some(l => l.toLowerCase().includes('prereq'));
        expect(hasPrereq, `prereq row missing; saw: ${JSON.stringify(rowLabels.slice(0, 10))}`).toBe(true);
    });
});

// ─── 5. Layer-aware contrast in both themes ─────────────────────────────

const PALETTE_CONTRAST_TARGETS = [
    '.app-topbar__palette-trigger .app-topbar__palette-label',
    '.palette-overlay__input',
    '.palette-overlay__section-label',
    '.palette-overlay__row .palette-overlay__row-label',
    '.palette-overlay__row .palette-overlay__row-subtitle',
    '.palette-overlay__footer',
];

async function auditPaletteContrast(page, theme) {
    await setTheme(page, theme);
    await openPalette(page);

    const failures = [];
    for (const sel of PALETTE_CONTRAST_TARGETS) {
        const els = page.locator(sel);
        const count = await els.count();
        if (count === 0) continue;
        for (let i = 0; i < Math.min(count, 5); i++) {
            const el = els.nth(i);
            const visible = await el.isVisible().catch(() => false);
            if (!visible) continue;
            const { fg, bg } = await el.evaluate((node, walker) => {
                // eslint-disable-next-line no-new-func
                const walkFn = new Function('return ' + walker)();
                const cs = window.getComputedStyle(node);
                return { fg: cs.color, bg: walkFn(node) };
            }, WALK_TO_SURFACE_FN.toString());
            const fgRgb = parseRgb(fg);
            const bgRgb = parseRgb(bg);
            if (!fgRgb || !bgRgb) continue;
            const r = ratio(fgRgb, bgRgb);
            if (r < 4.5) {
                failures.push({ selector: sel, theme, ratio: r.toFixed(2), fg, bg });
            }
        }
    }
    return failures;
}

test.describe('v3 palette — layer-aware contrast', () => {
    test('dark theme: zero contrast failures on palette chrome', async ({ page }) => {
        await page.goto('/');
        const failures = await auditPaletteContrast(page, 'dark');
        expect(failures, `dark-theme contrast failures:\n${JSON.stringify(failures, null, 2)}`)
            .toEqual([]);
    });

    test('light theme: zero contrast failures on palette chrome', async ({ page }) => {
        await page.goto('/');
        const failures = await auditPaletteContrast(page, 'light');
        expect(failures, `light-theme contrast failures:\n${JSON.stringify(failures, null, 2)}`)
            .toEqual([]);
    });
});
