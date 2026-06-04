// Verifies the walkthrough dock behaviour on the LIVE Bolt-ons page:
// slides in ONLY during a walkthrough, dismisses (restoring the catalog)
// on close / Esc / back. The catalog page layout is untouched otherwise.
const { test, expect } = require('@playwright/test');

async function bootBoltOns(page) {
    await page.goto('/');
    await page.waitForFunction(() => window.APP && window.APP.activeDeployment, { timeout: 10000 });
    // Activate the demo deployment (has the test_lab bolt-on catalog).
    await page.evaluate(() => window.APP.startDemoMode && window.APP.startDemoMode());
    await page.waitForTimeout(600);
    // Navigate to the Bolt-ons sub-pill.
    await page.evaluate(() => window.APP.navigateTo('deployments-tab', 'bolt-ons'));
    await page.waitForTimeout(800);
    // Pick a host so the catalog renders.
    await page.evaluate(() => {
        const sel = document.getElementById('bolton-host-select');
        if (sel) {
            sel.value = 'tldc01';
            sel.dispatchEvent(new Event('change', { bubbles: true }));
        }
    });
    await page.waitForTimeout(1200);
}

test('walkthrough dock — default closed', async ({ page }) => {
    await bootBoltOns(page);
    const pane = page.locator('#subpill-pane-bolt-ons');
    // Default: no dock class, catalog at full width.
    await expect(pane).not.toHaveClass(/is-wt-docked/);
});

test('walkthrough dock — slides in on openDetail, out on close', async ({ page }) => {
    await bootBoltOns(page);
    const pane = page.locator('#subpill-pane-bolt-ons');

    // Open a walkthrough.
    await page.evaluate(() =>
        window.APP.bolton.openDetail('bolton.identity-kerberos.kerberoastable-svc', 'walkthrough'));
    await page.waitForTimeout(600);

    // Dock present + pane in docked state + catalog shrunk.
    await expect(pane).toHaveClass(/is-wt-docked/);
    await expect(page.locator('[data-bolton-wt-dock]')).toBeVisible();
    await expect(page.locator('.bolton-detail')).toBeVisible();
    await expect(page.locator('.bolton-detail__tab')).toHaveCount(3);
    // Catalog underneath shrunk to ~44%.
    const catW = await page.evaluate(() => {
        const sc = document.getElementById('bolt-ons-scoped-content');
        const pane = document.getElementById('subpill-pane-bolt-ons');
        return sc && pane ? (sc.getBoundingClientRect().width / pane.getBoundingClientRect().width) : 1;
    });
    expect(catW).toBeLessThan(0.6); // shrunk from 1.0
    await page.screenshot({ path: '/tmp/dock-open-live.png' });

    // Close via the ✕ button.
    await page.click('.bolton-wt-dock__close');
    await page.waitForTimeout(500);
    await expect(pane).not.toHaveClass(/is-wt-docked/);
    // Catalog restored to full width.
    const catW2 = await page.evaluate(() => {
        const sc = document.getElementById('bolt-ons-scoped-content');
        const pane = document.getElementById('subpill-pane-bolt-ons');
        return sc && pane ? (sc.getBoundingClientRect().width / pane.getBoundingClientRect().width) : 1;
    });
    expect(catW2).toBeGreaterThan(0.9); // back to full
    await page.screenshot({ path: '/tmp/dock-closed-live.png' });
});

test('walkthrough dock — Esc closes it', async ({ page }) => {
    await bootBoltOns(page);
    const pane = page.locator('#subpill-pane-bolt-ons');
    await page.evaluate(() =>
        window.APP.bolton.openDetail('bolton.known-cve.zerologon', 'walkthrough'));
    await page.waitForTimeout(600);
    await expect(pane).toHaveClass(/is-wt-docked/);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(400);
    await expect(pane).not.toHaveClass(/is-wt-docked/);
});

test('walkthrough dock — back link closes it', async ({ page }) => {
    await bootBoltOns(page);
    const pane = page.locator('#subpill-pane-bolt-ons');
    await page.evaluate(() =>
        window.APP.bolton.openDetail('bolton.identity-kerberos.kerberoastable-svc', 'walkthrough'));
    await page.waitForTimeout(600);
    await expect(pane).toHaveClass(/is-wt-docked/);
    await page.click('.bolton-wt-dock__back');
    await page.waitForTimeout(400);
    await expect(pane).not.toHaveClass(/is-wt-docked/);
});
