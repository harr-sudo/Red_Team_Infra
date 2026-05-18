/**
 * M-OperatorManagement (Phase 3) — Manage operators modal Playwright tests.
 *
 * Smoke + interaction coverage for the modal wired from the operator chip
 * dropdown's "Manage…" item. Each test seeds at least two operators via
 * the live POST endpoint so deletion paths (which can't touch the only
 * operator or the active one) have something to act on.
 *
 * Tests assume the backend is running on the same origin as Playwright's
 * baseURL (see playwright.config.js → http://127.0.0.1:5050). Failures
 * here typically indicate either the route wiring broke, the modal
 * markup drifted, or the .spec-row primitives changed contract.
 */

import { test, expect } from '@playwright/test';

const MGMT_MODAL = '#operator-management-modal';
const MGMT_LIST = '#operator-management-list';

async function ensureSecondOperator(page, id = 'pwtest') {
    // Create via API (no UI) so each test starts from a known state. If the
    // operator already exists the backend returns 400 — that's fine, we just
    // need it to be present.
    await page.evaluate(async (opId) => {
        try {
            await fetch('/api/operators', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: opId, display: 'Pw Test', color: '#65a30d' }),
            });
        } catch (_) { /* idempotent */ }
    }, id);
}

async function openManagementModal(page) {
    // Open via the dropdown so we verify the wire-up.
    await page.locator('#operator-chip').click();
    await page.locator('#operator-menu-manage').click();
    await page.locator(MGMT_MODAL).waitFor({ state: 'visible' });
}

