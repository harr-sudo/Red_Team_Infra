/**
 * 2026-05-20 (UX audit Batch B · C5 + C6) — Configure V2 family-change.
 *
 * Covers:
 *   1. Family switch resets all confirmed sections (including Identity)
 *      AND re-paints the TOC rail with the new family's section list.
 *   2. Combined family now exposes the Test Lab section (Batch B · C6).
 *   3. Test Lab toggle in c2-adhoc adds 4 line items to the cost table.
 *
 * Spec: docs/internal/UX_AUDIT_2026-05-20.md (C5, C6)
 */

import { test, expect } from '@playwright/test';

async function openDraftConfigure(page) {
    await page.goto('/');
    await page.locator('#global-new-deployment-btn').waitFor({ timeout: 5000 });
    await page.evaluate(() => { window.confirm = () => true; });
    await page.click('#global-new-deployment-btn');
    await page.waitForTimeout(400);
    await page.locator('#configure-v2-pane').waitFor({ timeout: 5000 });
    await page.evaluate(() => {
        if (window.APP && window.APP.configureV2 && window.APP.configureV2.ensureInitialized) {
            return window.APP.configureV2.ensureInitialized();
        }
    });
    await page.waitForTimeout(300);
}

async function pickFamily(page, family) {
    // 2026-05-20 (Batch C) — When Identity is confirmed, its body collapses
    // (grid-template-rows: 0fr) so the family seg-control is hidden. The
    // pencil button on the confirmed chip row re-opens Identity into stage
    // 'family'. Re-edit Identity first if it's confirmed.
    await page.evaluate(() => {
        const sec = document.querySelector('.cfg-section[data-cfg-section="identity"]');
        if (sec && sec.classList.contains('is-confirmed')) {
            const editBtn = document.getElementById('cfg-identity-edit-btn');
            if (editBtn) editBtn.click();
        }
    });
    await page.waitForTimeout(120);
    await page.click(`#cfg-family-row [data-cfg-family="${family}"]`);
    await page.waitForTimeout(200);
}

// 2026-05-20 (Batch C) — Identity now lands on stage 'family'. To expose
// the Confirm button + project_name input, the operator must click a type
// tile first.
async function pickType(page, typeId) {
    if (!typeId) {
        // Read the first tile in the current grid.
        typeId = await page.locator('#cfg-type-grid .cfg-type-btn').first().getAttribute('data-cfg-type');
    }
    await page.waitForSelector(`#cfg-type-grid [data-cfg-type="${typeId}"]`, { state: 'visible' });
    await page.click(`#cfg-type-grid [data-cfg-type="${typeId}"]`);
    await page.waitForSelector('#cfg-project-name', { state: 'visible' });
    await page.waitForTimeout(150);
}

// Unlock every section so checkboxes/inputs inside pending bodies become
// reachable. Production-grade gating preserves the progressive reveal; this
// is a test-only escape hatch.
async function unlockAllSections(page) {
    await page.evaluate(() => {
        document.querySelectorAll('.cfg-section').forEach(s => {
            s.classList.remove('is-pending', 'is-confirmed');
            s.classList.add('is-active');
        });
    });
    await page.waitForTimeout(80);
}

