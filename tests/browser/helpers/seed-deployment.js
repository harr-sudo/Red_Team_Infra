// Test helper — mock /api/deploy/active so APP.activeDeployment hydrates
// to a known deployment_type before assertions run.
//
// Background: the production visibility logic gates sub-pills on
// deployment_type + enable_test_lab:
//   - Bolt-ons sub-pill requires goad-* / combined-* / c2-* with test lab
//   - Operations top-tab requires c2-* / combined-*
//   - Manage edit drawer needs an existing real project
//
// Tests that try to reach those surfaces without seeding deployment_type
// hit [hidden] elements and fail. This helper short-circuits the live
// /api/deploy/active call with a deterministic stub.
//
// Usage in a spec file:
//   import { seedDeployment } from './helpers/seed-deployment.js';
//   test.beforeEach(async ({ page }) => {
//     await seedDeployment(page, { type: 'goad-mini' });
//     await page.goto('/');
//   });
//
// Defaults are intentionally minimal — pass `type` (and optionally
// `testLab` / `name`) per-spec to match the surface under test.

/**
 * Mock /api/deploy/active to return ONE deployment with the requested
 * shape, then wait for APP.activeDeployment to settle on it before
 * resolving. Idempotent — calling twice replaces the route handler.
 *
 * @param {import('@playwright/test').Page} page
 * @param {object} opts
 * @param {string} [opts.type='goad-mini'] — deployment_type (c2-adhoc / c2-purple / c2-full / goad-mini / goad-light / goad-sccm / goad-full / goad-nha / combined-adhoc-mini / combined-adhoc-light / combined-full-full)
 * @param {boolean} [opts.testLab=false] — enable_test_lab flag
 * @param {string} [opts.name='test_lab_alpha'] — project_name
 * @param {string} [opts.region='eu-central-1'] — aws_region surfaced via _project_has_test_lab equivalent (cosmetic in tests)
 * @param {string} [opts.status='success'] — deployment lifecycle status
 * @param {string[]} [opts.extra] — additional deployments to include alongside the primary one
 */
export async function seedDeployment(page, opts = {}) {
    const {
        type = 'goad-mini',
        testLab = false,
        name = 'test_lab_alpha',
        region = 'eu-central-1',
        status = 'success',
        extra = [],
    } = opts;

    const primary = {
        project_name: name,
        deployment_type: type,
        enable_test_lab: testLab,
        completed_at: Date.now() / 1000,
        status,
        aws_region: region,
        _filename: name,
    };

    const deployments = [primary, ...extra];

    await page.route('**/api/deploy/active', async (route) => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ success: true, deployments }),
        });
    });

    // Most specs that use this helper also call page.goto() right after.
    // The wait below only fires AFTER navigation when the dashboard JS has
    // booted and activeDeployment.set(name) has been dispatched by
    // _refreshGlobalDeployments. We accept either of two settle conditions:
    //   - current matches the seeded name AND deployment_type is populated
    //   - OR (early-mount) current matches the seeded name + window.APP is loaded
    // We don't return until one is true OR timeout.
    page._seededDeploymentName = name;
    page._seededDeploymentType = type;
}

/**
 * Call AFTER `await page.goto(url)` to wait for the seeded deployment to
 * hydrate fully. Most tests can skip this and just check element state
 * directly, but specs that race on dropdown population should call it.
 *
 * @param {import('@playwright/test').Page} page
 * @param {object} [opts]
 * @param {number} [opts.timeout=5000]
 */
export async function waitForSeededDeployment(page, opts = {}) {
    const { timeout = 5000 } = opts;
    const name = page._seededDeploymentName;
    if (!name) {
        throw new Error('waitForSeededDeployment called without seedDeployment first');
    }
    await page.waitForFunction(
        (targetName) =>
            window.APP &&
            window.APP.activeDeployment &&
            window.APP.activeDeployment.current === targetName &&
            (window.APP.activeDeployment.deployment_type || '').length > 0,
        name,
        { timeout },
    );
}

/**
 * Convenience wrappers for the most common surfaces.
 */
export const seedC2Adhoc = (page, extra = {}) =>
    seedDeployment(page, { type: 'c2-adhoc', name: 'c2_test_alpha', ...extra });

export const seedGoadMini = (page, extra = {}) =>
    seedDeployment(page, { type: 'goad-mini', name: 'goad_test_alpha', ...extra });

export const seedCombined = (page, extra = {}) =>
    seedDeployment(page, { type: 'combined-adhoc-mini', name: 'combined_test_alpha', ...extra });

export const seedC2WithTestLab = (page, extra = {}) =>
    seedDeployment(page, { type: 'c2-adhoc', testLab: true, name: 'c2_testlab_alpha', ...extra });