test.describe('operator management modal', () => {
    test('dropdown "Manage…" opens the modal and lists every operator', async ({ page }) => {
        await page.goto('/');
        await ensureSecondOperator(page);
        await openManagementModal(page);

        // List populates with at least 2 rows (the seeded default + pwtest).
        const rows = page.locator(`${MGMT_LIST} [data-op-id]`);
        await expect(rows.first()).toBeVisible();
        const count = await rows.count();
        expect(count).toBeGreaterThanOrEqual(2);
        // Every row exposes the edit affordance.
        await expect(page.locator(`${MGMT_LIST} [data-mgmt-edit]`).first()).toBeVisible();
    });

    test('edit flow: clicking the pencil expands the editor; Save persists', async ({ page }) => {
        await page.goto('/');
        await ensureSecondOperator(page);
        await openManagementModal(page);

        const row = page.locator(`${MGMT_LIST} [data-op-id="pwtest"]`);
        await row.locator('[data-mgmt-edit]').click();
        await expect(row).toHaveAttribute('data-editing', 'true');
        // Editor exposes display input + color grid + Save/Cancel/Delete.
        const input = row.locator('[data-mgmt-display]');
        await expect(input).toBeVisible();
        await input.fill('Renamed Pw');
        await row.locator('[data-mgmt-save]').click();

        // Row collapses back to read state and re-renders with the new name.
        await expect(row).not.toHaveAttribute('data-editing', 'true');
        await expect(row.locator('.operator-mgmt__display')).toHaveText('Renamed Pw');
    });

    test('cancel collapses the editor without saving', async ({ page }) => {
        await page.goto('/');
        await ensureSecondOperator(page);
        await openManagementModal(page);

        const row = page.locator(`${MGMT_LIST} [data-op-id="pwtest"]`);
        const originalName = await row.locator('.operator-mgmt__display').textContent();
        await row.locator('[data-mgmt-edit]').click();
        await row.locator('[data-mgmt-display]').fill('NOPE');
        await row.locator('[data-mgmt-cancel]').click();
        await expect(row).not.toHaveAttribute('data-editing', 'true');
        // Display still matches what it was before the abandoned edit.
        await expect(row.locator('.operator-mgmt__display')).toHaveText(originalName.trim());
    });

    test('delete flow: confirm strip appears, Confirm removes the row', async ({ page }) => {
        await page.goto('/');
        // Use a fresh non-active id so deletion isn't blocked.
        const id = 'deltest';
        await page.evaluate(async (opId) => {
            await fetch('/api/operators', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: opId, display: 'Delete Me', color: '#7c3aed' }),
            }).catch(() => {});
        }, id);
        await openManagementModal(page);

        const row = page.locator(`${MGMT_LIST} [data-op-id="${id}"]`);
        await row.locator('[data-mgmt-edit]').click();
        const delBtn = row.locator('[data-mgmt-delete]');
        await expect(delBtn).toBeEnabled();
        await delBtn.click();
        // Inline confirm appears
        await expect(row.locator('.operator-mgmt__confirm')).toBeVisible();
        await row.locator('[data-mgmt-delete-confirm]').click();
        // Row is gone after the API completes + re-render.
        await expect(row).toHaveCount(0, { timeout: 5000 });
    });

    test('cannot delete the currently-active operator — button disabled with tooltip', async ({ page }) => {
        await page.goto('/');
        await ensureSecondOperator(page);
        await openManagementModal(page);

        // The current operator row carries the "Active" pill.
        const currentRow = page.locator(`${MGMT_LIST} .spec-row`).filter({
            has: page.locator('.operator-mgmt__pill--current'),
        }).first();
        await currentRow.locator('[data-mgmt-edit]').click();
        const delBtn = currentRow.locator('[data-mgmt-delete]');
        await expect(delBtn).toBeDisabled();
        // Tooltip surfaces the reason
        const tip = await delBtn.getAttribute('title');
        expect(tip || '').toMatch(/switch/i);
    });

    test('Add operator button chains to the existing Add Operator modal', async ({ page }) => {
        await page.goto('/');
        await ensureSecondOperator(page);
        await openManagementModal(page);

        await page.locator('#operator-management-add').click();
        // Management modal closes; Add modal opens.
        await expect(page.locator(MGMT_MODAL)).toBeHidden();
        await expect(page.locator('#add-operator-modal')).toBeVisible();
    });

    for (const theme of ['dark', 'light']) {
        test(`modal renders with no AA contrast failures (${theme})`, async ({ page }) => {
            await page.goto('/');
            await ensureSecondOperator(page);
            // Set theme BEFORE opening so the editor + pills paint with the
            // right tokens from the start.
            await page.evaluate((t) => document.documentElement.setAttribute('data-theme', t), theme);
            await openManagementModal(page);
            // Expand a row's editor so its inputs/buttons enter the DOM and
            // get walked by the contrast sweep.
            const firstRow = page.locator(`${MGMT_LIST} [data-op-id]`).first();
            await firstRow.locator('[data-mgmt-edit]').click();
            // Walk every visible text element inside the modal and flag
            // anything below AA threshold. Walking the modal alone (not
            // the whole page) keeps this test self-contained — the global
            // sweep lives in test_contrast_invariants.spec.js.
            const failures = await page.locator(MGMT_MODAL).evaluate((root) => {
                function parseRgb(s) {
                    const m = s.match(/rgba?\(([^)]+)\)/);
                    if (!m) return null;
                    return m[1].split(',').map((p) => parseFloat(p.trim()));
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
                function walkBg(el) {
                    let cur = el;
                    while (cur) {
                        const cs = getComputedStyle(cur);
                        const bg = parseRgb(cs.backgroundColor || '');
                        if (bg && (bg[3] === undefined || bg[3] >= 0.5)) return bg;
                        cur = cur.parentElement;
                    }
                    return parseRgb(getComputedStyle(document.body).backgroundColor);
                }
                const out = [];
                root.querySelectorAll('*').forEach((el) => {
                    const cs = getComputedStyle(el);
                    if (cs.display === 'none' || cs.visibility === 'hidden') return;
                    if (el.getAttribute('aria-hidden') === 'true') return;
                    // Skip legacy global primitives that aren't owned by this
                    // modal — .btn-primary contrast is governed by the global
                    // contrast invariants suite, not this in-modal sweep.
                    if (el.classList.contains('btn-primary')) return;
                    if (el.classList.contains('btn-secondary')) return;
                    let hasText = false;
                    for (const c of el.childNodes) {
                        if (c.nodeType === 3 && c.textContent.trim().length > 0) {
                            hasText = true; break;
                        }
                    }
                    if (!hasText) return;
                    const fg = parseRgb(cs.color);
                    const bg = walkBg(el);
                    if (!fg || !bg) return;
                    if (fg[3] !== undefined && fg[3] < 0.5) return;
                    const r = ratio(fg.slice(0, 3), bg.slice(0, 3));
                    const fontSize = parseFloat(cs.fontSize);
                    const fontWeight = parseInt(cs.fontWeight, 10) || 400;
                    const isLarge = fontSize >= 24 || (fontSize >= 18.66 && fontWeight >= 700);
                    const threshold = isLarge ? 3.0 : 4.5;
                    if (r < threshold) {
                        out.push({
                            text: (el.textContent || '').trim().slice(0, 50),
                            ratio: Number(r.toFixed(2)),
                            threshold,
                            cls: el.className,
                        });
                    }
                });
                return out;
            });
            expect(failures, `${theme} contrast failures inside modal:\n${JSON.stringify(failures, null, 2)}`).toEqual([]);
        });
    }
});
