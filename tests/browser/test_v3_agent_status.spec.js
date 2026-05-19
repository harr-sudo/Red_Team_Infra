/**
 * task #52 — Detection Agent (bolt-on agentic fallback) status surfacing.
 *
 * Coverage:
 *   1. Settings → Prereqs renders the new "Detection Agent" check row.
 *   2. When /api/health/agent returns configured=false, the row shows
 *      the draft pill + a remediation callout.
 *   3. When configured=true, the row shows the live pill (no callout).
 *   4. When SDK is missing, the row shows the error pill + callout.
 *   5. The bolt-on STUCK overlay disables Invoke Agent when configured=false.
 *   6. The bolt-on STUCK overlay keeps Invoke Agent enabled when configured=true.
 *   7. Both themes: contrast clean on the new row + disabled overlay state.
 *
 * The bolt-on overlay test drives APP.bolton._showAgentPanel directly so
 * we don't need to stand up a full STUCK job (the install-service stub
 * path would require BOLTON_SIMULATE_ANSIBLE=1 plus a forced status flip).
 */

import { test, expect } from '@playwright/test';

// ─── WCAG helpers (mirrors test_v3_settings.spec.js) ─────────────────────

function parseRgb(s) {
    const m = s.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const parts = m[1].split(',').map((p) => parseFloat(p.trim()));
    return [parts[0], parts[1], parts[2], parts.length === 4 ? parts[3] : 1];
}
function lin(c) {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
}
function lum([r, g, b]) {
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}
function contrast(a, b) {
    const L1 = lum(a);
    const L2 = lum(b);
    return (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
}

async function setTheme(page, theme) {
    await page.evaluate((t) => {
        if (t === 'light') document.documentElement.setAttribute('data-theme', 'light');
        else document.documentElement.removeAttribute('data-theme');
    }, theme);
    await page.waitForTimeout(220);
}

async function mockAgentHealth(page, body) {
    await page.route('**/api/health/agent', (route) => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ success: true, ...body }),
        });
    });
}

async function navigateToSettings(page) {
    await page.goto('/');
    await page.locator('button.tab-btn[data-target="settings"]').waitFor({ timeout: 5000 });
    await page.click('button.tab-btn[data-target="settings"]');
    await page.waitForTimeout(900);
}

// ─────────────────────────────────────────────────────────────────────────
// 1. Settings → Prereqs has the new Detection Agent row
// ─────────────────────────────────────────────────────────────────────────

test.describe('task #52 — Detection Agent settings row', () => {
    test('Settings → Prereqs renders the Detection Agent check section', async ({ page }) => {
        await mockAgentHealth(page, {
            configured: true,
            model: 'claude-sonnet-4-6',
            key_source: 'env',
            anthropic_sdk_installed: true,
        });
        await navigateToSettings(page);
        await page.waitForTimeout(600);
        const card = page.locator('#settings-agent-check');
        await expect(card, '#settings-agent-check section must exist').toHaveCount(1);
        await expect(card.locator('h3')).toContainText('Detection Agent');
        // The row container is populated by loadSettingsAgentCheck().
        await expect(page.locator('#settings-agent-check-row .spec-list')).toBeVisible();
    });

    test('configured=true → live pill, no remediation callout', async ({ page }) => {
        await mockAgentHealth(page, {
            configured: true,
            model: 'claude-sonnet-4-6',
            key_source: 'env',
            anthropic_sdk_installed: true,
        });
        await navigateToSettings(page);
        await page.waitForTimeout(600);
        const row = page.locator('#settings-agent-check-row');
        await expect(row.locator('.spec-pill--live')).toHaveCount(1);
        await expect(row.locator('.spec-pill--draft')).toHaveCount(0);
        await expect(row.locator('.spec-pill--error')).toHaveCount(0);
        await expect(row.locator('[data-agent-callout="true"]')).toHaveCount(0);
        // Model + key source shown in the eyebrow.
        await expect(row.locator('.spec-row__hint')).toContainText('claude-sonnet-4-6');
        await expect(row.locator('.spec-row__hint')).toContainText('env');
    });

    test('configured=false (SDK present) → draft pill + warning callout', async ({ page }) => {
        await mockAgentHealth(page, {
            configured: false,
            model: 'claude-sonnet-4-6',
            key_source: 'none',
            anthropic_sdk_installed: true,
        });
        await navigateToSettings(page);
        await page.waitForTimeout(600);
        const row = page.locator('#settings-agent-check-row');
        await expect(row.locator('.spec-pill--draft')).toHaveCount(1);
        await expect(row.locator('.spec-pill--live')).toHaveCount(0);
        // Remediation callout present + has the docs link.
        const callout = row.locator('[data-agent-callout="true"]');
        await expect(callout).toHaveCount(1);
        await expect(callout).toContainText('ANTHROPIC_API_KEY');
        await expect(callout.locator('a[href*="VULNERABLE_LAB_BOLTON_PLAN.md"]')).toHaveCount(1);
    });

    test('SDK missing → error pill + danger callout', async ({ page }) => {
        await mockAgentHealth(page, {
            configured: false,
            model: 'claude-sonnet-4-6',
            key_source: 'none',
            anthropic_sdk_installed: false,
        });
        await navigateToSettings(page);
        await page.waitForTimeout(600);
        const row = page.locator('#settings-agent-check-row');
        await expect(row.locator('.spec-pill--error')).toHaveCount(1);
        const callout = row.locator('[data-agent-callout="true"]');
        await expect(callout).toHaveCount(1);
        await expect(callout).toContainText('Anthropic SDK');
    });
});

