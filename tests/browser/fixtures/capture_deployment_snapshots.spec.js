/**
 * Snapshot capture — generates the deployment-type cascade baseline.
 *
 * Run this ON-DEMAND (not on every CI cycle) to produce
 * tests/browser/fixtures/deployment_snapshots.json. That file is the
 * baseline consumed by test_deployment_type_snapshot_regression.spec.js.
 *
 * Re-bless workflow:
 *   1. Make an intentional change to webapp/frontend/js/app.js
 *      updateDeploymentType() or the section-card markup in index.html.
 *   2. Run: npx playwright test tests/browser/fixtures/capture_deployment_snapshots.spec.js
 *      (or: make snapshot-bless)
 *   3. Diff deployment_snapshots.json — verify each change is intentional.
 *   4. Commit the new baseline.
 *
 * Source-of-truth: the <option value="..."> entries inside the
 * <select id="deployment-type"> in webapp/frontend/index.html (~L67-87).
 *
 * Plan ref: §21.5, §27.2 (T0.9), §27.7 (D3 risks)
 */

import { test, expect } from '@playwright/test';
import fs from 'fs';
import path from 'path';

// Playwright treats these .spec.js files as CommonJS (no "type":
// "module" in package.json), so we can use Node's built-in __dirname.
// Using import.meta.url would throw "require is not defined".
const SNAPSHOT_PATH = path.join(__dirname, 'deployment_snapshots.json');

// Source-of-truth deployment-type values, extracted from
// webapp/frontend/index.html lines 70-84 (the deployment-type <select>).
// Empty option values are intentionally excluded.
const DEPLOYMENT_TYPES = [
    // Full C2 Infrastructure
    'c2-adhoc',
    'c2-purple',
    'c2-full',
    // GOAD + Cobalt Strike
    'goad-mini',
    'goad-light',
    'goad-sccm',
    'goad-full',
    'goad-nha',
    // Combined C2 + GOAD
    'combined-adhoc-mini',
    'combined-adhoc-light',
    'combined-full-full',
];

// Watch list from plan §20.2 — the conditional sections that
// updateDeploymentType() in app.js (L7517+) shows/hides.
const WATCH_SECTIONS = [
    'deployment-overview',
    'domain-config-section',
    'ssl-config-section',
    'domain-fronting-section',
    'file-portal-section',
    'attack-box-config-section',
    'decoy-theme-section',
    'malleable-profile-section',
    'goad-network-config-section',
    'c2-server-count-group',
    'c2-instance-type-group',
];

// Per-section "present + visible" probe. We record both because some
// sections may be conditionally added/removed from the DOM (not just
// toggled). `present` = element exists in DOM. `visible` = it's
// rendered and not display:none / visibility:hidden.
async function probeSection(page, sectionId) {
    const locator = page.locator(`#${sectionId}`);
    const present = (await locator.count()) > 0;
    let visible = false;
    let displayed = false;
    if (present) {
        // .isVisible() returns false for display:none, visibility:hidden,
        // zero-sized boxes — matches the "is this user-visible" semantic.
        visible = await locator.isVisible();
        // Also record the computed display value distinctly — gives us
        // a more granular diff when something changes.
        const display = await locator.evaluate((el) => getComputedStyle(el).display);
        displayed = display !== 'none';
    }
    return { present, visible, displayed };
}

// Aggregate all results into a single object, then write once at the end.
const allSnapshots = {};

test.describe.serial('deployment-type snapshot capture', () => {
    for (const dt of DEPLOYMENT_TYPES) {
        test(`capture: ${dt}`, async ({ page }) => {
            await page.goto('/');
            // The dashboard is the active tab by default; the
            // deployment-type <select> lives inside the Configuration
            // tab, which is hidden until clicked.
            await page.locator('button.tab-btn[data-target="configuration"]').click();
            // Wait for the dropdown to be ready (visible)
            await page.locator('#deployment-type').waitFor({ state: 'visible', timeout: 5000 });

            // Select the deployment type and fire the change event so
            // updateDeploymentType() runs. selectOption() dispatches
            // change automatically.
            await page.selectOption('#deployment-type', dt);

            // Per §27.2 T0.9 risk note: give DOM mutations / any async
            // work in updateDeploymentType() time to settle.
            await page.waitForTimeout(250);

            const sections = {};
            for (const sec of WATCH_SECTIONS) {
                sections[sec] = await probeSection(page, sec);
            }

            // Record key-pair-name disabled state — also driven by
            // deployment type (GOAD-only auto-generates its keys).
            const keyPair = page.locator('#key-pair-name');
            const keyPairDisabled = await keyPair.isDisabled();

            allSnapshots[dt] = {
                sections,
                keyPairDisabled,
            };
        });
    }

    test.afterAll(async () => {
        // Sort keys deterministically so diffs stay readable
        const sortedKeys = Object.keys(allSnapshots).sort();
        const ordered = {};
        for (const k of sortedKeys) ordered[k] = allSnapshots[k];

        fs.writeFileSync(SNAPSHOT_PATH, JSON.stringify(ordered, null, 2) + '\n');
        // eslint-disable-next-line no-console
        console.log(
            `Captured ${sortedKeys.length} deployment-type snapshots ` +
            `→ fixtures/deployment_snapshots.json`
        );
    });
});
