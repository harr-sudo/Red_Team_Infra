/**
 * v3-production-rollout 2026-05-19 — Deploy sub-pill audit.
 *
 * Verifies the Composition A spec-list + action strip + live-progress
 * overlay + last-applied attribution + two-stage destroy confirm + dual-
 * theme contrast on the Deploy sub-pill (#subpill-pane-deploy).
 *
 * Skipped assertions are gated on whether a live config is present
 * (the dev harness usually has configs/terraform.tfvars populated); the
 * always-on assertions (legacy-absence, action-strip presence, primary
 * button class) run unconditionally.
 */

import { test, expect } from '@playwright/test';
import { railNavigate, clickSubPill } from './helpers/nav.js';

async function setTheme(page, theme) {
    await page.evaluate((t) => {
        if (t === 'light') document.documentElement.setAttribute('data-theme', 'light');
        else document.documentElement.removeAttribute('data-theme');
    }, theme);
    await page.waitForTimeout(280);
}

async function navigateToDeploySubPill(page) {
    await page.goto('/');
    await railNavigate(page, 'deployments-tab');
    await clickSubPill(page, 'deploy');
    // Give loadConfigSummary + audit fetch time to fire.
    await page.waitForTimeout(700);
}

test('Deploy sub-pill: Composition A spec-list renders with expected rows', async ({ page }) => {
    await navigateToDeploySubPill(page);
    const section = page.locator('#config-summary-section');
    const isVisible = await section.evaluate(el => el.style.display !== 'none');
    if (!isVisible) {
        test.skip(true, 'no live config — skipping spec-list assertions');
        return;
    }
    // The canonical 5 always-present rows
    await expect(page.locator('.spec-row[data-summary-row="type"]')).toBeVisible();
    await expect(page.locator('.spec-row[data-summary-row="project_name"]')).toBeVisible();
    await expect(page.locator('.spec-row[data-summary-row="environment"]')).toBeVisible();
    await expect(page.locator('.spec-row[data-summary-row="aws_region"]')).toBeVisible();
    await expect(page.locator('.spec-row[data-summary-row="management_cidr"]')).toBeVisible();
    // Either key-pair OR ssh-keys row (one of, depending on deployment type)
    const keyRow = page.locator('.spec-row[data-summary-row="key_pair_name"], .spec-row[data-summary-row="ssh_keys"]');
    expect(await keyRow.count()).toBeGreaterThanOrEqual(1);
});

test('Deploy sub-pill: legacy emoji tile grid is gone and inline-config-panel removed', async ({ page }) => {
    await navigateToDeploySubPill(page);
    // Legacy artefacts that v2.5.0 removed
    expect(await page.locator('#config-summary-grid').count(), 'legacy #config-summary-grid must be gone').toBe(0);
    expect(await page.locator('#inline-config-panel').count(), 'legacy #inline-config-panel must be gone').toBe(0);
    // The standalone full-page "Edit Config" CTA is gone — per-row pencils
    // replace it. The validate button moved into the new action strip
    // (#deployment-actions); the legacy #validate-deploy-section wrapper is
    // gone. The action strip is always present and visible.
    expect(await page.locator('#validate-deploy-section').count(), 'legacy validate section wrapper must be gone').toBe(0);
    await expect(page.locator('#deployment-actions')).toBeVisible();
});

test('Deploy sub-pill: Apply is .btn-primary and prominent in the action strip', async ({ page }) => {
    await navigateToDeploySubPill(page);
    const apply = page.locator('#deploy-btn');
    await expect(apply).toBeVisible();
    await expect(apply).toHaveClass(/btn-primary/);
    await expect(apply).toHaveAttribute('data-deploy-action', 'apply');
});

test('Deploy sub-pill: Plan button is present and disabled until validate', async ({ page }) => {
    await navigateToDeploySubPill(page);
    const plan = page.locator('#deploy-plan-btn');
    await expect(plan).toBeVisible();
    await expect(plan).toHaveAttribute('data-deploy-action', 'plan');
    // Initial state: disabled (action strip locked until validate)
    await expect(plan).toBeDisabled();
});

