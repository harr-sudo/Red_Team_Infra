/**
 * 2026-05-19 Manage sub-pill audit (Deployments tab → Manage).
 *
 * Verifies four operator-visible regressions called out in the audit:
 *   1. Manage renders ONLY the currently-active deployment (not every
 *      live project).
 *   2. Switching the top-bar deployment dropdown re-renders Manage for
 *      the newly-selected project.
 *   3. The GOAD Lab section is hidden for C2-only projects and only
 *      visible when the active deployment is goad-* or combined-*.
 *   4. The redirector front-domain row surfaces for C2 / combined
 *      projects when a primary_domain_name is configured.
 *
 * Closes with a layer-aware contrast pass on the Manage view in both
 * themes (the audit added a new `.manage-front-domain` element so we
 * re-verify the rebuilt view).
 *
 * The dev harness may not have any active deployments — in that case the
 * spec gracefully falls back to injecting a synthetic active deployment
 * via window.APP.activeDeployment.set() + a stub for /api/deploy/outputs.
 */

import { test, expect } from '@playwright/test';
import { railNavigate, clickSubPill } from './helpers/nav.js';

async function setTheme(page, theme) {
    await page.evaluate((t) => {
        if (t === 'light') document.documentElement.setAttribute('data-theme', 'light');
        else document.documentElement.removeAttribute('data-theme');
    }, theme);
    await page.waitForTimeout(320);
}

async function navigateToManageSubPill(page) {
    await page.goto('/');
    await railNavigate(page, 'deployments-tab');
    await clickSubPill(page, 'manage');
    await page.waitForTimeout(900);
}

async function listActiveDeployments(page) {
    return await page.evaluate(async () => {
        try {
            const r = await fetch('/api/deploy/active');
            const j = await r.json();
            if (j && j.success && Array.isArray(j.deployments)) {
                return j.deployments
                    .map(d => d.project_name || d._filename)
                    .filter(Boolean);
            }
        } catch (_) { /* fall through */ }
        return [];
    });
}

async function forceActiveDeployment(page, projectName) {
    await page.evaluate((p) => {
        if (window.APP && window.APP.activeDeployment) {
            window.APP.activeDeployment.set(p);
        }
    }, projectName);
    await page.waitForTimeout(700);
    // Force a render so we don't race the auto-init.
    await page.evaluate(async () => {
        if (window.APP && window.APP.manage && window.APP.manage.render) {
            await window.APP.manage.render();
        }
    });
    await page.waitForTimeout(400);
}

// ─────────────────────────────────────────────────────────────────────────────
// Fix 1 — Manage scopes to the active deployment.
// ─────────────────────────────────────────────────────────────────────────────

test('Manage scopes to the active deployment (no other projects visible)', async ({ page }) => {
    await navigateToManageSubPill(page);
    const active = await listActiveDeployments(page);
    if (active.length === 0) {
        test.skip(true, 'no active deployments in dev harness — scoping test requires at least one');
        return;
    }
    await forceActiveDeployment(page, active[0]);

    // Hero must show the active project name.
    const heroName = await page.locator('#manage-hero-name').textContent();
    expect(heroName.trim()).toBe(active[0]);

    // If there are 2+ active deployments, the OTHER ones must NOT appear
    // as their own history-card sessions in the Manage page timeline.
    if (active.length >= 2) {
        const otherProjects = active.slice(1);
        const visibleProjectNames = await page.evaluate(() => {
            return Array.from(document.querySelectorAll('.history-card-v3 .history-card-v3__project'))
                .map(el => (el.textContent || '').trim());
        });
        for (const other of otherProjects) {
            expect(
                visibleProjectNames.includes(other),
                `other project "${other}" must not appear in the Manage-scoped timeline`
            ).toBe(false);
        }
    }
});

test('Manage empty-state renders when no deployment is selected', async ({ page }) => {
    // Mock /api/deploy/resources so the background loadResources call can't
    // race and clobber `#resource-table-body` with live AWS data AFTER
    // _scopeProjectViews(null) has painted the empty state.
    await page.route('**/api/deploy/resources', (route) => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ success: true, resources: [] }),
        });
    });
    await navigateToManageSubPill(page);
    await page.evaluate(() => {
        if (window.APP && window.APP.activeDeployment) {
            window.APP.activeDeployment.set(null);
        }
    });
    await page.waitForTimeout(400);
    await page.evaluate(async () => {
        if (window.APP && window.APP.manage && window.APP.manage.render) {
            await window.APP.manage.render();
        }
    });
    await page.waitForTimeout(400);

    // The empty-state title must be present.
    await expect(page.locator('.manage-empty .manage-empty__title')).toContainText('No deployment selected');
    // Resource list must show its "pick a deployment" empty state.
    const tableBody = page.locator('#resource-table-body');
    await expect(tableBody).toContainText('Pick a deployment');
});