// ─────────────────────────────────────────────────────────────────────────
// 2. Bolt-on STUCK overlay — Invoke Agent gated on agent health
// ─────────────────────────────────────────────────────────────────────────

test.describe('task #52 — STUCK overlay Invoke Agent gating', () => {
    test('configured=false → Invoke Agent button is disabled + explainer visible', async ({ page }) => {
        await mockAgentHealth(page, {
            configured: false,
            model: 'claude-sonnet-4-6',
            key_source: 'none',
            anthropic_sdk_installed: true,
        });
        await page.goto('/');
        // Stand up a minimal bolt-on progress shell + drive _showAgentPanel
        // directly. APP.bolton._openProgress would normally create this
        // body element; we mount the minimum it needs.
        await page.evaluate(() => {
            const host = document.createElement('div');
            host.id = 'bolton-progress-fallback-host';
            host.innerHTML = '<div id="bolton-progress-body"></div>';
            document.body.appendChild(host);
            // Reset cached agent health so the fetch fires under our mock.
            if (window.APP && window.APP.bolton) {
                window.APP.bolton._agentHealthCache = null;
            }
            window.APP.bolton._showAgentPanel('j_stuck_test');
        });
        // Allow the fetch + render to settle.
        await page.waitForTimeout(450);
        const panel = page.locator('.bolton-agent-panel[data-job-id="j_stuck_test"]');
        await expect(panel).toBeVisible();
        const invoke = panel.locator('[data-bolton-agent-action="invoke"]');
        // Disabled both ways (HTML + ARIA).
        await expect(invoke).toBeDisabled();
        await expect(invoke).toHaveAttribute('aria-disabled', 'true');
        // Explainer callout visible.
        const unavail = panel.locator('.bolton-agent-panel__unavailable');
        await expect(unavail).toBeVisible();
        await expect(unavail).toContainText('ANTHROPIC_API_KEY');
        // Go-to-Settings link present.
        await expect(panel.locator('[data-bolton-agent-action="goto-settings"]')).toHaveCount(1);
    });

    test('configured=true → Invoke Agent button stays enabled', async ({ page }) => {
        await mockAgentHealth(page, {
            configured: true,
            model: 'claude-sonnet-4-6',
            key_source: 'env',
            anthropic_sdk_installed: true,
        });
        await page.goto('/');
        await page.evaluate(() => {
            const host = document.createElement('div');
            host.id = 'bolton-progress-fallback-host';
            host.innerHTML = '<div id="bolton-progress-body"></div>';
            document.body.appendChild(host);
            if (window.APP && window.APP.bolton) {
                window.APP.bolton._agentHealthCache = null;
            }
            window.APP.bolton._showAgentPanel('j_ok_test');
        });
        await page.waitForTimeout(450);
        const panel = page.locator('.bolton-agent-panel[data-job-id="j_ok_test"]');
        await expect(panel).toBeVisible();
        const invoke = panel.locator('[data-bolton-agent-action="invoke"]');
        await expect(invoke).toBeEnabled();
        // Unavailable callout stays hidden.
        const unavail = panel.locator('.bolton-agent-panel__unavailable');
        await expect(unavail).toBeHidden();
    });
});

// ─────────────────────────────────────────────────────────────────────────
// 3. Both-theme contrast — Detection Agent row + disabled overlay state
// ─────────────────────────────────────────────────────────────────────────

const WALK_TO_SURFACE_FN = function walkToSurface(el) {
    function parseRgba(s) {
        const m = s.match(/rgba?\(([^)]+)\)/);
        if (!m) return null;
        const parts = m[1].split(',').map((p) => parseFloat(p.trim()));
        return [parts[0], parts[1], parts[2], parts.length === 4 ? parts[3] : 1];
    }
    const stack = [];
    let cur = el;
    while (cur && cur !== document.documentElement) {
        const cs = window.getComputedStyle(cur);
        const parsed = parseRgba(cs.backgroundColor);
        if (parsed && parsed[3] > 0.01) {
            stack.push(parsed);
            if (parsed[3] >= 0.99) break;
        }
        cur = cur.parentElement;
    }
    if (stack.length === 0 || stack[stack.length - 1][3] < 0.99) {
        const bodyBg = parseRgba(window.getComputedStyle(document.body).backgroundColor) || [255, 255, 255, 1];
        stack.push(bodyBg);
    }
    let [r, g, b] = stack[stack.length - 1].slice(0, 3);
    for (let i = stack.length - 2; i >= 0; i--) {
        const [or, og, ob, oa] = stack[i];
        r = or * oa + r * (1 - oa);
        g = og * oa + g * (1 - oa);
        b = ob * oa + b * (1 - oa);
    }
    return `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`;
};

