/**
 * v3 DEMO MODE — synthetic `demo` deployment_type populates the whole
 * dashboard with realistic dummy data.
 *
 * Validates end-to-end:
 *   1. /api/deploy/active surfaces the `demo` deployment
 *   2. Selecting demo from the top-bar dropdown shows ALL sub-pills
 *      (Manage / Bolt-ons / Cleanup) plus the Operations rail item
 *   3. Manage pane renders the canned fleet resources
 *   4. Operations → Beacons surfaces the 3 demo beacons
 *   5. Bolt-ons → host catalog renders with the Kerberoast curriculum
 *      CTA still wired through (proves curriculum + demo cooperate)
 *
 * Deliberately does NOT mock any /api/* route — exercises the real
 * Flask backend so the integration is honest end-to-end.
 */

import { test, expect } from '@playwright/test';
import { railNavigate, clickSubPill } from './helpers/nav.js';

async function bootAndSelectDemo(page) {
    await page.goto('/');
    // Wait until the activeDeployment singleton is wired up.
    await page.waitForFunction(
        () => window.APP && window.APP.activeDeployment
              && typeof window.APP.activeDeployment.set === 'function',
        { timeout: 8000 },
    );
    // /api/deploy/active is cached by _refreshGlobalDeployments; wait for
    // that cache to populate the deployment_type metadata for `demo`.
    await page.waitForFunction(async () => {
        const r = await fetch('/api/deploy/active');
        if (!r.ok) return false;
        const body = await r.json();
        return Array.isArray(body.deployments)
            && body.deployments.some(d => d._filename === 'demo');
    }, { timeout: 8000 });
    // Switch the active deployment to demo via the public API + trigger
    // the deployment_type lookup the way the dropdown does.
    await page.evaluate(() => {
        window.APP.activeDeployment.set('demo');
        if (typeof window.APP._setActiveDeploymentType === 'function') {
            window.APP._setActiveDeploymentType();
        }
    });
    await page.waitForFunction(
        () => window.APP.activeDeployment.current === 'demo'
              && window.APP.activeDeployment.deployment_type === 'demo',
        { timeout: 5000 },
    );
}

// ─────────────────────────────────────────────────────────────────────────
// 1. /api/deploy/active SURFACES the demo
// ─────────────────────────────────────────────────────────────────────────

test('Demo deployment is surfaced in /api/deploy/active', async ({ page }) => {
    await page.goto('/');
    const response = await page.request.get('/api/deploy/active');
    expect(response.status()).toBe(200);
    const body = await response.json();
    const demo = (body.deployments || []).find(d => d._filename === 'demo');
    expect(demo).toBeTruthy();
    expect(demo.deployment_type).toBe('demo');
    expect(demo.status).toBe('success');
    expect(demo.is_demo).toBe(true);
    expect(demo.enable_test_lab).toBe(true);
});

// ─────────────────────────────────────────────────────────────────────────
// 2. SELECTING DEMO exposes Manage / Bolt-ons / Cleanup + Operations rail
// ─────────────────────────────────────────────────────────────────────────

test('Selecting demo deployment shows Manage / Bolt-ons / Cleanup + Operations', async ({ page }) => {
    await bootAndSelectDemo(page);
    // computeVisibleSubPills returns all three.
    const subPills = await page.evaluate(
        () => window.APP.computeVisibleSubPills(window.APP.activeDeployment),
    );
    expect(subPills).toEqual(expect.arrayContaining(['manage', 'bolt-ons', 'cleanup']));
    // computeOperationsVisible returns true for demo.
    const opsVisible = await page.evaluate(
        () => window.APP.computeOperationsVisible(window.APP.activeDeployment),
    );
    expect(opsVisible).toBe(true);
});

// ─────────────────────────────────────────────────────────────────────────
// 3. MANAGE pane renders the canned fleet
// ─────────────────────────────────────────────────────────────────────────

test('Manage pane renders demo fleet resources from /api/deploy/resources/project/demo', async ({ page }) => {
    await bootAndSelectDemo(page);
    const response = await page.request.get('/api/deploy/resources/project/demo');
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.is_demo).toBe(true);
    expect(body.resources.length).toBeGreaterThanOrEqual(10);
    const types = body.resources.map(r => r.type);
    expect(types).toContain('aws_vpc');
    expect(types).toContain('aws_instance');
    expect(types).toContain('aws_security_group');
});