// Toggle the test-lab checkbox via the change-event dispatch so it survives
// pointer-event interception from a `.is-pending` section wrapper.
async function toggleTestLab(page) {
    await page.evaluate(() => {
        const cb = document.getElementById('cfg-enable-test-lab');
        if (!cb) return;
        cb.checked = !cb.checked;
        cb.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await page.waitForTimeout(80);
}

test('Family switch c2 → goad resets Identity AND re-paints rail with 5-section GOAD layout', async ({ page }) => {
    await openDraftConfigure(page);
    await pickFamily(page, 'c2');

    // 2026-05-20 (Batch C) — pick a type tile so Identity moves into stage
    // 'sub', materialising the project_name input + Confirm button.
    await pickType(page);
    // Project name auto-fills from machine suffix; mgmt CIDR is optional for
    // Identity confirm (it lives in Network). Click the Identity Confirm
    // button — `data-cfg-confirm="identity"` (exclude the Skip variant which
    // also matches the attribute selector).
    await page.click('[data-cfg-confirm="identity"]:not([data-cfg-skip])');
    await page.waitForTimeout(200);

    // Identity should be confirmed.
    const identitySection = page.locator('.cfg-section[data-cfg-section="identity"]');
    await expect(identitySection).toHaveClass(/is-confirmed/);

    // Switch family c2 → goad. Identity should no longer be confirmed and
    // the rail should now reflect the 5-section GOAD ordering.
    await pickFamily(page, 'goad');
    await expect(identitySection).not.toHaveClass(/is-confirmed/);
    await expect(identitySection).toHaveClass(/is-active/);

    // Rail visible items match the GOAD section list (identity, network,
    // ssh, attackbox, cost) — 5 entries, no domain/ssl/c2/testlab.
    const visibleRailIds = await page.evaluate(() => {
        const items = Array.from(document.querySelectorAll('.cfg-rail__item'));
        return items
            .filter(el => !el.classList.contains('is-hidden'))
            .map(el => el.dataset.cfgSectionId);
    });
    expect(visibleRailIds).toEqual(['identity', 'network', 'ssh', 'attackbox', 'cost']);

    // Test Lab section is hidden for goad.
    const testlabSec = page.locator('.cfg-section[data-cfg-section="testlab"]');
    await expect(testlabSec).toHaveClass(/is-hidden/);
});

test('Family switch goad → combined exposes Test Lab section (Batch B · C6)', async ({ page }) => {
    await openDraftConfigure(page);
    await pickFamily(page, 'combined');

    // Test Lab section IS visible for combined (Batch B · C6).
    const testlabSec = page.locator('.cfg-section[data-cfg-section="testlab"]');
    await expect(testlabSec).toBeVisible();
    const testlabRail = page.locator('.cfg-rail__item[data-cfg-section-id="testlab"]');
    await expect(testlabRail).toBeVisible();

    // The combined-family explainer note is rendered + visible.
    const combinedNote = page.locator('#cfg-test-lab-combined-note');
    await expect(combinedNote).toBeVisible();
    await expect(combinedNote).toContainText('Combined deployments already include a GOAD lab');
});

test('Test Lab toggle in c2-adhoc adds 4 cost rows', async ({ page }) => {
    await openDraftConfigure(page);
    await pickFamily(page, 'c2');
    // Default type for c2 family is c2-adhoc per TYPES_BY_FAMILY[0].

    // 2026-05-20 (Batch C) — unlock so the test-lab section body is
    // reachable; dispatch the change event directly to survive section-level
    // pointer interception.
    await unlockAllSections(page);
    const beforeRows = await page.locator('#cfg-cost-body tr').count();
    await toggleTestLab(page);
    const afterRows = await page.locator('#cfg-cost-body tr').count();
    expect(afterRows - beforeRows).toBe(4);

    // Sanity-check assembleConfig surfaces the flag.
    const cfg = await page.evaluate(() => window.APP.configureV2.assembleConfig());
    expect(cfg.enable_test_lab).toBe(true);
});

test('Test Lab toggle in combined-* also adds 4 cost rows (Batch B · C6)', async ({ page }) => {
    await openDraftConfigure(page);
    await pickFamily(page, 'combined');

    await unlockAllSections(page);
    const beforeRows = await page.locator('#cfg-cost-body tr').count();
    await toggleTestLab(page);
    const afterRows = await page.locator('#cfg-cost-body tr').count();
    expect(afterRows - beforeRows).toBe(4);

    const cfg = await page.evaluate(() => window.APP.configureV2.assembleConfig());
    expect(cfg.enable_test_lab).toBe(true);
});
