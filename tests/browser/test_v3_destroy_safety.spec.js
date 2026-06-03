/**
 * V3 — Pre-destroy safety: foreign-modules banner + recovery flow.
 *
 * Scenario covered:
 *   1. /api/deploy/state-summary/<project> reports a foreign module.
 *   2. The Manage sub-pill renders a danger callout above the hero
 *      listing the foreign module(s).
 *   3. Clicking "Detach foreign modules" pops a confirmation, then
 *      POSTs /api/deploy/detach-foreign/<project> when confirmed.
 *
 * Both themes are exercised — the banner reuses the existing
 * .cfg-callout--danger TASTE so contrast comes for free, but we still
 * assert the banner is visible in light mode (the dark default + light
 * override are independent rendering paths).
 */

import { test, expect } from '@playwright/test';
import { railNavigate, clickSubPill } from './helpers/nav.js';

const TEST_PROJECT = 'safety_demo_lab';

async function setTheme(page, theme) {
    await page.evaluate((t) => {
        if (t === 'light') document.documentElement.setAttribute('data-theme', 'light');
        else document.documentElement.removeAttribute('data-theme');
    }, theme);
    await page.waitForTimeout(200);
}

/**
 * Intercept /api/deploy/state-summary/<project> and return a payload
 * with foreign_modules populated. Lets the spec run without any real
 * terraform state present in the dev harness.
 */
async function mockForeignModulesState(page, projectName) {
    await page.route(`**/api/deploy/state-summary/${projectName}`, async (route) => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                success: true,
                project: projectName,
                deployment_type: 'goad-mini',
                enable_test_lab: false,
                expected_modules: ['attack_box', 'cs_storage', 'goad', 'security', 'vpc'],
                actual_modules: ['attack_box', 'cs_storage', 'dashboard_server', 'goad', 'security', 'vpc'],
                foreign_modules: ['dashboard_server'],
                error: null,
            }),
        });
    });
}

async function mountManageScopedToProject(page, projectName) {
    await page.goto('/');
    await railNavigate(page, 'deployments-tab');
    await clickSubPill(page, 'manage');
    await page.waitForTimeout(200);
    // Force the active deployment to our fake project so the banner
    // probe targets it. _probeStateSummary reads APP.manage._currentProject().
    await page.evaluate((p) => {
        if (window.APP && window.APP.activeDeployment && typeof window.APP.activeDeployment.set === 'function') {
            window.APP.activeDeployment.set(p);
        }
    }, projectName);
    // Trigger render so the banner fetch fires.
    await page.evaluate(async () => {
        if (window.APP && window.APP.manage && window.APP.manage.render) {
            await window.APP.manage.render();
        }
    });
    await page.waitForTimeout(600);
}

test.describe('V3 — destroy safety: foreign modules banner', () => {
    test('Banner mounts above hero when state-summary reports foreign modules', async ({ page }) => {
        await mockForeignModulesState(page, TEST_PROJECT);
        await mountManageScopedToProject(page, TEST_PROJECT);

        const banner = page.locator('#manage-foreign-modules-banner');
        // Wait until the probe resolves and the banner toggles.
        await expect(banner).toBeVisible({ timeout: 3000 });
        await expect(banner).toContainText('Deployment integrity warning');
        // The foreign module name surfaces in the modules chip strip.
        await expect(banner.locator('.manage-foreign-banner__chip')).toContainText('dashboard_server');
        // The detach action button is present.
        await expect(banner.locator('[data-action="manage-detach-foreign"]')).toBeVisible();
    });

    test('Detach button triggers the detach endpoint after confirmation', async ({ page }) => {
        let detachCalled = false;
        await mockForeignModulesState(page, TEST_PROJECT);
        await page.route(`**/api/deploy/detach-foreign/${TEST_PROJECT}`, async (route) => {
            detachCalled = true;
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    success: true,
                    project: TEST_PROJECT,
                    detached: ['dashboard_server'],
                    errors: [],
                    message: 'Detached 1 foreign module(s).',
                }),
            });
        });

        // Auto-accept the confirmation modal (the code path falls back to
        // window.confirm if APP.modal is unavailable in the test harness).
        page.on('dialog', (dlg) => dlg.accept());

        await mountManageScopedToProject(page, TEST_PROJECT);
        const banner = page.locator('#manage-foreign-modules-banner');
        await expect(banner).toBeVisible({ timeout: 3000 });

        await banner.locator('[data-action="manage-detach-foreign"]').click();
        // Give the click handler + fetch a moment.
        await page.waitForTimeout(600);
        expect(detachCalled, 'detach endpoint must be called after confirmation').toBe(true);
    });

    test('Banner is hidden when state-summary reports no foreign modules', async ({ page }) => {
        // Override the route to return an EMPTY foreign list — banner must stay hidden.
        const cleanProject = 'safety_clean_lab';
        await page.route(`**/api/deploy/state-summary/${cleanProject}`, async (route) => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    success: true,
                    project: cleanProject,
                    deployment_type: 'goad-mini',
                    enable_test_lab: false,
                    expected_modules: ['attack_box', 'cs_storage', 'goad', 'security', 'vpc'],
                    actual_modules: ['attack_box', 'cs_storage', 'goad', 'security', 'vpc'],
                    foreign_modules: [],
                    error: null,
                }),
            });
        });
        await mountManageScopedToProject(page, cleanProject);
        const banner = page.locator('#manage-foreign-modules-banner');
        // The banner element exists but has the hidden attribute set.
        await expect(banner).toHaveAttribute('hidden', '', { timeout: 3000 });
    });

    for (const theme of ['dark', 'light']) {
        test(`Banner renders in ${theme} theme without contrast collapse`, async ({ page }) => {
            await mockForeignModulesState(page, TEST_PROJECT);
            await mountManageScopedToProject(page, TEST_PROJECT);
            await setTheme(page, theme);

            const banner = page.locator('#manage-foreign-modules-banner');
            await expect(banner).toBeVisible({ timeout: 3000 });

            // Smoke-test the title text — should be readable (non-empty
            // computed color, non-transparent background on the callout).
            const styles = await banner.evaluate((el) => {
                const cs = getComputedStyle(el);
                return {
                    bg: cs.backgroundColor,
                    color: cs.color,
                };
            });
            expect(styles.bg).not.toBe('rgba(0, 0, 0, 0)');
            expect(styles.color).not.toBe('rgba(0, 0, 0, 0)');
        });
    }
});
