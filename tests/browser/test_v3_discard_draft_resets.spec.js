/**
 * 2026-05-20 (UX audit Batch A · C2 + H1 + H4)
 *
 * Verifies the "Discard draft" affordance fully resets every Configure
 * surface to a clean empty state:
 *
 *   - Legacy `.configuration-editor` form stays hidden
 *   - V2 pane (#configure-v2-pane) stays hidden
 *   - Discard banner (#configure-discard-draft) is re-hidden
 *   - Context banner copy returns to the empty-state default
 *
 * Repro for the bug this guards against:
 *   1. Click "+ New Deployment"
 *   2. Click Discard draft
 *   3. Observe: legacy form re-appears alongside V2 because the
 *      else branch of applyDraftMode used to re-show legacy chrome
 *      whenever isDraft was false (which includes null/empty).
 */

import { test, expect } from '@playwright/test';

async function gotoDashboard(page) {
    await page.goto('/');
    await page.locator('[data-page="dashboard"]').first().waitFor({ timeout: 5000 });
    await page.waitForTimeout(300);
}

test.describe('v3 discard draft — full reset', () => {
    test('discard hides legacy form, V2 pane, and the discard banner', async ({ page }) => {
        await gotoDashboard(page);

        // Drop into draft mode programmatically (same code path as the
        // "+ New Deployment" button click).
        await page.evaluate(() => {
            if (window.APP && window.APP._startDraftFlow) {
                window.APP._startDraftFlow();
            } else if (window.APP && window.APP.activeDeployment) {
                window.APP.activeDeployment.set(window.APP.activeDeployment.DRAFT_SENTINEL);
            }
        });

        // Wait for draft sentinel to take effect.
        await page.waitForFunction(() => {
            return window.APP && window.APP.activeDeployment &&
                   window.APP.activeDeployment.isDraft && window.APP.activeDeployment.isDraft();
        }, null, { timeout: 3000 });

        // Discard banner must be visible while in draft.
        const discardBanner = page.locator('#configure-discard-draft');
        await expect(discardBanner).toBeVisible();

        // Now click Discard draft.
        await page.click('#configure-discard-draft-btn');

        // Wait for the sentinel to clear.
        await page.waitForFunction(() => {
            return window.APP && window.APP.activeDeployment &&
                   (!window.APP.activeDeployment.isDraft || !window.APP.activeDeployment.isDraft());
        }, null, { timeout: 3000 });

        // 1) Discard banner must be hidden.
        await expect(discardBanner).toBeHidden();

        // 2) V2 pane must be hidden.
        const v2Pane = page.locator('#configure-v2-pane');
        await expect(v2Pane).toBeHidden();

        // 3) Legacy form must be hidden (the C2 bug surfaced as this
        // becoming display:'' on the empty-state branch).
        const legacyState = await page.evaluate(() => {
            const editor = document.querySelector('#configure-edit-pane .configuration-editor');
            const advanced = document.getElementById('configure-advanced-details');
            const actions = document.querySelector('#configure-edit-pane .configure-form-actions');
            return {
                editor: editor ? editor.style.display : 'no-element',
                advanced: advanced ? advanced.style.display : 'no-element',
                actions: actions ? actions.style.display : 'no-element',
            };
        });
        // None of these should be visible. They may be 'no-element' if
        // the page hasn't mounted them yet — that's also fine (means
        // nothing is showing).
        if (legacyState.editor !== 'no-element') expect(legacyState.editor).toBe('none');
        if (legacyState.advanced !== 'no-element') expect(legacyState.advanced).toBe('none');
        if (legacyState.actions !== 'no-element') expect(legacyState.actions).toBe('none');

        // 4) Context banner copy is back to its empty-state default.
        const hint = page.locator('#configure-context-hint');
        if (await hint.count() > 0) {
            const text = await hint.textContent();
            expect(text || '').not.toMatch(/Editing/i);
        }
    });
});
