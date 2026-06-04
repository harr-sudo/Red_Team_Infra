/**
 * v3 BOLT-ON CURRICULUM — Bolt-on detail drawer with 3 tabs.
 *
 * Validates the unified Bolt-on detail surface that wraps three faces
 * of one vulnerability:
 *
 *   1. Walkthrough — guided steps + assessment (curriculum block)
 *   2. Detections — existing Elastic rules surfaced (detection block)
 *   3. Install — descriptor metadata
 *
 * Seeds a goad-mini deployment, mocks the bolton catalog routes so the
 * kerberoastable-svc card appears, then drives the drawer via the same
 * JS entry-point the row-click handler invokes (APP.bolton.openDetail).
 *
 * The row-click → openDetail wiring is verified by a single smoke test
 * (`Walkthrough button on row is wired to openDetail`); every other test
 * exercises the drawer code directly so the suite doesn't fight
 * Playwright's headless visibility heuristic on the nested bolt-on
 * sections (which clip overflow in unpredictable ways at small
 * viewports). The end-to-end user flow is still covered — the click
 * handler dispatch is asserted to call the same function the tests use.
 */

import { test, expect } from '@playwright/test';
import { seedDeployment } from './helpers/seed-deployment.js';
import { railNavigate, clickSubPill } from './helpers/nav.js';

const VULN_ID = 'bolton.identity-kerberos.kerberoastable-svc';

test.beforeEach(async ({ page }) => {
    page.on('pageerror', (err) => {
        // eslint-disable-next-line no-console
        console.log('[page-error]', (err && err.message) || err);
    });
});

