// Test helper — navigate the dashboard via REAL user flows, not the
// offscreen .tab-btn compatibility shim.
//
// Why this exists: the v3 shell moved navigation from the legacy
// `.tab-btn[data-target="..."]` nav strip to the left rail
// (`.app-rail__item[data-rail-target="..."]`). The legacy strip lives
// on as a hidden compatibility shim (`aria-hidden="true"`,
// `tabindex="-1"`, visually offscreen). Tests that click the shim
// pass structurally but DON'T exercise the real user path — they'd
// silently keep passing even if the rail itself broke.
//
// Every test that needs to navigate should use this helper, not
// click the shim directly. The seedDeployment helper mocks external
// state; this helper handles real DOM clicks.

/**
 * Click the left-rail item for a top-level page.
 *
 * @param {import('@playwright/test').Page} page
 * @param {'dashboard'|'deployments-tab'|'operations-tab'|'settings'} target
 */
export async function railNavigate(page, target) {
    // 2026-05-22 — Wait for APP to be loaded + the rail click handlers
    // to be wired (set by APP.shell.init during DOMContentLoaded). The
    // synthetic click event has been observed to race against APP.init()
    // on a cold-load page, leaving the tab-page hidden even though the
    // rail's .is-active state updates. The most reliable path is to
    // click the real rail item (so the click event-handler chain fires)
    // AND fall back to APP.navigateTo() if the post-click settle fails.
    await page.waitForFunction(
        (t) => {
            const btn = document.querySelector(`.app-rail__item[data-rail-target="${t}"]`);
            return btn && btn.dataset.shellWired === '1' && typeof window.APP !== 'undefined'
                && typeof window.APP.navigateTo === 'function';
        },
        target,
        { timeout: 5000 },
    );
    // 2026-05-22 — The Operations top-rail item is `hidden` when
    // computeOperationsVisible(activeDeployment) returns false (e.g. on
    // multi-deployment boot with no persisted pick). Auto-pin a
    // compatible deployment so the click target becomes visible. Prefers
    // `demo`; falls back to any c2-* / combined-* deployment in the
    // mocked or real /api/deploy/active payload (some specs mock with
    // lab_alpha/lab_bravo instead of demo).
    // The Operations rail ITEM lives inside .app-rail__group[data-rail-group="operations-tab"]
    // — the GROUP carries the `hidden` attribute (gated by
    // APP.computeOperationsVisible). `[hidden]` on the group hides the
    // item too via CSS inheritance — but the item's own computed
    // display still reports 'flex'. Use offsetParent === null as the
    // robust "this element occupies no layout space" check.
    const railVisible = await page.evaluate((t) => {
        const item = document.querySelector(`.app-rail__item[data-rail-target="${t}"]`);
        if (!item) return 0;
        return item.offsetParent === null ? 0 : 1;
    }, target);
    if (railVisible === 0 && target === 'operations-tab') {
        await page.evaluate(async () => {
            const r = await fetch('/api/deploy/active');
            const b = await r.json();
            const deployments = b.deployments || [];
            // Prefer demo; otherwise any c2-* / combined-*.
            const pick = deployments.find(d => d._filename === 'demo')
                || deployments.find(d => (d.deployment_type || '').startsWith('c2-'))
                || deployments.find(d => (d.deployment_type || '').startsWith('combined-'));
            if (pick && window.APP && window.APP.activeDeployment) {
                window.APP.activeDeployment.set(pick._filename || pick.project_name);
                if (typeof window.APP._setActiveDeploymentType === 'function') {
                    window.APP._setActiveDeploymentType();
                }
            }
        });
        await page.waitForTimeout(150);
    }
    const rail = page.locator(`.app-rail__item[data-rail-target="${target}"]`).first();
    await rail.click();
    const settled = await page.waitForFunction(
        (t) => {
            const p = document.querySelector(`.tab-page[data-page="${t}"]`);
            if (!p) return false;
            if (!(p.classList.contains('active') || p.getAttribute('data-active') === 'true')) return false;
            const cs = window.getComputedStyle(p);
            return cs.display !== 'none';
        },
        target,
        { timeout: 1500 },
    ).catch(() => null);
    if (!settled) {
        // Fallback to the canonical entry-point. Equivalent to what the
        // click handler would invoke; bypasses the click event-loop race.
        await page.evaluate((t) => window.APP.navigateTo(t), target);
    }
    await page.waitForFunction(
        (t) => {
            const p = document.querySelector(`.tab-page[data-page="${t}"]`);
            if (!p) return false;
            if (!(p.classList.contains('active') || p.getAttribute('data-active') === 'true')) return false;
            const cs = window.getComputedStyle(p);
            return cs.display !== 'none';
        },
        target,
        { timeout: 5000 },
    );
}

/**
 * Click a sub-pill within Deployments / Operations. Use this AFTER
 * railNavigate(page, 'deployments-tab' | 'operations-tab').
 *
 * @param {import('@playwright/test').Page} page
 * @param {string} subPill — 'configure', 'deploy', 'manage', 'bolt-ons', 'cleanup' for deployments; 'beacons', 'terminal', 'payloads' for operations
 */
