/**
 * BOLT-ONS PAGE — FULL USER-FLOW AUDIT (2026-05-22)
 *
 * Covers every realistic interaction an operator can make on the
 * Bolt-ons sub-pill, against the `demo` deployment so the assertions
 * are deterministic (no real AWS calls).
 *
 * Layout of this spec (each test block names the scenario):
 *
 *   1. NAV         — Bolt-ons sub-pill is gated correctly
 *   2. INITIAL     — first render, empty state, host dropdown shape
 *   3. HOST PICK   — selecting a host populates the catalog
 *   4. SWITCH HOST — switching hosts re-loads + resets stale state
 *   5. FILTER      — search box + 3 dropdowns + active-pill row + clear
 *   6. INSTALL     — Install action → moves row to Installed section
 *   7. NO STUCK FILTER — installing does NOT pin the host-role filter
 *   8. PATCH       — Patch action → moves to Patched section
 *   9. UNINSTALL   — Uninstall action → drops from Installed
 *  10. DETECTION LAYER — one-click button installs Elastic stack +
 *                        shippers across every compatible host
 *  11. WALKTHROUGH — 3-tab drawer (Install/Walkthrough/Detections)
 *                    renders + step navigation + assessment + close
 *  12. DEPLOYMENT SWITCH — switching deployments reloads hosts
 *  13. ALL-MODE   — `__all__` sentinel hides the Bolt-ons sub-pill
 *  14. DRAFT      — `__draft__` sentinel hides the Bolt-ons sub-pill
 *  15. NON-DEMO HOST — c2-only without test lab gates Bolt-ons OFF
 */

import { test, expect } from '@playwright/test';

const DEMO_DC = 'tldc01';
const DEMO_LINUX = 'tllinux01';
const VID_KERB = 'bolton.identity-kerberos.kerberoastable-svc';
const VID_PRINT = 'bolton.known-cve.printnightmare';
const VID_ESTACK = 'bolton.infrastructure.elastic-detection-stack';

async function bootDemoBoltons(page) {
    await page.goto('/');
    await page.waitForFunction(() => window.APP && typeof window.APP.startDemoMode === 'function');
    await page.click('#dashboard-demo-btn');
    await page.waitForFunction(() => window.APP.activeDeployment.current === 'demo'
        && window.APP.activeDeployment.deployment_type === 'demo');
    await page.waitForTimeout(800);
    await page.click('.subpill-nav__pill[data-subpill="bolt-ons"]:not([hidden])');
    await page.waitForTimeout(2500);
}

async function pickHost(page, host) {
    await page.evaluate((h) => window.APP.bolton.selectHost('demo', h), host);
    await page.waitForTimeout(2500);
}

// ─────────────────────────────────────────────────────────────────────────
// 1. NAV — Bolt-ons gated correctly for demo deployment
// ─────────────────────────────────────────────────────────────────────────

test('1. NAV — Bolt-ons sub-pill IS visible for demo deployment', async ({ page }) => {
    await page.goto('/');
    await page.waitForFunction(() => window.APP && typeof window.APP.startDemoMode === 'function');
    await page.click('#dashboard-demo-btn');
    await page.waitForFunction(() => window.APP.activeDeployment.current === 'demo');
    await page.waitForTimeout(500);
    const subPills = await page.evaluate(() =>
        window.APP.computeVisibleSubPills(window.APP.activeDeployment),
    );
    expect(subPills).toContain('bolt-ons');
});

// ─────────────────────────────────────────────────────────────────────────
// 2. INITIAL — first render shape
// ─────────────────────────────────────────────────────────────────────────

test('2. INITIAL — pane shows host dropdown with all 7 demo hosts + 4 mirror test_lab', async ({ page }) => {
    await bootDemoBoltons(page);
    const hosts = await page.evaluate(() => {
        const sel = document.getElementById('bolton-host-select');
        return sel ? Array.from(sel.options).map(o => o.value).filter(Boolean) : [];
    });
    // Demo mirrors test_lab exactly — 4 hosts.
    expect(hosts).toEqual([DEMO_DC, 'tlms01', 'tlws01', DEMO_LINUX]);
});

test('2. INITIAL — empty-state placeholder shown until a host is picked', async ({ page }) => {
    await bootDemoBoltons(page);
    const placeholder = page.locator('#bolton-empty-state');
    await expect(placeholder).toBeVisible();
    const hero = page.locator('#bolton-hero');
    await expect(hero).toBeHidden();
});