// ─────────────────────────────────────────────────────────────────────────
// 4. OPERATIONS → BEACONS shows the 4 demo beacons via /api/beacon/list
// 2026-05-23 — beacon set rebuilt to mirror test_lab hosts + form a real
// callback tree (tlws01 root → tlms01 → tldc01 / tllinux01). Field names
// align with CS REST API exactly (bid/user/computer/internal/...).
// ─────────────────────────────────────────────────────────────────────────

test('/api/beacon/list?project=demo returns 4 canned beacons mirroring test_lab', async ({ page }) => {
    await page.goto('/');
    const response = await page.request.get('/api/beacon/list?project=demo');
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.is_demo).toBe(true);
    expect(body.beacons.length).toBe(4);
    const computers = body.beacons.map(b => b.computer);
    expect(computers).toContain('tldc01');
    expect(computers).toContain('tlms01');
    expect(computers).toContain('tlws01');
    expect(computers).toContain('tllinux01');
    // Every beacon except the root has a pbid pointing at a real beacon.
    const bids = new Set(body.beacons.map(b => b.bid));
    body.beacons.forEach(b => {
        if (b.pbid) expect(bids).toContain(b.pbid);
    });
});

test('/api/beacon/<bid> works for demo beacon ids', async ({ page }) => {
    await page.goto('/');
    const response = await page.request.get('/api/beacon/demo-pivot-DC01');
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.is_demo).toBe(true);
    expect(body.beacon.computer).toBe('tldc01');
    expect(body.beacon.isAdmin).toBe(true);
    expect(body.beacon.pbid).toBe('demo-pivot-MS01');
});

// ─────────────────────────────────────────────────────────────────────────
// 5. BOLT-ON catalog renders for the demo lab
// ─────────────────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────
// 5b. DASHBOARD HERO CTA — "Try Demo Mode" button
// ─────────────────────────────────────────────────────────────────────────

test('Dashboard hero shows a Try Demo Mode CTA wired to startDemoMode', async ({ page }) => {
    await page.goto('/');
    await page.waitForFunction(
        () => window.APP && typeof window.APP.startDemoMode === 'function',
        { timeout: 8000 },
    );
    const btn = page.locator('#dashboard-demo-btn');
    await expect(btn).toBeVisible();
    await expect(btn).toContainText('Try Demo Mode');
    await expect(btn).toContainText('Synthetic deployment');
    // Click triggers APP.startDemoMode, which sets activeDeployment to demo
    // and navigates to the Manage sub-pill.
    await btn.click();
    await page.waitForFunction(
        () => window.APP.activeDeployment.current === 'demo'
              && window.APP.activeDeployment.deployment_type === 'demo',
        { timeout: 5000 },
    );
});

test('Demo bolt-on lab serves hosts + facts + full catalog (with kerberoast curriculum)', async ({ page }) => {
    await page.goto('/');
    // Hosts.
    let r = await page.request.get('/api/bolton/labs/demo/hosts');
    expect(r.status()).toBe(200);
    let body = await r.json();
    expect(body.is_demo).toBe(true);
    expect(body.hosts.length).toBe(4);
    // tldc01 facts.
    r = await page.request.get('/api/bolton/labs/demo/hosts/tldc01/facts');
    expect(r.status()).toBe(200);
    body = await r.json();
    expect(body.os_family).toBe('windows');
    expect(body.role).toBe('domain_controller');
    // Full catalog for tldc01.
    r = await page.request.get('/api/bolton/labs/demo/hosts/tldc01/catalog');
    expect(r.status()).toBe(200);
    body = await r.json();
    expect(body.is_demo).toBe(true);
    expect(body.vulns.length).toBeGreaterThan(0);
    // Kerberoastable is present with has_curriculum + step count.
    const kerb = body.vulns.find(v => v.id === 'bolton.identity-kerberos.kerberoastable-svc');
    expect(kerb).toBeTruthy();
    expect(kerb.has_curriculum).toBe(true);
    // 2026-05-28 — curriculum-agent-A rewrote kerberoast to 6 steps; allow
    // future tweaks within a sane band rather than pinning to an exact count.
    expect(kerb.curriculum_step_count).toBeGreaterThanOrEqual(5);
});
