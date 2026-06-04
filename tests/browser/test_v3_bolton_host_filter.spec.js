/**
 * v3 BOLT-ON HOST FILTER — descriptor-driven Target Host dropdown filter.
 *
 * Verifies that picking a catalog descriptor narrows the host dropdown to
 * hosts whose role matches the descriptor's targets.required_roles, and that
 * the dispatch-time backstop stays untouched. Four cases per the spec:
 *
 *   1. Descriptor requires [domain_controller] → only DC hosts in dropdown
 *   2. Descriptor requires [linux_member] with no Linux host → empty state
 *   3. Switching descriptor A (DC) → descriptor B (member_server) re-filters
 *   4. Descriptor with no required_roles → every host shown (regression)
 *
 * The host dropdown filter is a UX guardrail, not a security boundary —
 * webapp/backend/services/bolton_install_service.py still enforces the
 * dispatch-time CompatibilityRefusedError backstop.
 */

import { test, expect } from '@playwright/test';
import { seedDeployment } from './helpers/seed-deployment.js';
import { railNavigate, clickSubPill } from './helpers/nav.js';

// ─── Fixtures ──────────────────────────────────────────────────────────────

// Mixed-role lab: 2 DCs, 1 member_server, 1 workstation. NO linux_member.
const MIXED_LAB_HOSTS = {
    success: true,
    lab: 'goad-light',
    hosts: [
        { name: 'dc01', host_id: 'dc01', role: 'domain_controller', os_family: 'windows', os_version: '2019', installed_count: 0, stale: true },
        { name: 'dc02', host_id: 'dc02', role: 'domain_controller', os_family: 'windows', os_version: '2022', installed_count: 0, stale: true },
        { name: 'srv01', host_id: 'srv01', role: 'member_server', os_family: 'windows', os_version: '2019', installed_count: 0, stale: true },
        { name: 'ws01', host_id: 'ws01', role: 'workstation', os_family: 'windows', os_version: '10', installed_count: 0, stale: true },
    ],
};

// Vuln-only lab: just one DC, no member_server, no workstation, no linux.
const SINGLE_DC_LAB_HOSTS = {
    success: true,
    lab: 'goad-mini',
    hosts: [
        { name: 'dc01', host_id: 'dc01', role: 'domain_controller', os_family: 'windows', os_version: '2019', installed_count: 0, stale: true },
    ],
};

// Descriptor fixtures — keyed by id, served by /api/bolton/vulns/<id>.
const DESCRIPTORS = {
    'bolton.knowncve.zerologon': {
        success: true,
        vuln: {
            id: 'bolton.knowncve.zerologon',
            name: 'Zerologon (CVE-2020-1472)',
            category: 'known-cve',
            targets: {
                supported_os: [{ family: 'windows', min_version: '2008', max_version: '2019' }],
                required_roles: ['domain_controller'],
            },
        },
    },
    'bolton.webapp.dvwa-lite': {
        success: true,
        vuln: {
            id: 'bolton.webapp.dvwa-lite',
            name: 'DVWA-lite container',
            category: 'web-app',
            targets: {
                supported_os: [{ family: 'linux', min_version: '20.04' }],
                required_roles: ['linux_member'],
            },
        },
    },
    'bolton.svcmisc.share-everyone': {
        success: true,
        vuln: {
            id: 'bolton.svcmisc.share-everyone',
            name: 'Writable share — Everyone',
            category: 'service-misconfig',
            targets: {
                supported_os: [{ family: 'windows', min_version: '2016' }],
                required_roles: ['member_server'],
            },
        },
    },
    // Descriptor with NO required_roles — regression case for current behavior.
    'bolton.infra.sysmon-norole': {
        success: true,
        vuln: {
            id: 'bolton.infra.sysmon-norole',
            name: 'Sysmon shipper (no role constraint)',
            category: 'infrastructure',
            targets: {
                supported_os: [{ family: 'windows', min_version: '2016' }],
                required_roles: [],
            },
        },
    },
};

