/**
 * D6 — Bookmarkable URLs.
 *
 * Verifies the URL parse/write contract added in D6.1 + D6.2:
 *
 *   Hash      `#parent` or `#parent/subPill`   — the active tab + sub-pill
 *   Query     `?dep=PROJECT_NAME`              — the active deployment
 *
 * The two halves are independently bookmarkable and can be combined into a
 * single deep-link (`/?dep=foo#deployments-tab/manage`). On load the parser
 * sets APP.activeDeployment BEFORE the first navigateTo() so subscribers see
 * the right context. On navigation the writer uses history.replaceState so
 * the back button is NOT polluted with every tab/sub-pill flip.
 *
 * Plan ref: §21.7 D6.1 + D6.2.
 */

import { test, expect } from '@playwright/test';

test.describe('D6 — bookmarkable URL contract', () => {
    test('hash deep-link restores parent tab + sub-pill on load', async ({ page }) => {
        // Plain hash, no query — operator pasted a tab+sub-pill bookmark.
        await page.goto('/#operations-tab/beacons');

        // Operations tab nav button must be the active one.
        await expect(
            page.locator('button.tab-btn[data-target="operations-tab"].active')
        ).toBeVisible({ timeout: 5000 });

        // Beacons sub-pill must be the active one inside the Operations pane.
        await expect(
            page.locator('.tab-page[data-page="operations-tab"] .subpill-nav__pill[data-subpill="beacons"].is-active')
        ).toHaveCount(1, { timeout: 5000 });
    });

    test('?dep=NAME deep-link populates APP.activeDeployment on load', async ({ page }) => {
        const projectName = 'c2_adhoc_dev_harriss_macbook_pro_01';
        await page.goto(`/?dep=${encodeURIComponent(projectName)}`);

        // Wait for the SPA to boot before asking about APP state.
        await page.locator('button.tab-btn[data-target="dashboard"]').waitFor({ timeout: 5000 });

        // The activeDeployment container is the source of truth — read it
        // directly rather than relying on the global combobox (which won't
        // contain this project unless /api/deploy/active returns it).
        // APP is declared `const APP = ...` at top level of app.js (classic
        // script, not a module). `const` does NOT attach to window, so we
        // reference it by its bare name inside page.evaluate. localStorage is
        // the persistence layer behind APP.activeDeployment.set() — it gives
        // us a probe that doesn't require touching the JS global.
        const active = await page.evaluate(() => localStorage.getItem('activeDeployment'));
        expect(active).toBe(projectName);
    });

    test('combined ?dep=NAME#tab/subPill deep-link sets BOTH on load', async ({ page }) => {
        const projectName = 'goad_mini_dev_harriss_macbook_pro';
        await page.goto(`/?dep=${encodeURIComponent(projectName)}#deployments-tab/manage`);

        // Deployments tab + Manage sub-pill must both be active.
        await expect(
            page.locator('button.tab-btn[data-target="deployments-tab"].active')
        ).toBeVisible({ timeout: 5000 });
        await expect(
            page.locator('.tab-page[data-page="deployments-tab"] .subpill-nav__pill[data-subpill="manage"].is-active')
        ).toHaveCount(1, { timeout: 5000 });

        // And the active deployment must reflect the ?dep= half.
        // APP is declared `const APP = ...` at top level of app.js (classic
        // script, not a module). `const` does NOT attach to window, so we
        // reference it by its bare name inside page.evaluate. localStorage is
        // the persistence layer behind APP.activeDeployment.set() — it gives
        // us a probe that doesn't require touching the JS global.
        const active = await page.evaluate(() => localStorage.getItem('activeDeployment'));
        expect(active).toBe(projectName);
    });

    test('clicking Deployments tab + Configure sub-pill updates URL via replaceState (no history entry added)', async ({ page }) => {
        // Land on Dashboard, then navigate to Deployments → Configure via the UI.
        await page.goto('/');
        await page.locator('button.tab-btn[data-target="dashboard"]').waitFor({ timeout: 5000 });
        const historyLengthBefore = await page.evaluate(() => history.length);

        await page.locator('button.tab-btn[data-target="deployments-tab"]').click();
        // Configure is the default sub-pill on first entry (D3.5), so the
        // URL should land at #deployments-tab/configure automatically.
        await page.locator(
            '.tab-page[data-page="deployments-tab"] .subpill-nav__pill[data-subpill="configure"].is-active'
        ).waitFor({ timeout: 5000 });

        // URL hash matches the (tab, sub-pill) pair.
        const hash = await page.evaluate(() => window.location.hash);
        expect(hash).toBe('#deployments-tab/configure');

        // Critical: history.replaceState (NOT pushState) — same number of
        // entries before vs after, so the browser back-button isn't
        // polluted with every navigation flip.
        const historyLengthAfter = await page.evaluate(() => history.length);
        expect(historyLengthAfter).toBe(historyLengthBefore);
    });

    test('changing APP.activeDeployment appends ?dep=NAME to the URL', async ({ page }) => {
        await page.goto('/#deployments-tab/configure');
        await page.locator(
            '.tab-page[data-page="deployments-tab"] .subpill-nav__pill[data-subpill="configure"].is-active'
        ).waitFor({ timeout: 5000 });

        // initGlobalHeader() is deferred via setTimeout(0) and its
        // _refreshGlobalDeployments() is async — it fetches /api/deploy/active
        // and then calls APP.activeDeployment.set(...) (either to the first
        // deployment or to null on empty state). If we set BEFORE that
        // completes, our value would be overwritten. Wait for the global
        // header listbox to be populated (or for the empty-state item to
        // appear) so the deferred set has already fired.
        await page.waitForFunction(
            () => {
                const lb = document.getElementById('global-deploy-listbox');
                return lb && lb.children.length > 0;
            },
            null,
            { timeout: 5000 }
        );

        // Use the public APP.activeDeployment.set() API (same path the
        // global combobox click handler walks: _selectGlobalOption →
        // APP.activeDeployment.set(value)). Drives the D6.2 subscriber.
        const projectName = 'c2_purple_dev_test_url_writer';
        await page.evaluate((name) => APP.activeDeployment.set(name), projectName);

        // The URL writer is synchronous inside the subscriber.
        await page.waitForFunction(
            (name) => window.location.search.includes(`dep=${encodeURIComponent(name)}`),
            projectName,
            { timeout: 2000 }
        );

        const url = page.url();
        expect(url).toContain(`?dep=${encodeURIComponent(projectName)}`);
        expect(url).toContain('#deployments-tab/configure');
    });
});
