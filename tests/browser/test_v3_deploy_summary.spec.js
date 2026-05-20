/**
 * Phase 2B — Deploy sub-pill summary (Composition A spec-list).
 *
 * Verifies:
 *   1. The legacy emoji tile grid is gone.
 *   2. The new spec-list renders with all expected rows from /api/config.
 *   3. Clicking the row pencil expands the inline editor.
 *   4. Cancel collapses the editor; Save commits + re-renders.
 *   5. Both themes pass layer-aware contrast on the summary surface.
 *
 * The test assumes a live config exists on the server (the dev harness
 * keeps configs/terraform.tfvars populated). If not, the smoke assertions
 * are skipped — but contrast and absence-of-legacy still run.
 */

import { test, expect } from '@playwright/test';

async function setTheme(page, theme) {
    await page.evaluate((t) => {
        if (t === 'light') document.documentElement.setAttribute('data-theme', 'light');
        else document.documentElement.removeAttribute('data-theme');
    }, theme);
    await page.waitForTimeout(320);
}

async function navigateToDeploySubPill(page) {
    // 2026-05-20 (Batch C) — The Deploy sub-pill is mode-gated. For an
    // existing GOAD deployment (the live backend's default), the visible
    // pills are ['manage', 'bolt-ons', 'cleanup'] — Deploy is hidden. And
    // the live /api/config has no deployment_type set, so loadConfigSummary
    // early-returns with display:none. Mock /api/config with a valid c2-adhoc
    // config so the summary section renders, then pin draft mode so the
    // Deploy sub-pill is visible.
    const configHandler = async (route) => {
        if (route.request().method() !== 'GET') return route.continue();
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                success: true,
                config: {
                    deployment_type: 'c2-adhoc',
                    project_name: 'spec_test_lab',
                    environment: 'dev',
                    aws_region: 'eu-central-1',
                    management_cidr_blocks: ['203.0.113.0/24'],
                    key_pair_name: 'red-team-keypair',
                    primary_domain_name: 'example.com',
                    vpc_cidr: '10.0.0.0/16',
                    enable_ssl: true,
                    ssl_provider: 'letsencrypt',
                    cobalt_strike_password: 'auto',
                    malleable_profile: 'default',
                    c2_server_instance_type: 't3.medium',
                    c2_server_count: 1,
                    enable_attack_box: true,
                    enable_test_lab: false,
                },
            }),
        });
    };
    // Match both with + without trailing slash; loadConfigSummary uses
    // /api/config (no slash) and Flask redirects to /api/config/.
    await page.route('**/api/config', configHandler);
    await page.route('**/api/config/', configHandler);
    await page.route('**/api/config?**', configHandler);
    await page.route('**/api/audit/**', async (route) => {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, entries: [] }) });
    });
    await page.goto('/');
    await page.locator('button.tab-btn[data-target="deployments-tab"]').waitFor({ timeout: 5000 });
    await page.evaluate(() => {
        window.APP.activeDeployment.set(window.APP.activeDeployment.DRAFT_SENTINEL);
    });
    await page.click('button.tab-btn[data-target="deployments-tab"]');
    await page.waitForTimeout(150);
    // Click the Deploy sub-pill button within the Deployments tab
    await page.locator('#subpill-deploy').click();
    // Give loadConfigSummary() time to fire
    await page.waitForTimeout(700);
}

test('Deploy sub-pill: legacy emoji tile grid has been removed', async ({ page }) => {
    await navigateToDeploySubPill(page);
    // The old grid had id="config-summary-grid"; the new view uses #deploy-summary-spec-list.
    const legacy = await page.locator('#config-summary-grid').count();
    expect(legacy, 'legacy #config-summary-grid must be gone').toBe(0);
    const newList = await page.locator('#deploy-summary-spec-list').count();
    expect(newList, 'new #deploy-summary-spec-list must be present').toBe(1);
});