async function mockBoltonRoutes(page) {
    let progressState = {
        operator_id: 'test_op', vuln_id: VULN_ID,
        started_at: null, completed_at: null,
        completed_steps: [], assessments: {},
    };

    await page.route('**/api/bolton/labs/*/hosts', async (route) => {
        await route.fulfill({
            status: 200, contentType: 'application/json',
            body: JSON.stringify({
                success: true, lab: 'goad_test_alpha',
                hosts: [{ name: 'tldc01', role: 'domain_controller',
                          os: 'Windows 2022', ip: '10.0.10.10',
                          installed_count: 0 }],
            }),
        });
    });
    await page.route('**/api/bolton/labs/*/hosts/*/facts', async (route) => {
        await route.fulfill({
            status: 200, contentType: 'application/json',
            body: JSON.stringify({
                success: true, host: 'tldc01', host_id: 'tldc01',
                os_family: 'windows', os_version: '2022',
                role: 'domain_controller', gathered_at: new Date().toISOString(),
                stale: false, installed_boltons: [],
            }),
        });
    });
    await page.route('**/api/bolton/labs/*/hosts/*/catalog', async (route) => {
        await route.fulfill({
            status: 200, contentType: 'application/json',
            body: JSON.stringify({
                success: true, host_id: 'tldc01',
                host_facts_summary: {
                    os: 'windows 2022', role: 'domain_controller',
                    installed_count: 0, stale: false,
                    collected_at: new Date().toISOString(),
                },
                counts_by_state: { INSTALLABLE: 1 },
                vulns: [{
                    id: VULN_ID, name: 'Kerberoastable Service Account',
                    slug: 'kerberoastable-svc', category: 'identity-kerberos',
                    subcategory: 'kerberoasting',
                    tags: ['kerberos', 'credential-access'],
                    coverage_status: 'covered', cve: [],
                    mitre_technique: 'T1558', status: 'stable',
                    description: 'Creates an AD user account with a registered SPN and weak password.',
                    has_curriculum: true, curriculum_step_count: 5,
                    state: 'INSTALLABLE', reason: null, suggested_action: null,
                    blocking: false, rollback_supported: true,
                    estimated_time_seconds: 30,
                }],
            }),
        });
    });
    await page.route(`**/api/bolton/vulns/${VULN_ID}`, async (route) => {
        await route.fulfill({
            status: 200, contentType: 'application/json',
            body: JSON.stringify({
                success: true,
                vuln: {
                    id: VULN_ID, name: 'Kerberoastable Service Account',
                    slug: 'kerberoastable-svc', category: 'identity-kerberos',
                    subcategory: 'kerberoasting',
                    description: 'Creates an AD user account with a registered SPN and weak password.',
                    status: 'stable',
                    mitre: {
                        tactic: { id: 'TA0006', name: 'Credential Access' },
                        technique: { id: 'T1558', name: 'Steal or Forge Kerberos Tickets' },
                        subtechnique: { id: 'T1558.003', name: 'Kerberoasting' },
                    },
                    install: { estimated_time_seconds: 30 },
                    patch: { rollback_supported: true },
                    detection: {
                        coverage_status: 'covered',
                        elastic_rules: [
                            { rule_uuid: '897dc6b5-b39f-432a-8d75-d3730d50c782',
                              rule_name: 'Kerberoasting, Unusual Process Behavior',
                              coverage: 'full', confidence: 'high',
                              last_validated: '2026-04-15' },
                            { rule_uuid: '0b2f3da5-b5ec-47d1-908b-6ebb74814289',
                              rule_name: 'SPN Attribute Modified',
                              coverage: 'indirect', confidence: 'medium',
                              last_validated: '2026-04-15' },
                        ],
                        signal_sources: ['Windows Event 4769', 'Windows Event 5136'],
                    },
                },
            }),
        });
    });
    await page.route(`**/api/bolton/vulns/${VULN_ID}/curriculum`, async (route) => {
        await route.fulfill({
            status: 200, contentType: 'application/json',
            body: JSON.stringify({
                success: true, vuln_id: VULN_ID,
                curriculum: {
                    title: 'Kerberoasting end-to-end',
                    summary: 'Guided walkthrough of T1558.003 against the lab service account.',
                    learning_objectives: ['Enumerate SPNs', 'Crack TGS offline'],
                    prerequisites: ['rockyou.txt', 'hashcat'],
                    estimated_total_minutes: 35,
                    steps: [
                        { id: '01-discover-spns', title: 'Enumerate SPNs',
                          markdown: '## Step 1\n\nFind every account with an SPN.',
                          assets: [], estimated_minutes: 5 },
                        { id: '02-request-tgs', title: 'Request TGS',
                          markdown: '## Step 2\n\nRoast it.',
                          assets: [], estimated_minutes: 5 },
                        { id: '03-crack-offline', title: 'Crack offline',
                          markdown: '## Step 3\n\nhashcat mode 13100.',
                          assets: [],
                          assessment: {
                              question: 'Which hashcat mode for TGS-REP RC4?',
                              options: ['5500', '13100', '1000', '18200'],
                              correct_index: 1,
                              explanation: '13100 is the canonical mode.',
                          },
                          estimated_minutes: 15 },
                        { id: '04-detection-mapping', title: 'Detections',
                          markdown: '## Step 4\n\nElastic rules.',
                          assets: [], estimated_minutes: 5 },
                        { id: '05-apply-patch', title: 'Patch and re-test',
                          markdown: '## Step 5\n\nApply the patch.',
                          assets: [], estimated_minutes: 5 },
                    ],
                },
                progress: progressState,
            }),
        });
    });
    await page.route(`**/api/bolton/vulns/${VULN_ID}/progress/step`, async (route) => {
        const body = JSON.parse(route.request().postData() || '{}');
        if (body.action === 'undo') {
            progressState.completed_steps = progressState.completed_steps.filter(s => s !== body.step_id);
            progressState.completed_at = null;
        } else {
            if (!progressState.completed_steps.includes(body.step_id)) {
                progressState.completed_steps.push(body.step_id);
            }
            if (progressState.completed_steps.length >= 5) {
                progressState.completed_at = new Date().toISOString();
            }
        }
        await route.fulfill({
            status: 200, contentType: 'application/json',
            body: JSON.stringify({ success: true, progress: progressState }),
        });
    });
    await page.route(`**/api/bolton/vulns/${VULN_ID}/progress/assessment`, async (route) => {
        const body = JSON.parse(route.request().postData() || '{}');
        const correct = body.answer_index === 1;
        progressState.assessments[body.step_id] = {
            answer_index: body.answer_index, correct,
            answered_at: new Date().toISOString(),
        };
        progressState.latest_correct = correct;
        progressState.latest_step = body.step_id;
        await route.fulfill({
            status: 200, contentType: 'application/json',
            body: JSON.stringify({
                success: true, correct, correct_index: 1,
                explanation: '13100 is the canonical mode.',
                progress: progressState,
            }),
        });
    });
}