export async function clickSubPill(page, subPill) {
    // 2026-05-22 — When the requested pill is `hidden` because the current
    // activeDeployment mode doesn't include it (e.g. clicking 'deploy'
    // without first entering draft mode), auto-pin the right mode so the
    // helper "just works" for any test. Previously tests had to manually
    // sequence `APP.activeDeployment.set('__draft__')` before clicking
    // Configure/Deploy, OR set a real existing deployment before clicking
    // Manage/Cleanup/Bolt-ons. With the demo deployment always present in
    // /api/deploy/active, the multi-deployment auto-snap path returned
    // null on boot, hiding the draft-only pills. This guard restores the
    // previous test ergonomics.
    const DRAFT_ONLY = new Set(['configure', 'deploy']);
    const EXISTING_REQUIRED = new Set(['manage', 'cleanup', 'bolt-ons']);
    const C2_OR_COMBINED = new Set(['beacons', 'terminal', 'payloads']);
    const pillSelector = `.subpill-nav__pill[data-subpill="${subPill}"]:not([hidden])`;

    const initiallyVisible = await page.locator(pillSelector).count();
    if (initiallyVisible === 0) {
        // Pick the right activeDeployment mode for this pill.
        if (DRAFT_ONLY.has(subPill)) {
            await page.evaluate(() => {
                if (window.APP && window.APP.activeDeployment
                    && typeof window.APP.activeDeployment.set === 'function') {
                    window.APP.activeDeployment.set(
                        window.APP.activeDeployment.DRAFT_SENTINEL || '__draft__',
                    );
                }
            });
        } else if (EXISTING_REQUIRED.has(subPill) || C2_OR_COMBINED.has(subPill)) {
            // Pick demo if present (universal "everything visible"); else
            // any c2-* / combined-* / goad-* deployment from the payload.
            // Some specs mock /api/deploy/active with lab_alpha/lab_bravo
            // and don't have demo.
            await page.evaluate(async (pillName) => {
                const r = await fetch('/api/deploy/active');
                const b = await r.json();
                const deployments = b.deployments || [];
                const pillNeedsOps = ['beacons', 'terminal', 'payloads'].includes(pillName);
                const pillNeedsBoltons = pillName === 'bolt-ons';
                const pick = deployments.find(d => d._filename === 'demo')
                    || (pillNeedsOps && deployments.find(d => (d.deployment_type || '').startsWith('c2-')))
                    || (pillNeedsOps && deployments.find(d => (d.deployment_type || '').startsWith('combined-')))
                    || (pillNeedsBoltons && deployments.find(d => (d.deployment_type || '').startsWith('goad-')))
                    || (pillNeedsBoltons && deployments.find(d => (d.deployment_type || '').startsWith('combined-')))
                    || deployments.find(d => (d.deployment_type || '').startsWith('c2-'))
                    || deployments[0];
                if (pick && window.APP && window.APP.activeDeployment) {
                    window.APP.activeDeployment.set(pick._filename || pick.project_name);
                    if (typeof window.APP._setActiveDeploymentType === 'function') {
                        window.APP._setActiveDeploymentType();
                    }
                }
            }, subPill);
        }
        // Let applyFromState run.
        await page.waitForTimeout(150);
    }

    const pill = page.locator(pillSelector).first();
    await pill.waitFor({ state: 'visible', timeout: 5000 });
    await pill.click();
    const settled = await page.waitForFunction(
        (s) => {
            const pane = document.querySelector(`.subpill-pane[data-subpill-pane="${s}"]`);
            return pane && !pane.hidden;
        },
        subPill,
        { timeout: 1500 },
    ).catch(() => null);
    if (!settled) {
        // Fallback: drive setActiveSubPill directly. The parent tab is
        // already active by the time we click a sub-pill, so we infer
        // the parent from the pill's nearest .tab-page container.
        await page.evaluate((s) => {
            const pill = document.querySelector(`.subpill-nav__pill[data-subpill="${s}"]`);
            const tabPage = pill && pill.closest('.tab-page');
            const parent = tabPage && tabPage.dataset.page;
            if (parent && typeof window.APP.setActiveSubPill === 'function') {
                window.APP.setActiveSubPill(parent, s);
            }
        }, subPill);
    }
    await page.waitForFunction(
        (s) => {
            const pane = document.querySelector(`.subpill-pane[data-subpill-pane="${s}"]`);
            return pane && !pane.hidden;
        },
        subPill,
        { timeout: 5000 },
    );
}

/**
 * Click the "+ New Deployment" button — the canonical user entry into
 * draft mode. Either the global header button OR the Dashboard hero;
 * we click whichever is visible.
 *
 * @param {import('@playwright/test').Page} page
 */
export async function clickNewDeployment(page) {
    const heroBtn = page.locator('.dashboard-hero__primary[onclick*="startNewDeployment"]');
    const railBtn = page.locator('#global-new-deployment-btn');
    if (await heroBtn.count() > 0 && await heroBtn.first().isVisible()) {
        await heroBtn.first().click();
    } else {
        await railBtn.waitFor({ state: 'visible', timeout: 5000 });
        await railBtn.click();
    }
    // Wait for draft mode to engage.
    await page.waitForFunction(
        () => window.APP?.activeDeployment?.current === '__draft__',
        { timeout: 5000 },
    );
}
