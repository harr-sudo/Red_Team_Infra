/**
 * v3 SHELL — Production scaffold tests (Agent A, 2026-05-18)
 *
 * Verifies the .app-shell wrapping that the production rollout introduces.
 * The shell is composed of three pieces:
 *
 *   .app-topbar  — top utility bar (breadcrumb left, deployment selector +
 *                  cost + operator + theme RIGHT)
 *   .app-rail    — left primary nav (Dashboard / Deployments / Operations /
 *                  Settings) with nested sub-pills under the active parent
 *   .app-content — page panes live unchanged inside (Phase 2b/3 interiors)
 *
 * These tests prove the foundation contract. Sibling agents B/C/D will
 * mount on top of this shell (palette trigger, overlay shells, new
 * sub-pills) and rely on every assertion here holding.
 *
 * Critical invariants:
 *   1. .app-shell DOM is present on every page load
 *   2. Rail renders all 4 primary nav items
 *   3. Active state moves between rail items on click
 *   4. Expanding a parent reveals its sub-pills
 *   5. Top-bar deployment selector sits on the RIGHT (per 2026-05-18 user)
 *   6. D6 bookmarkable URL hash still works
 *   7. Both themes pass layer-aware contrast on shell chrome
 */

import { test, expect } from '@playwright/test';

// ─────────────────────────────────────────────────────────────────────
// WCAG helpers (sRGB → relative luminance → contrast ratio). Same
// shape as test_v3_dashboard.spec.js so this suite is self-contained.
// ─────────────────────────────────────────────────────────────────────

function parseRgb(s) {
    const m = s.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const parts = m[1].split(',').map((p) => parseFloat(p.trim()));
    return [parts[0], parts[1], parts[2], parts.length === 4 ? parts[3] : 1];
}
function lin(c) {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
}
function lum([r, g, b]) {
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}
function ratio(a, b) {
    const L1 = lum(a);
    const L2 = lum(b);
    return (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
}

const WALK_TO_SURFACE_FN = function walkToSurface(el) {
    function parseRgba(s) {
        const m = s.match(/rgba?\(([^)]+)\)/);
        if (!m) return null;
        const parts = m[1].split(',').map((p) => parseFloat(p.trim()));
        return [parts[0], parts[1], parts[2], parts.length === 4 ? parts[3] : 1];
    }
    const stack = [];
    let cur = el;
    while (cur && cur !== document.documentElement) {
        const cs = window.getComputedStyle(cur);
        const parsed = parseRgba(cs.backgroundColor);
        if (parsed && parsed[3] > 0.01) {
            stack.push(parsed);
            if (parsed[3] >= 0.99) break;
        }
        cur = cur.parentElement;
    }
    if (stack.length === 0 || stack[stack.length - 1][3] < 0.99) {
        const bodyBg = parseRgba(window.getComputedStyle(document.body).backgroundColor) || [255, 255, 255, 1];
        stack.push(bodyBg);
    }
    let [r, g, b] = stack[stack.length - 1].slice(0, 3);
    for (let i = stack.length - 2; i >= 0; i--) {
        const [or, og, ob, oa] = stack[i];
        r = or * oa + r * (1 - oa);
        g = og * oa + g * (1 - oa);
        b = ob * oa + b * (1 - oa);
    }
    return `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`;
};

async function setTheme(page, theme) {
    await page.evaluate((t) => {
        if (t === 'light') document.documentElement.setAttribute('data-theme', 'light');
        else document.documentElement.removeAttribute('data-theme');
    }, theme);
    await page.waitForTimeout(280);
}

// ─────────────────────────────────────────────────────────────────────
// 1. SHELL MARKUP — smoke
// ─────────────────────────────────────────────────────────────────────

