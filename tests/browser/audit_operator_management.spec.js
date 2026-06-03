/**
 * audit_operator_management.spec.js — end-to-end audit of the OPERATOR
 * MANAGEMENT MODAL user flow, validating the 7 pipelines:
 *
 *   1. Operator chip in top-bar shows current operator name + colored dot
 *   2. Click chip → dropdown opens with Switch / Manage entries
 *   3. "Manage operators" → modal with one .spec-row per operator
 *   4. GET  /api/operators        → shape {operators[], current, default}
 *      where each operator carries {id, display, color, last_active, action_count}
 *   5. POST /api/operators        → create
 *      PATCH /api/operators/<id>  → rename + recolor → {operator}
 *   6. DELETE /api/operators/<id> → protections enforced
 *      (cannot delete current operator → 400)
 *   7. Switch operator via chip dropdown → dashboard_operator cookie updates
 *      + audit log records `operator.switch`
 *
 * SELF-CLEANUP:
 *   The user instructed us NOT to touch ~/.dashboard/operators.json. Because
 *   Flask is already running with its OWN state dir (read at module import
 *   time), this spec can't redirect Flask's storage via env var. Instead we
 *   prefix every created operator with `taudit_` + a per-suite timestamp so
 *   IDs are unique, and an afterAll() block deletes anything we created via
 *   DELETE /api/operators/<id>. The chip + cookie state is also restored
 *   to whatever the operator had before the suite ran. End-state == start.
 */

import { test, expect, request as pwRequest } from '@playwright/test';

const MGMT_MODAL = '#operator-management-modal';
const MGMT_LIST = '#operator-management-list';

// Unique per-run prefix so parallel-suite collisions are impossible and
// the afterAll cleanup can target only IDs that this run created.
const RUN_TAG = `taudit_${Date.now().toString(36)}`;
const PRIMARY_ID = `${RUN_TAG}_a`;     // will be renamed
const SECONDARY_ID = `${RUN_TAG}_b`;   // used as the switch-target / delete-target
const CREATED_IDS = new Set();

async function apiCreate(api, id, display, color = '#3b82f6') {
    const r = await api.post('/api/operators', {
        data: { id, display, color },
        headers: { 'Content-Type': 'application/json' },
    });
    CREATED_IDS.add(id);
    return { status: r.status(), body: await r.json() };
}
async function apiPatch(api, id, payload) {
    const r = await api.patch(`/api/operators/${id}`, {
        data: payload,
        headers: { 'Content-Type': 'application/json' },
    });
    return { status: r.status(), body: await r.json() };
}
async function apiDelete(api, id) {
    const r = await api.delete(`/api/operators/${id}`);
    return { status: r.status(), body: await r.json() };
}
async function apiSwitch(api, id) {
    const r = await api.post('/api/operators/switch', {
        data: { id },
        headers: { 'Content-Type': 'application/json' },
    });
    return { status: r.status(), body: await r.json(), headers: r.headers() };
}
async function apiList(api) {
    const r = await api.get('/api/operators');
    return { status: r.status(), body: await r.json() };
}
async function apiAudit(api, limit = 50) {
    const r = await api.get(`/api/audit?limit=${limit}`);
    return { status: r.status(), body: await r.json() };
}

let _originalCurrentId = null;

test.beforeAll(async () => {
    const ctx = await pwRequest.newContext({ baseURL: 'http://127.0.0.1:5050' });
    const { body } = await apiList(ctx);
    _originalCurrentId = body && body.current && body.current.id;
    await ctx.dispose();
});

test.afterAll(async () => {
    // Restore the original operator first (so we can delete anything we made
    // that might be "current" at suite end), then sweep CREATED_IDS.
    const ctx = await pwRequest.newContext({ baseURL: 'http://127.0.0.1:5050' });
    try {
        if (_originalCurrentId) {
            await apiSwitch(ctx, _originalCurrentId).catch(() => {});
        }
        for (const id of CREATED_IDS) {
            await apiDelete(ctx, id).catch(() => {});
        }
    } finally {
        await ctx.dispose();
    }
});

