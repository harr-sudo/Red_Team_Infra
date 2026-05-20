/**
 * 2026-05-20 (UX audit Critical · C1)
 *
 * Verifies the "+ New Deployment" entry point lands the operator in a
 * clean Configure V2 surface — NOT the legacy form, NOT a stale draft.
 *
 * Repro for the bug this guards against:
 *   1. Click "+ New Deployment"
 *   2. Operator should see the family/type picker prominent, with no
 *      auto-populated project name from a prior session, and no legacy
 *      .configuration-editor chrome visible.
 *   3. Hero pill reads "Draft" and the V2 pane is mounted.
 *
 * The bug surfaced as: stale draft project bleeding through from a
 * previous "+ New" click + the legacy form occasionally visible.
 */

import { test, expect } from '@playwright/test';

async function gotoDashboard(page) {
    await page.goto('/');
    await page.locator('[data-page="dashboard"]').first().waitFor({ timeout: 5000 });
    await page.evaluate(() => { window.confirm = () => true; });
    await page.waitForTimeout(300);
}

test.describe('v3 "+ New Deployment" — landing state', () => {
    test('clicking + New mounts V2 pane and pins draft sentinel', async ({ page }) => {
        await gotoDashboard(page);
        await page.locator('#global-new-deployment-btn').click();
        await page.waitForTimeout(400);

        // V2 pane is visible.
        await expect(page.locator('#configure-v2-pane')).toBeVisible({ timeout: 5000 });

        // Active deployment is the draft sentinel.
        const sentinel = await page.evaluate(() => {
            const ad = window.APP && window.APP.activeDeployment;
            return ad && ad.isDraft && ad.isDraft();
        });
        expect(sentinel).toBe(true);

        // Discard banner is visible.
        await expect(page.locator('#configure-discard-draft')).toBeVisible();

        // Hero pill reads "Draft" (not "Live" / not stale state).
        const pillText = await page.locator('#cfg-hero-pill').textContent();
        expect(pillText.trim()).toMatch(/^Draft/);
    });

    test('family selector is rendered and operator can pick a family', async ({ page }) => {
        await gotoDashboard(page);
        await page.locator('#global-new-deployment-btn').click();
        await page.waitForTimeout(400);

        // Family row is visible inside Identity.
        const familyRow = page.locator('#cfg-family-row');
        await expect(familyRow).toBeVisible({ timeout: 5000 });

        // All 3 family buttons are present.
        const c2Btn = page.locator('#cfg-family-row [data-cfg-family="c2"]');
        const goadBtn = page.locator('#cfg-family-row [data-cfg-family="goad"]');
        const combinedBtn = page.locator('#cfg-family-row [data-cfg-family="combined"]');
        await expect(c2Btn).toBeVisible();
        await expect(goadBtn).toBeVisible();
        await expect(combinedBtn).toBeVisible();
    });

    test('legacy .configuration-editor chrome stays hidden on landing', async ({ page }) => {
        await gotoDashboard(page);
        await page.locator('#global-new-deployment-btn').click();
        await page.waitForTimeout(500);

        // The legacy form must not be visible (display !== '' / hidden).
        const legacy = await page.evaluate(() => {
            const editor = document.querySelector('#configure-edit-pane .configuration-editor');
            const advanced = document.getElementById('configure-advanced-details');
            return {
                editor: editor ? editor.style.display : 'no-element',
                advanced: advanced ? advanced.style.display : 'no-element',
            };
        });
        if (legacy.editor !== 'no-element') expect(legacy.editor).toBe('none');
        if (legacy.advanced !== 'no-element') expect(legacy.advanced).toBe('none');
    });

    test('repeated + New clicks reset draftProject (no stale name carry-over)', async ({ page }) => {
        await gotoDashboard(page);

        // First click → set a faux draftProject.
        await page.locator('#global-new-deployment-btn').click();
        await page.waitForTimeout(200);
        await page.evaluate(() => {
            if (window.APP && window.APP.activeDeployment) {
                window.APP.activeDeployment.draftProject = 'stale_project_from_previous_session';
            }
        });

        // Second click of + New — startDraftFlow should wipe draftProject.
        await page.locator('#global-new-deployment-btn').click();
        await page.waitForTimeout(300);

        const draft = await page.evaluate(() => {
            const ad = window.APP && window.APP.activeDeployment;
            return ad ? ad.draftProject : 'no-active';
        });
        expect(draft).toBeFalsy();
    });

    test('Deployments sub-pills collapse to {configure, deploy, cleanup} in draft', async ({ page }) => {
        await gotoDashboard(page);
        await page.locator('#global-new-deployment-btn').click();
        await page.waitForTimeout(400);

        const visible = await page.evaluate(() => {
            if (!window.APP || !window.APP.computeVisibleSubPills) return null;
            return window.APP.computeVisibleSubPills(window.APP.activeDeployment);
        });
        expect(visible).not.toBeNull();
        // Draft mode visibility (per app.js:2248) — configure + deploy + cleanup.
        expect(visible).toContain('configure');
        expect(visible).toContain('deploy');
        // Manage / bolt-ons must be absent in draft state.
        expect(visible).not.toContain('manage');
        expect(visible).not.toContain('bolt-ons');
    });
});