test.describe('v3 shell — markup', () => {
    test('app-shell wraps the entire app on page load', async ({ page }) => {
        await page.goto('/');
        await expect(page.locator('.app-shell')).toHaveCount(1, { timeout: 5000 });
        // Three direct structural children must exist.
        await expect(page.locator('.app-shell > .app-topbar')).toHaveCount(1);
        await expect(page.locator('.app-shell > .app-rail')).toHaveCount(1);
        await expect(page.locator('.app-shell > .app-content')).toHaveCount(1);
    });

    test('rail renders all 4 primary nav items in order', async ({ page }) => {
        await page.goto('/');
        const items = page.locator('.app-rail .app-rail__item[data-rail-target]');
        await expect(items).toHaveCount(4, { timeout: 5000 });

        const labels = await items.evaluateAll((els) =>
            els.map((el) => el.querySelector('.app-rail__label')?.textContent?.trim())
        );
        expect(labels).toEqual(['Dashboard', 'Deployments', 'Operations', 'Settings']);
    });

    test('rail brand band shows project name', async ({ page }) => {
        await page.goto('/');
        await expect(page.locator('.app-rail__brand-name')).toContainText('RED TEAM INFRA', { timeout: 5000 });
    });

    test('rail footer renders a version label', async ({ page }) => {
        await page.goto('/');
        // 2026-05-20: The dedicated rail-footer version label was removed
        // when the app-level #app-version-footer (separate floating footer)
        // was introduced. The version surface now lives outside the rail in
        // #app-version-footer / #app-version-footer-text. The brand kicker
        // inside the rail still shows the version short-form.
        await expect(page.locator('#app-version-footer-text')).toBeVisible({ timeout: 5000 });
    });
});

// ─────────────────────────────────────────────────────────────────────
// 2. TOP-BAR ORDERING — deployment selector on the RIGHT
//    (user directive 2026-05-18)
// ─────────────────────────────────────────────────────────────────────

test.describe('v3 shell — top utility bar', () => {
    test('deployment selector is positioned on the right side of the top bar', async ({ page }) => {
        await page.goto('/');
        const breadcrumb = page.locator('#app-topbar-breadcrumb');
        const deployChip = page.locator('#global-deployment-chip');
        await expect(breadcrumb).toBeVisible({ timeout: 5000 });
        await expect(deployChip).toBeVisible();

        // The deployment chip's left edge MUST be to the right of the
        // breadcrumb's left edge — i.e., it sits on the right cluster.
        const breadcrumbBox = await breadcrumb.boundingBox();
        const deployBox = await deployChip.boundingBox();
        expect(deployBox.x).toBeGreaterThan(breadcrumbBox.x + breadcrumbBox.width / 2);
    });

    test('right cluster has selector → cost → operator → theme in DOM order', async ({ page }) => {
        await page.goto('/');
        // All 4 right-side controls must exist with their canonical IDs
        // (preserve every existing data binding per agent A constraint).
        await expect(page.locator('#global-deployment-chip')).toBeVisible({ timeout: 5000 });
        await expect(page.locator('#global-cost-chip')).toBeVisible();
        await expect(page.locator('#operator-chip')).toBeVisible();
        await expect(page.locator('#global-theme-toggle')).toBeVisible();

        // DOM ordering check inside .app-topbar__right.
        const order = await page.evaluate(() => {
            const right = document.querySelector('.app-topbar__right');
            if (!right) return [];
            const ids = ['global-deployment-chip', 'global-cost-chip', 'operator-chip', 'global-theme-toggle'];
            return ids.map((id) => {
                const el = right.querySelector(`#${id}`);
                if (!el) return -1;
                // Index among children of .app-topbar__right.
                return Array.prototype.indexOf.call(right.children, el);
            });
        });
        // Each subsequent control should appear after the previous one
        // in the right cluster's child list.
        for (let i = 1; i < order.length; i++) {
            expect(order[i]).toBeGreaterThan(order[i - 1]);
        }
    });

    test('breadcrumb updates as the operator navigates', async ({ page }) => {
        await page.goto('/');
        await page.locator('.app-rail__item[data-rail-target="dashboard"]').waitFor({ timeout: 5000 });
        await expect(page.locator('#app-topbar-crumb-page')).toContainText('Dashboard');

        // Navigate to Deployments. 2026-05-19 (deployments nav restructure)
        // — default sub-pill is mode-aware (manage on empty, configure on
        // draft). Breadcrumb shows whichever lands.
        await page.locator('.app-rail__item[data-rail-target="deployments-tab"]').click();
        await expect(page.locator('#app-topbar-crumb-page')).toContainText('Deployments', { timeout: 5000 });
        await expect(page.locator('#app-topbar-crumb-page')).toContainText(/Configure|Manage/, { timeout: 5000 });
    });
});

// ─────────────────────────────────────────────────────────────────────
// 3. ACTIVE STATE + NAV BEHAVIOR
// ─────────────────────────────────────────────────────────────────────

