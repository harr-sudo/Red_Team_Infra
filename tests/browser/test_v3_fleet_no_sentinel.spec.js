/**
 * 2026-05-20 (UX audit Batch A · C4 + P2)
 *
 * Verifies the Manage fleet table NEVER renders a row whose project
 * name is one of the sentinel values (`__draft__`, `__all__`).
 *
 * Repro for the bug this guards against:
 *   1. "+ New Deployment" → operator is in draft sentinel mode
 *   2. Switch the top-bar selector to "All deployments"
 *   3. Manage fleet table loop used to iterate the deployment payload
 *      without filtering sentinel-named entries, occasionally rendering
 *      an empty row.
 *
 * The fix layers a single source of truth — APP.activeDeployment
 * .isUserVisibleProject(name) — at every render-by-deployment loop.
 * This spec also asserts the helper exists on the global API surface.
 */

import { test, expect } from '@playwright/test';

async function gotoDashboard(page) {
    await page.goto('/');
    await page.locator('[data-page="dashboard"]').first().waitFor({ timeout: 5000 });
    await page.waitForTimeout(300);
}

test.describe('v3 fleet — sentinel filter', () => {
    test('isUserVisibleProject helper is exposed on APP.activeDeployment', async ({ page }) => {
        await gotoDashboard(page);
        const result = await page.evaluate(() => {
            const ad = window.APP && window.APP.activeDeployment;
            if (!ad) return null;
            return {
                hasHelper: typeof ad.isUserVisibleProject === 'function',
                rejectsDraft: ad.isUserVisibleProject('__draft__'),
                rejectsAll: ad.isUserVisibleProject('__all__'),
                rejectsEmpty: ad.isUserVisibleProject(''),
                rejectsNull: ad.isUserVisibleProject(null),
                acceptsReal: ad.isUserVisibleProject('c2_adhoc_demo'),
            };
        });
        expect(result).not.toBeNull();
        expect(result.hasHelper).toBe(true);
        expect(result.rejectsDraft).toBe(false);
        expect(result.rejectsAll).toBe(false);
        expect(result.rejectsEmpty).toBe(false);
        expect(result.rejectsNull).toBe(false);
        expect(result.acceptsReal).toBe(true);
    });

    test('fleet table never renders a sentinel-named row', async ({ page }) => {
        // Stub /api/deploy/active so the response contains a poisoned
        // sentinel record alongside a clean one. This is the worst-case
        // input the renderer would see if a backend bug ever wrote a
        // sentinel through to disk.
        await page.route('**/api/deploy/active', async (route) => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    deployments: [
                        { project_name: '__draft__', status: 'success', deployment_type: 'c2-adhoc' },
                        { project_name: '__all__',   status: 'success', deployment_type: 'c2-adhoc' },
                        { project_name: 'c2_adhoc_real_project', status: 'success', deployment_type: 'c2-adhoc' },
                    ],
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

        await gotoDashboard(page);

        // Drop into draft so the dropdown pins "All deployments" as an
        // option, then flip to All.
        await page.evaluate(() => {
            window.APP.activeDeployment.set(window.APP.activeDeployment.DRAFT_SENTINEL);
        });
        await page.evaluate(() => {
            window.APP.activeDeployment.set(window.APP.activeDeployment.ALL_SENTINEL);
        });

        // Navigate to Manage → fleet renders.
        await page.evaluate(() => {
            if (window.APP && window.APP.navigateTo) {
                window.APP.navigateTo('deployments-tab', 'manage');
            }
        });

        // Wait for fleet body to populate.
        const fleetBody = page.locator('[data-fleet-tbody]');
        await fleetBody.waitFor({ state: 'visible', timeout: 5000 });
        // Wait for at least the clean row to appear OR an empty state.
        await page.waitForFunction(() => {
            const tbody = document.querySelector('[data-fleet-tbody]');
            if (!tbody) return false;
            const rows = tbody.querySelectorAll('tr[data-fleet-project]');
            const empty = tbody.querySelector('.manage-fleet__cell--empty');
            return rows.length > 0 || empty !== null;
        }, null, { timeout: 5000 });

        // No row's data-fleet-project should be a sentinel.
        const sentinelRows = await page.locator(
            '[data-fleet-tbody] tr[data-fleet-project="__draft__"], ' +
            '[data-fleet-tbody] tr[data-fleet-project="__all__"]'
        ).count();
        expect(sentinelRows).toBe(0);

        // The clean row should be present.
        const realRow = page.locator('[data-fleet-tbody] tr[data-fleet-project="c2_adhoc_real_project"]');
        await expect(realRow).toHaveCount(1);
    });
});