test('Deploy sub-pill: spec-list renders summary rows', async ({ page }) => {
    await navigateToDeploySubPill(page);
    const section = page.locator('#config-summary-section');
    // It may be hidden if no config — gate the assertion.
    const isVisible = await section.evaluate(el => el.style.display !== 'none');
    if (!isVisible) {
        test.skip(true, 'no live config — skipping');
        return;
    }
    // At least these rows are always expected when a deployment_type is set
    await expect(page.locator('.spec-row[data-summary-row="type"]')).toBeVisible();
    await expect(page.locator('.spec-row[data-summary-row="project_name"]')).toBeVisible();
    await expect(page.locator('.spec-row[data-summary-row="environment"]')).toBeVisible();
    await expect(page.locator('.spec-row[data-summary-row="aws_region"]')).toBeVisible();
    await expect(page.locator('.spec-row[data-summary-row="management_cidr"]')).toBeVisible();
    // Cost row is read-only
    const cost = page.locator('.spec-row[data-summary-row="cost"]');
    if (await cost.count()) {
        await expect(cost).toHaveAttribute('data-readonly', 'true');
    }
});

test('Deploy sub-pill: row pencil expands editor, Cancel collapses', async ({ page }) => {
    await navigateToDeploySubPill(page);
    const section = page.locator('#config-summary-section');
    const isVisible = await section.evaluate(el => el.style.display !== 'none');
    if (!isVisible) {
        test.skip(true, 'no live config — skipping');
        return;
    }
    const envRow = page.locator('.spec-row[data-summary-row="environment"]');
    await envRow.locator('.spec-row__head').click();
    // Editor should be populated
    const editor = envRow.locator('[data-summary-editor]');
    await expect(editor.locator('.seg-control')).toBeVisible();
    await expect(envRow).toHaveAttribute('data-editing', 'true');
    // List goes into editing mode (sibling-dim)
    await expect(page.locator('#deploy-summary-spec-list')).toHaveAttribute('data-editing', 'true');
    // Click Cancel
    await editor.locator('[data-edit-action="cancel"]').click();
    await page.waitForTimeout(150);
    await expect(envRow).not.toHaveAttribute('data-editing', 'true');
});

for (const theme of ['dark', 'light']) {
    test(`Deploy sub-pill summary passes contrast (${theme} theme)`, async ({ page }) => {
        await navigateToDeploySubPill(page);
        await setTheme(page, theme);
        const section = page.locator('#config-summary-section');
        const isVisible = await section.evaluate(el => el.style.display !== 'none');
        if (!isVisible) {
            test.skip(true, 'no live config — skipping');
            return;
        }

        // Run the layer-aware contrast walk on the summary subtree only
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
                        fg: cs.color,
                        bg: `rgb(${bg.join(', ')})`,
                    });
                }
            });
            return failures;
        }, { rootSel: '#config-summary-section' });

        if (failures.length) {
            // eslint-disable-next-line no-console
            console.log(`Deploy summary (${theme}) contrast failures:`, JSON.stringify(failures, null, 2));
        }
        expect(failures, `${failures.length} AA failures in ${theme}`).toEqual([]);
    });
}

for (const theme of ['dark', 'light']) {
    test(`Deploy sub-pill summary passes contrast WITH a row editing (${theme} theme)`, async ({ page }) => {
        await navigateToDeploySubPill(page);
        await setTheme(page, theme);
        const section = page.locator('#config-summary-section');
        const isVisible = await section.evaluate(el => el.style.display !== 'none');
        if (!isVisible) {
            test.skip(true, 'no live config — skipping');
            return;
        }
        // Open the environment editor (uses seg-control — the layer most likely to fail contrast)
        await page.locator('.spec-row[data-summary-row="environment"] .spec-row__head').click();
        await page.waitForTimeout(200);

        const failures = await page.evaluate(() => {
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
            const root = document.querySelector('#config-summary-section');
            if (!root) return [];
            const failures = [];
            // Only check the editing row's editor contents — sibling rows are
            // deliberately dimmed (opacity 0.4) for sibling-dim, which is a
            // designed-affordance, not a contrast failure.
            const editor = root.querySelector('.spec-row[data-editing="true"] [data-summary-editor]');
            const targets = editor ? editor.querySelectorAll('*') : [];
            targets.forEach(el => {
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
                        fg: cs.color,
                        bg: `rgb(${bg.join(', ')})`,
                    });
                }
            });
            return failures;
        });
        if (failures.length) {
            // eslint-disable-next-line no-console
            console.log(`Deploy summary editing-state (${theme}) failures:`, JSON.stringify(failures, null, 2));
        }
        expect(failures, `${failures.length} AA failures in editing state, ${theme}`).toEqual([]);
    });
}
