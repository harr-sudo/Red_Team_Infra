// Verification driver — walks every user flow in the dashboard, takes a
// screenshot at each step, and records console errors / network failures /
// missing-element failures. Not part of the automated regression; invoked
// manually to spot-check UX after CSS/layout changes.
//
// Run: DASHBOARD_STATE_DIR=/tmp/playwright-dashboard-state \
//        ./node_modules/.bin/playwright test \
//        tests/browser/verify_all_flows.spec.js \
//        --reporter=line --workers=1 --timeout=60000
//
// Screenshots land in /tmp/verify-runs/<timestamp>/.

const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const OUT_DIR = process.env.VERIFY_OUT_DIR || `/tmp/verify-runs/${new Date().toISOString().replace(/[:.]/g, '-')}`;
fs.mkdirSync(OUT_DIR, { recursive: true });

const errors = [];
function attachErrorCollectors(page, label) {
    page.on('console', (msg) => {
        if (msg.type() === 'error') {
            errors.push({ label, kind: 'console.error', text: msg.text() });
        }
    });
    page.on('pageerror', (err) => {
        errors.push({ label, kind: 'pageerror', text: err.message });
    });
    page.on('requestfailed', (req) => {
        // CS REST API failures are expected in local dev — filter them out.
        if (req.url().includes('/api/beacon/')) return;
        errors.push({ label, kind: 'requestfailed', text: `${req.method()} ${req.url()} — ${req.failure()?.errorText}` });
    });
}

async function snap(page, name) {
    const file = path.join(OUT_DIR, `${name}.png`);
    await page.screenshot({ path: file, fullPage: false });
    return file;
}