/*
 * 2026-05-20 (UX audit Batch A · C1) — Family-first staging.
 *
 * Operator complaint: "+ New Deployment" used to land on a pre-filled
 * form ("c2_adhoc_dev_mozilla_5_0_macintosh_in"). Fix: a two-stage
 * Identity section — landing stage shows only family + type pickers;
 * picking a type collapses them to a confirmed chip row and reveals
 * project_name / env / region.
 */
test.describe('v3 + New Deployment landing — family-first staging', () => {
    async function startNewDeployment(page) {
        await page.evaluate(() => {
            if (window.APP && window.APP._startDraftFlow) {
                window.APP._startDraftFlow();
            } else if (window.APP && window.APP.activeDeployment) {
                window.APP.activeDeployment.set(window.APP.activeDeployment.DRAFT_SENTINEL);
            }
        });
        await page.waitForFunction(() => {
            const p = document.getElementById('configure-v2-pane');
            return p && !p.hidden;
        }, null, { timeout: 3000 });
    }

    test('lands on family + type pickers; project_name hidden until type picked', async ({ page }) => {
        await gotoDashboard(page);
        await startNewDeployment(page);

        await expect(page.locator('#cfg-family-row')).toBeVisible();
        await expect(page.locator('#cfg-type-grid')).toBeVisible();
        await expect(page.locator('#cfg-type-grid .cfg-type-btn').first()).toBeVisible();

        // Sub-fields (project_name / env / region) hidden behind the
        // [data-cfg-identity-sub-fields] container.
        const subFieldsHidden = await page.evaluate(() => {
            const sub = document.querySelector('[data-cfg-identity-sub-fields]');
            return sub ? sub.hidden : null;
        });
        expect(subFieldsHidden).toBe(true);

        // Confirmed chip row not visible yet.
        const confirmedHidden = await page.evaluate(() => {
            const c = document.querySelector('[data-cfg-identity-confirmed]');
            return c ? c.hidden : null;
        });
        expect(confirmedHidden).toBe(true);

        // Hero text is abstract, NOT an auto-generated project name.
        await expect(page.locator('#cfg-hero-title-text')).toHaveText('New deployment');

        const stage = await page.evaluate(() => {
            const sec = document.querySelector('.cfg-section[data-cfg-section="identity"]');
            return sec ? sec.dataset.cfgIdentityStage : null;
        });
        expect(stage).toBe('family');
    });

    test('clicking C2 family keeps type tiles visible', async ({ page }) => {
        await gotoDashboard(page);
        await startNewDeployment(page);

        // Click GOAD then back to C2 to exercise the handler (default
        // family is already C2 — clicking the same family is a no-op).
        await page.click('#cfg-family-row .cfg-family-btn[data-cfg-family="goad"]');
        await page.click('#cfg-family-row .cfg-family-btn[data-cfg-family="c2"]');

        const stage = await page.evaluate(() => {
            const sec = document.querySelector('.cfg-section[data-cfg-section="identity"]');
            return sec ? sec.dataset.cfgIdentityStage : null;
        });
        expect(stage).toBe('family');

        const tileLabels = await page.locator('#cfg-type-grid .cfg-type-btn').allTextContents();
        expect(tileLabels.some(t => t.includes('c2-adhoc'))).toBe(true);
    });

    test('clicking c2-adhoc tile collapses pickers to chip row + reveals sub-fields', async ({ page }) => {
        await gotoDashboard(page);
        await startNewDeployment(page);

        await page.click('#cfg-type-grid .cfg-type-btn[data-cfg-type="c2-adhoc"]');

        const pickersHidden = await page.evaluate(() => {
            const p = document.querySelector('[data-cfg-identity-pickers]');
            return p ? p.hidden : null;
        });
        expect(pickersHidden).toBe(true);

        const confirmed = page.locator('[data-cfg-identity-confirmed]');
        await expect(confirmed).toBeVisible();
        await expect(page.locator('#cfg-identity-confirmed-family')).toHaveText('C2');
        await expect(page.locator('#cfg-identity-confirmed-type')).toHaveText('c2-adhoc');

        await expect(page.locator('#cfg-project-name')).toBeVisible();
        await expect(page.locator('#cfg-env-select')).toBeVisible();
        await expect(page.locator('#cfg-region-select')).toBeVisible();

        const projVal = await page.locator('#cfg-project-name').inputValue();
        expect(projVal).toMatch(/^c2_adhoc_dev_/);

        const heroText = await page.locator('#cfg-hero-title-text').textContent();
        expect(heroText).toMatch(/^c2_adhoc_dev_/);

        const stage = await page.evaluate(() => {
            const sec = document.querySelector('.cfg-section[data-cfg-section="identity"]');
            return sec ? sec.dataset.cfgIdentityStage : null;
        });
        expect(stage).toBe('sub');
    });

    test('chip row edit affordance re-expands pickers and hides sub-fields', async ({ page }) => {
        await gotoDashboard(page);
        await startNewDeployment(page);
        await page.click('#cfg-type-grid .cfg-type-btn[data-cfg-type="c2-adhoc"]');
        await expect(page.locator('[data-cfg-identity-confirmed]')).toBeVisible();

        await page.click('#cfg-identity-edit-btn');

        const pickersHidden = await page.evaluate(() => {
            const p = document.querySelector('[data-cfg-identity-pickers]');
            return p ? p.hidden : null;
        });
        expect(pickersHidden).toBe(false);

        const subHidden = await page.evaluate(() => {
            const s = document.querySelector('[data-cfg-identity-sub-fields]');
            return s ? s.hidden : null;
        });
        expect(subHidden).toBe(true);

        const confirmedHidden = await page.evaluate(() => {
            const c = document.querySelector('[data-cfg-identity-confirmed]');
            return c ? c.hidden : null;
        });
        expect(confirmedHidden).toBe(true);

        await expect(page.locator('#cfg-hero-title-text')).toHaveText('New deployment');

        const stage = await page.evaluate(() => {
            const sec = document.querySelector('.cfg-section[data-cfg-section="identity"]');
            return sec ? sec.dataset.cfgIdentityStage : null;
        });
        expect(stage).toBe('family');
    });

    test('family switch (via edit pencil → C2 → GOAD) resets stage + clears project_name', async ({ page }) => {
        await gotoDashboard(page);
        await startNewDeployment(page);

        // Stage 'sub' after picking c2-adhoc.
        await page.click('#cfg-type-grid .cfg-type-btn[data-cfg-type="c2-adhoc"]');
        await expect(page.locator('[data-cfg-identity-confirmed]')).toBeVisible();

        // Operator clicks the pencil → pickers re-expand → operator picks GOAD.
        // This is the natural flow: family seg-control is part of the collapsed
        // pickers, so re-picking family always goes through the edit pencil.
        await page.click('#cfg-identity-edit-btn');
        await page.click('#cfg-family-row .cfg-family-btn[data-cfg-family="goad"]');

        const stage = await page.evaluate(() => {
            const sec = document.querySelector('.cfg-section[data-cfg-section="identity"]');
            return sec ? sec.dataset.cfgIdentityStage : null;
        });
        expect(stage).toBe('family');

        // project_name input cleared so the next type pick re-engages auto-fill.
        const projVal = await page.evaluate(() => {
            const el = document.getElementById('cfg-project-name');
            return el ? el.value : null;
        });
        expect(projVal).toBe('');

        // GOAD type tiles populated for the new family.
        const tiles = await page.locator('#cfg-type-grid .cfg-type-btn').allTextContents();
        expect(tiles.some(t => t.includes('goad-mini'))).toBe(true);
    });
});
