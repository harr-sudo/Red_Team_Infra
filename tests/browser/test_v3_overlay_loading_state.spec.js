/**
 * 2026-05-20 (UX audit Batch A · C3 + H5 + P1 + L1)
 *
 * Verifies the Prereqs overlay shows a spinner-animated loading state
 * BEFORE its async fetches resolve, and swaps in the resolved content
 * cleanly once the network responses arrive. Uses page.route to delay
 * the three /api/aws/* endpoints so the spinner is observable.
 *
 * Why this matters: the legacy implementation rendered plain text
 * "Running prereqs…" with no animation — operators on slow networks
 * couldn't tell whether the overlay was hung or working. The unified
 * `APP.overlay._withAsyncBody()` helper mounts a CSS spinner immediately
 * and swaps in either content (resolve) or an error card (reject /
 * timeout) without leaving the overlay stranded.
 */

import { test, expect } from '@playwright/test';

async function gotoDashboard(page) {
    await page.goto('/');
    await page.locator('[data-page="dashboard"]').first().waitFor({ timeout: 5000 });
    await page.waitForTimeout(300);
}

test.describe('v3 overlay loading state — spinner + async swap', () => {
    test('Prereqs overlay shows spinner before content arrives', async ({ page }) => {
        // Delay the three /api/aws/* endpoints so the spinner has time to
        // render and we can assert against it.
        await page.route('**/api/aws/credentials', async (route) => {
            await new Promise(r => setTimeout(r, 1500));
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({ success: true, identity: 'arn:test' }),
            });
        });
        await page.route('**/api/aws/ssh-key', async (route) => {
            await new Promise(r => setTimeout(r, 1500));
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({ success: true, path: '/tmp/test.key' }),
            });
        });
        await page.route('**/api/aws/permissions', async (route) => {
            await new Promise(r => setTimeout(r, 1500));
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({ success: true, message: 'ok' }),
            });
        });

        await gotoDashboard(page);

        // Trigger the Prereqs overlay programmatically so we don't depend
        // on a specific widget DOM hook.
        await page.evaluate(() => {
            if (window.APP && window.APP.overlay && window.APP.overlay.openPrereqs) {
                window.APP.overlay.openPrereqs();
            }
        });

        // Spinner must be visible BEFORE the 1500ms responses arrive.
        const spinner = page.locator('.app-overlay[data-overlay-id="prereqs"] .app-overlay__spinner');
        await spinner.waitFor({ state: 'visible', timeout: 3000 });
        await expect(spinner).toBeVisible();

        // Spinner sits next to a textual status line.
        const text = page.locator('.app-overlay[data-overlay-id="prereqs"] .app-overlay__loading-text');
        await expect(text).toContainText(/Running prereq/i);

        // Now wait for the content to swap in — the spec-list rows for
        // AWS Credentials, SSH Key, IAM Permissions appear when the
        // fetches resolve.
        await page.locator('.app-overlay[data-overlay-id="prereqs"] .spec-list')
            .waitFor({ state: 'visible', timeout: 8000 });

        // Loading host should be gone after the swap.
        await expect(page.locator('.app-overlay[data-overlay-id="prereqs"] .app-overlay__loading'))
            .toHaveCount(0);

        // Sanity — at least one row rendered.
        const rowCount = await page.locator('.app-overlay[data-overlay-id="prereqs"] .spec-row').count();
        expect(rowCount).toBeGreaterThan(0);
    });

    test('APP.overlay exposes _withAsyncBody helper', async ({ page }) => {
        await gotoDashboard(page);
        const surface = await page.evaluate(() => ({
            withAsyncBody: typeof window.APP?.overlay?._withAsyncBody === 'function',
            loadingHost: typeof window.APP?.overlay?._loadingHost === 'function',
        }));
        expect(surface.withAsyncBody).toBe(true);
        expect(surface.loadingHost).toBe(true);
    });
});
