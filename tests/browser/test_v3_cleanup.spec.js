/**
 * Phase 3C — Cleanup sub-pill V3-native rebuild.
 *
 * Verifies the V3-native cleanup pane:
 *   1. Sub-pill loads, 4 stat cards visible.
 *   2. Resource list renders with .spec-row cleanup-row format.
 *   3. Mark-known stores attribution + timestamp (localStorage v2 shape).
 *   4. v1 (array) → v2 (id-keyed map) localStorage migration on load.
 *   5. Marked entries show "marked by [operator] [time]" + operator color dot.
 *   6. Both themes pass layer-aware contrast on the cleanup surface.
 *
 * The /api/deploy/resources/all-projects endpoint may be slow or empty;
 * the tests that depend on real data degrade gracefully via test.skip when
 * the resource list is empty or unreachable.
 */

import { test, expect } from '@playwright/test';

async function setTheme(page, theme) {
    await page.evaluate((t) => {
        if (t === 'light') document.documentElement.setAttribute('data-theme', 'light');
        else document.documentElement.removeAttribute('data-theme');
    }, theme);
    await page.waitForTimeout(320);
}

async function navigateToCleanupSubPill(page) {
    await page.goto('/');
    await page.locator('button.tab-btn[data-target="deployments-tab"]').waitFor({ timeout: 5000 });
    await page.click('button.tab-btn[data-target="deployments-tab"]');
    await page.waitForTimeout(150);
    await page.locator('button.subpill-nav__pill[data-subpill="cleanup"]').click();
    await page.waitForTimeout(400);
}

// Seed-injectors used by the localStorage tests so each test starts clean
// and explicit about what state it expects.
async function seedKnownExternal(page, value) {
    await page.evaluate((v) => {
        try {
            if (v === null) localStorage.removeItem('cleanup.knownExternal.v1');
            else localStorage.setItem('cleanup.knownExternal.v1', JSON.stringify(v));
        } catch (_) { /* ignore */ }
    }, value);
}

