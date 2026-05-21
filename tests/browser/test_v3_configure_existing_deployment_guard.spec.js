/**
 * 2026-05-21 (UX audit — Configure existing-deployment guard)
 *
 * Verifies that the Configure sub-pill renders a CLEAN EMPTY STATE when
 * the operator reaches it with an EXISTING deployment selected (not draft,
 * not All). The pane must NOT render either:
 *   - the V2 progressive Configure surface (#configure-v2-pane), or
 *   - the legacy `.configuration-editor` form + advanced details
 *     (#configure-advanced-details).
 *
 * Repro for the bug this guards against:
 *   1. Operator picks `goad_mini_dev_harriss_macbook_pro` in the top-bar.
 *   2. Operator deep-links to `#deployments-tab/configure?project=<name>`
 *      (or clicks Configure in the left rail before the rail-children
 *      visibility recompute fires).
 *   3. WITHOUT THIS FIX: both V2 (with stale "COMPOSING A NEW DEPLOYMENT"
 *      banner + "(unnamed)" hero) AND the legacy form render together,
 *      ~80 fields visible at once.
 *   4. WITH THIS FIX: only `#configure-existing-empty` renders, with two
 *      explicit CTAs steering the operator to the right surface.
 *
 * Also verifies:
 *   - "+ New Deployment" CTA fires startDraftFlow → DRAFT_SENTINEL + V2 paints.
 *   - "Open in Manage →" CTA flips the sub-pill to Manage.
 */

import { test, expect } from '@playwright/test';

const GOAD_PROJECT = 'goad_mini_dev_harriss_macbook_pro';

async function gotoWithDeployment(page, projectName, deploymentType) {
    // Mock /api/deploy/active so the global header listbox + the
    // _setActiveDeploymentType cache resolve the project to its type.
    await page.route('**/api/deploy/active', async (route) => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                deployments: [{
                    project_name: projectName,
                    deployment_type: deploymentType,
                    status: 'success',
                    environment: 'dev',
                    enable_test_lab: false,
                }],
            }),
        });
    });
    await page.route('**/api/costs/aggregate', async (route) => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ deployments: [] }),
        });
    });
    await page.route('**/api/cost/**', async (route) => {
        await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });
    // Direct deep-link onto Configure with the existing project pinned via
    // ?project=. This mirrors the URL grammar emitted by _updateUrlState.
    await page.goto(`/#deployments-tab/configure?project=${encodeURIComponent(projectName)}`);
    await page.evaluate(() => { window.confirm = () => true; });
    await page.locator('.tab-page[data-page="deployments-tab"]').waitFor({ timeout: 5000 });
    // Allow the boot pipeline (_initFromUrl → _refreshGlobalDeployments →
    // _setActiveDeploymentType → applyFromState → applyDraftMode) to settle.
    await page.waitForFunction(
        (name) => window.APP && window.APP.activeDeployment &&
                  window.APP.activeDeployment.current === name &&
                  window.APP.activeDeployment.deployment_type,
        projectName,
        { timeout: 5000 }
    );
    await page.waitForTimeout(300);
}

