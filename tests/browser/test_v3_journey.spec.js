/**
 * Phase 2B — "+ New Deployment" Hybrid journey takeover.
 *
 * Verifies:
 *   1. Click "+ New" → takeover scrim + card animate in; body gets
 *      data-journey-open.
 *   2. Wizard steps 1-4 navigate forward + back.
 *   3. Step 4 → "Review" lands on the spec-list review screen with all
 *      7 expected rows.
 *   4. Clicking a review row pencil opens the editor; Save commits to
 *      the in-memory state and re-renders.
 *   5. Escape closes the takeover (no dirty state).
 *   6. Both themes pass layer-aware contrast over the takeover card
 *      (wizard view + review view + editing-row view).
 */

import { test, expect } from '@playwright/test';

async function setTheme(page, theme) {
    await page.evaluate((t) => {
        if (t === 'light') document.documentElement.setAttribute('data-theme', 'light');
        else document.documentElement.removeAttribute('data-theme');
    }, theme);
    await page.waitForTimeout(320);
}

async function openJourney(page) {
    await page.goto('/');
    await page.locator('#global-new-deployment-btn').waitFor({ timeout: 5000 });
    // Capture window.confirm so cancel-with-dirty doesn't block tests
    await page.evaluate(() => {
        window._origConfirm = window.confirm;
        window.confirm = () => true;
    });
    await page.click('#global-new-deployment-btn');
    // Wait for transition + first render
    await page.waitForTimeout(400);
}

test('+ New Deployment opens the takeover and dims the dashboard', async ({ page }) => {
    await openJourney(page);
    const card = page.locator('#journey-takeover');
    const scrim = page.locator('#journey-scrim');
    await expect(card).toBeVisible();
    await expect(card).toHaveAttribute('data-open', 'true');
    await expect(scrim).toHaveAttribute('data-open', 'true');
    const journeyOpen = await page.evaluate(() => document.body.getAttribute('data-journey-open'));
    expect(journeyOpen).toBe('true');
});

test('journey wizard navigates Family → Type → Identity → Network → Review', async ({ page }) => {
    await openJourney(page);
    // Step 1 — Family. Pick GOAD.
    await page.locator('#journey-takeover .journey-card-option input[value="goad"]').check();
    await page.click('#journey-next');
    await page.waitForTimeout(150);
    expect(await page.locator('.journey-step.is-active .journey-step__title').textContent()).toMatch(/specific type/i);

    // Step 2 — Type. (Default goad-mini selected.)
    await page.click('#journey-next');
    await page.waitForTimeout(150);
    expect(await page.locator('.journey-step.is-active .journey-step__title').textContent()).toMatch(/name this/i);

    // Step 3 — Identity. Continue.
    await page.click('#journey-next');
    await page.waitForTimeout(150);
    expect(await page.locator('.journey-step.is-active .journey-step__title').textContent()).toMatch(/network/i);

    // Step 4 — Network. Review.
    await page.click('#journey-next');
    await page.waitForTimeout(250);

    // Review phase
    await expect(page.locator('#journey-review')).toHaveClass(/is-active/);
    const rowCount = await page.locator('#journey-spec-list .spec-row').count();
    expect(rowCount).toBe(7);  // type, projectName, environment, region, cidr, ssh, cost
});

test('journey review: clicking a row expands the editor, Save commits', async ({ page }) => {
    await openJourney(page);
    // Fast-track to review
    await page.click('#journey-next');  // 1→2
    await page.waitForTimeout(120);
    await page.click('#journey-next');  // 2→3
    await page.waitForTimeout(120);
    await page.click('#journey-next');  // 3→4
    await page.waitForTimeout(120);
    await page.click('#journey-next');  // 4→Review
    await page.waitForTimeout(200);

    // Click the projectName row's head
    const row = page.locator('#journey-spec-list .spec-row[data-review-row="projectName"]');
    await row.locator('.spec-row__head').click();
    await page.waitForTimeout(150);
    await expect(row).toHaveAttribute('data-editing', 'true');

    // Type a new value and save
    const input = row.locator('[data-edit-input]');
    await input.fill('phase2b_test_project');
    await row.locator('[data-edit-action="save"]').click();
    await page.waitForTimeout(150);

    // Row should be closed and value visible
    await expect(row).not.toHaveAttribute('data-editing', 'true');
    await expect(row.locator('.spec-row__value')).toContainText('phase2b_test_project');
});

test('Escape closes the journey (confirm prompt is auto-accepted)', async ({ page }) => {
    await openJourney(page);
    // Dirty the state on step 1 (family is rendered)
    await page.locator('#journey-takeover .journey-card-option input[value="c2"]').check();
    await page.waitForTimeout(80);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(400);
    const open = await page.evaluate(() => document.body.getAttribute('data-journey-open'));
    expect(open).toBeNull();
});

// Helper used by the contrast tests
async function auditContrast(page, rootSel, opts = {}) {
    const { onlyEditor = false } = opts;
    return page.evaluate(({ rootSel, onlyEditor }) => {
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
        let scope = root;
        if (onlyEditor) {
            scope = root.querySelector('.spec-row[data-editing="true"] [data-review-editor]') || root;
        }
        scope.querySelectorAll('*').forEach(el => {
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
            // Skip sibling-dim rows (designed affordance)
            if (el.closest('.spec-row:not([data-editing="true"])') && el.closest('.spec-list[data-editing="true"]')) {
                return;
            }
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
                    bg: `rgb(${bg.join(', ')})`,
                });
            }
        });
        return failures;
    }, { rootSel, onlyEditor });
}

for (const theme of ['dark', 'light']) {
    test(`journey wizard passes contrast (${theme} theme)`, async ({ page }) => {
        await openJourney(page);
        await setTheme(page, theme);
        const failures = await auditContrast(page, '#journey-takeover');
        if (failures.length) {
            // eslint-disable-next-line no-console
            console.log(`Journey wizard (${theme}) failures:`, JSON.stringify(failures, null, 2));
        }
        expect(failures, `${failures.length} AA failures in journey wizard, ${theme}`).toEqual([]);
    });
}

for (const theme of ['dark', 'light']) {
    test(`journey review passes contrast (${theme} theme)`, async ({ page }) => {
        await openJourney(page);
        // Fast-track to review
        for (let i = 0; i < 4; i++) {
            await page.click('#journey-next');
            await page.waitForTimeout(120);
        }
        await setTheme(page, theme);
        await page.waitForTimeout(200);

        const failures = await auditContrast(page, '#journey-review');
        if (failures.length) {
            // eslint-disable-next-line no-console
            console.log(`Journey review (${theme}) failures:`, JSON.stringify(failures, null, 2));
        }
        expect(failures, `${failures.length} AA failures in journey review, ${theme}`).toEqual([]);
    });
}

for (const theme of ['dark', 'light']) {
    test(`journey review editor (open row) passes contrast (${theme} theme)`, async ({ page }) => {
        await openJourney(page);
        for (let i = 0; i < 4; i++) {
            await page.click('#journey-next');
            await page.waitForTimeout(120);
        }
        await page.locator('#journey-spec-list .spec-row[data-review-row="environment"] .spec-row__head').click();
        await page.waitForTimeout(200);
        await setTheme(page, theme);
        await page.waitForTimeout(200);

        const failures = await auditContrast(page, '#journey-review', { onlyEditor: true });
        if (failures.length) {
            // eslint-disable-next-line no-console
            console.log(`Journey editor (${theme}) failures:`, JSON.stringify(failures, null, 2));
        }
        expect(failures, `${failures.length} AA failures in journey editor, ${theme}`).toEqual([]);
    });
}
