/**
 * P1 #7.7 — T1 design pilot Playwright tests.
 *
 * Verifies:
 *   - /preview/header loads compare view with BOTH iframes
 *   - /preview/header?variant=baseline serves baseline page only (no compare grid)
 *   - /preview/header?variant=taste serves taste-skill page only
 *   - Both iframes loaded successfully (non-zero content height — no 404)
 *   - Theme toggle button flips the root data-theme attribute
 *
 * These tests are temporary — slated for removal at D1 completion per
 * Plan §17/§24 alongside the preview routes and pilot HTML files.
 */

import { test, expect } from '@playwright/test';

test.describe('design pilot — temporary, removed at D1 end', () => {
    test('compare view shows both iframes', async ({ page }) => {
        await page.goto('/preview/header');
        const iframes = page.locator('.compare-pane iframe');
        await expect(iframes).toHaveCount(2);
    });

    test('variant=baseline serves baseline page only (no compare grid)', async ({ page }) => {
        const response = await page.goto('/preview/header?variant=baseline');
        expect(response.status()).toBe(200);
        await expect(page.locator('.compare-grid')).toHaveCount(0);
    });

    test('variant=taste serves taste-skill page only (no compare grid)', async ({ page }) => {
        const response = await page.goto('/preview/header?variant=taste');
        expect(response.status()).toBe(200);
        await expect(page.locator('.compare-grid')).toHaveCount(0);
    });

    test('both iframes load successfully (non-zero content height)', async ({ page }) => {
        await page.goto('/preview/header');
        // Wait until each iframe's document is ready and has rendered content.
        const handles = await page.locator('.compare-pane iframe').elementHandles();
        expect(handles.length).toBe(2);
        for (const handle of handles) {
            const frame = await handle.contentFrame();
            expect(frame, 'iframe should have a content frame (loaded, not 404)').not.toBeNull();
            // Wait for DOM load inside the iframe before measuring.
            await frame.waitForLoadState('domcontentloaded');
            const bodyHeight = await frame.evaluate(() => document.body ? document.body.scrollHeight : 0);
            expect(bodyHeight, 'iframe body should have non-zero height').toBeGreaterThan(0);
        }
    });

    test('theme toggle flips root data-theme attribute', async ({ page }) => {
        await page.goto('/preview/header');
        const initial = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
        // Preview pages default to light per user preference; toggle flips to dark then back.
        expect(initial).toBe('light');
        await page.locator('#theme-toggle').click();
        const after = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
        expect(after).toBe('dark');
        await page.locator('#theme-toggle').click();
        const afterToggleBack = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
        expect(afterToggleBack).toBe('light');
    });
});