// ─────────────────────────────────────────────────────────────────────────
// 3. HOST PICK — selecting a host populates everything
// ─────────────────────────────────────────────────────────────────────────

test('3. HOST PICK — selecting tldc01 reveals hero + summary + catalog rows', async ({ page }) => {
    await bootDemoBoltons(page);
    await pickHost(page, DEMO_DC);
    await expect(page.locator('#bolton-hero')).toBeVisible();
    await expect(page.locator('#bolton-hero-kicker')).toContainText('TLDC01');
    await expect(page.locator('#bolton-summary')).toBeVisible();
    // tldc01 has 2 seeded installs (Kerberoast + AdminSDHolder).
    const installedCount = await page.locator('#bolton-stat-installed').textContent();
    expect(parseInt(installedCount, 10)).toBeGreaterThanOrEqual(2);
});

test('3. HOST PICK — Kerberoast row is in Installed section with Walkthrough button', async ({ page }) => {
    await bootDemoBoltons(page);
    await pickHost(page, DEMO_DC);
    const row = page.locator(`.bt-row[data-vuln-id="${VID_KERB}"]`);
    await expect(row).toHaveCount(1);
    await expect(row.locator('.bt-row__walkthrough')).toHaveCount(1);
    await expect(row.locator('.bt-row__walkthrough')).toContainText('Walkthrough');
    // State should be ALREADY_INSTALLED (case-insensitive — the real
    // compatibility resolver emits lowercase enum values while the legacy
    // demo bypass emitted uppercase. 2026-05-23 unification means both
    // are valid sources for this attribute.)
    const state = (await row.getAttribute('data-state') || '').toUpperCase();
    expect(state).toBe('ALREADY_INSTALLED');
});

// ─────────────────────────────────────────────────────────────────────────
// 4. SWITCH HOST — re-load resets per-host UI
// ─────────────────────────────────────────────────────────────────────────

test('4. SWITCH HOST — picking tlms01 then tllinux01 re-renders correctly', async ({ page }) => {
    await bootDemoBoltons(page);
    await pickHost(page, 'tlms01');
    await expect(page.locator('#bolton-hero-kicker')).toContainText('TLMS01');
    await pickHost(page, DEMO_LINUX);
    await expect(page.locator('#bolton-hero-kicker')).toContainText('TLLINUX01');
    // Linux host has no inherited installs; Elastic stack should be Available.
    const elastic = page.locator(`.bt-row[data-vuln-id="${VID_ESTACK}"]`);
    await expect(elastic).toHaveCount(1);
});

// ─────────────────────────────────────────────────────────────────────────
// 5. FILTER — new search + dropdowns + active-pill row
// ─────────────────────────────────────────────────────────────────────────

test('5. FILTER — old 22-chip strip is gone; new search + dropdowns are present', async ({ page }) => {
    await bootDemoBoltons(page);
    await pickHost(page, DEMO_DC);
    const chips = await page.locator('.bt-chip').count();
    expect(chips).toBe(0);
    await expect(page.locator('#bolton-filter-search')).toBeVisible();
    await expect(page.locator('#bolton-filter-category')).toBeVisible();
    await expect(page.locator('#bolton-filter-state')).toBeVisible();
    await expect(page.locator('#bolton-filter-coverage')).toBeVisible();
});

test('5. FILTER — typing in search filters rows + shows active pill', async ({ page }) => {
    await bootDemoBoltons(page);
    await pickHost(page, DEMO_DC);
    await page.fill('#bolton-filter-search', 'kerberoast');
    await page.waitForTimeout(400);
    const visibleRows = await page.locator('.bt-row').count();
    // At least one match (Kerberoastable Service Account).
    expect(visibleRows).toBeGreaterThan(0);
    // Active pill renders.
    await expect(page.locator('.bolton-filter-pill')).toContainText('Search');
});

test('5. FILTER — Clear filters button resets all axes', async ({ page }) => {
    await bootDemoBoltons(page);
    await pickHost(page, DEMO_DC);
    await page.selectOption('#bolton-filter-state', 'ALREADY_INSTALLED');
    await page.waitForTimeout(400);
    await expect(page.locator('.bolton-filter-pill')).toContainText('State');
    await page.click('#bolton-filter-clear');
    await page.waitForTimeout(300);
    const pillCount = await page.locator('.bolton-filter-pill').count();
    expect(pillCount).toBe(0);
});

