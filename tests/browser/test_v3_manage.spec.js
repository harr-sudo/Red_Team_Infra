/**
 * Phase 3a — Manage sub-pill (Deployments tab → Manage).
 *
 * Verifies the V3-native rebuild:
 *   1. Manage sub-pill loads with a project selected, key elements visible.
 *   2. Spec-list renders with the expected rows from /api/deploy/infrastructure.
 *   3. Last-touched-by attribution surfaces an operator name when the audit
 *      log has at least one deploy.* entry for the project.
 *   4. Both themes pass layer-aware contrast on the Manage view surface.
 *
 * Assumes the dev harness keeps an active deployment + non-empty audit log.
 * If neither exists, smoke assertions are skipped (contrast still runs).
 */

import { test, expect } from '@playwright/test';

async function setTheme(page, theme) {
    await page.evaluate((t) => {
        if (t === 'light') document.documentElement.setAttribute('data-theme', 'light');
        else document.documentElement.removeAttribute('data-theme');
    }, theme);
    await page.waitForTimeout(320);
}

async function navigateToManageSubPill(page) {
    await page.goto('/');
    await page.locator('button.tab-btn[data-target="deployments-tab"]').waitFor({ timeout: 5000 });
    await page.click('button.tab-btn[data-target="deployments-tab"]');
    await page.waitForTimeout(150);
    // Click the Manage sub-pill button within the Deployments tab.
    await page.locator('#subpill-manage').click();
    // Give APP.manage.render() time to fire + fetch in parallel.
    await page.waitForTimeout(900);
}

test('Manage sub-pill: V3 chrome (hero + spec-list + actions strip) is mounted', async ({ page }) => {
    await navigateToManageSubPill(page);
    // The new V3 frame is always present (even if .display = 'none' when no project).
    await expect(page.locator('#manage-view')).toHaveCount(1);
    await expect(page.locator('#manage-hero-name')).toHaveCount(1);
    await expect(page.locator('#manage-hero-type')).toHaveCount(1);
    await expect(page.locator('#manage-spec-list')).toHaveCount(1);
    await expect(page.locator('#manage-actions')).toHaveCount(1);
    // The four action buttons by data-attr.
    await expect(page.locator('[data-manage-action="refresh"]')).toHaveCount(1);
    await expect(page.locator('[data-manage-action="logs"]')).toHaveCount(1);
    await expect(page.locator('[data-manage-action="health"]')).toHaveCount(1);
    await expect(page.locator('[data-manage-action="destroy"]')).toHaveCount(1);
});

test('Manage sub-pill: status pill renders with one of the three variants', async ({ page }) => {
    await navigateToManageSubPill(page);
    const pill = page.locator('#manage-status-pill');
    await expect(pill).toHaveCount(1);
    // Wait for the pill to settle into one of the three states.
    await page.waitForTimeout(400);
    const cls = await pill.getAttribute('class');
    expect(cls).toBeTruthy();
    const hasVariant =
        cls.includes('spec-pill--live') ||
        cls.includes('spec-pill--draft') ||
        cls.includes('spec-pill--error');
    expect(hasVariant, 'pill must carry a live/draft/error variant').toBe(true);
});

test('Manage sub-pill: spec-list renders expected resource rows when a project is selected', async ({ page }) => {
    await navigateToManageSubPill(page);
    // Force a project so render() exits the no-project empty state.
    const hasProject = await page.evaluate(() => {
        const p = window.APP && window.APP.activeDeployment && window.APP.activeDeployment.current;
        return !!p;
    });
    if (!hasProject) {
        // Try to pick the first deployment from the header selector.
        const opts = await page.evaluate(() => {
            const sel = document.querySelector('#header-deployment-select, #project-name');
            if (!sel || sel.tagName !== 'SELECT') return [];
            return Array.from(sel.options).map(o => o.value).filter(Boolean);
        });
        if (opts.length === 0) {
            test.skip(true, 'no active deployment in dev harness — skipping spec-list rows');
            return;
        }
        await page.evaluate((p) => {
            if (window.APP && window.APP.activeDeployment) window.APP.activeDeployment.set(p);
        }, opts[0]);
        await page.waitForTimeout(700);
    }
    // Trigger render explicitly so we don't race the auto-init.
    await page.evaluate(async () => {
        if (window.APP && window.APP.manage && window.APP.manage.render) {
            await window.APP.manage.render();
        }
    });
    await page.waitForTimeout(400);
    // The region row is always rendered (defaults to eu-central-1).
    await expect(page.locator('.spec-row[data-manage-row="region"]')).toBeVisible();
    // Instances row is always present (renders '—' if no infra).
    await expect(page.locator('.spec-row[data-manage-row="instances"]')).toBeVisible();
});

test('Manage sub-pill: last-touched-by attribution surfaces operator name when audit data exists', async ({ page }) => {
    // Probe the audit endpoint directly. If empty, skip.
    const auditResp = await page.request.get('/api/audit?action_prefix=deploy.&limit=1');
    const auditBody = await auditResp.json();
    if (!auditBody || !auditBody.success || !(auditBody.entries || []).length) {
        test.skip(true, 'no deploy.* audit entries — skipping attribution surface');
        return;
    }
    const entry = auditBody.entries[0];
    const project = entry.project;
    if (!project) {
        test.skip(true, 'audit entry lacks a project — skipping');
        return;
    }
    await navigateToManageSubPill(page);
    await page.evaluate((p) => {
        if (window.APP && window.APP.activeDeployment) window.APP.activeDeployment.set(p);
    }, project);
    await page.waitForTimeout(800);
    // Re-render in case the activeDeployment subscriber didn't fire fast enough.
    await page.evaluate(async () => {
        if (window.APP && window.APP.manage && window.APP.manage.render) {
            await window.APP.manage.render();
        }
    });
    await page.waitForTimeout(400);
    const attrRow = page.locator('.spec-row[data-manage-row="last_touched"]');
    await expect(attrRow, 'last-touched row must render when audit data exists').toBeVisible();
    // The operator name token must be present (either .manage-attr or the unknown variant).
    const attrText = await attrRow.locator('.manage-attr').first().textContent();
    expect(attrText && attrText.trim().length > 0, 'attribution token must have text').toBe(true);
});

for (const theme of ['dark', 'light']) {
    test(`Manage sub-pill: passes layer-aware contrast (${theme} theme)`, async ({ page }) => {
        await navigateToManageSubPill(page);
        await setTheme(page, theme);

        // Force-render in case the empty state is up.
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
                        fg: cs.color,
                        bg: `rgb(${bg.join(', ')})`,
                    });
                }
            });
            return failures;
        }, { rootSel: '#manage-view' });

        if (failures.length) {
            // eslint-disable-next-line no-console
            console.log(`Manage view (${theme}) contrast failures:`, JSON.stringify(failures, null, 2));
        }
        expect(failures, `${failures.length} AA failures in ${theme}`).toEqual([]);
    });
}
