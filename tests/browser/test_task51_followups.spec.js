/**
 * Task 51 — Four queued UI follow-ups (2026-05-19).
 *
 *   1. Journey review CTA renames "Deploy ▸" → "Save & continue ▸" and the
 *      eyebrow swaps "READY TO DEPLOY" → "READY TO SAVE". A hint below the
 *      CTA explains: "Saves these settings; you'll fine-tune Attack Box, C2
 *      profile, and other options in Configure next." The action (POST
 *      /api/config + transition to edit mode) is unchanged — only the label
 *      reflects reality.
 *
 *   2. The "Why?" link on incompatible bolt-on rows opens a positioned
 *      tooltip showing state + reason + suggested_action (instead of the
 *      browser-native title attribute). Click outside / Escape closes it.
 *
 *   3. When `?new=1` is in the URL (wizard inline-mode), the legacy
 *      "Configuration Editor" h2 + "What do you want to deploy?" dropdown
 *      are hidden. The dropdown is redundant — the wizard already asks
 *      this in step 1.
 *
 *   4. Configure edit pane renders a Composition A spec-list at the top
 *      (7 core rows: deployment type, project name, environment, AWS
 *      region, management CIDR, key pair, est. cost). Clicking a row
 *      opens an inline editor. Type-specific config (Attack Box, Malleable,
 *      Redirector Domain, Domain Fronting, GOAD Network) is collapsed under
 *      a single <details id="configure-advanced-details">.
 */

import { test, expect } from '@playwright/test';

async function setTheme(page, theme) {
    await page.evaluate((t) => {
        if (t === 'light') document.documentElement.setAttribute('data-theme', 'light');
        else document.documentElement.removeAttribute('data-theme');
    }, theme);
    await page.waitForTimeout(200);
}

async function acceptConfirm(page) {
    await page.evaluate(() => { window.confirm = () => true; });
}

// ─── Item 1 — Journey review CTA rename ─────────────────────────────────────

test.describe('Item 1 — journey review CTA reflects "save, not deploy"', () => {
    test('review screen eyebrow says "READY TO SAVE" and CTA reads "Save & continue"', async ({ page }) => {
        await page.goto('/');
        await acceptConfirm(page);
        await page.locator('#global-new-deployment-btn').waitFor({ timeout: 5000 });
        await page.click('#global-new-deployment-btn');
        await page.waitForTimeout(400);
        // Fast-forward through 4 wizard steps → review
        for (let i = 0; i < 4; i++) {
            await page.click('#journey-next');
            await page.waitForTimeout(120);
        }
        await expect(page.locator('#journey-review')).toHaveClass(/is-active/);
        // Eyebrow
        const eyebrowText = await page.locator('#journey-review-eyebrow').textContent();
        expect(eyebrowText.trim()).toBe('READY TO SAVE');
        // CTA primary button label
        const ctaText = await page.locator('#journey-deploy').textContent();
        expect(ctaText).toMatch(/Save\s*&\s*continue/i);
        // Hint below the CTA
        const hintText = await page.locator('#journey-review-cta-hint').textContent();
        expect(hintText).toMatch(/fine[- ]tune.*Attack Box/i);
        expect(hintText).toMatch(/Configure next/i);
        // Lower crumb still mono-caps
        const crumbText = await page.locator('#journey-review .journey-foot__crumb').textContent();
        expect(crumbText.trim()).toMatch(/Ready to save/i);
    });
});

// ─── Item 2 — Bolton Why? tooltip ───────────────────────────────────────────

test.describe('Item 2 — "Why?" on incompatible bolt-on rows opens a tooltip', () => {
    // Visit the bolton sub-pill directly. We don't depend on real catalog data —
    // instead we inject a synthetic row through APP.bolton._renderSections so
    // the test asserts the wiring without needing a live deployment.
    test('clicking Why? renders a popover with state + reason + suggested action', async ({ page }) => {
        await page.goto('/');
        // Navigate to Deployments → Bolt-ons.
        await page.evaluate(() => {
            if (window.APP && typeof window.APP.navigateTo === 'function') {
                window.APP.navigateTo('deployments-tab', 'bolt-ons');
            }
        });
        await page.waitForTimeout(400);
        // Inject a synthetic catalog row into the incompatible bucket and
        // force the bolton-sections container + the "incompatible" accordion
        // open so the row is visible.
        await page.evaluate(() => {
            const sections = document.getElementById('bolton-sections');
            if (sections) sections.hidden = false;
            const incompatibleSection = document.querySelector('[data-section="incompatible"]');
            if (incompatibleSection) {
                incompatibleSection.dataset.open = 'true';
                const btn = incompatibleSection.querySelector('.bt-section__header');
                if (btn) btn.setAttribute('aria-expanded', 'true');
            }
            const row = {
                id: 'cve-synth-001',
                name: 'Synthetic vuln (test fixture)',
                state: 'INCOMPATIBLE_OS',
                category: 'web',
                coverage: 'covered',
                mitre: 'T1190',
                reason: 'Target OS is Linux; this vuln only applies to Windows hosts.',
                suggested_action: 'Switch to a Windows host or pick a different bolt-on.',
            };
            if (window.APP && window.APP.bolton && typeof window.APP.bolton._renderSections === 'function') {
                window.APP.bolton._renderSections([row]);
            }
        });
        await page.waitForTimeout(200);
        // The button is now rendered but the accordion body may still have
        // display:none via CSS — force it open programmatically.
        await page.evaluate(() => {
            const body = document.querySelector('[data-section="incompatible"] .bt-section__body');
            if (body) {
                body.style.display = 'block';
                body.style.maxHeight = 'none';
            }
            const inner = document.querySelector('[data-section="incompatible"] .bt-section__body-inner');
            if (inner) {
                inner.style.display = 'block';
                inner.style.maxHeight = 'none';
                inner.style.opacity = '1';
            }
        });
        const whyBtn = page.locator('[data-bolton-why]').first();
        await expect(whyBtn).toBeVisible();
        await whyBtn.click();
        await page.waitForTimeout(120);
        const tooltip = page.locator('.bolton-why-tooltip');
        await expect(tooltip).toBeVisible();
        await expect(tooltip).toContainText('INCOMPATIBLE_OS');
        await expect(tooltip).toContainText('Target OS is Linux');
        await expect(tooltip).toContainText('Switch to a Windows host');
        // Escape closes it.
        await page.keyboard.press('Escape');
        await page.waitForTimeout(150);
        await expect(tooltip).toHaveCount(0);
    });
});