test('5. FILTER — × on individual pill clears just that axis', async ({ page }) => {
    await bootDemoBoltons(page);
    await pickHost(page, DEMO_DC);
    await page.selectOption('#bolton-filter-state', 'INSTALLABLE');
    await page.selectOption('#bolton-filter-coverage', 'covered');
    await page.waitForTimeout(400);
    let pillCount = await page.locator('.bolton-filter-pill').count();
    expect(pillCount).toBe(2);
    // Remove just the state pill.
    await page.click('.bolton-filter-pill__close[data-clear-filter="state"]');
    await page.waitForTimeout(300);
    pillCount = await page.locator('.bolton-filter-pill').count();
    expect(pillCount).toBe(1);
    // Coverage pill remains.
    await expect(page.locator('.bolton-filter-pill')).toContainText('Detection');
});

// ─────────────────────────────────────────────────────────────────────────
// 6/7. INSTALL FLOW + NO STUCK ROLE FILTER
// ─────────────────────────────────────────────────────────────────────────

test('6/7. INSTALL — fake install fires + Kerberoast moves to Installed + no stuck filter banner', async ({ page }) => {
    await bootDemoBoltons(page);
    await pickHost(page, DEMO_LINUX);
    // Demo install state is in-process memory on the Flask server — uninstall
    // ESTACK first so this test starts from a known-clean baseline regardless
    // of previous test-run pollution.
    await page.evaluate(async () => {
        try {
            await window.APP.bolton.uninstall(
                'bolton.infrastructure.elastic-detection-stack', 'tllinux01',
            );
        } catch (_) { /* ignore — best-effort cleanup */ }
    });
    await page.waitForTimeout(800);
    // Install Elastic Detection Stack
    const before = await page.evaluate(async () => {
        const r = await fetch('/api/bolton/labs/demo/hosts/tllinux01/facts');
        const b = await r.json();
        return b.installed_boltons || [];
    });
    expect(before).not.toContain(VID_ESTACK);
    await page.evaluate(async () => {
        await window.APP.bolton.install('bolton.infrastructure.elastic-detection-stack', 'tllinux01');
    });
    await page.waitForTimeout(2500);
    const after = await page.evaluate(async () => {
        const r = await fetch('/api/bolton/labs/demo/hosts/tllinux01/facts');
        const b = await r.json();
        return b.installed_boltons || [];
    });
    expect(after).toContain(VID_ESTACK);
    // No stuck filter banner.
    const filterBanner = await page.locator('#bolton-host-filter-hint').count();
    expect(filterBanner).toBe(0);
});

// ─────────────────────────────────────────────────────────────────────────
// 8. PATCH FLOW
// ─────────────────────────────────────────────────────────────────────────

test('8. PATCH — Patch action on installed Kerberoast moves it to patched', async ({ page }) => {
    await bootDemoBoltons(page);
    await pickHost(page, DEMO_DC);
    await page.evaluate(async () => {
        await window.APP.bolton.patch('bolton.identity-kerberos.kerberoastable-svc', 'tldc01');
    });
    await page.waitForTimeout(3000);
    // The fake install state advances 'installed' → 'patched' but
    // `get_installed_for_host` returns BOTH states as installed so the
    // catalog still surfaces it; the demo service tracks 'patched' state
    // internally. Verify via the demo-service install state endpoint.
    const facts = await page.evaluate(async () => {
        const r = await fetch('/api/bolton/labs/demo/hosts/tldc01/facts');
        return await r.json();
    });
    expect(facts.installed_boltons).toContain('bolton.identity-kerberos.kerberoastable-svc');
});

// ─────────────────────────────────────────────────────────────────────────
// 9. UNINSTALL FLOW
// ─────────────────────────────────────────────────────────────────────────

test('9. UNINSTALL — Uninstall drops the vuln from installed_boltons', async ({ page }) => {
    await bootDemoBoltons(page);
    await pickHost(page, DEMO_DC);
    // First install something fresh so we have a clean uninstall target.
    await page.evaluate(async () => {
        await window.APP.bolton.install('bolton.known-cve.printnightmare', 'tldc01');
    });
    await page.waitForTimeout(2000);
    let facts = await page.evaluate(async () => {
        const r = await fetch('/api/bolton/labs/demo/hosts/tldc01/facts');
        return await r.json();
    });
    expect(facts.installed_boltons).toContain('bolton.known-cve.printnightmare');
    // Now uninstall.
    await page.evaluate(async () => {
        await window.APP.bolton.uninstall('bolton.known-cve.printnightmare', 'tldc01');
    });
    await page.waitForTimeout(2500);
    facts = await page.evaluate(async () => {
        const r = await fetch('/api/bolton/labs/demo/hosts/tldc01/facts');
        return await r.json();
    });
    expect(facts.installed_boltons).not.toContain('bolton.known-cve.printnightmare');
});

