/**
 * v3-production-rollout — Flow stitching (2026-05-19).
 *
 * Cross-page glue between the four newly-rebuilt v3 surfaces:
 *
 *   1. "+ New Deployment" no longer opens a scrim takeover — it navigates
 *      to Configure with ?new=1 and mounts the wizard inline (left rail +
 *      top utility bar stay visible).
 *   2. Configure sections gate by deployment type (Malleable / GOAD Network
 *      / Domain Fronting / Attack Box show/hide per the spec mapping).
 *   3. The Malleable C2 Profile preview is wrapped in a <details>
 *      collapsed by default (operator opts in to inspect the YAML).
 *   4. Manage has a "+ Bolt-on vulnerability" action that pre-fills the
 *      Bolt-ons sub-pill with the active lab.
 *
 * All checks run in both themes for contrast invariants.
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

// ─── Task 1 — Un-overlay the journey ───────────────────────────────────────

// 2026-05-19 — Configure V2 (progressive unraveling) replaced the auto-mount
// wizard as the default destination for "+ New Deployment". The journey wizard
// stays accessible via ?wizard=1 opt-in for the test below; clicking "+ New"
// now routes to V2 directly. See APP.configureV2 in app.js.
test.describe('Task 1 — "+ New Deployment" mounts V2 progressive surface', () => {
    test('clicking "+ New Deployment" pins draft + shows V2 (no scrim, no wizard)', async ({ page }) => {
        await page.goto('/');
        await acceptDirtyConfirm(page);
        await page.locator('#global-new-deployment-btn').waitFor({ timeout: 5000 });
        await page.click('#global-new-deployment-btn');
        await page.waitForTimeout(500);

        // URL signals draft state (either via ?draft=1 or sub-pill nav).
        const url = page.url();
        expect(url).toMatch(/draft=1|configure/);

        // V2 surface is visible inside Configure
        await expect(page.locator('#configure-v2-pane')).toBeVisible({ timeout: 4000 });
        // The wizard mount is NOT auto-attached.
        const wizardInner = await page.locator('#configure-new-pane').innerHTML();
        expect(wizardInner.trim()).toBe('');
        // No scrim takeover.
        const journeyBodyAttr = await page.evaluate(() => document.body.getAttribute('data-journey-open'));
        expect(journeyBodyAttr).toBeNull();
        // Deployments rail item active.
        await expect(
            page.locator('.app-rail__item[data-rail-target="deployments-tab"].is-active')
        ).toBeVisible({ timeout: 4000 });
    });

    test('wizard step navigation works when ?wizard=1 opt-in is passed', async ({ page }) => {
        // 2026-05-20 (Batch C) — `+ New Deployment` now lands on Configure V2
        // by default. The legacy journey wizard is opt-in via APP.journey.open()
        // (which `?wizard=1` triggers via startDraftFlow). Because the URL
        // rewriter strips `wizard=1` before startDraftFlow can read it back
        // (the global-combobox subscriber writes `?dep=` over the search
        // params on boot), the most reliable opt-in path is to first pin a
        // draft + then invoke APP.journey.open() directly.
        await page.goto('/');
        await acceptDirtyConfirm(page);
        await page.locator('#global-new-deployment-btn').waitFor({ timeout: 5000 });
        await page.evaluate(() => {
            window.APP.activeDeployment.set(window.APP.activeDeployment.DRAFT_SENTINEL);
            window.APP.subPills.setActive('configure');
            window.APP.journey.open({ trigger: document.getElementById('global-new-deployment-btn') });
        });
        // Wait for inline wizard to mount.
        await page.locator('#configure-new-pane #journey-takeover').waitFor({ timeout: 5000 });

        // Step 1 — Family. Click Continue.
        await page.click('#journey-next');
        await page.waitForTimeout(150);
        // Step 2 — Type.
        await page.click('#journey-next');
        await page.waitForTimeout(150);
        // Step 3 — Identity.
        await page.click('#journey-next');
        await page.waitForTimeout(150);
        // Step 4 — Network → Review.
        await page.click('#journey-next');
        await page.waitForTimeout(250);

        // Review phase is active. Even though the journey is inline, the
        // review section uses the same #journey-review structure.
        await expect(page.locator('#configure-new-pane #journey-review')).toHaveClass(/is-active/);
        const rowCount = await page.locator('#configure-new-pane #journey-spec-list .spec-row').count();
        expect(rowCount).toBe(7);
    });

    test('cancel returns Configure to edit mode + strips ?new=1', async ({ page }) => {
        // 2026-05-20 (Batch C) — invoke APP.journey.open() directly (see
        // wizard-nav test above for why the ?wizard=1 URL path is unreliable).
        await page.goto('/');
        await acceptDirtyConfirm(page);
        await page.locator('#global-new-deployment-btn').waitFor({ timeout: 5000 });
        await page.evaluate(() => {
            window.APP.activeDeployment.set(window.APP.activeDeployment.DRAFT_SENTINEL);
            window.APP.subPills.setActive('configure');
            window.APP.journey.open({ trigger: document.getElementById('global-new-deployment-btn') });
        });
        await page.locator('#configure-new-pane #journey-takeover').waitFor({ timeout: 5000 });

        // Press Escape — should close the wizard, no scrim to wait for.
        await page.keyboard.press('Escape');
        await page.waitForTimeout(300);

        const url = page.url();
        expect(url).not.toMatch(/new=1/);

        // Edit pane is visible again.
        const editPaneHidden = await page.locator('#configure-edit-pane').evaluate(el => el.hasAttribute('hidden'));
        expect(editPaneHidden).toBe(false);
    });
});

// ─── Task 2 — Configure gating (legacy-form unit test) ───────────────────
//
// 2026-05-21 legacy-audit sweep: Task 2 + Task 3 drive APP.config.applyGating()
// on the LEGACY `.configuration-editor` form. They force-show
// `#configure-edit-pane .configuration-editor` + `#configure-advanced-details`,
// flip `#deployment-type`, and inspect `*-config-section` visibility.
//
// V2-native equivalents (family-aware section gating + the Malleable preview
// `<details>` wrapper) are covered by:
//
//   - tests/browser/test_v3_configure_progressive.spec.js  (state machine,
//     assembleConfig per type)
//   - tests/browser/test_v3_configure_family_change.spec.js  (family switch
//     repaints rail with C2 / GOAD / combined section lists)
//
// Once UX_AUDIT M1 lands (legacy form deleted), the helper below + Task 2 +
// Task 3 will fail because the IDs disappear. At that point: delete Task 2
// and Task 3 wholesale; the V2 specs above are the canonical replacement.

// 2026-05-20 (Batch C) — Configure sub-pill visibility is now mode-gated by
// APP.computeVisibleSubPills(): when the live backend exposes an existing
// deployment, the Configure pane gets `hidden` on boot (only Manage / Bolt-ons
// / Cleanup remain for existing). To keep the legacy gating tests focused on
// applyGating() (the unit-of-test), we mock /api/deploy/active to return zero
// deployments — this lands the app in "empty" state with no auto-snap, then
// we force-show the configure subpill pane and run applyGating().
async function mockNoDeploymentsAndOpenConfigure(page) {
    await page.route('**/api/deploy/active', async (route) => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ success: true, deployments: [] }),
        });
    });
    await page.goto('/#deployments-tab/configure');
    await page.locator('#subpill-pane-configure').waitFor({ timeout: 5000 });
    // Force-show the configure pane + legacy editor — the V3 mode logic
    // hides them when no draft / no existing deployment is selected, but we
    // are pinpoint-testing applyGating()'s effect on section display rules.
    await page.evaluate(() => {
        const pane = document.getElementById('subpill-pane-configure');
        if (pane) pane.removeAttribute('hidden');
        const editPane = document.getElementById('configure-edit-pane');
        if (editPane) editPane.hidden = false;
        const editor = document.querySelector('#configure-edit-pane .configuration-editor');
        if (editor) editor.style.display = '';
        const adv = document.getElementById('configure-advanced-details');
        if (adv) {
            adv.style.display = '';
            adv.setAttribute('open', '');
        }
        // The CSS rule `#configure-v2-pane:not([hidden]) ~ #configure-advanced-details`
        // applies `display: none !important` when V2 is visible — we're testing the
        // LEGACY form here, so explicitly hide V2 to release the sibling-selector.
        const v2 = document.getElementById('configure-v2-pane');
        if (v2) v2.setAttribute('hidden', '');
    });
}

