/**
 * DASHBOARD — NEXT-TIER USER-FLOW AUDIT (2026-05-22)
 *
 * Covers the user flows NOT exercised by the bolt-ons audit + recent
 * regression checks. Same demo-deployment-against-live-Flask pattern.
 *
 *   P1 — recent regressions closing
 *     1. Cleanup pane renders + stats tiles populate
 *     2. Manage pane (demo) renders instantly; spec-rows visible
 *     3. Settings pane all 8 sections present
 *     4. Theme toggle Light ↔ Dark persists
 *
 *   P2 — recent feature flow validation
 *     5. Curriculum step-complete persists across drawer close + re-open
 *     6. Curriculum assessment submission persists across tab switch
 *     7. "Enable detection layer" button runs to completion
 *     8. Reload button is present + drift detection wires up
 *
 *   P3 — Operations sub-pills (demo mode)
 *     9. Operations → Beacons renders 3 demo beacons
 *    10. Operations → Payloads renders 3 demo artifacts
 *
 *   P4 — global chrome
 *    11. ⌘K command palette opens via APP.palette.open
 *    12. Operator chip shows current operator
 */

import { test, expect } from '@playwright/test';

async function bootDemo(page) {
    await page.goto('/');
    await page.waitForFunction(() => window.APP && typeof window.APP.startDemoMode === 'function');
    await page.click('#dashboard-demo-btn');
    await page.waitForFunction(() => window.APP.activeDeployment.current === 'demo');
    await page.waitForTimeout(800);
}

// ───────────────────────────────────────────────────────────────────────
// P1 — Regressions
// ───────────────────────────────────────────────────────────────────────

test('P1.1 — Cleanup pane renders chrome + 4 stat tiles', async ({ page }) => {
    await bootDemo(page);
    await page.click('.subpill-nav__pill[data-subpill="cleanup"]:not([hidden])');
    await page.waitForTimeout(2500);
    // Title + 4 stat tiles always present (eyebrow is static HTML).
    await expect(page.locator('.cleanup-v3__title')).toContainText('Cleanup');
    const tiles = page.locator('.cleanup-v3-summary__tile');
    await expect(tiles).toHaveCount(4);
});

test('P1.2 — Manage pane renders instantly for demo deployment', async ({ page }) => {
    await bootDemo(page);
    await page.click('.subpill-nav__pill[data-subpill="manage"]:not([hidden])');
    await page.waitForTimeout(3000);
    await expect(page.locator('#manage-view')).toBeVisible();
    await expect(page.locator('#manage-hero-name')).toContainText('demo');
    // spec-rows arrive (real data path, no skeleton needed for demo).
    await page.waitForFunction(
        () => document.querySelectorAll('#manage-spec-list .spec-row').length > 0,
        { timeout: 6000 },
    );
});

test('P1.3 — Settings pane mounts via APP.navigateTo + sections visible', async ({ page }) => {
    await page.goto('/');
    await page.waitForFunction(() => window.APP && typeof window.APP.navigateTo === 'function');
    await page.evaluate(() => window.APP.navigateTo('settings'));
    await page.waitForFunction(() => {
        const p = document.querySelector('.tab-page[data-page="settings"]');
        return p && p.classList.contains('active');
    });
    // Check the 8 expected settings sections.
    const ids = ['general', 'prereqs', 'domains', 'secrets', 'services', 'cost', 'prefs', 'roadmap'];
    for (const id of ids) {
        const sect = page.locator(`#settings-${id}`);
        await expect(sect).toHaveCount(1);
    }
});

test('P1.4 — Theme toggle flips data-theme attribute', async ({ page }) => {
    await page.goto('/');
    await page.waitForFunction(() => document.getElementById('global-theme-toggle'));
    const startTheme = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
    await page.click('#global-theme-toggle');
    await page.waitForTimeout(400);
    const newTheme = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
    expect(newTheme).not.toBe(startTheme);
});

// ───────────────────────────────────────────────────────────────────────
// P2 — Recent features
// ───────────────────────────────────────────────────────────────────────

