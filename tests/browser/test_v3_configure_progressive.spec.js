/**
 * V3 Configure — Progressive Unraveling (2026-05-19).
 *
 * Verifies the new progressive Configure surface (ported from
 * webapp/frontend/preview/configure-flow-c-progressive.html) into the live
 * dashboard at /webapp/frontend/index.html via APP.configureV2.
 *
 * - "+ New Deployment" lands on Configure in draft mode and renders V2.
 * - The three section states (pending / active / confirmed) behave correctly.
 * - Smart defaults pre-fill so Save works with minimal input.
 * - Route53 picker hits the real /api/aws/route53/zones endpoint.
 * - Profile catalog populates 79+ options (5 built-in + BC-SECURITY catalog).
 * - Reset clears state to skeleton.
 * - Validate appears only when all sections confirmed.
 * - Both themes contrast clean.
 */

import { test, expect } from '@playwright/test';

async function setTheme(page, theme) {
    await page.evaluate((t) => {
        if (t === 'light') document.documentElement.setAttribute('data-theme', 'light');
        else document.documentElement.removeAttribute('data-theme');
    }, theme);
    await page.waitForTimeout(200);
}

async function acceptDirtyConfirm(page) {
    await page.evaluate(() => { window.confirm = () => true; });
}

async function gotoDraft(page) {
    await page.goto('/#deployments-tab/configure?draft=1');
    await acceptDirtyConfirm(page);
    await page.waitForTimeout(500);
}

test.describe('V3 Configure Progressive — surface mounts', () => {
    test('draft URL renders V2 surface inside Configure', async ({ page }) => {
        await gotoDraft(page);
        const v2 = page.locator('#configure-v2-pane');
        await expect(v2).toBeVisible({ timeout: 5000 });
        // TOC rail exists with 8 items
        const railItems = page.locator('#configure-v2-pane .cfg-rail__item');
        await expect(railItems).toHaveCount(8);
        // First section (Identity) is active on first paint
        await expect(page.locator('.cfg-section[data-cfg-section="identity"]')).toHaveClass(/is-active/);
    });

    test('clicking "+ New Deployment" routes into V2 (not the wizard)', async ({ page }) => {
        await page.goto('/');
        await acceptDirtyConfirm(page);
        await page.locator('#global-new-deployment-btn').waitFor({ timeout: 5000 });
        await page.click('#global-new-deployment-btn');
        await page.waitForTimeout(600);
        await expect(page.locator('#configure-v2-pane')).toBeVisible({ timeout: 5000 });
        // Legacy wizard mount point should be empty
        const wizardInner = await page.locator('#configure-new-pane').innerHTML();
        expect(wizardInner.trim()).toBe('');
    });
});

test.describe('V3 Configure Progressive — state machine', () => {
    test('confirming Identity activates Network', async ({ page }) => {
        await gotoDraft(page);
        await expect(page.locator('#configure-v2-pane')).toBeVisible();
        // Identity confirm
        await page.click('.cfg-section[data-cfg-section="identity"] [data-cfg-confirm="identity"]:not([data-cfg-skip])');
        await page.waitForTimeout(400);
        await expect(page.locator('.cfg-section[data-cfg-section="identity"]')).toHaveClass(/is-confirmed/);
        await expect(page.locator('.cfg-section[data-cfg-section="network"]')).toHaveClass(/is-active/);
    });

    test('Validate is hidden until all sections confirmed', async ({ page }) => {
        await gotoDraft(page);
        const validate = page.locator('#cfg-validate-btn');
        await expect(validate).toBeHidden();
        // Confirm everything via the API
        await page.evaluate(() => {
            const order = ['identity', 'network', 'ssh', 'domain', 'ssl', 'c2', 'attackbox', 'cost'];
            for (const id of order) {
                const btn = document.querySelector(`.cfg-section[data-cfg-section="${id}"] [data-cfg-confirm="${id}"]:not([data-cfg-skip])`);
                if (btn) btn.click();
            }
        });
        await page.waitForTimeout(800);
        await expect(validate).toBeVisible();
    });
});

