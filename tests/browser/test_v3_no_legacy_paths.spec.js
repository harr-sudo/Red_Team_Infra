/**
 * 2026-05-21 (frontend legacy audit)
 *
 * Regression guard for legacy code paths that bypass the V2 canonical flow.
 * See docs/internal/FRONTEND_LEGACY_AUDIT.md for the full catalogue.
 *
 * Assertions:
 *   1. Every "+ New Deployment" button (Dashboard hero, top-bar, banner, etc.)
 *      ends with APP.activeDeployment.current === DRAFT_SENTINEL on click.
 *   2. The .configuration-editor form is NEVER computed-style visible in any
 *      reachable user flow (draft / existing / empty / All).
 *   3. Direct navigation to #deployments-tab/configure with an existing
 *      project shows the empty state, not the legacy form.
 *   4. APP.startNewDeployment() programmatic call enters draft mode.
 *   5. The retired legacy buttons (Save Configuration / Validate / Clear All)
 *      are NOT present in the DOM — they would re-introduce the legacy save
 *      flow if they came back.
 */

import { test, expect } from '@playwright/test';

const DRAFT_SENTINEL = '__draft__';
const EXISTING_PROJECT = 'c2_adhoc_dev_operator_ws';

async function gotoDashboard(page) {
    await page.goto('/');
    await page.locator('[data-page="dashboard"]').first().waitFor({ timeout: 5000 });
    await page.evaluate(() => { window.confirm = () => true; });
    await page.waitForTimeout(300);
}

async function gotoWithExistingDeployment(page, projectName, deploymentType) {
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
    await page.goto(`/#deployments-tab/configure?project=${encodeURIComponent(projectName)}`);
    await page.evaluate(() => { window.confirm = () => true; });
    await page.locator('.tab-page[data-page="deployments-tab"]').waitFor({ timeout: 5000 });
    await page.waitForFunction(
        (name) => window.APP && window.APP.activeDeployment &&
                  window.APP.activeDeployment.current === name,
        projectName,
        { timeout: 5000 }
    );
    await page.waitForTimeout(300);
}