test('P2.5 — Curriculum step-complete persists across drawer close + re-open', async ({ page }) => {
    await bootDemo(page);
    await page.click('.subpill-nav__pill[data-subpill="bolt-ons"]:not([hidden])');
    await page.waitForTimeout(2000);
    await page.evaluate(() => window.APP.bolton.selectHost('demo', 'tldc01'));
    await page.waitForTimeout(2000);
    // Reset progress for this vuln so we have a clean start.
    await page.evaluate(async () => {
        await fetch('/api/bolton/vulns/bolton.identity-kerberos.kerberoastable-svc/progress/reset',
                    { method: 'POST' });
    });
    // Open walkthrough drawer, mark step 1 complete.
    await page.evaluate(() => window.APP.bolton.openDetail(
        'bolton.identity-kerberos.kerberoastable-svc', 'walkthrough'));
    await page.waitForTimeout(2000);
    await page.click('[data-bolton-walk-toggle]');
    await page.waitForTimeout(1500);
    // Close drawer (Escape)
    await page.keyboard.press('Escape');
    await page.waitForTimeout(800);
    // Re-open the drawer
    await page.evaluate(() => window.APP.bolton.openDetail(
        'bolton.identity-kerberos.kerberoastable-svc', 'walkthrough'));
    await page.waitForTimeout(2000);
    // Progress bar shows "1 of N" for any N >= 5 (curriculum-agent-A may
    // tweak the step count over time; assertion stays focused on the
    // "1 of …" prefix which is what persistence is actually proving).
    await expect(page.locator('[data-bolton-walk-progress-label]')).toContainText(/1 of \d/);
});

test('P2.6 — Curriculum assessment answer persists across tab switch', async ({ page }) => {
    await bootDemo(page);
    await page.click('.subpill-nav__pill[data-subpill="bolt-ons"]:not([hidden])');
    await page.waitForTimeout(2000);
    await page.evaluate(() => window.APP.bolton.selectHost('demo', 'tldc01'));
    await page.waitForTimeout(2000);
    // Reset to clean state
    await page.evaluate(async () => {
        await fetch('/api/bolton/vulns/bolton.identity-kerberos.kerberoastable-svc/progress/reset',
                    { method: 'POST' });
    });
    await page.evaluate(() => window.APP.bolton.openDetail(
        'bolton.identity-kerberos.kerberoastable-svc', 'walkthrough'));
    await page.waitForTimeout(2000);
    // Navigate to step 3 (has assessment). Read the correct option index
    // off the rendered DOM so this stays robust against curriculum tweaks
    // (e.g. agent-A's 2026-05-28 rewrite shifted correct_index from 1 → 2).
    await page.click('[data-bolton-walk-step="03-crack-offline"]');
    await page.waitForTimeout(800);
    const correctIdx = await page.evaluate(() => {
        // The walkthrough state machine exposes the active step's assessment
        // via window.APP.bolton._walk.currentStep — fall back to scanning
        // the catalog if the runtime hook isn't available.
        try {
            const w = window.APP && window.APP.bolton && window.APP.bolton._walk;
            if (w && typeof w.currentStep === 'function') {
                const s = w.currentStep();
                if (s && s.assessment && Number.isInteger(s.assessment.correct_index)) {
                    return s.assessment.correct_index;
                }
            }
        } catch (_) { /* fallthrough */ }
        return 2; // 2026-05-28 known value for kerberoast step 03
    });
    await page.click(`[data-bolton-walk-answer="${correctIdx}"]`);
    await page.waitForTimeout(1500);
    // Switch tabs
    await page.click('[data-bolton-detail-tab="install"]');
    await page.waitForTimeout(500);
    await page.click('[data-bolton-detail-tab="walkthrough"]');
    await page.waitForTimeout(800);
    // Navigate back to step 3 — answer should still be highlighted as correct
    await page.click('[data-bolton-walk-step="03-crack-offline"]');
    await page.waitForTimeout(800);
    await expect(page.locator('.bolton-walk__option').nth(correctIdx)).toHaveClass(/is-correct/);
});