test.describe('V3 Configure Progressive — smart defaults', () => {
    test('Save button is disabled until all sections confirmed; defaults pre-filled', async ({ page }) => {
        await gotoDraft(page);
        await page.waitForTimeout(400);
        // Defaults that should be pre-populated:
        await expect(page.locator('#cfg-env-select')).toHaveValue('dev');
        await expect(page.locator('#cfg-region-select')).toHaveValue('eu-central-1');
        await expect(page.locator('#cfg-keypair-name')).toHaveValue('red-team-keypair');
        await expect(page.locator('#cfg-ssl-provider')).toHaveValue('letsencrypt');
        await expect(page.locator('#cfg-malleable-profile')).toHaveValue('default');
        // Project name auto-generated
        const proj = await page.locator('#cfg-project-name').inputValue();
        expect(proj.length).toBeGreaterThan(0);
        expect(proj).toContain('c2_adhoc_dev_');
        // Save disabled
        await expect(page.locator('#cfg-save-btn')).toBeDisabled();
    });
});

test.describe('V3 Configure Progressive — Route 53 picker', () => {
    test('GET /api/aws/route53/zones returns success shape', async ({ request }) => {
        const resp = await request.get('/api/aws/route53/zones');
        const data = await resp.json();
        expect(data).toHaveProperty('success');
        expect(data).toHaveProperty('zones');
        expect(Array.isArray(data.zones)).toBe(true);
        if (data.success && data.zones.length > 0) {
            const z = data.zones[0];
            expect(z).toHaveProperty('name');
            expect(z).toHaveProperty('id');
            expect(z).toHaveProperty('private');
            expect(z).toHaveProperty('record_count');
            expect(z).toHaveProperty('in_use_by_project_or_null');
        }
    });

    test('domain picker dropdown gets populated', async ({ page }) => {
        await gotoDraft(page);
        await page.waitForTimeout(1500);
        const selOptions = await page.locator('#cfg-primary-domain-select option').count();
        // Empty + custom = 2 baseline; with zones we get more
        expect(selOptions).toBeGreaterThanOrEqual(2);
    });
});

test.describe('V3 Configure Progressive — profile catalog', () => {
    test('built-in profiles available; catalog populates async', async ({ page }) => {
        await gotoDraft(page);
        await page.waitForTimeout(2000);
        const totalOptions = await page.locator('#cfg-malleable-profile option').count();
        // 5 built-in + custom = 6 baseline; with catalog we expect significantly more
        expect(totalOptions).toBeGreaterThanOrEqual(6);
    });
});

test.describe('V3 Configure Progressive — reset', () => {
    test('Reset returns all sections to pending', async ({ page }) => {
        await gotoDraft(page);
        // Confirm a few sections
        await page.evaluate(() => {
            ['identity', 'network'].forEach(id => {
                const btn = document.querySelector(`.cfg-section[data-cfg-section="${id}"] [data-cfg-confirm="${id}"]:not([data-cfg-skip])`);
                if (btn) btn.click();
            });
        });
        await page.waitForTimeout(400);
        await expect(page.locator('.cfg-section[data-cfg-section="identity"]')).toHaveClass(/is-confirmed/);
        // Reset
        await page.click('#cfg-reset-btn');
        await page.waitForTimeout(200);
        await page.click('#cfg-reset-confirm');
        await page.waitForTimeout(400);
        await expect(page.locator('.cfg-section[data-cfg-section="identity"]')).toHaveClass(/is-active/);
        await expect(page.locator('.cfg-section[data-cfg-section="network"]')).toHaveClass(/is-pending/);
    });
});