async function bootBoltOns(page) {
    await seedDeployment(page, { type: 'goad-mini', name: 'goad_test_alpha' });
    await mockBoltonRoutes(page);
    await page.goto('/');
    await railNavigate(page, 'deployments-tab');
    await clickSubPill(page, 'bolt-ons');
    // Wait for the host dropdown to populate from the mocked /hosts route.
    await page.waitForFunction(
        () => !!document.querySelector('#bolton-host-select option[value="tldc01"]'),
        { timeout: 5000 },
    );
}

async function openDrawer(page, initialTab = 'walkthrough') {
    await page.evaluate(({ vid, tab }) => {
        window.APP.bolton.selectHost('goad_test_alpha', 'tldc01');
        // Allow the catalog-render microtask to settle, then invoke the
        // same entry-point the Walkthrough button's click handler does.
        return new Promise((resolve) => {
            setTimeout(() => {
                window.APP.bolton.openDetail(vid, tab);
                resolve();
            }, 40);
        });
    }, { vid: VULN_ID, tab: initialTab });
    await page.waitForSelector('.bolton-detail', { state: 'visible', timeout: 5000 });
}

// ─────────────────────────────────────────────────────────────────────────
// 1. ROW WIRING — the Walkthrough button on a row dispatches to openDetail
// ─────────────────────────────────────────────────────────────────────────

test('Row-level Walkthrough button is rendered and wired to openDetail', async ({ page }) => {
    await bootBoltOns(page);
    await page.evaluate(() => window.APP.bolton.selectHost('goad_test_alpha', 'tldc01'));
    // Wait for the row to mount in the DOM.
    await page.waitForFunction(
        (vid) => !!document.querySelector(`.bt-row[data-vuln-id="${vid}"] .bt-row__walkthrough`),
        VULN_ID,
        { timeout: 5000 },
    );
    // Inspect attributes that prove the click is wired to the openDetail action.
    const wiring = await page.evaluate((vid) => {
        const btn = document.querySelector(`.bt-row[data-vuln-id="${vid}"] .bt-row__walkthrough`);
        return {
            found: !!btn,
            text: btn ? btn.textContent.trim() : null,
            action: btn ? btn.dataset.boltonAction : null,
            tab: btn ? btn.dataset.initialTab : null,
            dispatcherWires: typeof window.APP.bolton.openDetail === 'function',
        };
    }, VULN_ID);
    expect(wiring.found).toBe(true);
    expect(wiring.text).toContain('Walkthrough');
    expect(wiring.text).toContain('5');             // step count
    expect(wiring.action).toBe('openDetail');       // dispatcher target
    expect(wiring.tab).toBe('walkthrough');         // initial tab
    expect(wiring.dispatcherWires).toBe(true);      // function exists
    // Now dispatch the click handler exactly like a real click would.
    // This goes through the same code path as the user's click event.
    await page.evaluate((vid) => {
        const btn = document.querySelector(`.bt-row[data-vuln-id="${vid}"] .bt-row__walkthrough`);
        btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    }, VULN_ID);
    await expect(page.locator('.bolton-detail')).toBeVisible({ timeout: 5000 });
});

// ─────────────────────────────────────────────────────────────────────────
// 2. DRAWER — three tabs render, walkthrough active by default
// ─────────────────────────────────────────────────────────────────────────

test('Drawer mounts with three tabs and walkthrough active by default', async ({ page }) => {
    await bootBoltOns(page);
    await openDrawer(page);
    const tabs = page.locator('.bolton-detail__tab');
    await expect(tabs).toHaveCount(3);
    await expect(tabs.nth(0)).toContainText('Install');
    await expect(tabs.nth(1)).toContainText('Walkthrough');
    await expect(tabs.nth(2)).toContainText('Detections');
    await expect(tabs.nth(1)).toHaveClass(/is-active/);
});

// ─────────────────────────────────────────────────────────────────────────
// 3. WALKTHROUGH PANE — title, summary, step list, first article body
// ─────────────────────────────────────────────────────────────────────────