test.describe('Cleanup sub-pill (Phase 3c V3-native)', () => {
    test('legacy .cleanup-header / .cleanup-resource-row markup is gone from the live DOM', async ({ page }) => {
        await navigateToCleanupSubPill(page);
        // The legacy skeleton classes must not appear in the new render. The
        // CSS rules still exist (marked deprecated) for backwards-compat but
        // the live cleanup pane should never emit them.
        const legacyHeader = await page.locator('#subpill-pane-cleanup .cleanup-header').count();
        expect(legacyHeader, 'legacy .cleanup-header must be gone from the live cleanup pane').toBe(0);
        // The new namespace must be present.
        const v3Root = await page.locator('#subpill-pane-cleanup .cleanup-v3').count();
        expect(v3Root, 'new .cleanup-v3 namespace must be present').toBe(1);
    });

    test('4 summary stat tiles render with the V3 layout', async ({ page }) => {
        await navigateToCleanupSubPill(page);
        const tiles = page.locator('#subpill-pane-cleanup .cleanup-v3-summary__tile');
        await expect(tiles).toHaveCount(4);
        // Each tile has a number + a caps label.
        for (let i = 0; i < 4; i++) {
            await expect(tiles.nth(i).locator('.cleanup-v3-summary__num')).toBeVisible();
            await expect(tiles.nth(i).locator('.cleanup-v3-summary__label')).toBeVisible();
        }
    });

    test('Refresh button triggers a scan + populates the last-refreshed-at hint', async ({ page }) => {
        await navigateToCleanupSubPill(page);
        await page.locator('#cleanup-refresh-btn').click();
        // Wait for the scan to complete (loading attr removed).
        await expect(page.locator('#cleanup-refresh-btn')).not.toHaveAttribute('data-loading', 'true', { timeout: 8000 });
        const refreshed = page.locator('#cleanup-refreshed-at');
        const refreshedHidden = await refreshed.evaluate(el => el.hidden);
        expect(refreshedHidden, 'last-refreshed-at hint should be visible after a scan').toBe(false);
        const text = (await refreshed.textContent() || '').trim();
        expect(text, 'refreshed-at must read "LAST SCAN HH:MM:SS"').toMatch(/LAST SCAN \d{2}:\d{2}:\d{2}/);
    });

    test('resource rows (if any) use the .spec-row .cleanup-row format', async ({ page }) => {
        await navigateToCleanupSubPill(page);
        await page.locator('#cleanup-refresh-btn').click();
        await expect(page.locator('#cleanup-refresh-btn')).not.toHaveAttribute('data-loading', 'true', { timeout: 8000 });

        const rowCount = await page.locator('#subpill-pane-cleanup .spec-row.cleanup-row').count();
        if (rowCount === 0) {
            test.skip(true, 'no orphan resources in this environment — skipping row shape assertion');
            return;
        }
        const firstRow = page.locator('#subpill-pane-cleanup .spec-row.cleanup-row').first();
        await expect(firstRow.locator('.spec-row__key')).toBeVisible();
        await expect(firstRow.locator('.spec-row__value')).toBeVisible();
        await expect(firstRow.locator('.cleanup-row__actions')).toBeVisible();
        // 3 action buttons per row (Adopt, Destroy, Mark known)
        await expect(firstRow.locator('.cleanup-row__action')).toHaveCount(3);
        // The Destroy button uses the danger variant.
        await expect(firstRow.locator('.spec-edit-btn--danger')).toHaveCount(1);
    });

    test('localStorage v1 array format migrates to v2 id-keyed map on load', async ({ page }) => {
        await page.goto('/');
        // Seed the legacy v1 (array of strings) format BEFORE the cleanup
        // module runs readKnown() — readKnown() is the trigger that writes
        // back the migrated v2 map.
        await seedKnownExternal(page, ['eip::test-legacy-1', 'acm::test-legacy-2']);
        // Trigger a readKnown() — this is what runs in the loader.
        const migrated = await page.evaluate(() => {
            const result = APP.cleanup.readKnown();
            const raw = localStorage.getItem('cleanup.knownExternal.v1');
            return { result, raw };
        });
        // Migrated map keys are the legacy ids.
        expect(Object.keys(migrated.result).sort()).toEqual(['acm::test-legacy-2', 'eip::test-legacy-1']);
        expect(migrated.result['eip::test-legacy-1']).toMatchObject({ id: 'eip::test-legacy-1', by: null, at: null });
        // The migration also rewrites the storage to the v2 object form.
        const reparsed = JSON.parse(migrated.raw);
        expect(Array.isArray(reparsed), 'after migration the stored value must NOT be an array').toBe(false);
        expect(reparsed['eip::test-legacy-1']).toBeTruthy();
    });

    test('cleanupMarkKnown writes the v2 attribution shape (id, by, at)', async ({ page }) => {
        await navigateToCleanupSubPill(page);
        // Force a clean state so we can assert exact contents.
        await seedKnownExternal(page, null);
        const result = await page.evaluate(() => {
            APP.cleanup.addKnown('eip::test-mark-1');
            return APP.cleanup.readKnown();
        });
        const entry = result['eip::test-mark-1'];
        expect(entry, 'addKnown must write an entry keyed by id').toBeTruthy();
        expect(entry.id).toBe('eip::test-mark-1');
        // `by` is the current operator id (string) OR null if no operator
        // backend is live. Both are valid; assert the field is present.
        expect('by' in entry).toBe(true);
        // `at` MUST be a valid ISO timestamp (not null) since addKnown sets it.
        expect(entry.at).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
    });

    test('synthetic marked row renders attribution dot + draft pill (no AWS dep)', async ({ page }) => {
        // Exercise the marked-state render path WITHOUT depending on real
        // orphan resources. Calls _renderCleanupGroups() directly with a
        // synthetic dataset + a pre-seeded known map.
        await navigateToCleanupSubPill(page);
        // Wait for any auto-fired loadCleanupResources to settle (empty-state
        // or error) so it doesn't race with our synthetic innerHTML injection.
        await page.waitForTimeout(1200);
        // Sanity: confirm the renderer is reachable from window scope.
        const rendererAvailable = await page.evaluate(() => typeof window._renderCleanupGroups);
        expect(rendererAvailable, '_renderCleanupGroups must be on window').toBe('function');
        await page.evaluate(() => {
            const synthetic = {
                eips: [
                    { _id: 'eip::synthetic-1', _kind: 'eip', public_ip: '203.0.113.7', allocation_id: 'eipalloc-synth1', region: 'eu-central-1' },
                ],
                acm_certs: [],
                s3_buckets: [],
                snapshots: [],
                workspaces: [],
                total: 1,
            };
            const known = {
                'eip::synthetic-1': { id: 'eip::synthetic-1', by: 'alice', at: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString() },
            };
            // Inject a fake operator so attribution resolves.
            APP.operator.all = (APP.operator.all || []).concat([{ id: 'alice', display: 'Alice', color: '#7c3aed' }]);
            const list = document.getElementById('cleanup-resource-list');
            list.innerHTML = _renderCleanupGroups(synthetic, known);
        });
        await page.waitForTimeout(150);

        // Debug: dump the cleanup list HTML.
        const html = await page.evaluate(() => document.getElementById('cleanup-resource-list').innerHTML.slice(0, 800));
        const rowExists = await page.evaluate(() => {
            return Array.from(document.querySelectorAll('#subpill-pane-cleanup .cleanup-row'))
                       .some(el => el.getAttribute('data-resource-id') === 'eip::synthetic-1');
        });
        expect(rowExists, 'synthetic cleanup row must be rendered. HTML: ' + html).toBe(true);
        // Now use a stable selector — query by data-kind which doesn't have colons.
        const row = page.locator('#subpill-pane-cleanup .cleanup-row[data-kind="eip"]').first();
        await expect(row).toHaveAttribute('data-marked-known', 'true');
        await expect(row.locator('[data-attribution]')).toBeVisible();
        const text = (await row.locator('[data-attribution]').textContent() || '').toLowerCase();
        expect(text).toContain('marked by');
        expect(text).toContain('alice');
        // Relative time should show "3d ago" or similar.
        expect(text).toMatch(/\d+[dhms] ago/);
        // Color dot is set to the operator color.
        const dotStyle = await row.locator('.cleanup-row__attribution-dot').getAttribute('style');
        expect(dotStyle || '').toContain('#7c3aed');
        // Draft pill is present + visible.
        await expect(row.locator('.spec-pill--draft')).toBeVisible();
    });

    test('marked entries render with attribution dot + "marked by [op]" hint', async ({ page }) => {
        await navigateToCleanupSubPill(page);
        await page.locator('#cleanup-refresh-btn').click();
        await expect(page.locator('#cleanup-refresh-btn')).not.toHaveAttribute('data-loading', 'true', { timeout: 8000 });

        const rowCount = await page.locator('#subpill-pane-cleanup .spec-row.cleanup-row').count();
        if (rowCount === 0) {
            test.skip(true, 'no orphan resources — cannot exercise mark flow');
            return;
        }
        const firstRow = page.locator('#subpill-pane-cleanup .spec-row.cleanup-row').first();
        const resourceId = await firstRow.getAttribute('data-resource-id');
        expect(resourceId).toBeTruthy();

        // Click the "Mark known" button.
        await firstRow.locator('button[onclick^="cleanupMarkKnown"]').click();
        await page.waitForTimeout(150);

        // Row stays in the DOM but now has data-marked-known.
        await expect(firstRow).toHaveAttribute('data-marked-known', 'true');
        // Attribution element rendered.
        await expect(firstRow.locator('[data-attribution]')).toBeVisible();
        const text = await firstRow.locator('[data-attribution]').textContent();
        expect((text || '').toLowerCase()).toContain('marked by');
        // Color dot present.
        await expect(firstRow.locator('.cleanup-row__attribution-dot')).toBeVisible();
        // Draft pill present.
        await expect(firstRow.locator('.spec-pill--draft')).toBeVisible();
    });
});

for (const theme of ['dark', 'light']) {
    test(`Cleanup sub-pill passes contrast (${theme} theme)`, async ({ page }) => {
        await navigateToCleanupSubPill(page);
        await setTheme(page, theme);
        // Trigger one scan so the rows + summary are populated. If the
        // endpoint is unreachable we still run the contrast walk on the
        // eyebrow + summary chrome.
        await page.locator('#cleanup-refresh-btn').click();
        await page.waitForTimeout(800);

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
                // Skip sibling-dim rows (designed affordance — opacity 0.4).
                if (parseFloat(cs.opacity) < 0.7) return;
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
        }, { rootSel: '#subpill-pane-cleanup' });

        if (failures.length) {
            // eslint-disable-next-line no-console
            console.log(`Cleanup (${theme}) contrast failures:`, JSON.stringify(failures, null, 2));
        }
        expect(failures, `${failures.length} AA failures in ${theme}`).toEqual([]);
    });
}