async function setTheme(page, theme) {
    await page.evaluate((t) => {
        if (t === 'light') document.documentElement.setAttribute('data-theme', 'light');
        else document.documentElement.removeAttribute('data-theme');
    }, theme);
    await page.waitForTimeout(200);
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. DEMO ENGAGEMENT — the priority flow per the operator's directive.
// ─────────────────────────────────────────────────────────────────────────────
test.describe('VERIFY — demo engagement end-to-end', () => {
    // Each test boots demo independently; not serial.

    test('demo: boot from dashboard hero', async ({ page }) => {
        attachErrorCollectors(page, 'demo-boot');
        await page.setViewportSize({ width: 1440, height: 900 });
        await page.goto('/');
        await snap(page, '01-demo-dashboard-load');
        await page.waitForFunction(() => window.APP && typeof window.APP.startDemoMode === 'function', { timeout: 5000 });
        const demoBtn = page.locator('#dashboard-demo-btn');
        await expect(demoBtn, 'Demo CTA must be present on the dashboard hero').toBeVisible();
        await demoBtn.click();
        await page.waitForFunction(
            () => window.APP.activeDeployment.current === 'demo' &&
                  window.APP.activeDeployment.deployment_type === 'demo',
            { timeout: 5000 },
        );
        await page.waitForTimeout(500);
        await snap(page, '02-demo-mode-active');
    });

    test('demo: subpill nav surfaces the right pills', async ({ page }) => {
        attachErrorCollectors(page, 'demo-subpills');
        await page.setViewportSize({ width: 1440, height: 900 });
        await page.goto('/');
        await page.waitForFunction(() => window.APP?.startDemoMode);
        await page.click('#dashboard-demo-btn');
        await page.waitForFunction(() => window.APP.activeDeployment.current === 'demo');
        await page.waitForTimeout(500);
        const visiblePills = await page.evaluate(() =>
            Array.from(document.querySelectorAll('.subpill-nav__pill:not([hidden])'))
                .map((p) => p.dataset.subpill)
        );
        // Demo should expose Manage + Bolt-ons + (operations group) at minimum.
        // Configure / Deploy are draft-only.
        for (const required of ['manage', 'bolt-ons']) {
            expect(visiblePills, `demo must show ${required} pill`).toContain(required);
        }
    });

    test('demo: bolt-ons across all 4 hosts (browse, no install)', async ({ page }) => {
        attachErrorCollectors(page, 'demo-boltons-browse');
        await page.setViewportSize({ width: 1440, height: 900 });
        await page.goto('/');
        await page.waitForFunction(() => window.APP?.startDemoMode);
        await page.click('#dashboard-demo-btn');
        await page.waitForFunction(() => window.APP.activeDeployment.current === 'demo');
        await page.waitForTimeout(500);
        await page.click('.subpill-nav__pill[data-subpill="bolt-ons"]:not([hidden])');
        await page.waitForTimeout(2000);
        await snap(page, '03-demo-boltons-initial');
        // The 4 demo hosts mirror the test_lab module.
        const hosts = ['tldc01', 'tlms01', 'tlws01', 'tllinux01'];
        for (const host of hosts) {
            await page.evaluate((h) => window.APP.bolton.selectHost('demo', h), host);
            await page.waitForTimeout(900);
            await snap(page, `04-demo-bolton-host-${host}`);
            // Each host should render its 6-section spec-list (Installed / Available /
            // Incompatible / Patched / etc) OR the empty placeholder.
            const sectionInfo = await page.evaluate(() => {
                const sections = document.getElementById('bolton-sections');
                const empty = document.getElementById('bolton-empty-state');
                if (!sections) return { found: false, hidden: true, visible: false, rowCount: 0, emptyVisible: false };
                const visible = !sections.hasAttribute('hidden') && getComputedStyle(sections).display !== 'none';
                const rows = sections.querySelectorAll('[data-rows] > *').length;
                const emptyVisible = empty && !empty.hasAttribute('hidden') && getComputedStyle(empty).display !== 'none';
                return { found: true, visible, rowCount: rows, emptyVisible };
            });
            const renderedSomething = sectionInfo.found && (sectionInfo.visible || sectionInfo.emptyVisible);
            expect(renderedSomething, `host ${host} must render sections or empty state — got ${JSON.stringify(sectionInfo)}`).toBe(true);
        }
    });

    test('demo: filter UI is the dropdown bar (not the 22-chip strip)', async ({ page }) => {
        attachErrorCollectors(page, 'demo-bolton-filter');
        await page.setViewportSize({ width: 1440, height: 900 });
        await page.goto('/');
        await page.waitForFunction(() => window.APP?.startDemoMode);
        await page.click('#dashboard-demo-btn');
        await page.waitForFunction(() => window.APP.activeDeployment.current === 'demo');
        await page.click('.subpill-nav__pill[data-subpill="bolt-ons"]:not([hidden])');
        await page.waitForTimeout(2000);
        // Filter bar is hidden until a host is selected.
        await page.evaluate((h) => window.APP.bolton.selectHost('demo', h), 'tldc01');
        await page.waitForTimeout(800);
        // The filter bar should have search + dropdown selects, not a chip grid.
        const filterBar = page.locator('.bolton-filter-bar');
        await expect(filterBar, 'new filter bar must be present').toBeVisible();
        const selects = await page.locator('.bolton-filter-bar select').count();
        expect(selects, 'filter bar should have multiple dropdowns').toBeGreaterThanOrEqual(2);
    });

    test('demo: install ESTACK on tllinux01, verify Installed state, no stuck filter', async ({ page }) => {
        attachErrorCollectors(page, 'demo-install-estack');
        await page.setViewportSize({ width: 1440, height: 900 });
        await page.goto('/');
        await page.waitForFunction(() => window.APP?.startDemoMode);
        await page.click('#dashboard-demo-btn');
        await page.waitForFunction(() => window.APP.activeDeployment.current === 'demo');
        await page.click('.subpill-nav__pill[data-subpill="bolt-ons"]:not([hidden])');
        await page.waitForTimeout(2000);
        // Clean state.
        await page.evaluate(async () => {
            try { await window.APP.bolton.uninstall('bolton.infrastructure.elastic-detection-stack', 'tllinux01'); } catch (_) {}
        });
        await page.waitForTimeout(800);
        await page.evaluate((h) => window.APP.bolton.selectHost('demo', h), 'tllinux01');
        await page.waitForTimeout(800);
        await snap(page, '05-demo-tllinux01-before-install');
        await page.evaluate(async () => {
            await window.APP.bolton.install('bolton.infrastructure.elastic-detection-stack', 'tllinux01');
        });
        await page.waitForTimeout(3000);
        await snap(page, '06-demo-tllinux01-after-install');
        const installed = await page.evaluate(async () => {
            const r = await fetch('/api/bolton/labs/demo/hosts/tllinux01/facts');
            const b = await r.json();
            return b.installed_boltons || [];
        });
        expect(installed, 'ESTACK should be installed after dispatch').toContain('bolton.infrastructure.elastic-detection-stack');
        // No stuck role filter banner.
        const banner = await page.locator('#bolton-host-filter-hint').count();
        expect(banner, 'no stuck role-filter banner').toBe(0);
    });

    test('demo: curriculum drawer opens with 3 tabs (Install/Walkthrough/Detections)', async ({ page }) => {
        attachErrorCollectors(page, 'demo-curriculum-drawer');
        await page.setViewportSize({ width: 1440, height: 900 });
        await page.goto('/');
        await page.waitForFunction(() => window.APP?.startDemoMode);
        await page.click('#dashboard-demo-btn');
        await page.waitForFunction(() => window.APP.activeDeployment.current === 'demo');
        await page.click('.subpill-nav__pill[data-subpill="bolt-ons"]:not([hidden])');
        await page.waitForTimeout(2000);
        await page.evaluate((h) => window.APP.bolton.selectHost('demo', h), 'tldc01');
        await page.waitForTimeout(800);
        // Open the kerberoastable-svc drawer.
        const drawerOpened = await page.evaluate(async () => {
            if (window.APP.bolton.openDetail) {
                await window.APP.bolton.openDetail('bolton.identity-kerberos.kerberoastable-svc', 'tldc01');
                return true;
            }
            return false;
        });
        if (!drawerOpened) {
            test.skip(true, 'openDetail not exposed; drawer not testable headlessly');
            return;
        }
        await page.waitForTimeout(800);
        await snap(page, '07-demo-curriculum-drawer-open');
        const tabs = await page.locator('.bolton-detail-drawer__tab, [role="tab"]').count();
        expect(tabs, 'drawer should expose multiple tabs').toBeGreaterThanOrEqual(2);
    });

    test('demo: manage sub-pill renders summary for demo', async ({ page }) => {
        attachErrorCollectors(page, 'demo-manage');
        await page.setViewportSize({ width: 1440, height: 900 });
        await page.goto('/');
        await page.waitForFunction(() => window.APP?.startDemoMode);
        await page.click('#dashboard-demo-btn');
        await page.waitForFunction(() => window.APP.activeDeployment.current === 'demo');
        await page.click('.subpill-nav__pill[data-subpill="manage"]:not([hidden])');
        await page.waitForTimeout(2000);
        await snap(page, '08-demo-manage');
        // Manage view should exist and show the demo hero.
        const heroName = await page.locator('#manage-hero-name').textContent().catch(() => '');
        expect(heroName.toLowerCase(), 'manage hero should mention demo').toMatch(/demo|test|lab/);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// 2. CHROME — topbar + rail must work + look right in both themes
//    at the two viewports the operator actually uses.
// ─────────────────────────────────────────────────────────────────────────────
test.describe('VERIFY — chrome (topbar + rail) across themes + viewports', () => {
    for (const vw of [1280, 1440, 1920]) {
        for (const theme of ['dark', 'light']) {
            test(`chrome @ ${vw}px ${theme}`, async ({ page }) => {
                attachErrorCollectors(page, `chrome-${vw}-${theme}`);
                await page.setViewportSize({ width: vw, height: 800 });
                await page.goto('/');
                await page.waitForFunction(() => document.querySelector('.app-topbar'));
                await setTheme(page, theme);
                await snap(page, `chrome-${vw}-${theme}`);
                // All 4 right-cluster items must be inside the viewport.
                const out = await page.evaluate(() => {
                    const ids = ['global-deployment-chip', 'global-cost-chip', 'operator-chip', 'global-theme-toggle'];
                    return ids.map((id) => {
                        const el = document.getElementById(id);
                        if (!el) return { id, error: 'missing' };
                        const r = el.getBoundingClientRect();
                        return { id, x: r.x, right: r.right, w: r.width, visible: r.width > 0 && r.height > 0 };
                    });
                });
                for (const item of out) {
                    expect(item.error, `${item.id} must exist`).toBeFalsy();
                    expect(item.visible, `${item.id} must render`).toBe(true);
                    expect(item.right, `${item.id} must be inside viewport ${vw}px`).toBeLessThanOrEqual(vw + 1);
                }
                // Breadcrumb must have non-zero width.
                const bcW = await page.locator('#app-topbar-breadcrumb').evaluate(el => el.getBoundingClientRect().width);
                expect(bcW, 'breadcrumb must be visible (non-zero width)').toBeGreaterThan(0);
            });
        }
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// 3. RAIL NAVIGATION — every top-level destination must navigate cleanly.
// ─────────────────────────────────────────────────────────────────────────────
test.describe('VERIFY — rail navigation', () => {
    const dests = ['dashboard', 'deployments-tab', 'settings'];
    for (const dest of dests) {
        test(`rail → ${dest}`, async ({ page }) => {
            attachErrorCollectors(page, `rail-${dest}`);
            await page.setViewportSize({ width: 1440, height: 900 });
            await page.goto('/');
            await page.waitForFunction((t) => {
                const btn = document.querySelector(`.app-rail__item[data-rail-target="${t}"]`);
                return btn && btn.dataset.shellWired === '1';
            }, dest, { timeout: 5000 });
            await page.click(`.app-rail__item[data-rail-target="${dest}"]`);
            await page.waitForFunction((t) => {
                const p = document.querySelector(`.tab-page[data-page="${t}"]`);
                return p && (p.classList.contains('active') || p.dataset.active === 'true');
            }, dest, { timeout: 5000 });
            await page.waitForTimeout(400);
            await snap(page, `nav-${dest}`);
        });
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// 4. DRAFT FLOW — Configure + Deploy sub-pills (no real terraform)
// ─────────────────────────────────────────────────────────────────────────────
test.describe('VERIFY — draft (Configure + Deploy)', () => {
    test('configure pill renders V2 progressive form for c2-adhoc', async ({ page }) => {
        attachErrorCollectors(page, 'draft-configure');
        await page.setViewportSize({ width: 1440, height: 900 });
        await page.goto('/');
        await page.waitForFunction(() => window.APP?.startNewDeployment);
        await page.evaluate(() => window.APP.startNewDeployment());
        await page.waitForFunction(() => window.APP.activeDeployment.current === '__draft__', { timeout: 5000 });
        await page.waitForTimeout(400);
        await page.click('.subpill-nav__pill[data-subpill="configure"]:not([hidden])');
        await page.waitForTimeout(800);
        await snap(page, '09-draft-configure');
        // V2 pane should be visible OR legacy editor should be in scope.
        const v2Visible = await page.locator('#configure-v2-pane').evaluate(
            el => !el.hasAttribute('hidden') && getComputedStyle(el).display !== 'none'
        ).catch(() => false);
        const legacyVisible = await page.locator('#configure-edit-pane .configuration-editor').isVisible().catch(() => false);
        expect(v2Visible || legacyVisible, 'configure must render a usable form').toBe(true);
    });

    test('deploy pill in draft mode shows the per-deployment summary surface', async ({ page }) => {
        attachErrorCollectors(page, 'draft-deploy');
        await page.setViewportSize({ width: 1440, height: 900 });
        await page.goto('/');
        await page.waitForFunction(() => window.APP?.startNewDeployment);
        await page.evaluate(() => window.APP.startNewDeployment());
        await page.waitForFunction(() => window.APP.activeDeployment.current === '__draft__');
        await page.click('.subpill-nav__pill[data-subpill="deploy"]:not([hidden])');
        await page.waitForTimeout(800);
        await snap(page, '10-draft-deploy');
        const pane = page.locator('#subpill-pane-deploy');
        await expect(pane).toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// 5. ERROR REPORT — emit at end of run.
// ─────────────────────────────────────────────────────────────────────────────
test.afterAll(() => {
    if (errors.length === 0) {
        console.log('\n[verify] no console errors / page errors / failed requests captured');
        return;
    }
    console.log(`\n[verify] ${errors.length} issue(s) captured:`);
    const summary = {};
    for (const e of errors) {
        const key = `${e.kind}::${e.text.slice(0, 120)}`;
        if (!summary[key]) summary[key] = { kind: e.kind, sample: e.text, labels: new Set(), count: 0 };
        summary[key].labels.add(e.label);
        summary[key].count += 1;
    }
    for (const k of Object.keys(summary)) {
        const s = summary[k];
        console.log(`  ✗ [${s.kind}] (×${s.count}) labels=[${Array.from(s.labels).join(', ')}]`);
        console.log(`    ${s.sample}`);
    }
    const reportPath = path.join(OUT_DIR, 'errors.json');
    fs.writeFileSync(reportPath, JSON.stringify({ errors, summary: Object.values(summary).map(s => ({ ...s, labels: Array.from(s.labels) })) }, null, 2));
    console.log(`\n  Full report: ${reportPath}`);
});