async function auditScope(page, scopeSelector) {
    return page.evaluate(({ scopeSelector, walkSrc }) => {
        // eslint-disable-next-line no-new-func
        const walkToSurface = new Function('return ' + walkSrc)();
        function parseRgb(s) {
            const m = s.match(/rgba?\(([^)]+)\)/);
            if (!m) return null;
            const parts = m[1].split(',').map((p) => parseFloat(p.trim()));
            return [parts[0], parts[1], parts[2], parts.length === 4 ? parts[3] : 1];
        }
        function lin(c) { const v = c / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }
        function lum([r, g, b]) { return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b); }
        function ratio(a, b) { const L1 = lum(a); const L2 = lum(b); return (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05); }

        const root = document.querySelector(scopeSelector);
        if (!root) return { found: false, failures: [] };
        const failures = [];
        const els = root.querySelectorAll('*');
        for (const el of els) {
            const cs = window.getComputedStyle(el);
            if (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0') continue;
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) continue;
            if (el.getAttribute('aria-hidden') === 'true') continue;
            let hasText = false;
            for (const child of el.childNodes) {
                if (child.nodeType === 3 && child.textContent.trim().length > 0) {
                    hasText = true;
                    break;
                }
            }
            if (!hasText) continue;
            if (el.closest('pre, code')) continue;  // mono blocks are by-design dark
            const fg = parseRgb(cs.color);
            if (!fg) continue;
            const surface = walkToSurface(el);
            const bg = parseRgb(surface);
            if (!bg) continue;
            if (fg[3] < 0.5) continue;
            const r = ratio(fg.slice(0, 3), bg.slice(0, 3));
            const fontSize = parseFloat(cs.fontSize);
            const fontWeight = parseInt(cs.fontWeight, 10) || 400;
            const isLarge = fontSize >= 24 || (fontSize >= 18.66 && fontWeight >= 700);
            const threshold = isLarge ? 3.0 : 4.5;
            if (r < threshold) {
                failures.push({
                    tag: el.tagName.toLowerCase(),
                    cls: String(el.className || '').slice(0, 80),
                    text: (el.textContent || '').trim().slice(0, 60),
                    ratio: Number(r.toFixed(2)),
                    threshold,
                    fg: cs.color,
                    bg: surface,
                });
            }
        }
        return { found: true, failures };
    }, { scopeSelector, walkSrc: WALK_TO_SURFACE_FN.toString() });
}

for (const theme of ['dark', 'light']) {
    test(`Detection Agent settings row — contrast clean (${theme}, unconfigured)`, async ({ page }) => {
        await mockAgentHealth(page, {
            configured: false,
            model: 'claude-sonnet-4-6',
            key_source: 'none',
            anthropic_sdk_installed: true,
        });
        await navigateToSettings(page);
        await setTheme(page, theme);
        await page.locator('#settings-agent-check').scrollIntoViewIfNeeded();
        await page.waitForTimeout(400);
        const { found, failures } = await auditScope(page, '#settings-agent-check');
        expect(found, '#settings-agent-check not found').toBe(true);
        if (failures.length > 0) {
            // eslint-disable-next-line no-console
            console.log(`\nDetection Agent row (${theme}) — ${failures.length} contrast failures:`);
            for (const f of failures.slice(0, 8)) {
                // eslint-disable-next-line no-console
                console.log(`  <${f.tag}.${(f.cls || '').split(' ').join('.')}> "${f.text}" — ${f.ratio}:1 (need ${f.threshold})`);
            }
        }
        expect(failures, `${failures.length} AA failures`).toEqual([]);
    });

    test(`STUCK overlay disabled state — contrast clean (${theme})`, async ({ page }) => {
        await mockAgentHealth(page, {
            configured: false,
            model: 'claude-sonnet-4-6',
            key_source: 'none',
            anthropic_sdk_installed: true,
        });
        await page.goto('/');
        await setTheme(page, theme);
        await page.evaluate(() => {
            const host = document.createElement('div');
            host.id = 'bolton-progress-fallback-host';
            host.innerHTML = '<div id="bolton-progress-body"></div>';
            document.body.appendChild(host);
            if (window.APP && window.APP.bolton) {
                window.APP.bolton._agentHealthCache = null;
            }
            window.APP.bolton._showAgentPanel('j_contrast_test');
        });
        await page.waitForTimeout(500);
        const { found, failures } = await auditScope(page, '.bolton-agent-panel[data-job-id="j_contrast_test"]');
        expect(found).toBe(true);
        if (failures.length > 0) {
            // eslint-disable-next-line no-console
            console.log(`\nSTUCK overlay (${theme}) — ${failures.length} contrast failures:`);
            for (const f of failures.slice(0, 8)) {
                // eslint-disable-next-line no-console
                console.log(`  <${f.tag}.${(f.cls || '').split(' ').join('.')}> "${f.text}" — ${f.ratio}:1 (need ${f.threshold})`);
            }
        }
        expect(failures, `${failures.length} AA failures`).toEqual([]);
    });
}