test('Deploy sub-pill: Destroy button shows two-stage confirm panel', async ({ page }) => {
    await navigateToDeploySubPill(page);
    // Force-unlock the action strip via the exposed helper so we can drive
    // the destroy click without going through a real validate cycle.
    await page.evaluate(() => {
        if (typeof window._setDeployActionsEnabled === 'function') {
            window._setDeployActionsEnabled(true);
        } else if (typeof _setDeployActionsEnabled === 'function') {
            _setDeployActionsEnabled(true);
        } else {
            ['deploy-btn', 'deploy-plan-btn', 'deploy-destroy-btn'].forEach(id => {
                const el = document.getElementById(id);
                if (el) { el.removeAttribute('disabled'); el.removeAttribute('aria-disabled'); }
            });
        }
    });
    const destroy = page.locator('#deploy-destroy-btn');
    await expect(destroy).toBeVisible();
    await expect(destroy).toHaveClass(/btn-danger/);
    // Stage 1: panel hidden by default
    const panel = page.locator('#deploy-destroy-confirm');
    await expect(panel).toHaveAttribute('hidden', /.*/);
    // Click Destroy → panel becomes visible
    await destroy.click();
    await expect(panel).not.toHaveAttribute('hidden', /.*/);
    await expect(page.locator('#deploy-destroy-confirm-btn')).toBeVisible();
    // Click Cancel → panel hidden again
    await panel.locator('button.btn-secondary').click();
    await expect(panel).toHaveAttribute('hidden', /.*/);
});

test('Deploy sub-pill: action strip stays gated until Validate runs', async ({ page }) => {
    await navigateToDeploySubPill(page);
    // Validate button itself is always interactive
    await expect(page.locator('#validate-deploy-btn')).toBeEnabled();
    // Apply / Plan / Destroy locked
    await expect(page.locator('#deploy-btn')).toBeDisabled();
    await expect(page.locator('#deploy-plan-btn')).toBeDisabled();
    await expect(page.locator('#deploy-destroy-btn')).toBeDisabled();
});

test('Deploy sub-pill: Last applied by attribution row renders with operator dot when audit exists', async ({ page }) => {
    await navigateToDeploySubPill(page);
    // Stub the audit endpoint so we can deterministically assert the row.
    await page.route('**/api/audit?action_prefix=deploy.*', (route) => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                success: true,
                entries: [{
                    op: 'alice',
                    action: 'deploy.apply',
                    ts: new Date(Date.now() - 7200_000).toISOString(),
                    project: 'unit_test_project',
                }],
            }),
        });
    });
    // Trigger a reload of the summary so the stubbed audit fetch runs.
    const triggered = await page.evaluate(() => {
        if (typeof loadConfigSummary === 'function') {
            return loadConfigSummary().then(() => true).catch(() => false);
        }
        return false;
    });
    if (!triggered) {
        test.skip(true, 'loadConfigSummary not available in window scope');
        return;
    }
    await page.waitForTimeout(400);
    const section = page.locator('#config-summary-section');
    const isVisible = await section.evaluate(el => el.style.display !== 'none');
    if (!isVisible) {
        test.skip(true, 'no live config — skipping attribution assertion');
        return;
    }
    const row = page.locator('.spec-row[data-summary-row="last_applied"]');
    await expect(row).toBeVisible();
    // Operator dot present
    await expect(row.locator('.operator-dot')).toHaveCount(1);
    // Operator name renders
    await expect(row.locator('[data-deploy-attr-operator]')).toHaveText(/alice/);
    // Relative time renders (matches "Nh ago" / "N min ago" / "Nd ago")
    await expect(row.locator('[data-deploy-attr-time]')).toContainText(/ago|just now/);
});