test.describe('v3 shell — rail navigation', () => {
    test('clicking Deployments expands its sub-pill children', async ({ page }) => {
        await page.goto('/');
        const deployGroup = page.locator('.app-rail__group[data-rail-group="deployments-tab"]');
        const children = deployGroup.locator('.app-rail__children');

        // Initially collapsed (not is-open).
        await expect(children).not.toHaveClass(/is-open/);

        await page.locator('.app-rail__item[data-rail-target="deployments-tab"]').click();

        // After click, the group expands.
        await expect(children).toHaveClass(/is-open/, { timeout: 5000 });

        // All 5 sub-pills are present after Agent D's bolt-ons mount.
        const subItems = deployGroup.locator('.app-rail__child');
        await expect(subItems).toHaveCount(5);
        const subLabels = await subItems.evaluateAll((els) =>
            els.map((el) => el.textContent?.trim())
        );
        expect(subLabels).toEqual(['Configure', 'Deploy', 'Manage', 'Cleanup', 'Bolt-ons']);
    });

    test('active state moves between rail items as you click them', async ({ page }) => {
        await page.goto('/');
        // Dashboard is the default active item.
        await expect(
            page.locator('.app-rail__item[data-rail-target="dashboard"]')
        ).toHaveClass(/is-active/, { timeout: 5000 });

        // Click Settings → active state moves there.
        await page.locator('.app-rail__item[data-rail-target="settings"]').click();
        await expect(
            page.locator('.app-rail__item[data-rail-target="settings"]')
        ).toHaveClass(/is-active/, { timeout: 5000 });
        await expect(
            page.locator('.app-rail__item[data-rail-target="dashboard"]')
        ).not.toHaveClass(/is-active/);

        // Click Operations → active state moves again.
        await page.locator('.app-rail__item[data-rail-target="operations-tab"]').click();
        await expect(
            page.locator('.app-rail__item[data-rail-target="operations-tab"]')
        ).toHaveClass(/is-active/, { timeout: 5000 });
        await expect(
            page.locator('.app-rail__item[data-rail-target="settings"]')
        ).not.toHaveClass(/is-active/);
    });

    test('clicking a sub-pill child navigates + activates that child', async ({ page }) => {
        // 2026-05-20: Operations rail group is now hidden when the active
        // deployment has no C2 component (goad-* / draft / empty). Stub
        // /api/deploy/active to return a C2 deployment so the Operations
        // sub-pill children stay reachable for this navigation test.
        await page.route('**/api/deploy/active', async (route) => {
            await route.fulfill({
                status: 200, contentType: 'application/json',
                body: JSON.stringify({ success: true, deployments: [
                    { project_name: 'c2_test_fixture', _filename: 'c2_test_fixture', deployment_type: 'c2-adhoc', status: 'success' },
                ]}),
            });
        });
        await page.goto('/');
        // Wait for the rail to settle on the C2 deployment so Operations is
        // visible before exercising the click path.
        await page.waitForFunction(() => {
            try {
                return APP.activeDeployment.current === 'c2_test_fixture'
                    && APP.computeOperationsVisible(APP.activeDeployment);
            } catch (_) { return false; }
        }, null, { timeout: 5000 });
        // Open the Operations group, then click its Terminal sub-pill.
        await page.locator('.app-rail__item[data-rail-target="operations-tab"]').click();
        // 2026-05-20: rail children use a grid-template-rows transition
        // (~280ms motion-duration-base). Wait for the is-open class so the
        // child target is stable before clicking, otherwise the still-
        // animating nav intercepts the pointer.
        await expect(
            page.locator('.app-rail__group[data-rail-group="operations-tab"] .app-rail__children')
        ).toHaveClass(/is-open/, { timeout: 5000 });
        await page.waitForTimeout(320);
        await page.locator(
            '.app-rail__child[data-rail-target="operations-tab"][data-rail-subpill="terminal"]'
        ).click();

        // The child gets the is-active class.
        await expect(
            page.locator(
                '.app-rail__child[data-rail-target="operations-tab"][data-rail-subpill="terminal"]'
            )
        ).toHaveClass(/is-active/, { timeout: 5000 });

        // The Operations tab page is the visible one (Phase 3 sub-pill machinery
        // still fires unchanged).
        await expect(
            page.locator('.tab-page[data-page="operations-tab"] .subpill-nav__pill[data-subpill="terminal"].is-active')
        ).toHaveCount(1, { timeout: 5000 });
    });
});

// ─────────────────────────────────────────────────────────────────────
// 4. D6 BOOKMARKABLE URL HASH STILL WORKS
// ─────────────────────────────────────────────────────────────────────