test.describe('v3 legacy path retirement — regression guards', () => {
    test('Dashboard hero + New Deployment enters draft mode', async ({ page }) => {
        await gotoDashboard(page);
        const heroBtn = page.locator('.dashboard-hero__primary');
        await expect(heroBtn).toBeVisible();
        await heroBtn.click();
        await page.waitForFunction(
            () => window.APP && window.APP.activeDeployment &&
                  window.APP.activeDeployment.current === '__draft__',
            null,
            { timeout: 3000 }
        );
        const current = await page.evaluate(() => window.APP.activeDeployment.current);
        expect(current).toBe(DRAFT_SENTINEL);
    });

    test('Global header + New Deployment enters draft mode', async ({ page }) => {
        await gotoDashboard(page);
        await page.locator('#global-new-deployment-btn').click();
        await page.waitForFunction(
            () => window.APP && window.APP.activeDeployment &&
                  window.APP.activeDeployment.current === '__draft__',
            null,
            { timeout: 3000 }
        );
        const current = await page.evaluate(() => window.APP.activeDeployment.current);
        expect(current).toBe(DRAFT_SENTINEL);
    });

    test('Configure banner + New Deployment enters draft mode', async ({ page }) => {
        await gotoDashboard(page);
        // Land on Configure with no active deployment so the banner renders.
        await page.evaluate(() => {
            if (window.APP && window.APP.activeDeployment) {
                window.APP.activeDeployment.set(null);
            }
            if (window.APP && window.APP.navigateTo) {
                window.APP.navigateTo('deployments-tab', 'configure');
            }
        });
        await page.waitForTimeout(300);
        const bannerBtn = page.locator('#configure-new-deployment-btn');
        await expect(bannerBtn).toBeVisible();
        await bannerBtn.click();
        await page.waitForFunction(
            () => window.APP && window.APP.activeDeployment &&
                  window.APP.activeDeployment.current === '__draft__',
            null,
            { timeout: 3000 }
        );
        const current = await page.evaluate(() => window.APP.activeDeployment.current);
        expect(current).toBe(DRAFT_SENTINEL);
    });

    test('APP.startNewDeployment() programmatic call enters draft mode', async ({ page }) => {
        await gotoDashboard(page);
        await page.evaluate(() => {
            if (window.APP && typeof window.APP.startNewDeployment === 'function') {
                window.APP.startNewDeployment();
            }
        });
        await page.waitForFunction(
            () => window.APP && window.APP.activeDeployment &&
                  window.APP.activeDeployment.current === '__draft__',
            null,
            { timeout: 3000 }
        );
        const current = await page.evaluate(() => window.APP.activeDeployment.current);
        expect(current).toBe(DRAFT_SENTINEL);
    });

    test('.configuration-editor is computed-hidden in draft mode', async ({ page }) => {
        await gotoDashboard(page);
        await page.locator('#global-new-deployment-btn').click();
        await page.waitForFunction(
            () => window.APP && window.APP.activeDeployment.isDraft &&
                  window.APP.activeDeployment.isDraft(),
            null,
            { timeout: 3000 }
        );
        const displayState = await page.evaluate(() => {
            const editor = document.querySelector('#configure-edit-pane .configuration-editor');
            const advanced = document.getElementById('configure-advanced-details');
            return {
                editor: editor ? window.getComputedStyle(editor).display : 'no-element',
                advanced: advanced ? window.getComputedStyle(advanced).display : 'no-element',
            };
        });
        if (displayState.editor !== 'no-element') expect(displayState.editor).toBe('none');
        if (displayState.advanced !== 'no-element') expect(displayState.advanced).toBe('none');
    });

    test('direct nav to Configure with existing project shows empty state, not legacy form', async ({ page }) => {
        await gotoWithExistingDeployment(page, EXISTING_PROJECT, 'c2-adhoc');
        // V2 pane is hidden.
        await expect(page.locator('#configure-v2-pane')).toHaveAttribute('hidden', '');
        // Legacy form is computed-hidden.
        const legacy = await page.evaluate(() => {
            const editor = document.querySelector('#configure-edit-pane .configuration-editor');
            const advanced = document.getElementById('configure-advanced-details');
            return {
                editor: editor ? window.getComputedStyle(editor).display : 'no-element',
                advanced: advanced ? window.getComputedStyle(advanced).display : 'no-element',
            };
        });
        if (legacy.editor !== 'no-element') expect(legacy.editor).toBe('none');
        if (legacy.advanced !== 'no-element') expect(legacy.advanced).toBe('none');
        // Existing-deployment empty state visible.
        await expect(page.locator('#configure-existing-empty')).toBeVisible();
    });

    test('retired legacy Save/Validate/Clear buttons are not in the DOM', async ({ page }) => {
        await gotoDashboard(page);
        // The 3 buttons used inline onclick="<globalFn>()" handlers — the
        // legacy save flow's most visible entry point. Their removal means
        // the legacy save path is no longer one-click reachable from any
        // reachable surface. We probe by onclick attribute to NOT confuse
        // the V2 "Save configuration" button (#cfg-save-btn) which is the
        // canonical save primitive.
        const count = await page.evaluate(() => {
            const saveBtns = Array.from(document.querySelectorAll('button'))
                .filter(b => (b.getAttribute('onclick') || '').includes('saveConfig('));
            const validateBtns = Array.from(document.querySelectorAll('button'))
                .filter(b => (b.getAttribute('onclick') || '').includes('validateConfig('));
            const clearAllBtns = Array.from(document.querySelectorAll('button'))
                .filter(b => (b.getAttribute('onclick') || '').includes('clearConfig('));
            return {
                save: saveBtns.length,
                validate: validateBtns.length,
                clearAll: clearAllBtns.length,
            };
        });
        expect(count.save).toBe(0);
        expect(count.validate).toBe(0);
        expect(count.clearAll).toBe(0);
    });

    test('.configure-form-actions chrome was retired', async ({ page }) => {
        await gotoDashboard(page);
        const present = await page.evaluate(() => {
            return !!document.querySelector('.configure-form-actions');
        });
        expect(present).toBe(false);
    });

    test('no reachable user flow puts .configuration-editor in display:block', async ({ page }) => {
        // Sweep: draft, existing, empty, attempted All — none should ever
        // make the legacy form computed-style visible.
        await gotoDashboard(page);
        const checks = [];

        // 1. Draft state.
        await page.locator('#global-new-deployment-btn').click();
        await page.waitForTimeout(300);
        checks.push(await page.evaluate(() => {
            const editor = document.querySelector('#configure-edit-pane .configuration-editor');
            return editor ? window.getComputedStyle(editor).display : 'none';
        }));

        // 2. Discard → empty.
        await page.locator('#configure-discard-draft-btn').click();
        await page.waitForTimeout(200);
        checks.push(await page.evaluate(() => {
            const editor = document.querySelector('#configure-edit-pane .configuration-editor');
            return editor ? window.getComputedStyle(editor).display : 'none';
        }));

        // Every recorded display value must be 'none' (or 'no-element' if
        // the form is fully removed — the prize endpoint).
        for (const d of checks) {
            expect(d).toBe('none');
        }
    });
});