// ─── Helpers ───────────────────────────────────────────────────────────────

async function gotoBoltons(page) {
    // Seed a goad-mini deployment so the Bolt-ons sub-pill is visible.
    await seedDeployment(page, { type: 'goad-mini', name: 'goad_test_alpha' });
    await page.goto('/');
    await railNavigate(page, 'deployments-tab');
    await clickSubPill(page, 'bolt-ons');
}

/**
 * Stub /api/bolton/vulns/<id> with our descriptor fixtures + /api/bolton/labs/.../hosts
 * with the supplied host list. Anything else passes through.
 */
async function installApiStubs(page, hostsBody) {
    await page.route('**/api/bolton/labs/**/hosts', (route) => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(hostsBody),
        });
    });
    await page.route('**/api/bolton/vulns/**', (route) => {
        const url = route.request().url();
        // Match the last path segment as the vuln id (encoded). Skip
        // /vulns?... (catalog list) — that has no segment after vulns.
        const m = url.match(/\/api\/bolton\/vulns\/([^/?]+)(?:\?|$)/);
        if (!m) {
            route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, vulns: [], total: 0 }) });
            return;
        }
        const vid = decodeURIComponent(m[1]);
        const body = DESCRIPTORS[vid];
        if (!body) {
            route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ success: false, error: 'not found' }) });
            return;
        }
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });
}

// Force loadHosts to finish before each assertion: APP.bolton.loadHosts is
// fire-and-forget so we call it explicitly + await the dropdown population.
async function loadHostsAndWait(page, lab) {
    await page.evaluate((l) => {
        window.APP.bolton.state.lab = l;
        window.APP.bolton.state.selectedDescriptorId = null;
        window.APP.bolton.state.selectedDescriptor = null;
        return window.APP.bolton.loadHosts(l);
    }, lab);
    // Wait until at least one host option is rendered.
    await page.waitForFunction(() => {
        const sel = document.getElementById('bolton-host-select');
        if (!sel) return false;
        const opts = Array.from(sel.options).map(o => o.value).filter(v => v);
        return opts.length > 0;
    }, { timeout: 5000 });
}

// ─── 1. Descriptor requires domain_controller → only DC hosts ──────────────

test.describe('v3 bolt-on host filter — descriptor selection', () => {
    test('descriptor with required_roles=[domain_controller] filters dropdown to DC hosts', async ({ page }) => {
        await installApiStubs(page, MIXED_LAB_HOSTS);
        await gotoBoltons(page);
        await loadHostsAndWait(page, 'goad-light');

        // Pre-condition: dropdown shows all 4 hosts.
        const before = await page.locator('#bolton-host-select option').count();
        expect(before).toBe(5); // 4 hosts + the "select a host" placeholder

        // Pick the DC-only descriptor.
        await page.evaluate(() => window.APP.bolton.selectDescriptor('bolton.knowncve.zerologon'));
        await page.waitForFunction(() => {
            const sel = document.getElementById('bolton-host-select');
            const hostOpts = Array.from(sel.options).filter(o => o.value);
            return hostOpts.length === 2; // dc01, dc02 only
        }, { timeout: 3000 });

        const optionValues = await page.locator('#bolton-host-select option').evaluateAll(
            opts => opts.map(o => o.value).filter(v => v)
        );
        expect(optionValues.sort()).toEqual(['dc01', 'dc02']);

        // Hint should be present + reference the role.
        const hint = page.locator('#bolton-host-filter-hint');
        await expect(hint).toBeVisible();
        const hintText = await hint.textContent();
        expect(hintText).toContain('domain_controller');
        expect(hintText).toContain('2 of 4');
    });
});

// ─── 2. Descriptor requires linux_member, lab has no Linux → empty state ───