test.describe('v3 shell — D6 regression', () => {
    test('hash deep-link sets the active rail item + sub-pill on load', async ({ page }) => {
        // 2026-05-20: applyFromState({snap: true}) now redirects
        // operations-tab → deployments-tab/manage when no C2 deployment is
        // active. Stub the dropdown payload with a C2 deployment so the
        // initial navigateTo('operations-tab', 'beacons') sticks.
        await page.route('**/api/deploy/active', async (route) => {
            await route.fulfill({
                status: 200, contentType: 'application/json',
                body: JSON.stringify({ success: true, deployments: [
                    { project_name: 'c2_test_fixture', _filename: 'c2_test_fixture', deployment_type: 'c2-adhoc', status: 'success' },
                ]}),
            });
        });
        await page.goto('/#operations-tab/beacons');
        // Let the async deployment fetch resolve before asserting (otherwise
        // applyFromState may snap operations → deployments/manage mid-wait).
        await page.waitForFunction(() => {
            try { return APP.computeOperationsVisible(APP.activeDeployment); }
            catch (_) { return false; }
        }, null, { timeout: 5000 });

        // Operations rail item active.
        await expect(
            page.locator('.app-rail__item[data-rail-target="operations-tab"]')
        ).toHaveClass(/is-active/, { timeout: 5000 });

        // Beacons rail child active.
        await expect(
            page.locator('.app-rail__child[data-rail-subpill="beacons"]')
        ).toHaveClass(/is-active/, { timeout: 5000 });
    });

    test('URL hash updates when navigating via the rail', async ({ page }) => {
        await page.goto('/');
        await page.locator('.app-rail__item[data-rail-target="dashboard"]').waitFor({ timeout: 5000 });
        await page.locator('.app-rail__item[data-rail-target="deployments-tab"]').click();

        // 2026-05-19 (deployments nav restructure) — Default sub-pill on
        // first entry to Deployments is mode-aware (manage on empty,
        // manage on existing, configure on draft). Accept any sub-pill.
        const hash = await page.evaluate(() => window.location.hash);
        expect(hash).toMatch(/^#deployments-tab\/(manage|configure|deploy|cleanup|bolt-ons)$/);
    });
});

// ─────────────────────────────────────────────────────────────────────
// 5. LAYER-AWARE CONTRAST — both themes pass on shell chrome
// ─────────────────────────────────────────────────────────────────────

const SHELL_CONTRAST_TARGETS = [
    '.app-topbar__crumb.is-current',
    '.app-rail__brand-name',
    '.app-rail__brand-kicker',
    '.app-rail__item.is-active .app-rail__label',
    '.app-rail__item:not(.is-active) .app-rail__label',
    '.app-rail__footer-version',
];

async function auditShellContrast(page, theme) {
    await setTheme(page, theme);
    await page.locator('.app-shell').waitFor({ timeout: 5000 });
    // Ensure Deployments group is expanded so child labels are renderable.
    await page.locator('.app-rail__item[data-rail-target="deployments-tab"]').click();
    await page.waitForTimeout(280);

    const failures = [];
    for (const sel of SHELL_CONTRAST_TARGETS) {
        const els = page.locator(sel);
        const count = await els.count();
        if (count === 0) continue;
        for (let i = 0; i < count; i++) {
            const el = els.nth(i);
            // Skip nodes that are display:none / offscreen.
            const visible = await el.isVisible().catch(() => false);
            if (!visible) continue;

            const { fg, bg } = await el.evaluate((node, walker) => {
                // eslint-disable-next-line no-new-func
                const walkFn = new Function('return ' + walker)();
                const cs = window.getComputedStyle(node);
                return { fg: cs.color, bg: walkFn(node) };
            }, WALK_TO_SURFACE_FN.toString());

            const fgRgb = parseRgb(fg);
            const bgRgb = parseRgb(bg);
            if (!fgRgb || !bgRgb) continue;
            const r = ratio(fgRgb, bgRgb);
            // 4.5:1 for body text (eyebrow labels, primary nav items all count).
            if (r < 4.5) {
                failures.push({ selector: sel, theme, ratio: r.toFixed(2), fg, bg });
            }
        }
    }
    return failures;
}

test.describe('v3 shell — layer-aware contrast', () => {
    test('dark theme: zero contrast failures on shell chrome', async ({ page }) => {
        await page.goto('/');
        const failures = await auditShellContrast(page, 'dark');
        expect(failures, `dark-theme contrast failures:\n${JSON.stringify(failures, null, 2)}`)
            .toEqual([]);
    });

    test('light theme: zero contrast failures on shell chrome', async ({ page }) => {
        await page.goto('/');
        const failures = await auditShellContrast(page, 'light');
        expect(failures, `light-theme contrast failures:\n${JSON.stringify(failures, null, 2)}`)
            .toEqual([]);
    });
});
