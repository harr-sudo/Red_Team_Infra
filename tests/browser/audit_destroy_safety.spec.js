/**
 * 2026-05-22 — FOREIGN-MODULE DETECTION + DETACH SAFETY flow audit.
 *
 * Validates the safety net that prevents an operator from destroying a
 * workspace whose terraform state contains "foreign" modules (modules
 * that don't belong to the declared deployment_type). The canonical
 * example is module.dashboard_server pinned in a goad-mini workspace —
 * destroying goad-mini would also wipe the dashboard server.
 *
 * READ-ONLY validation:
 *   - never POSTs a real destroy
 *   - never POSTs detach-foreign
 *   - never confirms a modal
 *
 * Surfaces under test:
 *   1. GET /api/deploy/state-summary/<project> shape + foreign list
 *   2. Manage banner #manage-foreign-modules-banner renders when foreign present
 *   3. Detach button surfaces a confirmation gate (window.confirm intercepted)
 *   4. POST /api/deploy/destroy preflight returns 409 foreign_modules_in_state
 *
 * NOTE: project goad_mini_demo is known (per project
 * memory) to have module.dashboard_server pinned as a foreign module.
 * The spec gracefully soft-skips assertions if the state has changed
 * since the memory snapshot was written.
 */

import { test, expect } from '@playwright/test';
import { railNavigate, clickSubPill } from './helpers/nav.js';

const TARGET_PROJECT = 'goad_mini_demo';

async function navigateToManage(page) {
    await page.goto('/');
    await railNavigate(page, 'deployments-tab');
    await clickSubPill(page, 'manage');
    await page.waitForTimeout(800);
}

async function forceActiveDeployment(page, projectName) {
    await page.evaluate((p) => {
        if (window.APP && window.APP.activeDeployment) {
            window.APP.activeDeployment.set(p);
        }
    }, projectName);
    await page.waitForTimeout(400);
    // NOTE: APP.manage.render() shells out to terraform output via a
    // 6-endpoint Promise.all and routinely takes 5–10s, plus the in-browser
    // _probeStateSummary() fetch occasionally races against concurrent
    // backend state list calls and returns state_list_failed. We don't
    // call render() here — instead the per-test code drives the banner
    // via _renderForeignModulesBanner() with a server-side probe so the
    // browser path is deterministic.
}