test.describe('v3 bolt-on host filter — empty compatible set', () => {
    test('descriptor needing linux_member against a no-Linux lab shows empty-state UI', async ({ page }) => {
        await installApiStubs(page, MIXED_LAB_HOSTS);
        await gotoBoltons(page);
        await loadHostsAndWait(page, 'goad-light');

        await page.evaluate(() => window.APP.bolton.selectDescriptor('bolton.webapp.dvwa-lite'));
        await page.waitForFunction(() => !!document.getElementById('bolton-host-empty-compat'), { timeout: 3000 });

        const empty = page.locator('#bolton-host-empty-compat');
        await expect(empty).toBeVisible();
        const emptyText = await empty.textContent();
        expect(emptyText).toContain('No compatible hosts in this lab.');
        expect(emptyText).toContain('linux_member');
        // Available host roles list should mention the roles actually in the lab.
        expect(emptyText).toContain('domain_controller');
        expect(emptyText).toContain('member_server');
        expect(emptyText).toContain('workstation');

        // Dropdown is hidden (replaced by the empty state).
        await expect(page.locator('#bolton-host-select')).toBeHidden();

        // Testlab-mini doc link is present.
        await expect(empty.locator('[data-bolton-testlab-doc]')).toHaveCount(1);
    });
});

// ─── 3. Switching descriptors re-filters the dropdown ──────────────────────

test.describe('v3 bolt-on host filter — descriptor switching', () => {
    test('switching descriptor from DC → member_server re-filters the dropdown', async ({ page }) => {
        await installApiStubs(page, MIXED_LAB_HOSTS);
        await gotoBoltons(page);
        await loadHostsAndWait(page, 'goad-light');

        // First descriptor: needs domain_controller.
        await page.evaluate(() => window.APP.bolton.selectDescriptor('bolton.knowncve.zerologon'));
        await page.waitForFunction(() => {
            const sel = document.getElementById('bolton-host-select');
            const opts = Array.from(sel.options).filter(o => o.value);
            return opts.length === 2 && opts.every(o => o.value.startsWith('dc'));
        }, { timeout: 3000 });

        // Switch to descriptor that needs member_server.
        await page.evaluate(() => window.APP.bolton.selectDescriptor('bolton.svcmisc.share-everyone'));
        await page.waitForFunction(() => {
            const sel = document.getElementById('bolton-host-select');
            const opts = Array.from(sel.options).filter(o => o.value);
            return opts.length === 1 && opts[0].value === 'srv01';
        }, { timeout: 3000 });

        const optionValues = await page.locator('#bolton-host-select option').evaluateAll(
            opts => opts.map(o => o.value).filter(v => v)
        );
        expect(optionValues).toEqual(['srv01']);

        const hintText = await page.locator('#bolton-host-filter-hint').textContent();
        expect(hintText).toContain('member_server');
        expect(hintText).toContain('1 of 4');
    });
});

// ─── 4. No required_roles → every host shown (regression check) ────────────

test.describe('v3 bolt-on host filter — no required_roles regression', () => {
    test('descriptor with empty required_roles leaves every host visible (current behavior)', async ({ page }) => {
        await installApiStubs(page, MIXED_LAB_HOSTS);
        await gotoBoltons(page);
        await loadHostsAndWait(page, 'goad-light');

        await page.evaluate(() => window.APP.bolton.selectDescriptor('bolton.infra.sysmon-norole'));
        // Wait for the fetch to resolve (state.selectedDescriptor must be set).
        await page.waitForFunction(() => {
            const d = window.APP.bolton.state.selectedDescriptor;
            return d && d.id === 'bolton.infra.sysmon-norole';
        }, { timeout: 3000 });

        // Dropdown still has all 4 hosts.
        const optionValues = await page.locator('#bolton-host-select option').evaluateAll(
            opts => opts.map(o => o.value).filter(v => v)
        );
        expect(optionValues.sort()).toEqual(['dc01', 'dc02', 'srv01', 'ws01']);

        // Hint is hidden (filter inactive / all hosts pass).
        await expect(page.locator('#bolton-host-filter-hint')).toHaveCount(0);
        await expect(page.locator('#bolton-host-empty-compat')).toHaveCount(0);
    });
});