test.describe('operator management — full pipeline audit', () => {
    test.describe.configure({ mode: 'serial' });

    test('Pipeline 4: GET /api/operators returns the documented shape', async ({ request }) => {
        const { status, body } = await apiList(request);
        expect(status).toBe(200);
        expect(body.success).toBe(true);
        expect(Array.isArray(body.operators)).toBe(true);
        expect(body.operators.length).toBeGreaterThanOrEqual(1);
        expect(body.current).toBeTruthy();
        expect(typeof body.default).toBe('string');
        // Shape check: every entry has id/display/color/last_active/action_count.
        for (const op of body.operators) {
            expect(op).toHaveProperty('id');
            expect(op).toHaveProperty('display');
            expect(op).toHaveProperty('color');
            expect(op).toHaveProperty('last_active'); // null or ISO string
            expect(op).toHaveProperty('action_count');
            expect(typeof op.action_count).toBe('number');
        }
    });

    test('Pipeline 1+2: chip shows name + colored dot and click opens dropdown with Switch / Manage', async ({ page }) => {
        await page.goto('/');
        // Wait for operator chip to populate (loadOperators is async on DOMContentLoaded).
        const chip = page.locator('#operator-chip');
        await expect(chip).toBeVisible();
        const name = page.locator('#operator-chip-name');
        await expect(name).not.toHaveText('…', { timeout: 5000 });
        await expect(name).not.toHaveText('');
        // Dot has a computed background color (not the empty/default).
        const dotBg = await page.locator('#operator-chip-dot').evaluate(
            (el) => getComputedStyle(el).backgroundColor,
        );
        expect(dotBg).toMatch(/rgb/);
        expect(dotBg).not.toBe('rgba(0, 0, 0, 0)');

        // Click chip — dropdown should toggle visible.
        const menu = page.locator('#operator-menu');
        await expect(menu).toBeHidden();
        await chip.click();
        await expect(menu).toBeVisible();
        // "Switch operator" section label + list, and the two action items.
        await expect(menu.locator('text=Switch operator')).toBeVisible();
        await expect(page.locator('#operator-menu-list')).toBeVisible();
        await expect(page.locator('#operator-menu-add')).toBeVisible();
        await expect(page.locator('#operator-menu-manage')).toBeVisible();
    });

    test('Pipeline 3+5: Manage modal opens with one row per operator; create + rename + recolor round-trip', async ({ page, request }) => {
        // Seed two operators via API so the modal has rows to act on AND the
        // delete-protection test has a non-current operator to delete.
        await apiCreate(request, PRIMARY_ID, 'Audit Primary', '#3b82f6');
        await apiCreate(request, SECONDARY_ID, 'Audit Secondary', '#0d9488');

        await page.goto('/');
        await page.locator('#operator-chip').click();
        await page.locator('#operator-menu-manage').click();
        await page.locator(MGMT_MODAL).waitFor({ state: 'visible' });

        // Pipeline 3 — one .spec-row per operator. Verify both seeded ids render.
        const rows = page.locator(`${MGMT_LIST} [data-op-id]`);
        await expect(rows.first()).toBeVisible();
        await expect(page.locator(`${MGMT_LIST} [data-op-id="${PRIMARY_ID}"]`)).toBeVisible();
        await expect(page.locator(`${MGMT_LIST} [data-op-id="${SECONDARY_ID}"]`)).toBeVisible();

        // Pipeline 5 — UI rename + recolor via PATCH. Pick a swatch that differs.
        const primaryRow = page.locator(`${MGMT_LIST} [data-op-id="${PRIMARY_ID}"]`);
        await primaryRow.locator('[data-mgmt-edit]').click();
        await expect(primaryRow).toHaveAttribute('data-editing', 'true');

        await primaryRow.locator('[data-mgmt-display]').fill('Audit Renamed');
        // Click a different color swatch (#7c3aed = purple, definitely != current #3b82f6 blue).
        // Swatch button carries both `data-mgmt-color` (boolean) AND `data-color="<hex>"`.
        const newSwatch = primaryRow.locator('[data-mgmt-color][data-color="#7c3aed"]');
        await newSwatch.click();
        await expect(newSwatch).toHaveClass(/is-selected/);

        await primaryRow.locator('[data-mgmt-save]').click();

        // Row re-renders without editor and reflects the new display name.
        await expect(primaryRow).not.toHaveAttribute('data-editing', 'true', { timeout: 5000 });
        await expect(primaryRow.locator('.operator-mgmt__display')).toHaveText('Audit Renamed');

        // Backend state matches.
        const { body } = await apiList(request);
        const updated = body.operators.find((o) => o.id === PRIMARY_ID);
        expect(updated).toBeTruthy();
        expect(updated.display).toBe('Audit Renamed');
        expect(updated.color.toLowerCase()).toBe('#7c3aed');
    });

    test('Pipeline 5b: PATCH endpoint shape matches contract', async ({ request }) => {
        const { status, body } = await apiPatch(request, SECONDARY_ID, {
            display: 'Audit Second Renamed',
            color: '#ea580c',
        });
        expect(status).toBe(200);
        expect(body.success).toBe(true);
        expect(body.operator).toBeTruthy();
        expect(body.operator.id).toBe(SECONDARY_ID);
        expect(body.operator.display).toBe('Audit Second Renamed');
        expect(body.operator.color.toLowerCase()).toBe('#ea580c');
    });

    test('Pipeline 6: DELETE protections — UI disables delete for current operator; backend also rejects', async ({ page, request }) => {
        // 2026-05-23 — Backend gap audited here originally has now been
        // CLOSED. operator_service.remove() accepts `current_id` and the
        // route at routes/operators.py passes `g.operator['id']` so
        // direct DELETE on the cookie-resolved operator returns 400.

        // --- Layer 1: UI protection — current operator's Delete button is disabled.
        await apiSwitch(request, SECONDARY_ID);
        await page.goto('/');
        await page.locator('#operator-chip').click();
        await page.locator('#operator-menu-manage').click();
        await page.locator(MGMT_MODAL).waitFor({ state: 'visible' });
        const activeRow = page.locator(`${MGMT_LIST} .spec-row`).filter({
            has: page.locator('.operator-mgmt__pill--current'),
        }).first();
        await activeRow.locator('[data-mgmt-edit]').click();
        const delBtn = activeRow.locator('[data-mgmt-delete]');
        await expect(delBtn).toBeDisabled();
        const tip = await delBtn.getAttribute('title');
        expect(tip || '').toMatch(/switch|current/i);

        // --- Layer 2: Backend protection — direct DELETE on the current
        // operator now returns 400 with the "switch to another operator"
        // error message. Operator is NOT removed.
        const directDel = await apiDelete(request, SECONDARY_ID);
        expect(directDel.status).toBe(400);
        expect(directDel.body.success).toBe(false);
        expect((directDel.body.error || '').toLowerCase()).toMatch(/currently-active|switch/);
        const after = await apiList(request);
        expect(after.body.operators.find((o) => o.id === SECONDARY_ID)).toBeTruthy();

        // --- Layer 3: Backend also rejects not-found.
        const bogus = await apiDelete(request, `${RUN_TAG}_does_not_exist`);
        expect(bogus.status).toBe(400);
        expect(bogus.body.success).toBe(false);
        expect(typeof bogus.body.error).toBe('string');
        expect(bogus.body.error.toLowerCase()).toContain('not found');
    });

    test('Pipeline 6b: DELETE works for a non-current operator and removes it from /api/operators', async ({ request }) => {
        // Create a throwaway and switch off it before deleting so the
        // current-operator gap (audited in Pipeline 6) isn't on the path.
        const throwaway = `${RUN_TAG}_throwaway`;
        await apiCreate(request, throwaway, 'Throwaway', '#65a30d');
        await apiSwitch(request, PRIMARY_ID);

        const del = await apiDelete(request, throwaway);
        expect(del.status).toBe(200);
        expect(del.body.success).toBe(true);
        CREATED_IDS.delete(throwaway);

        const { body } = await apiList(request);
        expect(body.operators.find((o) => o.id === throwaway)).toBeFalsy();
    });

    test('Pipeline 7: switch via chip dropdown updates dashboard_operator cookie + audit log records operator.switch', async ({ page, request, context }) => {
        await page.goto('/');
        // Ensure PRIMARY_ID is in the dropdown by reloading operators state.
        await page.evaluate(() => (typeof loadOperators === 'function' ? loadOperators() : null));
        await page.locator('#operator-chip').click();
        await expect(page.locator('#operator-menu')).toBeVisible();

        // Click the PRIMARY_ID button inside the Switch operator list.
        const target = page.locator(`#operator-menu-list .operator-menu__operator:has-text("${PRIMARY_ID}")`).first();
        await target.click();

        // Chip should update its name (loadOperators / renderOperatorChip).
        await expect(page.locator('#operator-chip-name')).toHaveText('Audit Renamed', { timeout: 5000 });

        // Cookie set by /api/operators/switch — Playwright surfaces it on the
        // context.
        const cookies = await context.cookies();
        const ck = cookies.find((c) => c.name === 'dashboard_operator');
        expect(ck).toBeTruthy();
        expect(ck.value).toBe(PRIMARY_ID);

        // Audit log records the switch. Hit /api/audit and look for the row.
        const { body } = await apiAudit(request, 100);
        expect(Array.isArray(body.entries)).toBe(true);
        const switchEntry = body.entries.find(
            (e) => e.action === 'operator.switch' && e.target === PRIMARY_ID,
        );
        expect(switchEntry, 'expected an operator.switch audit row targeting PRIMARY_ID').toBeTruthy();
    });
});
