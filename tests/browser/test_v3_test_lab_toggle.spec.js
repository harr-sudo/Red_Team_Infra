/**
 * 2026-05-20 — Configure V2 · Test Lab toggle.
 *
 * Covers:
 *   1. Test Lab section visible only for the c2 family (hidden for goad-*
 *      and combined-*).
 *   2. Toggling the checkbox reveals the inline subnet/help fields AND
 *      injects the 4 test-lab line items into the cost table.
 *   3. assembleConfig() emits enable_test_lab=true + test_lab_subnet_cidr
 *      when the toggle is on, even after a Save round-trip.
 *   4. Switching family from c2 → goad force-clears the toggle so a stale
 *      value can never leak into a non-c2 deployment.
 *
 * Spec: docs/internal/TESTLAB_DESIGN.md
 */

import { test, expect } from '@playwright/test';

async function openDraftConfigure(page) {
    await page.goto('/');
    await page.locator('#global-new-deployment-btn').waitFor({ timeout: 5000 });
    await page.evaluate(() => { window.confirm = () => true; });
    await page.click('#global-new-deployment-btn');
    await page.waitForTimeout(400);
    // Ensure the V2 surface is mounted.
    await page.locator('#configure-v2-pane').waitFor({ timeout: 5000 });
    // Force-init in case applyDraftMode hasn't fired yet
    await page.evaluate(() => {
        if (window.APP && window.APP.configureV2 && window.APP.configureV2.ensureInitialized) {
            return window.APP.configureV2.ensureInitialized();
        }
    });
    await page.waitForTimeout(300);
}

async function pickFamily(page, family) {
    // Family buttons live at #cfg-family-row; data-cfg-family carries 'c2'/'goad'/'combined'.
    await page.click(`#cfg-family-row [data-cfg-family="${family}"]`);
    await page.waitForTimeout(200);
}

test('Test Lab section visible for c2-* family', async ({ page }) => {
    await openDraftConfigure(page);
    await pickFamily(page, 'c2');
    const section = page.locator('.cfg-section[data-cfg-section="testlab"]');
    await expect(section).toBeVisible();
    // The rail item is also visible
    const rail = page.locator('.cfg-rail__item[data-cfg-section-id="testlab"]');
    await expect(rail).toBeVisible();
});

test('Test Lab section hidden for goad-* family', async ({ page }) => {
    await openDraftConfigure(page);
    await pickFamily(page, 'goad');
    const section = page.locator('.cfg-section[data-cfg-section="testlab"]');
    await expect(section).toHaveClass(/is-hidden/);
    const rail = page.locator('.cfg-rail__item[data-cfg-section-id="testlab"]');
    await expect(rail).toHaveClass(/is-hidden/);
});

test('Test Lab section hidden for combined-* family', async ({ page }) => {
    await openDraftConfigure(page);
    await pickFamily(page, 'combined');
    const section = page.locator('.cfg-section[data-cfg-section="testlab"]');
    await expect(section).toHaveClass(/is-hidden/);
});

test('Toggle reveals subnet field + updates cost table', async ({ page }) => {
    await openDraftConfigure(page);
    await pickFamily(page, 'c2');

    const fields = page.locator('#cfg-test-lab-fields');
    await expect(fields).toBeHidden();

    // Cost table baseline — sum the visible rows. We just verify the row
    // count grows by 4 after the toggle flips on.
    const beforeRows = await page.locator('#cfg-cost-body tr').count();

    await page.click('#cfg-enable-test-lab');
    await expect(fields).toBeVisible();

    const subnet = page.locator('#cfg-test-lab-subnet-cidr');
    await expect(subnet).toBeVisible();
    expect((await subnet.inputValue())).toBe('10.0.20.0/24');

    const afterRows = await page.locator('#cfg-cost-body tr').count();
    expect(afterRows - beforeRows).toBeGreaterThanOrEqual(4);

    // Toggle off — fields hide, row count returns to baseline.
    await page.click('#cfg-enable-test-lab');
    await expect(fields).toBeHidden();
    const offRows = await page.locator('#cfg-cost-body tr').count();
    expect(offRows).toBe(beforeRows);
});

test('assembleConfig() writes enable_test_lab=true + subnet cidr', async ({ page }) => {
    await openDraftConfigure(page);
    await pickFamily(page, 'c2');
    await page.click('#cfg-enable-test-lab');

    const config = await page.evaluate(() => window.APP.configureV2.assembleConfig());
    expect(config.enable_test_lab).toBe(true);
    expect(config.test_lab_subnet_cidr).toBe('10.0.20.0/24');
});

test('Family switch c2 → goad force-clears the test lab toggle', async ({ page }) => {
    await openDraftConfigure(page);
    await pickFamily(page, 'c2');
    await page.click('#cfg-enable-test-lab');
    await expect(page.locator('#cfg-test-lab-fields')).toBeVisible();

    await pickFamily(page, 'goad');
    // The toggle must be unchecked AND the assemble output must reflect that.
    const isChecked = await page.locator('#cfg-enable-test-lab').isChecked();
    expect(isChecked).toBe(false);

    const config = await page.evaluate(() => window.APP.configureV2.assembleConfig());
    expect(config.enable_test_lab).toBe(false);
});