test('Walkthrough pane renders curriculum title, step list, and first step body', async ({ page }) => {
    await bootBoltOns(page);
    await openDrawer(page);
    await expect(page.locator('.bolton-walk__title')).toContainText('Kerberoasting end-to-end');
    await expect(page.locator('.bolton-walk__summary')).toContainText('T1558.003');
    await expect(page.locator('.bolton-walk__step')).toHaveCount(5);
    // Markdown is rendered to HTML via marked.js.
    await expect(page.locator('.bolton-walk__article-head h3')).toContainText('Enumerate SPNs');
    await expect(page.locator('.bolton-walk__article-body')).toContainText('Find every account with an SPN');
    await expect(page.locator('[data-bolton-walk-progress-label]')).toContainText('0 of 5');
});

// ─────────────────────────────────────────────────────────────────────────
// 4. STEP NAVIGATION + MARK COMPLETE
// ─────────────────────────────────────────────────────────────────────────

test('Mark step complete updates progress bar and step check icon', async ({ page }) => {
    await bootBoltOns(page);
    await openDrawer(page);
    await page.locator('[data-bolton-walk-toggle]').click();
    await expect(page.locator('[data-bolton-walk-progress-label]')).toContainText('1 of 5', { timeout: 5000 });
    await expect(page.locator('.bolton-walk__step').first()).toHaveClass(/is-done/);
});

// ─────────────────────────────────────────────────────────────────────────
// 5. ASSESSMENT — correct + wrong answers
// ─────────────────────────────────────────────────────────────────────────

test('Assessment correct answer highlights green and shows explanation', async ({ page }) => {
    await bootBoltOns(page);
    await openDrawer(page);
    await page.locator('[data-bolton-walk-step="03-crack-offline"]').click();
    await expect(page.locator('.bolton-walk__assessment')).toBeVisible();
    await page.locator('[data-bolton-walk-answer="1"]').click();
    await expect(page.locator('.bolton-walk__option').nth(1)).toHaveClass(/is-correct/);
    await expect(page.locator('[data-bolton-walk-feedback]')).toContainText('Correct');
    await expect(page.locator('[data-bolton-walk-feedback]')).toContainText('canonical');
});

test('Assessment wrong answer highlights red', async ({ page }) => {
    await bootBoltOns(page);
    await openDrawer(page);
    await page.locator('[data-bolton-walk-step="03-crack-offline"]').click();
    await page.locator('[data-bolton-walk-answer="0"]').click();
    await expect(page.locator('.bolton-walk__option').nth(0)).toHaveClass(/is-wrong/);
    await expect(page.locator('[data-bolton-walk-feedback]')).toContainText('Not quite');
});

// ─────────────────────────────────────────────────────────────────────────
// 6. DETECTIONS TAB surfaces the Elastic rules from the manifest
// ─────────────────────────────────────────────────────────────────────────

test('Detections tab lists Elastic rules from the bolt-on manifest', async ({ page }) => {
    await bootBoltOns(page);
    await openDrawer(page);
    await page.locator('[data-bolton-detail-tab="detections"]').click();
    const pane = page.locator('[data-bolton-detail-pane="detections"]');
    await expect(pane).toBeVisible();
    await expect(pane).toContainText('Kerberoasting, Unusual Process Behavior');
    await expect(pane).toContainText('SPN Attribute Modified');
    await expect(pane).toContainText('897dc6b5-b39f-432a-8d75-d3730d50c782');
    await expect(pane).toContainText('Windows Event 4769');
});

// ─────────────────────────────────────────────────────────────────────────
// 7. INSTALL TAB surfaces descriptor metadata (MITRE, ETA, status)
// ─────────────────────────────────────────────────────────────────────────

test('Install tab shows descriptor metadata (MITRE, status, ETA)', async ({ page }) => {
    await bootBoltOns(page);
    await openDrawer(page);
    await page.locator('[data-bolton-detail-tab="install"]').click();
    const pane = page.locator('[data-bolton-detail-pane="install"]');
    await expect(pane).toBeVisible();
    await expect(pane).toContainText('TA0006');
    await expect(pane).toContainText('Credential Access');
    await expect(pane).toContainText('T1558.003');
    await expect(pane).toContainText('Kerberoasting');
    await expect(pane).toContainText('~30s');
});