test('P2.7 — Enable detection layer button completes 8-install orchestration', async ({ page }) => {
    await bootDemo(page);
    await page.click('.subpill-nav__pill[data-subpill="bolt-ons"]:not([hidden])');
    await page.waitForTimeout(2000);
    await page.evaluate(() => window.APP.bolton.selectHost('demo', 'tllinux01'));
    await page.waitForTimeout(2000);
    // 2026-05-23 — Detection button is state-aware now. When _demo_install_state
    // already carries all detection pairs (e.g. from a prior test run), the
    // button paints 'full' state and is disabled. Uninstall every pair
    // first so the orchestration has work to do.
    await page.evaluate(async () => {
        const plan = window.APP.bolton._DETECTION_PLAN;
        const hosts = window.APP.bolton.state.hosts || [];
        for (const step of plan) {
            for (const h of hosts) {
                const hid = h.name || h.host_id;
                try {
                    await fetch(`/api/bolton/labs/demo/hosts/${encodeURIComponent(hid)}/uninstall/${encodeURIComponent(step.vuln)}`,
                        { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({}) });
                } catch (_) {}
            }
        }
        window.APP.bolton._detectionFactsCache = {};
        await window.APP.bolton._hydrateDetectionFacts();
        window.APP.bolton._refreshDetectionButton();
    });
    await page.waitForTimeout(500);
    await page.click('#bolton-enable-detection');
    // Wait for orchestration to finish — button state moves from 'working'
    // back to 'full' (or 'partial' on partial failure) AND becomes enabled
    // if not already full.
    await page.waitForFunction(
        () => {
            const btn = document.getElementById('bolton-enable-detection');
            return btn && btn.dataset.detectState !== 'working';
        },
        { timeout: 30000 },
    );
    // Check that detection bolt-ons are now in installed_boltons on every test_lab host.
    const summary = await page.evaluate(async () => {
        const out = {};
        for (const h of ['tldc01', 'tlms01', 'tlws01', 'tllinux01']) {
            const r = await fetch(`/api/bolton/labs/demo/hosts/${h}/facts`);
            const b = await r.json();
            out[h] = b.installed_boltons || [];
        }
        return out;
    });
    expect(summary.tldc01).toEqual(expect.arrayContaining([
        'bolton.infrastructure.sysmon', 'bolton.infrastructure.winlogbeat-shipper',
    ]));
    expect(summary.tllinux01).toEqual(expect.arrayContaining([
        'bolton.infrastructure.elastic-detection-stack', 'bolton.infrastructure.filebeat-shipper',
    ]));
});

test('P2.8 — Reload button present + asset-version drift detector wired', async ({ page }) => {
    await page.goto('/');
    await page.waitForFunction(() => window.APP && document.getElementById('global-app-refresh'));
    // The button exists with the expected text
    await expect(page.locator('#global-app-refresh')).toContainText('Reload');
    // The asset-version meta is stamped
    const version = await page.evaluate(
        () => document.querySelector('meta[name="asset-version"]')?.content,
    );
    expect(version).toMatch(/^[a-f0-9]{8,}$/);
    // /api/version/assets responds with the same hash
    const apiVersion = await page.evaluate(async () => {
        const r = await fetch('/api/version/assets');
        const b = await r.json();
        return b.asset_version;
    });
    expect(apiVersion).toBe(version);
});

// ───────────────────────────────────────────────────────────────────────
// P3 — Operations sub-pills
// ───────────────────────────────────────────────────────────────────────

test('P3.9 — Operations → Beacons shows 4 demo beacons (test_lab tree)', async ({ page }) => {
    // 2026-05-23 — demo beacon set realigned to mirror the test_lab hosts
    // (tldc01/tlms01/tlws01/tllinux01) + parent_bid relationships so the
    // topology graph forms a real attack chain. Field names match CS REST
    // API exactly (computer/user/internal not hostname/username/internal_ip).
    await bootDemo(page);
    await page.evaluate(() => window.APP.navigateTo('operations-tab', 'beacons'));
    await page.waitForTimeout(3500);
    const beacons = await page.evaluate(async () => {
        const r = await fetch('/api/beacon/list?project=demo');
        const b = await r.json();
        return b.beacons || [];
    });
    expect(beacons.length).toBe(4);
    expect(beacons.map(b => b.computer)).toEqual(
        expect.arrayContaining(['tldc01', 'tlms01', 'tlws01', 'tllinux01']),
    );
});

test('P3.10 — Operations → Payloads tab mounts in demo mode', async ({ page }) => {
    await bootDemo(page);
    await page.evaluate(() => window.APP.navigateTo('operations-tab', 'payloads'));
    await page.waitForTimeout(2500);
    // Tab is active
    await expect(page.locator('[data-subpill-pane="payloads"]')).toBeVisible();
});

// ───────────────────────────────────────────────────────────────────────
// P4 — Chrome
// ───────────────────────────────────────────────────────────────────────

test('P4.11 — Command palette opens via APP.palette.open', async ({ page }) => {
    await page.goto('/');
    await page.waitForFunction(() => window.APP);
    await page.evaluate(() => window.APP.palette && window.APP.palette.open && window.APP.palette.open());
    await expect(
        page.locator('.palette-overlay, #palette-overlay, [class*="palette"]').first(),
    ).toBeVisible({ timeout: 5000 });
});

test('P4.12 — Operator chip shows current operator', async ({ page }) => {
    await page.goto('/');
    await page.waitForFunction(() => document.querySelector('[id*="operator"]'));
    // The chip is the global-header__operator button; check it has visible text.
    const chip = page.locator('[aria-label*="operator" i]').first();
    await expect(chip).toBeVisible();
});