test.describe('v3 Configure — existing-deployment empty state guard', () => {
    test('V2 pane stays [hidden] on deep-link to Configure with existing project', async ({ page }) => {
        await gotoWithDeployment(page, GOAD_PROJECT, 'goad-mini');
        const v2Pane = page.locator('#configure-v2-pane');
        await expect(v2Pane).toHaveAttribute('hidden', '');
    });

    test('legacy form + advanced details are display:none', async ({ page }) => {
        await gotoWithDeployment(page, GOAD_PROJECT, 'goad-mini');
        const state = await page.evaluate(() => {
            const editor = document.querySelector('#configure-edit-pane .configuration-editor');
            const advanced = document.getElementById('configure-advanced-details');
            const actions = document.querySelector('#configure-edit-pane .configure-form-actions');
            const banner = document.getElementById('configure-new-deployment-banner');
            const summary = document.getElementById('configure-summary-section');
            const computed = (el) => el ? window.getComputedStyle(el).display : 'no-element';
            return {
                editor: computed(editor),
                advanced: computed(advanced),
                actions: computed(actions),
                banner: computed(banner),
                summary: computed(summary),
            };
        });
        // The legacy form, advanced details, and summary must all be hidden
        // when the operator is on Configure with an existing deployment.
        if (state.editor !== 'no-element') expect(state.editor).toBe('none');
        if (state.advanced !== 'no-element') expect(state.advanced).toBe('none');
        if (state.actions !== 'no-element') expect(state.actions).toBe('none');
        if (state.banner !== 'no-element') expect(state.banner).toBe('none');
        if (state.summary !== 'no-element') expect(state.summary).toBe('none');
    });

    test('#configure-existing-empty is visible and shows the project name', async ({ page }) => {
        await gotoWithDeployment(page, GOAD_PROJECT, 'goad-mini');
        const empty = page.locator('#configure-existing-empty');
        await expect(empty).toBeVisible();
        // Project name is stamped into the description for context.
        const projEl = page.locator('#configure-existing-empty-project');
        await expect(projEl).toHaveText(GOAD_PROJECT);
        // Both CTAs render.
        await expect(page.locator('#configure-existing-empty-new')).toBeVisible();
        await expect(page.locator('#configure-existing-empty-manage')).toBeVisible();
    });

    test('"+ New Deployment" CTA flips to DRAFT_SENTINEL and reveals V2', async ({ page }) => {
        await gotoWithDeployment(page, GOAD_PROJECT, 'goad-mini');
        // Click the primary CTA — should fire startDraftFlow().
        await page.click('#configure-existing-empty-new');
        // Wait for the draft state to land.
        await page.waitForFunction(
            () => window.APP && window.APP.activeDeployment &&
                  window.APP.activeDeployment.isDraft &&
                  window.APP.activeDeployment.isDraft(),
            null,
            { timeout: 3000 }
        );
        const current = await page.evaluate(() => window.APP.activeDeployment.current);
        expect(current).toBe('__draft__');
        // V2 pane must paint (no longer [hidden]).
        const v2Pane = page.locator('#configure-v2-pane');
        await expect(v2Pane).not.toHaveAttribute('hidden', '');
        // Empty state should now be hidden.
        await expect(page.locator('#configure-existing-empty')).toBeHidden();
    });

    test('"Open in Manage →" CTA navigates to Manage scoped to the project', async ({ page }) => {
        await gotoWithDeployment(page, GOAD_PROJECT, 'goad-mini');
        await page.click('#configure-existing-empty-manage');
        // Sub-pill should flip to manage. _updateUrlState appends ?project=.
        await page.waitForFunction(
            () => window.APP && window.APP.currentSubPill === 'manage',
            null,
            { timeout: 3000 }
        );
        // URL should reflect the manage pill + scoped project. _updateUrlState
        // writes `?project=...` to window.location.search and the sub-pill
        // to window.location.hash — assert against the full URL.
        const fullUrl = await page.evaluate(() => window.location.search + window.location.hash);
        expect(fullUrl).toContain('deployments-tab/manage');
        expect(fullUrl).toContain(`project=${GOAD_PROJECT}`);
        // activeDeployment.current must NOT have been cleared — Manage scoped
        // view depends on it.
        const current = await page.evaluate(() => window.APP.activeDeployment.current);
        expect(current).toBe(GOAD_PROJECT);
    });

    test('left rail children Configure + Deploy are [hidden] on first paint', async ({ page }) => {
        // Bug 1 — the rail visibility mirror must fire AFTER the deployment_type
        // is hydrated, so an existing (non-draft) deployment hides Configure +
        // Deploy in the left rail from first paint.
        await gotoWithDeployment(page, GOAD_PROJECT, 'goad-mini');
        const state = await page.evaluate(() => {
            const sel = (s) => document.querySelector(s);
            const get = (n) => sel(`.app-rail__child[data-rail-target="deployments-tab"][data-rail-subpill="${n}"]`);
            const has = (el) => el && el.hasAttribute('hidden');
            return {
                configure: has(get('configure')),
                deploy: has(get('deploy')),
                manage: has(get('manage')),
                cleanup: has(get('cleanup')),
                'bolt-ons': has(get('bolt-ons')),
            };
        });
        expect(state.configure).toBe(true);
        expect(state.deploy).toBe(true);
        expect(state.manage).toBe(false);
        expect(state.cleanup).toBe(false);
        // goad-* exposes bolt-ons (per computeVisibleSubPills) so it must NOT be hidden.
        expect(state['bolt-ons']).toBe(false);
    });
});