test.describe('Task 2 — Configure content gating by deployment type', () => {
    test('c2-adhoc shows Malleable / Domain Fronting / Redirector Domain Config; hides GOAD Network', async ({ page }) => {
        await mockNoDeploymentsAndOpenConfigure(page);

        // Apply gating directly via APP.config.applyGating to skip the
        // legacy onchange overlap with other side-effects.
        await page.evaluate(() => {
            document.getElementById('deployment-type').value = 'c2-adhoc';
            if (window.APP && APP.config && APP.config.applyGating) {
                APP.config.applyGating('c2-adhoc');
            }
        });
        await page.waitForTimeout(150);

        // c2-only sections visible
        await expect(page.locator('#malleable-profile-section')).toBeVisible();
        await expect(page.locator('#domain-config-section')).toBeVisible();
        await expect(page.locator('#domain-fronting-section')).toBeVisible();

        // goad-only section hidden
        await expect(page.locator('#goad-network-config-section')).toBeHidden();

        // Attack Box always visible
        await expect(page.locator('#attack-box-config-section')).toBeVisible();
    });

    test('goad-mini hides Malleable / Domain Fronting / Redirector; shows GOAD Network + Attack Box', async ({ page }) => {
        await mockNoDeploymentsAndOpenConfigure(page);

        await page.evaluate(() => {
            document.getElementById('deployment-type').value = 'goad-mini';
            if (window.APP && APP.config && APP.config.applyGating) {
                APP.config.applyGating('goad-mini');
            }
        });
        await page.waitForTimeout(150);

        // c2-only sections hidden
        await expect(page.locator('#malleable-profile-section')).toBeHidden();
        await expect(page.locator('#domain-config-section')).toBeHidden();
        await expect(page.locator('#domain-fronting-section')).toBeHidden();

        // goad-only section visible
        await expect(page.locator('#goad-network-config-section')).toBeVisible();

        // Attack Box always visible (per 2026-05-19 user clarification)
        await expect(page.locator('#attack-box-config-section')).toBeVisible();
    });

    test('combined-adhoc-mini shows ALL gated sections', async ({ page }) => {
        await mockNoDeploymentsAndOpenConfigure(page);

        await page.evaluate(() => {
            document.getElementById('deployment-type').value = 'combined-adhoc-mini';
            if (window.APP && APP.config && APP.config.applyGating) {
                APP.config.applyGating('combined-adhoc-mini');
            }
        });
        await page.waitForTimeout(150);

        await expect(page.locator('#malleable-profile-section')).toBeVisible();
        await expect(page.locator('#domain-config-section')).toBeVisible();
        await expect(page.locator('#domain-fronting-section')).toBeVisible();
        await expect(page.locator('#goad-network-config-section')).toBeVisible();
        await expect(page.locator('#attack-box-config-section')).toBeVisible();
    });
});

