/**
 * Task 51 — bolt-on "Why?" tooltip (2026-05-19).
 *
 * 2026-05-21 legacy-audit sweep: the original Item 1 (journey-review CTA
 * rename), Item 3 (legacy "Configuration Editor" dropdown hidden in wizard
 * mode), and Item 4 (Configure spec-list with 7 core rows) were deleted —
 * they asserted on flows that are no longer the default:
 *
 *   - Item 1 fired `+ New Deployment` and expected the journey wizard to
 *     auto-open; per 2026-05-19 flow-stitching, `+ New` now drops the
 *     operator into Configure V2 (progressive). The journey wizard only
 *     mounts via `?wizard=1` opt-in or explicit `APP.journey.open()` — both
 *     already covered by test_v3_journey.spec.js + test_v3_flow_stitching.spec.js.
 *   - Items 3 + 4 asserted on the legacy `.configuration-editor` /
 *     `#configure-advanced-details` / `#configure-summary-section` spec-list
 *     surfaces, which UX_AUDIT 2026-05-20 (M1) schedules for retirement
 *     alongside the rest of the legacy form. Re-asserting that legacy is
 *     hidden/visible encodes the wrong mental model going forward.
 *
 * Item 2 (bolt-on "Why?" tooltip) is the only legacy-retirement-safe
 * survivor — it tests live bolt-on UI surface that has no V2 replacement.
 */

import { test, expect } from '@playwright/test';

test.describe('bolton — "Why?" on incompatible bolt-on rows opens a tooltip', () => {
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
        // display:none via CSS — force it open programmatically. 2026-05-21:
        // commit f745c14 added a `[hidden] { display: none !important; }`
        // global guard which overrides inline `style.display = 'block'`. We
        // also strip the `hidden` attribute from every ancestor of the row
        // (`#bolt-ons-pane` is `hidden` when no active C2 deployment, which
        // cascades through the accordion body via the !important guard).
        await page.evaluate(() => {
            // Strip [hidden] from every ancestor of the bolton sections so
            // the !important guard doesn't override style.display below.
            let el = document.getElementById('bolton-sections');
            while (el) {
                if (el.hasAttribute('hidden')) el.removeAttribute('hidden');
                el = el.parentElement;
            }
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
