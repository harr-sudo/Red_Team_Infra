/**
 * P1 #7.6 — Version footer + modal Playwright tests.
 *
 * Verifies:
 *   - Footer is visible on page load with the v<x.y.z> (<sha>) format
 *   - Footer remains readable in BOTH themes (color != background)
 *   - Click footer -> modal becomes visible and shows version/sha/built_at
 *   - Modal closes via close button + Escape key
 *   - "View changelog" link in modal points at /changelog
 */

import { test, expect } from '@playwright/test';

const VERSION_RE = /v\d+\.\d+\.\d+ \([0-9a-f]+\)/;

test.describe('version footer', () => {
    test('footer renders with v<version> (<sha>) format on page load', async ({ page }) => {
        await page.goto('/');
        const footer = page.locator('#app-version-footer');
        await footer.waitFor({ state: 'visible', timeout: 5000 });
        // Wait until the JS has populated the text from /api/version
        await expect(page.locator('#app-version-footer-text')).toHaveText(VERSION_RE, { timeout: 5000 });
    });

    test('footer is readable in dark mode (color != background)', async ({ page }) => {
        await page.goto('/');
        const footer = page.locator('#app-version-footer');
        await footer.waitFor({ state: 'visible', timeout: 5000 });
        const { color, background } = await footer.evaluate(el => {
            const cs = getComputedStyle(el);
            return { color: cs.color, background: cs.backgroundColor };
        });
        expect(color).not.toBe('');
        expect(color).not.toBe(background);
    });

    test('footer is readable in light mode (color != background)', async ({ page }) => {
        await page.goto('/');
        // Force light mode the same way the theme toggle does
        await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'light'));
        const footer = page.locator('#app-version-footer');
        await expect(footer).toBeVisible();
        const { color, background } = await footer.evaluate(el => {
            const cs = getComputedStyle(el);
            return { color: cs.color, background: cs.backgroundColor };
        });
        expect(color).not.toBe('');
        expect(color).not.toBe(background);
    });

    test('clicking footer opens the version modal with populated fields', async ({ page }) => {
        await page.goto('/');
        await expect(page.locator('#app-version-footer-text')).toHaveText(VERSION_RE, { timeout: 5000 });
        await page.locator('#app-version-footer').click();
        const modal = page.locator('#version-modal');
        await expect(modal).toBeVisible();
        // All three rows must be populated with non-empty, non-"unknown" data
        // (the dev server has a real VERSION + git SHA).
        await expect(page.locator('#version-modal-version')).toHaveText(/^\d+\.\d+\.\d+$/);
        await expect(page.locator('#version-modal-sha')).toHaveText(/^[0-9a-f]+$/);
        await expect(page.locator('#version-modal-built')).not.toHaveText(/^\s*$/);
    });

    test('modal close button hides the modal', async ({ page }) => {
        await page.goto('/');
        await expect(page.locator('#app-version-footer-text')).toHaveText(VERSION_RE, { timeout: 5000 });
        await page.locator('#app-version-footer').click();
        await expect(page.locator('#version-modal')).toBeVisible();
        await page.locator('.version-modal__close').click();
        await expect(page.locator('#version-modal')).toBeHidden();
    });

    test('Escape key closes the modal', async ({ page }) => {
        await page.goto('/');
        await expect(page.locator('#app-version-footer-text')).toHaveText(VERSION_RE, { timeout: 5000 });
        await page.locator('#app-version-footer').click();
        await expect(page.locator('#version-modal')).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(page.locator('#version-modal')).toBeHidden();
    });

    test('"View changelog" link in modal points to /changelog', async ({ page }) => {
        await page.goto('/');
        await expect(page.locator('#app-version-footer-text')).toHaveText(VERSION_RE, { timeout: 5000 });
        await page.locator('#app-version-footer').click();
        const link = page.locator('#version-modal-changelog');
        await expect(link).toBeVisible();
        // href may resolve as absolute — assert it ends with /changelog.
        const href = await link.getAttribute('href');
        expect(href).toBe('/changelog');
    });
});