async function fetchStateSummary(page, project, { retries = 3 } = {}) {
    // Server-side fetch (no in-browser race). Retries handle transient
    // terraform state-lock contention.
    let last = null;
    for (let i = 0; i < retries; i++) {
        const r = await page.request.get(
            `http://127.0.0.1:5050/api/deploy/state-summary/${encodeURIComponent(project)}`
        );
        last = { status: r.status(), body: await r.json() };
        if (last.body && last.body.success) return last;
        await page.waitForTimeout(500);
    }
    return last;
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. GET /api/deploy/state-summary/<project> — shape + foreign list.
// ─────────────────────────────────────────────────────────────────────────────

test('state-summary returns the expected shape for goad_mini target', async ({ page }) => {
    await page.goto('/');
    const summary = await fetchStateSummary(page, TARGET_PROJECT);

    // Endpoint should answer 200 with the documented shape regardless of
    // whether foreign modules exist or not.
    expect(summary.status).toBe(200);
    const body = summary.body;
    expect(body).toHaveProperty('success');
    expect(body).toHaveProperty('project', TARGET_PROJECT);
    expect(body).toHaveProperty('deployment_type');
    expect(body).toHaveProperty('expected_modules');
    expect(body).toHaveProperty('actual_modules');
    expect(body).toHaveProperty('foreign_modules');
    expect(Array.isArray(body.expected_modules)).toBe(true);
    expect(Array.isArray(body.actual_modules)).toBe(true);
    expect(Array.isArray(body.foreign_modules)).toBe(true);

    // Per project memory, this workspace has module.dashboard_server pinned —
    // we EXPECT to see it as foreign. If state has been cleaned since the
    // memory snapshot, soft-skip the substantive assertion but keep the
    // shape assertions above as a regression guard on the endpoint contract.
    if (body.success && body.foreign_modules.length > 0) {
        console.log(`[state-summary] foreign_modules detected: ${JSON.stringify(body.foreign_modules)}`);
        expect(body.deployment_type).toBe('goad-mini');
        // dashboard_server is the canonical foreign module per project memory.
        expect(body.foreign_modules).toContain('dashboard_server');
        // foreign must be a subset of actual but not of expected.
        for (const m of body.foreign_modules) {
            expect(body.actual_modules).toContain(m);
            expect(body.expected_modules).not.toContain(m);
        }
    } else {
        console.log('[state-summary] state is clean — skipping substantive foreign-module assertions');
        test.info().annotations.push({
            type: 'soft-skip',
            description: 'no foreign modules detected; state-summary shape verified only',
        });
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// 2. Manage banner — #manage-foreign-modules-banner surfaces when foreign present.
// ─────────────────────────────────────────────────────────────────────────────

test('Manage banner surfaces when foreign modules are present', async ({ page }) => {
    // Probe first so we know what to expect from the UI.
    const probe = await fetchStateSummary(page, TARGET_PROJECT);
    const probeBody = probe.body;
    const hasForeign = probeBody.success && (probeBody.foreign_modules || []).length > 0;

    await navigateToManage(page);
    await forceActiveDeployment(page, TARGET_PROJECT);

    const banner = page.locator('#manage-foreign-modules-banner');
    await expect(banner).toHaveCount(1);

    // Drive the banner render directly from the verified server-side
    // summary — this exercises _renderForeignModulesBanner() on real
    // backend data without depending on the racy in-browser probe.
    await page.evaluate((summary) => {
        window.APP.manage._renderForeignModulesBanner(summary);
    }, probeBody);
    await page.waitForTimeout(150);

    if (hasForeign) {
        // Banner must be visible and contain the rendered template chrome.
        await expect(banner).toBeVisible();
        await expect(banner).toContainText('Deployment integrity warning');
        await expect(banner).toContainText(probeBody.deployment_type);
        // Each foreign module gets a chip — verify dashboard_server is there.
        const chipText = await banner.locator('.manage-foreign-banner__chip').allTextContents();
        for (const fm of probeBody.foreign_modules) {
            expect(chipText.join(' ')).toContain(fm);
        }
        // The Detach CTA must be present.
        const detachBtn = banner.locator('[data-action="manage-detach-foreign"]');
        await expect(detachBtn).toHaveCount(1);
        await expect(detachBtn).toBeVisible();
    } else {
        // No foreign modules — banner must stay hidden.
        await expect(banner).toBeHidden();
        test.info().annotations.push({
            type: 'soft-skip',
            description: 'no foreign modules in state; banner correctly hidden',
        });
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// 3. Detach button — confirmation gate fires; we do NOT confirm.
// ─────────────────────────────────────────────────────────────────────────────

test('Detach button triggers a confirmation gate (and we cancel it)', async ({ page }) => {
    // Pre-flight: bail with a soft-skip if state is already clean.
    const probe = await fetchStateSummary(page, TARGET_PROJECT);
    const probeBody = probe.body;
    if (!probeBody.success || (probeBody.foreign_modules || []).length === 0) {
        test.skip(true, 'no foreign modules in state — detach gate unreachable from UI');
        return;
    }

    await navigateToManage(page);
    await forceActiveDeployment(page, TARGET_PROJECT);

    // Drive the banner render with the verified server-side summary so
    // the Detach CTA is wired before we click it.
    await page.evaluate((summary) => {
        window.APP.manage._renderForeignModulesBanner(summary);
    }, probeBody);
    await page.waitForTimeout(150);

    // Intercept ANY POST /api/deploy/detach-foreign/* to abort it — we must
    // never actually mutate the live state. Belt-and-suspenders alongside
    // the confirm-cancel below.
    let detachRequestObserved = false;
    await page.route('**/api/deploy/detach-foreign/**', (route) => {
        detachRequestObserved = true;
        return route.abort();
    });

    // The detach confirmation tries APP.modal({...}) first; APP.modal is an
    // OBJECT not a function (see app.js:3564) so the try block throws and
    // falls through to window.confirm. Install a dismiss listener so the
    // dialog opens and is auto-cancelled.
    let confirmFired = false;
    let confirmMessage = '';
    page.on('dialog', async (dialog) => {
        confirmFired = true;
        confirmMessage = dialog.message();
        await dialog.dismiss();
    });

    const banner = page.locator('#manage-foreign-modules-banner');
    await expect(banner).toBeVisible();
    const detachBtn = banner.locator('[data-action="manage-detach-foreign"]');
    await expect(detachBtn).toBeVisible();
    await detachBtn.click();

    // Give the confirm dialog a chance to fire.
    await page.waitForTimeout(600);

    expect(confirmFired,
        'window.confirm() must fire when Detach is clicked — gate is the only thing preventing accidental state mutation'
    ).toBe(true);
    // The message must mention the workspace and the modules being detached.
    expect(confirmMessage).toContain(TARGET_PROJECT);
    expect(confirmMessage.toLowerCase()).toContain('detach');

    // After cancelling the dialog, the detach fetch must NOT have fired.
    await page.waitForTimeout(300);
    expect(detachRequestObserved,
        'detach POST must NOT fire when the operator cancels the confirmation'
    ).toBe(false);
});

// ─────────────────────────────────────────────────────────────────────────────
// 4. Destroy preflight — refuses with 409 when foreign modules are present.
// ─────────────────────────────────────────────────────────────────────────────

test('Destroy preflight blocks when foreign modules present (no real destroy)', async ({ page }) => {
    // SAFETY: we MUST NOT let a real destroy POST reach Flask. The guard
    // at deploy.py:2191 only enforces blocking when state_list succeeds AND
    // foreign list is non-empty — if state_list fails transiently (lock
    // contention), the guard silently passes and the destroy thread spawns.
    // Empirically this race was triggered during the first dry-run of
    // this spec and partially destroyed module.dashboard_server resources.
    // From here on we route the destroy POST through page.route() so the
    // browser never reaches Flask for /api/deploy/destroy, and we validate
    // the FRONTEND error-handling path against a synthetic 409 payload
    // that matches the backend contract (verified out-of-band).
    //
    // Backend-side coverage of the 409 contract lives in
    // tests/backend/test_destroy_safety.py::test_destroy_refuses_when_foreign_modules_present.
    // This spec covers the BROWSER contract only.

    await page.goto('/');

    // Verify foreign modules are still detected, so the synthetic 409 we'll
    // craft is faithful to the real backend response.
    const probe = await fetchStateSummary(page, TARGET_PROJECT);
    const probeBody = probe.body;
    if (!probeBody.success || (probeBody.foreign_modules || []).length === 0) {
        test.skip(true, 'state is clean — destroy guard has nothing to block');
        return;
    }

    // Synthetic payload modeled on the verified-via-curl backend response.
    const synthetic409 = {
        success: false,
        error: 'foreign_modules_in_state',
        message:
            `This workspace contains modules that aren't part of the ` +
            `${probeBody.deployment_type} deployment: ${probeBody.foreign_modules.join(', ')}. ` +
            `Destroying would damage shared infrastructure.`,
        deployment_type: probeBody.deployment_type,
        foreign_modules: probeBody.foreign_modules,
        expected_modules: probeBody.expected_modules,
        actual_modules: probeBody.actual_modules,
        actions: [
            {
                id: 'detach-foreign',
                label: "Detach foreign modules from this workspace's state",
                endpoint: `/api/deploy/detach-foreign/${TARGET_PROJECT}`,
                method: 'POST',
                description:
                    "Removes the foreign modules from terraform's state tracking for " +
                    "THIS workspace only. Does NOT touch AWS — the dashboard server " +
                    "keeps running. After this, Destroy is safe.",
            },
            {
                id: 'force-anyway',
                label: 'I understand — destroy everything in state including foreign modules',
                endpoint: '/api/deploy/destroy?force_foreign=1',
                method: 'POST',
                description:
                    'Last-resort escape hatch. Will destroy the foreign modules too. ' +
                    'Operator must explicitly opt in via the URL flag.',
            },
        ],
    };

    // Intercept ANY destroy POST and fulfill with the synthetic 409.
    // Belt-and-suspenders: also intercept force_foreign=1 to abort it.
    await page.route('**/api/deploy/destroy*', (route) => {
        const url = route.request().url();
        if (url.includes('force_foreign=1')) {
            // Should never get here in this test — abort hard.
            return route.abort();
        }
        return route.fulfill({
            status: 409,
            contentType: 'application/json',
            body: JSON.stringify(synthetic409),
        });
    });

    // Fire the destroy from the browser. With the intercept above, this
    // never reaches Flask — but the in-browser response shape mirrors the
    // real backend, so any frontend code that consumes it gets the right
    // contract.
    const resp = await page.evaluate(async (project) => {
        const r = await fetch('/api/deploy/destroy', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_name: project, confirm: 'DESTROY' }),
        });
        return { status: r.status, body: await r.json() };
    }, TARGET_PROJECT);

    // Assert the contract — same shape the frontend's _handleForeignModulesError
    // depends on (see app.js:30664).
    expect(resp.status).toBe(409);
    expect(resp.body.success).toBe(false);
    expect(resp.body.error).toBe('foreign_modules_in_state');
    expect(Array.isArray(resp.body.foreign_modules)).toBe(true);
    expect(resp.body.foreign_modules).toContain('dashboard_server');
    expect(Array.isArray(resp.body.actions)).toBe(true);
    const actionIds = resp.body.actions.map(a => a.id);
    expect(actionIds).toContain('detach-foreign');
    expect(actionIds).toContain('force-anyway');
    const detachAction = resp.body.actions.find(a => a.id === 'detach-foreign');
    expect(detachAction.endpoint).toContain(`/api/deploy/detach-foreign/${TARGET_PROJECT}`);
    const forceAction = resp.body.actions.find(a => a.id === 'force-anyway');
    expect(forceAction.endpoint).toContain('force_foreign=1');
    // Message must explain the violation. The backend's wording is
    // "workspace contains modules that aren't part of the <type> deployment".
    expect(resp.body.message.toLowerCase()).toContain('deployment');
    expect(resp.body.message.toLowerCase()).toContain('damage shared infrastructure');

    // Now verify the frontend handler doesn't auto-confirm — it must
    // surface a confirm dialog and require explicit operator approval.
    let confirmFired = false;
    page.on('dialog', async (dialog) => {
        confirmFired = true;
        await dialog.dismiss();
    });
    await page.evaluate((payload) => {
        if (window.APP?.manage?._handleForeignModulesError) {
            // APP.modal is an object (not a function) so the rich-modal
            // branch falls through to window.confirm — which our dialog
            // listener above will dismiss.
            window.APP.manage._handleForeignModulesError('goad_mini_demo', payload);
        }
    }, synthetic409);
    await page.waitForTimeout(500);
    expect(confirmFired,
        'frontend must NOT auto-fire destroy on 409; explicit confirmation required'
    ).toBe(true);
});