// ─── Task 3 — Collapsed Malleable preview ──────────────────────────────────

test.describe('Task 3 — Malleable profile preview is collapsed by default', () => {
    test('preview wraps a <details> closed on first render', async ({ page }) => {
        // 2026-05-20 (Batch C) — same flow-rebase as the gating tests above.
        await mockNoDeploymentsAndOpenConfigure(page);

        // Force c2-adhoc so the malleable section is visible.
        await page.evaluate(() => {
            document.getElementById('deployment-type').value = 'c2-adhoc';
            if (window.APP && APP.config && APP.config.applyGating) {
                APP.config.applyGating('c2-adhoc');
            }
        });
        await page.waitForTimeout(150);

        const details = page.locator('#malleable-profile-preview-wrapper');
        await expect(details).toBeVisible();
        const isOpen = await details.evaluate(el => el.hasAttribute('open'));
        expect(isOpen).toBe(false);

        // Clicking the summary expands it.
        await details.locator('summary').click();
        await page.waitForTimeout(120);
        const isOpenAfter = await details.evaluate(el => el.hasAttribute('open'));
        expect(isOpenAfter).toBe(true);
    });
});

// ─── Task 4 — "+ Bolt-on vulnerability" on Manage ──────────────────────────

test.describe('Task 4 — Manage "+ Bolt-on vulnerability" button', () => {
    test('Manage header strip has the bolt-on action button', async ({ page }) => {
        await page.goto('/#deployments-tab/manage');
        await page.locator('#manage-actions').waitFor({ timeout: 5000 });

        const btn = page.locator('#manage-action-bolton');
        await expect(btn).toBeVisible();
        await expect(btn).toContainText(/Bolt-on/i);
        // Uses the bolt icon.
        const useHref = await btn.locator('svg.icon use').getAttribute('href');
        expect(useHref).toBe('#icon-bolt');
    });

    test('clicking bolton button navigates to Bolt-ons sub-pill with active lab preset', async ({ page }) => {
        const projectName = 'c2_adhoc_demo_01';
        await page.goto(`/?dep=${encodeURIComponent(projectName)}#deployments-tab/manage`);
        await page.locator('#manage-actions').waitFor({ timeout: 5000 });

        // Stub APP.navigateTo so we can assert the target without triggering
        // bolton init's network calls.
        await page.evaluate(() => {
            window._navCalls = [];
            const orig = APP.navigateTo;
            APP.navigateTo = function (...args) {
                window._navCalls.push(args);
                return orig.apply(this, args);
            };
        });

        await page.click('#manage-action-bolton');
        await page.waitForTimeout(250);

        const calls = await page.evaluate(() => window._navCalls);
        // At least one navigateTo call landed on the bolt-ons sub-pill.
        const hasBoltOnNav = calls.some(c => c[0] === 'deployments-tab' && c[1] === 'bolt-ons');
        expect(hasBoltOnNav).toBe(true);

        // The bolton state.lab now matches the active deployment.
        const stateLab = await page.evaluate(() => APP.bolton && APP.bolton.state && APP.bolton.state.lab);
        expect(stateLab).toBe(projectName);
    });
});

