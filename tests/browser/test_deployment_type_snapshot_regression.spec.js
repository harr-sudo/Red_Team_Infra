/**
 * Layer 3 — Deployment-type cascade regression guard.
 *
 * Loads the deployment_snapshots.json baseline and verifies that for each
 * of the captured deployment types, the same sections are visible/hidden
 * as recorded at baseline capture time.
 *
 * This is the safety net for the D3 dashboard refactor (Configuration +
 * Deploy + Deployment Manager → Deployments tab). If re-parenting the
 * Configuration subtree breaks the 10-section conditional cascade,
 * THIS TEST FAILS LOUDLY with the exact deployment-type + section that
 * changed behavior.
 *
 * To re-bless the baseline after an intentional change:
 *   1. Run: npx playwright test tests/browser/fixtures/capture_deployment_snapshots.spec.js
 *      (or: make snapshot-bless)
 *   2. Inspect the diff to deployment_snapshots.json
 *   3. Commit if the change was intentional
 *
 * Plan ref: §21.5, §26.4 item 6, §27.7 (D3 risks)
 */

import { test, expect } from '@playwright/test';
import fs from 'fs';
import path from 'path';

// Playwright treats these .spec.js files as CommonJS (no "type":
// "module" in package.json), so we use Node's built-in __dirname.
const SNAPSHOT_PATH = path.join(__dirname, 'fixtures', 'deployment_snapshots.json');

// Load the baseline at module-load time so we can generate one test per
// deployment type. If the baseline is missing, fail loudly with a clear
// remediation hint.
if (!fs.existsSync(SNAPSHOT_PATH)) {
    throw new Error(
        `Snapshot baseline not found at ${SNAPSHOT_PATH}. ` +
        `Generate it with: make snapshot-bless ` +
        `(or: npx playwright test tests/browser/fixtures/capture_deployment_snapshots.spec.js)`
    );
}
const BASELINE = JSON.parse(fs.readFileSync(SNAPSHOT_PATH, 'utf8'));

async function probeSection(page, sectionId) {
    const locator = page.locator(`#${sectionId}`);
    const present = (await locator.count()) > 0;
    let visible = false;
    let displayed = false;
    if (present) {
        visible = await locator.isVisible();
        const display = await locator.evaluate((el) => getComputedStyle(el).display);
        displayed = display !== 'none';
    }
    return { present, visible, displayed };
}

// Parallel describe so the 11 deployment-type tests can run concurrently
// across Playwright workers without sharing state (each gets its own page).
test.describe.parallel('deployment-type cascade regression guard', () => {
    for (const [deploymentType, expected] of Object.entries(BASELINE)) {
        test(`cascade matches baseline: ${deploymentType}`, async ({ page }) => {
            // D3.1 — ?legacyTabs=1 keeps the legacy Configuration / Deploy /
            // Deployment Manager nav buttons visible during the merge refactor.
            // Until D3.2 re-parents the Configuration subtree under the new
            // Deployments tab, the snapshot guard still targets the legacy
            // tab. This query param is removed at D3.6 along with the legacy
            // buttons themselves.
            await page.goto('/?legacyTabs=1');
            // Navigate to the Configuration tab where the
            // deployment-type <select> lives.
            await page.locator('button.tab-btn[data-target="configuration"]').click();
            await page.locator('#deployment-type').waitFor({ state: 'visible', timeout: 5000 });
            await page.selectOption('#deployment-type', deploymentType);
            // Same settle wait as capture — keeps probe semantics aligned.
            await page.waitForTimeout(250);

            // Probe every section the baseline knows about, then compare.
            for (const [sectionId, expectedProbe] of Object.entries(expected.sections)) {
                const actual = await probeSection(page, sectionId);

                // Custom assertion message names the deployment + section
                // so a failure points directly at what regressed.
                if (actual.present !== expectedProbe.present) {
                    throw new Error(
                        `Deployment type '${deploymentType}': section #${sectionId} ` +
                        `expected present=${expectedProbe.present} but was ${actual.present} ` +
                        `(DOM membership changed — possible regression)`
                    );
                }
                if (actual.visible !== expectedProbe.visible) {
                    throw new Error(
                        `Deployment type '${deploymentType}': section #${sectionId} ` +
                        `expected ${expectedProbe.visible ? 'visible' : 'hidden'} ` +
                        `but was ${actual.visible ? 'visible' : 'hidden'} (regression?)`
                    );
                }
                if (actual.displayed !== expectedProbe.displayed) {
                    throw new Error(
                        `Deployment type '${deploymentType}': section #${sectionId} ` +
                        `expected display!=none=${expectedProbe.displayed} ` +
                        `but was ${actual.displayed} (regression?)`
                    );
                }
            }

            // key-pair-name disabled state — GOAD-only deployments
            // auto-generate keys, so the input must be disabled there.
            const actualDisabled = await page.locator('#key-pair-name').isDisabled();
            expect(
                actualDisabled,
                `Deployment type '${deploymentType}': #key-pair-name ` +
                `expected disabled=${expected.keyPairDisabled} but was ${actualDisabled}`
            ).toBe(expected.keyPairDisabled);
        });
    }
});