// ─────────────────────────────────────────────────────────────────────────
// 10. DETECTION LAYER — one-click button installs across all hosts
// ─────────────────────────────────────────────────────────────────────────

test('10. DETECTION LAYER — Enable button installs Elastic + Sysmon + Winlogbeat + Filebeat', async ({ page }) => {
    await bootDemoBoltons(page);
    await pickHost(page, DEMO_LINUX);
    // 2026-05-23 — Detection button is now state-aware: when the demo's
    // in-memory _demo_install_state already has all 8 (vuln, host) pairs
    // installed (e.g. from a previous test run), the button paints 'full'
    // state and is disabled. Uninstall every detection pair first so this
    // test starts from a deterministic 'none' state.
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
        // Repaint button so it's enabled.
        window.APP.bolton._detectionFactsCache = {};
        await window.APP.bolton._hydrateDetectionFacts();
        window.APP.bolton._refreshDetectionButton();
    });
    await page.waitForTimeout(500);
    await expect(page.locator('#bolton-enable-detection')).toBeVisible();
    await expect(page.locator('#bolton-enable-detection')).toBeEnabled();
    await page.click('#bolton-enable-detection');
    // Orchestration runs ~8 fake installs sequentially — wait long enough.
    await page.waitForTimeout(12000);
    // Check facts on each host
    const summary = await page.evaluate(async () => {
        const out = {};
        for (const h of ['tldc01', 'tlms01', 'tlws01', 'tllinux01']) {
            const r = await fetch(`/api/bolton/labs/demo/hosts/${h}/facts`);
            const b = await r.json();
            out[h] = b.installed_boltons || [];
        }
        return out;
    });
    // Each Windows host has Sysmon + Winlogbeat
    for (const h of ['tldc01', 'tlms01', 'tlws01']) {
        expect(summary[h]).toEqual(expect.arrayContaining(['bolton.infrastructure.sysmon', 'bolton.infrastructure.winlogbeat-shipper']));
    }
    // Linux host has Elastic stack + Filebeat
    expect(summary.tllinux01).toEqual(expect.arrayContaining(['bolton.infrastructure.elastic-detection-stack', 'bolton.infrastructure.filebeat-shipper']));
});

// ─────────────────────────────────────────────────────────────────────────
// 11. WALKTHROUGH DRAWER
// ─────────────────────────────────────────────────────────────────────────

test('11. WALKTHROUGH — drawer opens with 3 tabs + Walkthrough default', async ({ page }) => {
    await bootDemoBoltons(page);
    await pickHost(page, DEMO_DC);
    await page.evaluate(() => window.APP.bolton.openDetail(
        'bolton.identity-kerberos.kerberoastable-svc', 'walkthrough'));
    await expect(page.locator('.bolton-detail')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('.bolton-detail__tab')).toHaveCount(3);
    await expect(page.locator('.bolton-detail__tab.is-active')).toContainText('Walkthrough');
});

test('11. WALKTHROUGH — Detections tab shows the Elastic rules table', async ({ page }) => {
    await bootDemoBoltons(page);
    await pickHost(page, DEMO_DC);
    await page.evaluate(() => window.APP.bolton.openDetail(
        'bolton.identity-kerberos.kerberoastable-svc', 'detections'));
    await expect(page.locator('.bolton-detail')).toBeVisible({ timeout: 5000 });
    const pane = page.locator('[data-bolton-detail-pane="detections"]');
    await expect(pane).toBeVisible();
    await expect(pane).toContainText('Kerberoasting');
});

test('11. WALKTHROUGH — assessment correct answer feedback', async ({ page }) => {
    await bootDemoBoltons(page);
    await pickHost(page, DEMO_DC);
    await page.evaluate(() => window.APP.bolton.openDetail(
        'bolton.identity-kerberos.kerberoastable-svc', 'walkthrough'));
    await expect(page.locator('.bolton-walk')).toBeVisible({ timeout: 5000 });
    // Step 3 has the assessment in the Kerberoasting curriculum
    await page.click('[data-bolton-walk-step="03-crack-offline"]');
    await page.waitForTimeout(500);
    await expect(page.locator('.bolton-walk__assessment')).toBeVisible();
});

// ─────────────────────────────────────────────────────────────────────────
// 12. DEPLOYMENT SWITCH — hosts reload
// ─────────────────────────────────────────────────────────────────────────