test('Deploy sub-pill: live progress opens APP.overlay when startDeployment fires', async ({ page }) => {
    await navigateToDeploySubPill(page);
    // Stub the deploy POST so we can drive the overlay flow without
    // actually starting terraform. Use `*` suffix so the glob matches the
    // `?project=...` query string the production code appends.
    await page.route('**/api/deploy/deploy*', (route) => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ success: true, message: 'started', project_name: 'unit_test_project' }),
        });
    });
    // Stub status polling so updateDeploymentUI has something benign to render.
    await page.route('**/api/deploy/status*', (route) => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ success: true, status: { status: 'running', progress_percent: 5, step: 'Initialising', logs: [] } }),
        });
    });
    // Stub everything startDeployment pre-checks so it doesn't bail on
    // SSH/CS/domain/AWS prerequisite failures.
    await page.route('**/api/deploy/ssh-public-key', (route) => route.fulfill({ status: 200, body: JSON.stringify({ has_key: true, valid: true }) }));
    await page.route('**/api/health/cobalt-strike-file', (route) => route.fulfill({ status: 200, body: JSON.stringify({ success: true, has_file: true }) }));
    await page.route('**/api/health/domain-config', (route) => route.fulfill({ status: 200, body: JSON.stringify({ success: true, configured: true }) }));
    await page.route('**/api/health/aws-cli', (route) => route.fulfill({ status: 200, body: JSON.stringify({ success: true, installed: true }) }));
    // 2026-05-28 — HIGH #6 fix added /aws-check/credentials to startDeployment's
    // prereq pipeline (commit 9dffae9). Without this stub, the test bails on
    // STS validation before opening the overlay.
    await page.route('**/api/aws-check/credentials', (route) => route.fulfill({ status: 200, body: JSON.stringify({ authenticated: true }) }));
    // Bypass confirm() and force the project name + deployment type.
    // 2026-05-21 legacy-audit sweep — prefer V2 IDs (#cfg-*) when present;
    // fall back to the legacy form inputs (#project-name, #deployment-type)
    // only while the legacy block survives in the DOM. Once the parallel
    // frontend agent retires the legacy form per UX_AUDIT M1, the fallback
    // arm becomes a no-op and can be removed.
    // 2026-05-23 — Also pin draftProject so startDeployment's
    // effectiveProject() resolves to 'unit_test_project'. Without this,
    // startDeployment bails before opening the overlay because draft
    // mode + no draftProject returns null.
    await page.evaluate(() => {
        window.confirm = () => true;
        window.alert = () => undefined;
        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.value = val;
        };
        setVal('cfg-project-name', 'unit_test_project');
        setVal('cfg-deployment-type', 'c2-adhoc');
        setVal('project-name', 'unit_test_project');
        setVal('deployment-type', 'c2-adhoc');
        if (window.APP && window.APP.activeDeployment) {
            window.APP.activeDeployment.draftProject = 'unit_test_project';
        }
    });
    // Fire startDeployment
    const ok = await page.evaluate(async () => {
        if (typeof startDeployment !== 'function') return false;
        await startDeployment();
        return true;
    });
    if (!ok) {
        test.skip(true, 'startDeployment not in window scope');
        return;
    }
    await page.waitForTimeout(400);
    // Overlay should be open with id "deploy:<project>"
    const overlay = page.locator('.app-overlay[data-overlay-id="deploy:unit_test_project"]');
    await expect(overlay).toBeVisible();
    await expect(overlay.locator('.app-overlay__title')).toHaveText(/Deploying unit_test_project/);
    await expect(overlay.locator('.app-overlay__eyebrow')).toHaveText(/Live Deploy/i);
});

for (const theme of ['dark', 'light']) {
    test(`Deploy sub-pill: action strip + destroy confirm pass AA contrast (${theme} theme)`, async ({ page }) => {
        await navigateToDeploySubPill(page);
        await setTheme(page, theme);
        // Open destroy-confirm so its surface gets contrast-walked
        await page.evaluate(() => {
            if (typeof window._setDeployActionsEnabled === 'function') {
                window._setDeployActionsEnabled(true);
            }
            const p = document.getElementById('deploy-destroy-confirm');
            if (p) p.hidden = false;
        });
        const failures = await page.evaluate(({ rootSels }) => {
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
            const all = [];
            rootSels.forEach((sel) => {
                const root = document.querySelector(sel);
                if (!root) return;
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
                        all.push({
                            root: sel,
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
            });
            return all;
        }, { rootSels: ['#deployment-actions', '#validate-deploy-hint', '#deploy-destroy-confirm'] });

        if (failures.length) {
            // eslint-disable-next-line no-console
            console.log(`Deploy action strip (${theme}) contrast failures:`, JSON.stringify(failures, null, 2));
        }
        expect(failures, `${failures.length} AA failures in ${theme}`).toEqual([]);
    });
}
