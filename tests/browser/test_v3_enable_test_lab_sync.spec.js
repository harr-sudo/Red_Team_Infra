/**
 * 2026-05-20 (UX audit High · H2 + Medium · M2)
 *
 * Verifies the Bolt-ons sub-pill visibility is correctly gated by the
 * active deployment's `enable_test_lab` flag for c2-* deployments.
 *
 * Repro for the bug this guards against:
 *   1. Operator picks an existing c2-only deployment WITHOUT a test lab
 *      → Bolt-ons sub-pill must NOT appear.
 *   2. Operator picks an existing c2-only deployment WITH a test lab
 *      → Bolt-ons sub-pill MUST appear.
 *   3. The `enable_test_lab` value must be hydrated from
 *      `/api/deploy/active` into APP.activeDeployment.enable_test_lab
 *      so the helper hasTestLab() returns the right value.
 *
 * Fix (per app.js:2244 + :3308):
 *   - computeVisibleSubPills() consults active.hasTestLab().
 *   - _setActiveDeploymentType() reads `match.enable_test_lab` from the
 *     cached deployment record and writes it onto activeDeployment.
 */

import { test, expect } from '@playwright/test';

async function gotoWithMockedDeployments(page, deployments) {
    await page.route('**/api/deploy/active', async (route) => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ deployments }),
        });
    });
    await page.route('**/api/costs/aggregate', async (route) => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ deployments: [] }),
        });
    });
    await page.goto('/');
    await page.evaluate(() => { window.confirm = () => true; });
    await page.locator('[data-page="dashboard"]').first().waitFor({ timeout: 5000 });
    await page.waitForTimeout(400);
}

test.describe('v3 enable_test_lab sync — sub-pill visibility', () => {
    test('hasTestLab() helper exists on activeDeployment', async ({ page }) => {
        await gotoWithMockedDeployments(page, []);
        const result = await page.evaluate(() => {
            const ad = window.APP && window.APP.activeDeployment;
            if (!ad) return null;
            return {
                hasHelper: typeof ad.hasTestLab === 'function',
                getter: 'enable_test_lab' in ad,
            };
        });
        expect(result).not.toBeNull();
        expect(result.hasHelper).toBe(true);
        expect(result.getter).toBe(true);
    });

    test('c2-* deployment WITHOUT test lab hides Bolt-ons sub-pill', async ({ page }) => {
        await gotoWithMockedDeployments(page, [
            {
                project_name: 'c2_adhoc_no_lab',
                status: 'success',
                deployment_type: 'c2-adhoc',
                enable_test_lab: false,
            },
        ]);

        // Simulate the operator selecting this project from the dropdown.
        await page.evaluate(() => {
            window.APP.activeDeployment.set('c2_adhoc_no_lab');
        });
        await page.waitForTimeout(200);

        const visible = await page.evaluate(() => {
            return window.APP.computeVisibleSubPills(window.APP.activeDeployment);
        });
        expect(visible).toContain('manage');
        expect(visible).not.toContain('bolt-ons');
    });

    test('c2-* deployment WITH test lab shows Bolt-ons sub-pill', async ({ page }) => {
        await gotoWithMockedDeployments(page, [
            {
                project_name: 'c2_adhoc_with_lab',
                status: 'success',
                deployment_type: 'c2-adhoc',
                enable_test_lab: true,
            },
        ]);

        await page.evaluate(() => {
            window.APP.activeDeployment.set('c2_adhoc_with_lab');
        });
        await page.waitForTimeout(200);

        // Verify enable_test_lab hydrated correctly.
        const hydrated = await page.evaluate(() => {
            return {
                enableTestLab: window.APP.activeDeployment.enable_test_lab,
                hasTestLab: window.APP.activeDeployment.hasTestLab(),
                deploymentType: window.APP.activeDeployment.deployment_type,
            };
        });
        expect(hydrated.enableTestLab).toBe(true);
        expect(hydrated.hasTestLab).toBe(true);
        expect(hydrated.deploymentType).toBe('c2-adhoc');

        const visible = await page.evaluate(() => {
            return window.APP.computeVisibleSubPills(window.APP.activeDeployment);
        });
        expect(visible).toContain('manage');
        expect(visible).toContain('bolt-ons');
    });

    test('goad-* deployment always shows Bolt-ons regardless of enable_test_lab', async ({ page }) => {
        await gotoWithMockedDeployments(page, [
            {
                project_name: 'goad_light_lab',
                status: 'success',
                deployment_type: 'goad-light',
                enable_test_lab: false,
            },
        ]);

        await page.evaluate(() => {
            window.APP.activeDeployment.set('goad_light_lab');
        });
        await page.waitForTimeout(200);

        const visible = await page.evaluate(() => {
            return window.APP.computeVisibleSubPills(window.APP.activeDeployment);
        });
        expect(visible).toContain('manage');
        expect(visible).toContain('bolt-ons');
    });

    test('switching from c2-* without lab to c2-* with lab updates sub-pill set', async ({ page }) => {
        await gotoWithMockedDeployments(page, [
            { project_name: 'c2_no_lab',   status: 'success', deployment_type: 'c2-adhoc', enable_test_lab: false },
            { project_name: 'c2_with_lab', status: 'success', deployment_type: 'c2-adhoc', enable_test_lab: true },
        ]);

        await page.evaluate(() => {
            window.APP.activeDeployment.set('c2_no_lab');
        });
        await page.waitForTimeout(200);
        let visible = await page.evaluate(() =>
            window.APP.computeVisibleSubPills(window.APP.activeDeployment)
        );
        expect(visible).not.toContain('bolt-ons');

        // Switch to the lab-enabled project — bolt-ons must appear.
        await page.evaluate(() => {
            window.APP.activeDeployment.set('c2_with_lab');
        });
        await page.waitForTimeout(200);
        visible = await page.evaluate(() =>
            window.APP.computeVisibleSubPills(window.APP.activeDeployment)
        );
        expect(visible).toContain('bolt-ons');
    });
});