// ─── Item 3 — Legacy editor hidden in wizard mode ───────────────────────────

test.describe('Item 3 — legacy "Configuration Editor" dropdown is hidden in wizard mode', () => {
    test('the .configuration-editor block is not rendered when wizard is mounted', async ({ page }) => {
        await page.goto('/?new=1#deployments-tab/configure');
        await page.waitForTimeout(500);
        // Wizard mounted inside #configure-new-pane.
        await expect(page.locator('#configure-new-pane #journey-takeover')).toBeVisible({ timeout: 4000 });
        // .configuration-editor element exists but is not displayed.
        const editorExists = await page.locator('.configuration-editor').count();
        expect(editorExists).toBeGreaterThan(0);
        const editorVisible = await page.locator('.configuration-editor').isVisible();
        expect(editorVisible).toBe(false);
    });

    test('returning to edit mode restores the .configuration-editor block', async ({ page }) => {
        await page.goto('/');
        await page.waitForTimeout(400);
        // Navigate to Configure (edit mode by default).
        await page.evaluate(() => {
            if (window.APP && typeof window.APP.navigateTo === 'function') {
                window.APP.navigateTo('deployments-tab', 'configure');
            }
        });
        await page.waitForTimeout(400);
        const editorVisible = await page.locator('.configuration-editor').isVisible();
        expect(editorVisible).toBe(true);
    });
});

// ─── Item 4 — Configure TASTE redesign ──────────────────────────────────────

test.describe('Item 4 — Configure edit pane renders a Composition A spec-list', () => {
    test('the configure spec-list mounts with 7 core rows', async ({ page }) => {
        await page.goto('/');
        await page.evaluate(() => {
            if (window.APP && typeof window.APP.navigateTo === 'function') {
                window.APP.navigateTo('deployments-tab', 'configure');
            }
        });
        await page.waitForTimeout(600);
        // Hero strip
        await expect(page.locator('#configure-summary-hero-name')).toBeVisible();
        await expect(page.locator('#configure-summary-hero-type')).toBeVisible();
        // Status pill
        await expect(page.locator('#configure-summary-status')).toBeVisible();
        // Spec-list row keys (each row carries data-configure-row="…")
        const expectedRows = [
            'deployment_type',
            'project_name',
            'environment',
            'aws_region',
            'management_cidr',
            'key_pair_name',
            'cost',
        ];
        for (const key of expectedRows) {
            await expect(page.locator(`.spec-row[data-configure-row="${key}"]`)).toBeVisible();
        }
        const rowCount = await page.locator('#configure-summary-spec-list .spec-row').count();
        expect(rowCount).toBe(expectedRows.length);
    });

    test('clicking an editable row opens the inline editor', async ({ page }) => {
        await page.goto('/');
        await page.evaluate(() => {
            if (window.APP && typeof window.APP.navigateTo === 'function') {
                window.APP.navigateTo('deployments-tab', 'configure');
            }
        });
        await page.waitForTimeout(600);
        const row = page.locator('.spec-row[data-configure-row="project_name"]');
        await row.locator('.spec-row__head').click();
        await page.waitForTimeout(150);
        await expect(row).toHaveAttribute('data-editing', 'true');
        // Input is focused with the current value.
        const input = row.locator('[data-edit-input]');
        await expect(input).toBeVisible();
    });

    test('legacy form fields are wrapped in a collapsible <details>', async ({ page }) => {
        await page.goto('/');
        await page.evaluate(() => {
            if (window.APP && typeof window.APP.navigateTo === 'function') {
                window.APP.navigateTo('deployments-tab', 'configure');
            }
        });
        await page.waitForTimeout(500);
        const details = page.locator('#configure-advanced-details');
        await expect(details).toBeVisible();
        // Default open=true so operators can still access raw inputs.
        const isOpen = await details.evaluate(el => el.hasAttribute('open'));
        expect(isOpen).toBe(true);
        // Sticky form-actions strip carries the V3 class.
        await expect(page.locator('.configure-form-actions--sticky')).toBeVisible();
    });

    for (const theme of ['dark', 'light']) {
        test(`configure summary contrast (${theme} theme)`, async ({ page }) => {
            await page.goto('/');
            await page.evaluate(() => {
                if (window.APP && typeof window.APP.navigateTo === 'function') {
                    window.APP.navigateTo('deployments-tab', 'configure');
                }
            });
            await page.waitForTimeout(500);
            await setTheme(page, theme);
            await page.waitForTimeout(200);
            const failures = await page.evaluate((rootSel) => {
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
                    if (el.closest('.spec-row:not([data-editing="true"])') && el.closest('.spec-list[data-editing="true"]')) return;
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
            }, '#configure-summary-section');
            if (failures.length) {
                // eslint-disable-next-line no-console
                console.log(`Configure summary (${theme}) failures:`, JSON.stringify(failures, null, 2));
            }
            expect(failures, `${failures.length} AA failures in configure summary, ${theme}`).toEqual([]);
        });
    }
});