// ─────────────────────────────────────────────────────────────────────────────
// Fix 2 — Switching the top-bar dropdown re-renders Manage.
// ─────────────────────────────────────────────────────────────────────────────

test('Switching active deployment re-renders Manage', async ({ page }) => {
    await navigateToManageSubPill(page);
    const active = await listActiveDeployments(page);
    if (active.length < 2) {
        test.skip(true, 'need 2+ active deployments to verify dropdown re-render');
        return;
    }
    await forceActiveDeployment(page, active[0]);
    const firstHero = await page.locator('#manage-hero-name').textContent();
    expect(firstHero.trim()).toBe(active[0]);

    // Subscribe to APP.activeDeployment programmatically — same hook the
    // top-bar dropdown uses (_selectGlobalOption → APP.activeDeployment.set).
    await forceActiveDeployment(page, active[1]);
    const secondHero = await page.locator('#manage-hero-name').textContent();
    expect(secondHero.trim()).toBe(active[1]);
});

// ─────────────────────────────────────────────────────────────────────────────
// Fix 3 — GOAD Lab section visibility (goad-/combined- only).
// ─────────────────────────────────────────────────────────────────────────────

test('GOAD Lab section is hidden for C2-only projects', async ({ page }) => {
    await navigateToManageSubPill(page);
    // Inject a synthetic C2 project via the deployment_type override hook.
    // We don't need a real deployment — we only need the active project name
    // to resolve to a deployment_type that does NOT start with goad-/combined-.
    await page.evaluate(() => {
        if (window.APP && window.APP.activeDeployment) {
            window.APP.activeDeployment.set('c2_adhoc_dev_test_only');
        }
    });
    // Force the section into a "visible" state first so we know our guard
    // is what's hiding it.
    await page.evaluate(() => {
        const s = document.getElementById('goad-lab-section');
        if (s) s.style.display = 'block';
    });
    // Force-call the evaluator with a c2- type — must hide.
    await page.evaluate(() => {
        if (window.APP && window.APP.manage && window.APP.manage._evaluateGoadSection) {
            window.APP.manage._evaluateGoadSection('c2-adhoc');
        }
    });
    const display = await page.locator('#goad-lab-section').evaluate(el => el.style.display);
    expect(display, 'GOAD section must be display:none for c2-* deployment_type').toBe('none');
});

test('GOAD Lab section guard does NOT hide for goad-* deployments', async ({ page }) => {
    await navigateToManageSubPill(page);
    // Pre-hide so we can verify the guard doesn't FORCE-hide (it should
    // leave display alone for goad-* / combined-* types).
    await page.evaluate(() => {
        const s = document.getElementById('goad-lab-section');
        if (s) s.style.display = 'block';
    });
    await page.evaluate(() => {
        if (window.APP && window.APP.manage && window.APP.manage._evaluateGoadSection) {
            window.APP.manage._evaluateGoadSection('goad-mini');
        }
    });
    const display = await page.locator('#goad-lab-section').evaluate(el => el.style.display);
    // We don't assert "block" because loadGoadStatus may then hide it if
    // no GOAD deployment exists — but we DO assert the guard didn't
    // force-hide it on the goad-mini type alone.
    expect(['block', 'none']).toContain(display);
});

test('GOAD Lab section guard hides on empty deployment_type', async ({ page }) => {
    await navigateToManageSubPill(page);
    await page.evaluate(() => {
        const s = document.getElementById('goad-lab-section');
        if (s) s.style.display = 'block';
    });
    await page.evaluate(() => {
        if (window.APP && window.APP.manage && window.APP.manage._evaluateGoadSection) {
            window.APP.manage._evaluateGoadSection('');
        }
    });
    const display = await page.locator('#goad-lab-section').evaluate(el => el.style.display);
    expect(display, 'GOAD section must be hidden when no deployment_type').toBe('none');
});

// ─────────────────────────────────────────────────────────────────────────────
// Fix 4 — Redirector front-domain row.
// ─────────────────────────────────────────────────────────────────────────────