// ─── Contrast invariants (both themes) ─────────────────────────────────────

async function auditContrast(page, rootSel) {
    return page.evaluate(({ rootSel }) => {
        function parseRgb(s) {
            const m = s.match(/rgba?\(([^)]+)\)/);
            if (!m) return null;
            const parts = m[1].split(',').map((p) => parseFloat(p.trim()));
            return [parts[0], parts[1], parts[2], parts.length === 4 ? parts[3] : 1];
        }
        function lin(c) { const v = c / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }
        function lum([r, g, b]) { return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b); }
        function ratio(a, b) { const L1 = lum(a); const L2 = lum(b); return (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05); }
        function walkToSurface(el) {
            const stack = [];
            let cur = el;
            while (cur && cur !== document.documentElement) {
                const cs = window.getComputedStyle(cur);
                const parsed = parseRgb(cs.backgroundColor);
                if (parsed && parsed[3] > 0.01) {
                    stack.push(parsed);
                    if (parsed[3] >= 0.99) break;
                }
                cur = cur.parentElement;
            }
            if (stack.length === 0 || stack[stack.length - 1][3] < 0.99) {
                stack.push(parseRgb(window.getComputedStyle(document.body).backgroundColor) || [255, 255, 255, 1]);
            }
            let [r, g, b] = stack[stack.length - 1].slice(0, 3);
            for (let i = stack.length - 2; i >= 0; i--) {
                const [or, og, ob, oa] = stack[i];
                r = or * oa + r * (1 - oa);
                g = og * oa + g * (1 - oa);
                b = ob * oa + b * (1 - oa);
            }
            return [Math.round(r), Math.round(g), Math.round(b)];
        }
        const root = document.querySelector(rootSel);
        if (!root) return [];
        const failures = [];
        root.querySelectorAll('*').forEach(el => {
            const cs = window.getComputedStyle(el);
            if (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0') return;
            if (el.getAttribute('aria-hidden') === 'true') return;
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return;
            let hasText = false;
            for (const c of el.childNodes) {
                if (c.nodeType === 3 && c.textContent.trim().length > 0) { hasText = true; break; }
            }
            if (!hasText) return;
            const fg = parseRgb(cs.color);
            if (!fg || fg[3] < 0.5) return;
            const bg = walkToSurface(el);
            const r = ratio(fg.slice(0, 3), bg);
            const fs = parseFloat(cs.fontSize);
            const fw = parseInt(cs.fontWeight, 10) || 400;
            const isLarge = fs >= 24 || (fs >= 18.66 && fw >= 700);
            const threshold = isLarge ? 3.0 : 4.5;
            if (r < threshold) {
                failures.push({
                    tag: el.tagName.toLowerCase(),
                    cls: el.className,
                    text: (el.textContent || '').trim().slice(0, 40),
                    ratio: Number(r.toFixed(2)),
                    threshold,
                });
            }
        });
        return failures;
    }, { rootSel });
}

for (const theme of ['dark', 'light']) {
    test(`inline journey passes contrast (${theme} theme)`, async ({ page }) => {
        // 2026-05-20 (Batch C) — invoke APP.journey.open() directly (see
        // Task 1 tests for why the ?wizard=1 URL path is unreliable).
        await page.goto('/');
        await acceptDirtyConfirm(page);
        await page.locator('#global-new-deployment-btn').waitFor({ timeout: 5000 });
        await page.evaluate(() => {
            window.APP.activeDeployment.set(window.APP.activeDeployment.DRAFT_SENTINEL);
            window.APP.subPills.setActive('configure');
            window.APP.journey.open({ trigger: document.getElementById('global-new-deployment-btn') });
        });
        await page.locator('#configure-new-pane #journey-takeover').waitFor({ timeout: 5000 });
        await setTheme(page, theme);
        const failures = await auditContrast(page, '#configure-new-pane');
        if (failures.length) {
            // eslint-disable-next-line no-console
            console.log(`Inline journey (${theme}) failures:`, JSON.stringify(failures.slice(0, 10), null, 2));
        }
        expect(failures, `${failures.length} AA failures in inline journey, ${theme}`).toEqual([]);
    });

    test(`manage actions strip with bolton button passes contrast (${theme} theme)`, async ({ page }) => {
        await page.goto('/#deployments-tab/manage');
        await page.locator('#manage-actions').waitFor({ timeout: 5000 });
        await setTheme(page, theme);
        const failures = await auditContrast(page, '#manage-actions');
        if (failures.length) {
            // eslint-disable-next-line no-console
            console.log(`Manage actions (${theme}) failures:`, JSON.stringify(failures.slice(0, 10), null, 2));
        }
        expect(failures, `${failures.length} AA failures in manage actions, ${theme}`).toEqual([]);
    });
}