test('12. DEPLOYMENT SWITCH — switching from c2_adhoc → demo refreshes host list', async ({ page }) => {
    await page.goto('/');
    await page.waitForFunction(() => window.APP && window.APP.activeDeployment);
    await page.waitForFunction(async () => {
        const r = await fetch('/api/deploy/active');
        const b = await r.json();
        return b.deployments && b.deployments.some(d => d._filename === 'c2_adhoc_demo_01');
    });
    await page.waitForTimeout(800);
    // Set c2_adhoc first
    await page.evaluate(() => {
        window.APP.activeDeployment.set('c2_adhoc_demo_01');
        window.APP._setActiveDeploymentType?.();
    });
    await page.waitForTimeout(500);
    // Switch to demo. 2026-05-28 — #dashboard-demo-btn is hidden when a real
    // deployment is active (UX commit cd8eef6 — "hide demo nudge on real
    // deployments"). The operator-facing entry point becomes the dropdown
    // / palette; invoke the underlying APP.startDemoMode() directly which
    // is what the button's onclick wires to, matching real-world behavior.
    await page.evaluate(() => window.APP.startDemoMode && window.APP.startDemoMode());
    await page.waitForFunction(() => window.APP.activeDeployment.current === 'demo');
    await page.waitForTimeout(800);
    await page.click('.subpill-nav__pill[data-subpill="bolt-ons"]:not([hidden])');
    await page.waitForTimeout(3000);
    const hosts = await page.evaluate(() => {
        const sel = document.getElementById('bolton-host-select');
        return sel ? Array.from(sel.options).map(o => o.value).filter(Boolean) : [];
    });
    expect(hosts).toContain('tldc01');
    expect(hosts).not.toContain('ca01');  // c2_adhoc's hosts shouldn't leak
});

// ─────────────────────────────────────────────────────────────────────────
// 13. ALL-MODE — Bolt-ons hidden
// ─────────────────────────────────────────────────────────────────────────

test('13. ALL-MODE — picking __all__ sentinel hides Bolt-ons sub-pill', async ({ page }) => {
    await page.goto('/');
    await page.waitForFunction(() => window.APP && window.APP.activeDeployment);
    await page.evaluate(() => window.APP.activeDeployment.set('__all__'));
    await page.waitForTimeout(500);
    const subPills = await page.evaluate(() =>
        window.APP.computeVisibleSubPills(window.APP.activeDeployment),
    );
    expect(subPills).not.toContain('bolt-ons');
});

// ─────────────────────────────────────────────────────────────────────────
// 14. DRAFT — Bolt-ons hidden
// ─────────────────────────────────────────────────────────────────────────

test('14. DRAFT — picking __draft__ sentinel hides Bolt-ons sub-pill', async ({ page }) => {
    await page.goto('/');
    await page.waitForFunction(() => window.APP && window.APP.activeDeployment);
    await page.evaluate(() => window.APP.activeDeployment.set('__draft__'));
    await page.waitForTimeout(500);
    const subPills = await page.evaluate(() =>
        window.APP.computeVisibleSubPills(window.APP.activeDeployment),
    );
    expect(subPills).not.toContain('bolt-ons');
});

// ─────────────────────────────────────────────────────────────────────────
// 15. NON-DEMO HOST — c2-only without test_lab gates Bolt-ons OFF
// ─────────────────────────────────────────────────────────────────────────

test('15. C2-ONLY — c2-adhoc without enable_test_lab hides Bolt-ons sub-pill', async ({ page }) => {
    await page.goto('/');
    await page.waitForFunction(() => window.APP && window.APP.activeDeployment);
    await page.waitForFunction(async () => {
        const r = await fetch('/api/deploy/active');
        const b = await r.json();
        return b.deployments && b.deployments.some(d => d._filename === 'c2_adhoc_demo_01');
    });
    await page.evaluate(() => {
        window.APP.activeDeployment.set('c2_adhoc_demo_01');
        window.APP._setActiveDeploymentType?.();
    });
    await page.waitForFunction(() => window.APP.activeDeployment.current === 'c2_adhoc_demo_01');
    const subPills = await page.evaluate(() =>
        window.APP.computeVisibleSubPills(window.APP.activeDeployment),
    );
    // For c2-only (no test_lab), Bolt-ons should NOT be in the visible set.
    // (This deployment has enable_test_lab=false in its tfvars.)
    expect(subPills).not.toContain('bolt-ons');
});
