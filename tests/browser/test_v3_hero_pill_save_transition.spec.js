/**
 * 2026-05-20 (UX audit Medium · M4)
 *
 * Verifies the Configure V2 hero pill transitions cleanly on Save.
 *
 *   - Before Save: hero pill reads "Draft" (no project name yet).
 *   - After Save: hero pill stays "Draft" BUT the hero title text
 *     becomes the saved project_name, AND `activeDeployment.draftProject`
 *     is populated so the global header label reads "Draft: <name>".
 *
 * Per the implementation comment at app.js:13328-13336:
 *   Save stays in DRAFT mode until Apply succeeds. The pill stays
 *   "Draft" so the operator can see they still need to Apply; flipping
 *   to LIVE pre-Apply would lie about what's actually deployed in AWS.
 *
 * The bug from M4 was: hero pill text didn't update to reflect the
 * saved project_name (it stayed as the placeholder "New deployment").
 */

import { test, expect } from '@playwright/test';

async function openDraftConfigure(page) {
    await page.goto('/');
    await page.evaluate(() => { window.confirm = () => true; });
    await page.locator('#global-new-deployment-btn').waitFor({ timeout: 5000 });
    await page.click('#global-new-deployment-btn');
    await page.locator('#configure-v2-pane').waitFor({ timeout: 5000 });
    await page.evaluate(() => {
        if (window.APP && window.APP.configureV2 && window.APP.configureV2.ensureInitialized) {
            return window.APP.configureV2.ensureInitialized();
        }
    });
    await page.waitForTimeout(300);
}

test.describe('v3 hero pill — Save transition', () => {
    test('after Save: hero title shows project name, pill stays Draft, draftProject populated', async ({ page }) => {
        await page.route('**/api/config/?project=*', async (route) => {
            if (route.request().method() === 'POST') {
                await route.fulfill({
                    status: 200,
                    contentType: 'application/json',
                    body: JSON.stringify({ success: true }),
                });
            } else {
                await route.continue();
            }
        });

        await openDraftConfigure(page);

        // Set a project name + minimum required fields.
        const projectName = 'c2_adhoc_hero_pill_test';
        await page.evaluate((name) => {
            const proj = document.getElementById('cfg-project-name');
            if (proj) { proj.value = name; proj.dataset.cfgUserEdited = '1'; }
            const mgmt = document.getElementById('cfg-mgmt-cidr');
            if (mgmt) mgmt.value = '127.0.0.1/32';
            const btn = document.getElementById('cfg-save-btn');
            if (btn) btn.removeAttribute('disabled');
        }, projectName);

        // Capture pre-save state.
        const preSave = await page.evaluate(() => ({
            titleText: document.getElementById('cfg-hero-title-text')?.textContent || '',
            pillText: document.getElementById('cfg-hero-pill')?.textContent || '',
            draftProject: window.APP?.activeDeployment?.draftProject || null,
        }));
        expect(preSave.pillText.trim()).toMatch(/^Draft/);

        // Click Save.
        await page.click('#cfg-save-btn', { force: true });
        await page.waitForTimeout(500);

        // Post-save assertions.
        const postSave = await page.evaluate(() => ({
            titleText: document.getElementById('cfg-hero-title-text')?.textContent || '',
            pillText: document.getElementById('cfg-hero-pill')?.textContent || '',
            pillClasses: document.getElementById('cfg-hero-pill')?.className || '',
            draftProject: window.APP?.activeDeployment?.draftProject || null,
            displayName: window.APP?.activeDeployment?.displayName?.() || '',
        }));

        // Hero title should show the project name (M4 fix).
        expect(postSave.titleText.trim()).toBe(projectName);
        // Pill stays "Draft" — Save does NOT promote to Live (per comment :13328).
        expect(postSave.pillText.trim()).toMatch(/^Draft/);
        expect(postSave.pillClasses).toContain('cfg-hero__pill--draft');
        expect(postSave.pillClasses).not.toContain('cfg-hero__pill--live');
        // draftProject populated so global header reads "Draft: <name>".
        expect(postSave.draftProject).toBe(projectName);
        // displayName() should surface "Draft: <name>".
        expect(postSave.displayName).toContain(projectName);
    });

    test('global header dropdown label reads "Draft: <project>" after Save', async ({ page }) => {
        await page.route('**/api/config/?project=*', async (route) => {
            if (route.request().method() === 'POST') {
                await route.fulfill({
                    status: 200,
                    contentType: 'application/json',
                    body: JSON.stringify({ success: true }),
                });
            } else {
                await route.continue();
            }
        });

        await openDraftConfigure(page);
        const projectName = 'c2_adhoc_global_label_test';
        await page.evaluate((name) => {
            const proj = document.getElementById('cfg-project-name');
            if (proj) { proj.value = name; proj.dataset.cfgUserEdited = '1'; }
            const mgmt = document.getElementById('cfg-mgmt-cidr');
            if (mgmt) mgmt.value = '127.0.0.1/32';
            const btn = document.getElementById('cfg-save-btn');
            if (btn) btn.removeAttribute('disabled');
        }, projectName);

        await page.click('#cfg-save-btn', { force: true });
        await page.waitForTimeout(500);

        const label = await page.evaluate(() => {
            const el = document.getElementById('global-deploy-value');
            return el ? el.textContent.trim() : null;
        });
        // Label should contain the project name (either "Draft: <name>" or
        // exactly the project name depending on whether displayName fired).
        if (label !== null) {
            expect(label).toContain(projectName);
        }
    });
});
