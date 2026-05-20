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

    test('Refresh button issues a GET to /api/deploy/resources/all-projects', async ({ page }) => {
        // 2026-05-19 regression: operator reported the Cleanup page was
        // empty. Root cause was the endpoint omitting eips/acm/s3 — but
        // the click→fetch path must also work end-to-end. This test
        // intercepts the request and asserts the URL.
        await navigateToCleanupSubPill(page);
        const reqPromise = page.waitForRequest(req =>
            req.url().includes('/api/deploy/resources/all-projects') && req.method() === 'GET',
            { timeout: 8000 }
        );
        await page.locator('#cleanup-refresh-btn').click();
        const req = await reqPromise;
        // Force-refresh button passes `?refresh=1` so the URL must contain it.
        expect(req.url(), 'force refresh must pass ?refresh=1').toContain('refresh=1');
    });

    test('empty-state renders with scope readout + per-project summary when no orphans', async ({ page }) => {
        // 2026-05-19 fix: when the scan returns no orphans the list area
        // used to render a 4-line empty-state with no operational context.
        // It now renders a richer panel: scan-scope readout (e.g. "7 EIPs ·
        // 1 ACM cert · 4 S3 buckets · 14 snapshots") + a Tracked Deployments
        // section listing every project from `data.projects` + an inline
        // Re-scan button.
        //
        // Strategy: stub /api/deploy/resources/all-projects with a 200
        // response that has zero orphans but a non-empty projects array.
        // This works in CI without depending on real AWS state.
        await page.route('**/api/deploy/resources/all-projects*', async (route) => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    success: true,
                    region: 'eu-central-1',
                    scanned_at: '2026-05-19T12:00:00Z',
                    projects: [
                        { project_name: 'c2_adhoc_test', deployment_type: 'c2-adhoc', deployed_at: '2026-05-01T00:00:00', region: 'eu-central-1', resource_count: 30 },
                        { project_name: 'goad_mini_test', deployment_type: 'goad-mini', deployed_at: '2026-05-02T00:00:00', region: 'eu-central-1', resource_count: 24 },
                    ],
                    total_projects: 2,
                    eips: [
                        // All attached + Project-tagged — no orphans.
                        // 2026-05-20: _detectOrphans was tightened to flag
                        // untagged bindings (instance attached but no Project
                        // tag) — see commit covering NAT EIP detection.
                        // The stub now sets project_tag so this stays non-orphan.
                        { allocation_id: 'eipalloc-1', public_ip: '1.2.3.4', instance_id: 'i-aaa', project_tag: 'c2_adhoc_test', region: 'eu-central-1' },
                    ],
                    acm_certs: [
                        { arn: 'arn:aws:acm:eu-central-1:1:certificate/aaa', domain: 'example.com', status: 'ISSUED', in_use: true, region: 'eu-central-1' },
                    ],
                    s3_buckets: [
                        { name: 'c2-adhoc-test-tfstate', region: 'eu-central-1' },
                    ],
                    snapshots: [
                        { snapshot_id: 'snap-aaa', volume_id: 'vol-aaa', state: 'completed', region: 'eu-central-1' },
                    ],
                    acm_us_east_1: [],
                }),
            });
        });

        await navigateToCleanupSubPill(page);
        // Force the load so our route stub serves the payload.
        await page.evaluate(() => loadCleanupResources(true));
        await page.waitForTimeout(400);

        // 4 summary tiles still render with 0s.
        await expect(page.locator('#cleanup-orphan-count')).toHaveText('0');
        await expect(page.locator('#cleanup-eip-count')).toHaveText('0');
        await expect(page.locator('#cleanup-acm-count')).toHaveText('0');
        await expect(page.locator('#cleanup-buckets-count')).toHaveText('0');

        // The empty-state title is present.
        await expect(page.locator('#subpill-pane-cleanup .cleanup-empty')).toBeVisible();
        await expect(page.locator('#subpill-pane-cleanup .empty-state__title')).toHaveText('No orphan resources detected');

        // Scope readout calls out the numbers we stubbed.
        const scope = await page.locator('#subpill-pane-cleanup .cleanup-empty__scope').textContent();
        expect(scope || '').toContain('1 EIPs');
        expect(scope || '').toContain('1 ACM certs');
        expect(scope || '').toContain('1 S3 buckets');
        expect(scope || '').toContain('1 snapshots');

        // Per-project summary panel renders both deployments.
        await expect(page.locator('#subpill-pane-cleanup .cleanup-empty__projects')).toBeVisible();
        const projRows = page.locator('#subpill-pane-cleanup .cleanup-summary-row');
        await expect(projRows).toHaveCount(2);
        // First project row content.
        await expect(projRows.nth(0).locator('.spec-row__key')).toHaveText('C2-ADHOC');
        await expect(projRows.nth(0).locator('.spec-row__value')).toHaveText('c2_adhoc_test');

        // Inline Re-scan CTA in the empty-state body.
        await expect(page.locator('#subpill-pane-cleanup .cleanup-empty .empty-state__cta button')).toBeVisible();
    });

    test('empty-state Re-scan button triggers a new fetch', async ({ page }) => {
        // The inline Re-scan button calls loadCleanupResources(true). Stub
        // the endpoint and assert the second fetch fires when clicked.
        let callCount = 0;
        await page.route('**/api/deploy/resources/all-projects*', async (route) => {
            callCount += 1;
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    success: true, region: 'eu-central-1', scanned_at: '2026-05-19T12:00:00Z',
                    projects: [], total_projects: 0,
                    eips: [], acm_certs: [], s3_buckets: [], snapshots: [], acm_us_east_1: [],
                }),
            });
        });
        await navigateToCleanupSubPill(page);
        await page.evaluate(() => loadCleanupResources(true));
        await page.waitForTimeout(300);
        const before = callCount;
        await page.locator('#subpill-pane-cleanup .cleanup-empty .empty-state__cta button').click();
        await page.waitForTimeout(300);
        expect(callCount, 'inline Re-scan must trigger another endpoint hit').toBeGreaterThan(before);
    });

    test('orphan EIPs render as cleanup-rows when the endpoint returns unattached ones', async ({ page }) => {
        // Asserts the round-trip from backend payload to rendered orphan row.
        // Stubs an unattached EIP (instance_id=null) — _detectOrphans should
        // promote it into orphans.eips and the renderer should emit a
        // .spec-row.cleanup-row with the EIP value.
        await page.route('**/api/deploy/resources/all-projects*', async (route) => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    success: true, region: 'eu-central-1', scanned_at: '2026-05-19T12:00:00Z',
                    projects: [], total_projects: 0,
                    eips: [
                        { allocation_id: 'eipalloc-orphan', public_ip: '203.0.113.99', instance_id: null, region: 'eu-central-1' },
                    ],
                    acm_certs: [], s3_buckets: [], snapshots: [], acm_us_east_1: [],
                }),
            });
        });
        await navigateToCleanupSubPill(page);
        await page.evaluate(() => loadCleanupResources(true));
        await page.waitForTimeout(400);
        // Orphan tile + EIP tile both 1.
        await expect(page.locator('#cleanup-orphan-count')).toHaveText('1');
        await expect(page.locator('#cleanup-eip-count')).toHaveText('1');
        // Row rendered.
        const rows = page.locator('#subpill-pane-cleanup .cleanup-row[data-kind="eip"]');
        await expect(rows).toHaveCount(1);
        await expect(rows.first().locator('.spec-row__value').first()).toContainText('203.0.113.99');
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
        //
        // 2026-05-20: stub the all-projects endpoint to return EMPTY so the
        // auto-fired loadCleanupResources (or any later poll) does not
        // overwrite our synthetic innerHTML injection with real backend data.
        await page.route('**/api/deploy/resources/all-projects*', async (route) => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    success: true, region: 'eu-central-1', scanned_at: '2026-05-19T12:00:00Z',
                    projects: [], total_projects: 0,
                    eips: [], acm_certs: [], s3_buckets: [], snapshots: [], acm_us_east_1: [],
                }),
            });
        });
        await navigateToCleanupSubPill(page);
        // Wait for the stubbed auto-load to settle (empty state) so it doesn't
        // race with our synthetic innerHTML injection.
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
