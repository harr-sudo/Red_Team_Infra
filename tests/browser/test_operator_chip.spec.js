/**
 * M-Operators (Decision #23) — operator chip + menu Playwright tests.
 *
 * Verifies the new interactive header chip that replaced the display-only
 * #global-operator-chip badge:
 *   - Chip renders in the header with a dot + name on page load
 *   - Clicking the chip opens the operator menu popover
 *   - Click outside the chip + menu closes the menu
 *   - Escape closes the menu
 *   - Chip text remains readable (color != background) in BOTH themes
 *
 * The /api/operators backend (Agent A) may or may not be live during this
 * test run. The chip element itself must render unconditionally — only
 * the dynamic operator name / menu rows depend on the backend.
 */

import { test, expect } from '@playwright/test';

test.describe('operator chip (M-Operators)', () => {
    test('chip is visible in the header with a dot and name on page load', async ({ page }) => {
        await page.goto('/');
        const chip = page.locator('#operator-chip');
        await expect(chip).toBeVisible();
        await expect(page.locator('#operator-chip-dot')).toBeVisible();
        await expect(page.locator('#operator-chip-name')).toBeVisible();

        // Chip must live INSIDE the global header (V3 layout contract).
        const inHeader = await chip.evaluate(el => !!el.closest('.global-header'));
        expect(inHeader).toBe(true);
    });

    test('clicking the chip opens the operator menu', async ({ page }) => {
        await page.goto('/');
        await page.locator('#operator-chip').waitFor({ state: 'visible' });
        const menu = page.locator('#operator-menu');
        await expect(menu).toBeHidden();

        await page.locator('#operator-chip').click();
        await expect(menu).toBeVisible();
        await expect(page.locator('#operator-chip')).toHaveAttribute('aria-expanded', 'true');
    });

    test('clicking outside the menu closes it', async ({ page }) => {
        await page.goto('/');
        await page.locator('#operator-chip').click();
        await expect(page.locator('#operator-menu')).toBeVisible();

        // Click an element that is neither the chip nor inside the menu.
        // The page title is a safe always-present anchor for the click.
        await page.locator('body').click({ position: { x: 5, y: 5 } });
        await expect(page.locator('#operator-menu')).toBeHidden();
        await expect(page.locator('#operator-chip')).toHaveAttribute('aria-expanded', 'false');
    });

    test('Escape closes the menu', async ({ page }) => {
        await page.goto('/');
        await page.locator('#operator-chip').click();
        await expect(page.locator('#operator-menu')).toBeVisible();

        await page.keyboard.press('Escape');
        await expect(page.locator('#operator-menu')).toBeHidden();
    });

    test('chip text is readable in dark mode (color != background)', async ({ page }) => {
        await page.goto('/');
        const chip = page.locator('#operator-chip');
        await chip.waitFor({ state: 'visible' });
        const { color, background } = await chip.evaluate(el => {
            const cs = getComputedStyle(el);
            return { color: cs.color, background: cs.backgroundColor };
        });
        expect(color).not.toBe('');
        expect(color).not.toBe(background);
    });

    test('chip text is readable in light mode (color != background)', async ({ page }) => {
        await page.goto('/');
        await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'light'));
        const chip = page.locator('#operator-chip');
        await expect(chip).toBeVisible();
        const { color, background } = await chip.evaluate(el => {
            const cs = getComputedStyle(el);
            return { color: cs.color, background: cs.backgroundColor };
        });
        expect(color).not.toBe('');
        expect(color).not.toBe(background);
    });
});