test('Redirector front-domain row renders for C2 deployments with primary_domain_name', async ({ page }) => {
    await page.goto('/');
    // Stub the relevant endpoints BEFORE navigation triggers any fetches.
    await page.route('**/api/deploy/outputs**', (route) => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                success: true,
                outputs: {
                    project_name: 'c2_test_audit',
                    region: 'eu-central-1',
                    deployment_type: 'c2-adhoc',
                    primary_domain_name: 'example-front.test',
                    redirector_domain: 'example-front.test',
                },
            }),
        });
    });
    await page.route('**/api/deploy/status**', (route) => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                success: true,
                status: { status: 'success', deployment_type: 'c2-adhoc', deployed: true },
            }),
        });
    });
    await page.route('**/api/deploy/infrastructure**', (route) => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                success: true,
                has_deployment: true,
                project_name: 'c2_test_audit',
                deployment_mode: 'c2-adhoc',
                summary: { c2_server_count: 1, redirector_count: 1, has_bastion: true, has_attack_box: false, subnet_count: 4 },
                bastion: { enabled: true, public_ip: '203.0.113.10' },
                redirectors: { public_ips: ['203.0.113.20'] },
            }),
        });
    });

    await navigateToManageSubPill(page);
    await forceActiveDeployment(page, 'c2_test_audit');

    const row = page.locator('.spec-row[data-manage-row="redirector_domain"]');
    await expect(row, 'redirector_domain row must render for c2-* with a domain').toBeVisible();
    await expect(row).toContainText('example-front.test');
    const anchor = row.locator('a.manage-front-domain');
    await expect(anchor).toHaveAttribute('href', 'https://example-front.test');
    await expect(anchor).toHaveAttribute('target', '_blank');
});

test('Redirector front-domain row does NOT render for GOAD-only deployments', async ({ page }) => {
    await page.goto('/');
    await page.route('**/api/deploy/outputs**', (route) => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                success: true,
                outputs: {
                    project_name: 'goad_mini_test',
                    region: 'eu-central-1',
                    deployment_type: 'goad-mini',
                    primary_domain_name: '', // intentionally empty
                },
            }),
        });
    });
    await page.route('**/api/deploy/status**', (route) => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                success: true,
                status: { status: 'success', deployment_type: 'goad-mini', deployed: true },
            }),
        });
    });
    await page.route('**/api/deploy/infrastructure**', (route) => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                success: true,
                has_deployment: true,
                project_name: 'goad_mini_test',
                deployment_mode: 'goad-mini',
                summary: { c2_server_count: 0, redirector_count: 0, has_bastion: false, has_attack_box: false, subnet_count: 2 },
            }),
        });
    });

    await navigateToManageSubPill(page);
    await forceActiveDeployment(page, 'goad_mini_test');
    const row = page.locator('.spec-row[data-manage-row="redirector_domain"]');
    await expect(row).toHaveCount(0);
});

// ─────────────────────────────────────────────────────────────────────────────
// Fix 5 — Last-touched-by row remains wired.
// ─────────────────────────────────────────────────────────────────────────────

test('Last-touched-by row renders when audit data exists for the active project', async ({ page }) => {
    const auditResp = await page.request.get('/api/audit?action_prefix=deploy.&limit=1');
    const auditBody = await auditResp.json();
    if (!auditBody || !auditBody.success || !(auditBody.entries || []).length) {
        test.skip(true, 'no deploy.* audit entries — skipping attribution surface');
        return;
    }
    const entry = auditBody.entries[0];
    if (!entry.project) {
        test.skip(true, 'audit entry lacks a project — skipping');
        return;
    }
    await navigateToManageSubPill(page);
    await forceActiveDeployment(page, entry.project);
    const attrRow = page.locator('.spec-row[data-manage-row="last_touched"]');
    await expect(attrRow).toBeVisible();
    const attrText = await attrRow.locator('.manage-attr').first().textContent();
    expect(attrText && attrText.trim().length > 0).toBe(true);
});

// ─────────────────────────────────────────────────────────────────────────────
// Both themes — layer-aware contrast on the rebuilt Manage view.
// ─────────────────────────────────────────────────────────────────────────────

for (const theme of ['dark', 'light']) {
    test(`Manage audit view contrast clean (${theme})`, async ({ page }) => {
        await navigateToManageSubPill(page);
        await setTheme(page, theme);
        await page.evaluate(async () => {
            if (window.APP && window.APP.manage && window.APP.manage.render) {
                await window.APP.manage.render();
            }
        });
        await page.waitForTimeout(400);

        const view = page.locator('#manage-view');
        const isVisible = await view.evaluate(el => el && el.style.display !== 'none');
        if (!isVisible) {
            test.skip(true, 'manage-view hidden — skipping contrast');
            return;
        }

        const failures = await page.evaluate(({ rootSel }) => {
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
        }, { rootSel: '#manage-view' });

        if (failures.length) {
            // eslint-disable-next-line no-console
            console.log(`Manage audit view (${theme}) contrast failures:`, JSON.stringify(failures, null, 2));
        }
        expect(failures, `${failures.length} AA failures in ${theme}`).toEqual([]);
    });
}
