/**
 * v3 BOLT-ON DENSITY — visual chrome trim verification.
 *
 * The bolt-on page was previously a label-dense surface (4 verbose summary
 * labels, 3 filter rows each with a redundant label, 9 inline compat chips,
 * 6 collapsible sections each with a "this host" sub-hint, plus a visible
 * "Target host" <label> above the dropdown and a 3-sentence description).
 *
 * This spec freezes the trim:
 *   - .bolton-live__filters-rowlabel is gone (filter row labels dropped)
 *   - .bt-section__hint with "this host" is gone (redundant sub-hints dropped)
 *   - section title + count badge still render
 *   - host dropdown placeholder is "Pick a target host…"
 *   - host <label> next to the dropdown is gone (aria-label remains for a11y)
 *   - summary tile labels are single-word (Installed / Patched / Uncovered / Available)
 *   - compat chip strip is collapsed to 5 chips (All / Installed / Available / Patched / Blocked)
 *
 * Backend behaviour, install/patch/uninstall/revert flows, Elastic coverage
 * pills, and the descriptor-driven host-filter are all out of scope for this
 * file — they have dedicated specs.
 */

import { test, expect } from '@playwright/test';

const LAB_HOSTS = {
    success: true,
    lab: 'goad-light',
    hosts: [
        { name: 'dc01', host_id: 'dc01', role: 'domain_controller', os_family: 'windows', os_version: '2019', installed_count: 0, stale: true },
    ],
};

async function gotoBoltons(page) {
    await page.goto('/');
    await page.locator('.app-rail__item[data-rail-target="deployments-tab"]').click();
    const child = page.locator('.app-rail__child[data-rail-subpill="bolt-ons"]');
    await child.waitFor({ timeout: 5000 });
    await child.click();
    await page.locator('#subpill-pane-bolt-ons').waitFor({ state: 'visible', timeout: 5000 });
}

async function installApiStubs(page) {
    await page.route('**/api/bolton/labs/**/hosts', (route) => {
        route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(LAB_HOSTS),
        });
    });
}

async function loadHosts(page, lab) {
    await page.evaluate((l) => {
        window.APP.bolton.state.lab = l;
        window.APP.bolton.state.selectedDescriptorId = null;
        window.APP.bolton.state.selectedDescriptor = null;
        return window.APP.bolton.loadHosts(l);
    }, lab);
    await page.waitForFunction(() => {
        const sel = document.getElementById('bolton-host-select');
        if (!sel) return false;
        const opts = Array.from(sel.options).map(o => o.value).filter(v => v);
        return opts.length > 0;
    }, { timeout: 5000 });
}

test.describe('v3 bolt-on — visual density trim', () => {
    test('no .bolton-live__filters-rowlabel renders (filter row labels dropped)', async ({ page }) => {
        await installApiStubs(page);
        await gotoBoltons(page);
        const rowlabels = page.locator('.bolton-live__filters-rowlabel');
        await expect(rowlabels).toHaveCount(0);
    });

    test('no .bt-section__hint renders (redundant sub-hints dropped)', async ({ page }) => {
        await installApiStubs(page);
        await gotoBoltons(page);
        const hints = page.locator('.bt-section__hint');
        await expect(hints).toHaveCount(0);

        // Also confirm no element anywhere in the bolt-on root carries the
        // legacy "this host" wording — the operator's complaint was that
        // every section duplicated that phrase.
        const thisHost = page.locator('[data-bolton-root]').getByText(/this host/i);
        await expect(thisHost).toHaveCount(0);
    });

    test('section titles + count badges still render for all 6 sections', async ({ page }) => {
        await installApiStubs(page);
        await gotoBoltons(page);
        await loadHosts(page, 'goad-light');
        const sectionTitles = page.locator('#bolton-sections .bt-section__title');
        await expect(sectionTitles).toHaveCount(6);
        // Every title has a count <span data-count="…"> child.
        const titlesText = await sectionTitles.allTextContents();
        for (const t of titlesText) {
            expect(t).toMatch(/·\s*\d+/); // " · <n>"
        }
    });

    test('host dropdown placeholder is "Pick a target host…"', async ({ page }) => {
        await installApiStubs(page);
        await gotoBoltons(page);
        await loadHosts(page, 'goad-light');
        const placeholder = await page.locator('#bolton-host-select option').first().textContent();
        expect(placeholder).toContain('Pick a target host');
    });

    test('no visible <label> labels the host dropdown (aria-label remains)', async ({ page }) => {
        await installApiStubs(page);
        await gotoBoltons(page);
        // Legacy class is gone.
        await expect(page.locator('.bolton-live__host-label')).toHaveCount(0);
        // No <label for="bolton-host-select"> survives in the markup.
        await expect(page.locator('label[for="bolton-host-select"]')).toHaveCount(0);
        // Accessibility name is preserved via aria-label on the <select>.
        const ariaLabel = await page.locator('#bolton-host-select').getAttribute('aria-label');
        expect(ariaLabel).toBeTruthy();
    });

    test('summary tile labels are single-word (no "Pending detection coverage" / "Available compatible")', async ({ page }) => {
        await installApiStubs(page);
        await gotoBoltons(page);
        const labels = await page.locator('.bolton-live__summary-label').allTextContents();
        // 4 tiles still render.
        expect(labels.length).toBe(4);
        for (const l of labels) {
            // Single word — no spaces in the trimmed label.
            expect(l.trim().split(/\s+/).length).toBe(1);
        }
        // Confirm the verbose strings are gone.
        expect(labels.join('|')).not.toContain('Pending detection coverage');
        expect(labels.join('|')).not.toContain('Available compatible');
    });

    test('compat chip strip is collapsed (5 chips: All / Installed / Available / Patched / Blocked)', async ({ page }) => {
        await installApiStubs(page);
        await gotoBoltons(page);
        await loadHosts(page, 'goad-light');
        // The state group lives inside .bolton-live__filters with data-chip-group="state".
        const stateChips = page.locator('#bolton-filters [data-chip-group="state"] .bt-chip');
        await expect(stateChips).toHaveCount(5);
        const labels = await stateChips.allTextContents();
        expect(labels.map(s => s.trim())).toEqual(['All states', 'Installed', 'Available', 'Patched', 'Blocked']);
    });

    test('filter strip is a single row with separators between groups', async ({ page }) => {
        await installApiStubs(page);
        await gotoBoltons(page);
        await loadHosts(page, 'goad-light');
        // One .bolton-live__filters-row container — not three.
        const rows = page.locator('#bolton-filters .bolton-live__filters-row');
        await expect(rows).toHaveCount(1);
        // Two vertical separators between the three chip groups.
        const seps = page.locator('#bolton-filters .bolton-live__filters-sep');
        await expect(seps).toHaveCount(2);
    });
});