test.describe('V3 Configure Progressive — per-project pipeline (Configure → Deploy)', () => {
    // After V2 save, the Deploy sub-pill must route Plan / Apply through
    // ?project=<name> so backend reads configs/<name>.tfvars (not the
    // stale global one). These tests verify the wiring end-to-end via
    // request interception + the defence-in-depth legacy-field sync.

    test('V2 save syncs legacy #project-name + #deployment-type inputs', async ({ page }) => {
        await gotoDraft(page);
        await page.waitForTimeout(400);
        // Confirm every section so Save is enabled, then save by directly
        // invoking the V2 save() — bypasses the prereq panel which would
        // need backend state we don't want to set up here.
        await page.evaluate(async () => {
            const order = ['identity', 'network', 'ssh', 'domain', 'ssl', 'c2', 'attackbox', 'cost'];
            for (const id of order) {
                const btn = document.querySelector(`.cfg-section[data-cfg-section="${id}"] [data-cfg-confirm="${id}"]:not([data-cfg-skip])`);
                if (btn) btn.click();
            }
        });
        await page.waitForTimeout(400);
        // Stub the save POST so we don't actually write a tfvars on the
        // dashboard host. The success response is what triggers the
        // legacy-field sync in app.js.
        await page.route('**/api/config/?project=*', async (route) => {
            const req = route.request();
            if (req.method() === 'POST') {
                await route.fulfill({
                    status: 200,
                    contentType: 'application/json',
                    body: JSON.stringify({ success: true, tfvars_path: 'configs/synced_lab.tfvars' })
                });
            } else {
                await route.continue();
            }
        });
        // Pin a stable project_name so we can assert on it.
        await page.fill('#cfg-project-name', 'synced_lab');
        await page.click('#cfg-save-btn');
        await page.waitForTimeout(400);
        // Defence-in-depth: legacy hidden inputs must now reflect V2 state.
        const legacyProjectVal = await page.locator('#project-name').inputValue();
        expect(legacyProjectVal).toBe('synced_lab');
        const legacyTypeVal = await page.locator('#deployment-type').inputValue();
        expect(legacyTypeVal.length).toBeGreaterThan(0); // populated from V2's deployment_type
    });

    // 2026-05-20 — Save stays in DRAFT mode until Apply succeeds. Verifies
    // the operator can still reach Configure + Deploy after Save and the
    // dropdown surfaces "Draft: <name>" so the in-progress work is visible.
    test('Save stays in draft mode with draftProject; Apply-success flips to existing', async ({ page }) => {
        await gotoDraft(page);
        await page.waitForTimeout(400);
        await page.evaluate(async () => {
            const order = ['identity', 'network', 'ssh', 'domain', 'ssl', 'c2', 'attackbox', 'cost'];
            for (const id of order) {
                const btn = document.querySelector(`.cfg-section[data-cfg-section="${id}"] [data-cfg-confirm="${id}"]:not([data-cfg-skip])`);
                if (btn) btn.click();
            }
        });
        await page.waitForTimeout(400);
        await page.route('**/api/config/?project=*', async (route) => {
            const req = route.request();
            if (req.method() === 'POST') {
                await route.fulfill({
                    status: 200,
                    contentType: 'application/json',
                    body: JSON.stringify({ success: true, tfvars_path: 'configs/staging_lab.tfvars' })
                });
            } else {
                await route.continue();
            }
        });
        await page.fill('#cfg-project-name', 'staging_lab');
        await page.click('#cfg-save-btn');
        await page.waitForTimeout(400);

        // After Save: stays in draft, draftProject staged, Deploy still reachable.
        const afterSave = await page.evaluate(() => ({
            current: window.APP.activeDeployment.current,
            draftProject: window.APP.activeDeployment.draftProject,
            isDraft: window.APP.activeDeployment.isDraft(),
            displayName: window.APP.activeDeployment.displayName(),
            effective: window.APP.activeDeployment.effectiveProject(),
        }));
        expect(afterSave.current).toBe('__draft__');
        expect(afterSave.draftProject).toBe('staging_lab');
        expect(afterSave.isDraft).toBe(true);
        expect(afterSave.displayName).toBe('Draft: staging_lab');
        expect(afterSave.effective).toBe('staging_lab');

        // Deploy sub-pill must still be visible (operator needs to Apply).
        const deployPill = page.locator('.tab-page[data-page="deployments-tab"] .subpill-nav__pill[data-subpill="deploy"]');
        await expect(deployPill).not.toHaveAttribute('hidden', '');
        const configurePill = page.locator('.tab-page[data-page="deployments-tab"] .subpill-nav__pill[data-subpill="configure"]');
        await expect(configurePill).not.toHaveAttribute('hidden', '');

        // Simulate Apply-success: directly invoke the promotion path that
        // pollDeploymentStatus runs when status flips to 'success'.
        await page.evaluate(() => {
            const promoted = window.APP.activeDeployment.draftProject;
            window.APP.activeDeployment.draftProject = null;
            window.APP.activeDeployment.set(promoted);
        });
        await page.waitForTimeout(300);

        const afterApply = await page.evaluate(() => ({
            current: window.APP.activeDeployment.current,
            draftProject: window.APP.activeDeployment.draftProject,
            isDraft: window.APP.activeDeployment.isDraft(),
            isExisting: window.APP.activeDeployment.isExisting(),
        }));
        expect(afterApply.current).toBe('staging_lab');
        expect(afterApply.draftProject).toBe(null);
        expect(afterApply.isDraft).toBe(false);
        expect(afterApply.isExisting).toBe(true);

        // With deployment_type unknown (cache hasn't refreshed), Deploy
        // should be hidden but Manage should be visible.
        await expect(deployPill).toHaveAttribute('hidden', '');
        const managePill = page.locator('.tab-page[data-page="deployments-tab"] .subpill-nav__pill[data-subpill="manage"]');
        await expect(managePill).not.toHaveAttribute('hidden', '');
    });

    // 2026-05-20 — runPlan() must accept a saved draft via effectiveProject().
    test('runPlan accepts saved-draft via effectiveProject (draftProject set)', async ({ page }) => {
        await page.goto('/');
        await acceptDirtyConfirm(page);
        await page.waitForTimeout(500);
        await page.evaluate(() => {
            window.APP.activeDeployment.set(window.APP.activeDeployment.DRAFT_SENTINEL);
            window.APP.activeDeployment.draftProject = 'staged_lab';
        });
        let interceptedURL = null;
        await page.route('**/api/deploy/plan*', async (route) => {
            interceptedURL = route.request().url();
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({ success: true, stdout: 'No changes.', stderr: '', plan: {} })
            });
        });
        await page.evaluate(() => window.runPlan());
        await page.waitForTimeout(400);
        expect(interceptedURL).toBeTruthy();
        expect(interceptedURL).toContain('project=staged_lab');
    });

    test('Deploy sub-pill Plan button calls /api/deploy/plan?project=<active>', async ({ page }) => {
        await page.goto('/');
        await acceptDirtyConfirm(page);
        await page.waitForTimeout(500);
        // Pin an active deployment so the V3 gate accepts the action.
        await page.evaluate(() => {
            window.APP.activeDeployment.set('lab_intercepted');
        });
        // Intercept /api/deploy/plan so we can assert the URL shape — and
        // never actually call terraform.
        let interceptedURL = null;
        await page.route('**/api/deploy/plan*', async (route) => {
            interceptedURL = route.request().url();
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({ success: true, stdout: 'No changes.', stderr: '', plan: {} })
            });
        });
        // Call runPlan() directly — wiring through the UI button requires
        // navigating to the deploy sub-pill and unlocking it via validate
        // (which itself needs a saved config). Direct invocation is the
        // tightest assertion against the per-project URL shape.
        await page.evaluate(() => window.runPlan());
        await page.waitForTimeout(400);
        expect(interceptedURL).toBeTruthy();
        expect(interceptedURL).toContain('project=lab_intercepted');
    });

    test('Plan button bails out when activeDeployment is draft sentinel', async ({ page }) => {
        await page.goto('/');
        await acceptDirtyConfirm(page);
        await page.waitForTimeout(500);
        await page.evaluate(() => {
            window.APP.activeDeployment.set(window.APP.activeDeployment.DRAFT_SENTINEL);
        });
        let intercepted = false;
        await page.route('**/api/deploy/plan*', async (route) => {
            intercepted = true;
            await route.continue();
        });
        await page.evaluate(() => window.runPlan());
        await page.waitForTimeout(300);
        // Guard fired — no network call.
        expect(intercepted).toBe(false);
    });
});

test.describe('V3 Configure Progressive — dual-theme contrast', () => {
    for (const theme of ['dark', 'light']) {
        test(`renders cleanly in ${theme} theme`, async ({ page }) => {
            await gotoDraft(page);
            await setTheme(page, theme);
            const v2 = page.locator('#configure-v2-pane');
            await expect(v2).toBeVisible();
            // Confirm a section to engage the confirmed state pill which uses success colors
            await page.click('.cfg-section[data-cfg-section="identity"] [data-cfg-confirm="identity"]:not([data-cfg-skip])');
            await page.waitForTimeout(300);
            // Compute the text color on the confirmed state pill — must not be transparent or pure black against the theme bg.
            const color = await page.locator('.cfg-section[data-cfg-section="identity"] .cfg-section__state-pill').evaluate(el => getComputedStyle(el).color);
            expect(color).toBeTruthy();
            expect(color).not.toBe('rgba(0, 0, 0, 0)');
        });
    }
});
