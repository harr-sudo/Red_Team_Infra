/**
 * D0 routing alias layer tests (Layer 2 — Vitest + jsdom).
 *
 * Since app.js is a 21K-line monolith with no exports, we exercise
 * NAVIGATE_ALIASES + resolveNavigationTarget by reading the source file
 * directly and asserting that the expected constants/functions landed.
 * This stays a smoke-level check; the real verification of D0 behavior
 * happens in the Playwright tests (no new browser tests in D0 — the
 * D3.0 snapshot will catch cross-link regressions when sub-pills come
 * online).
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

function loadAppJsSource() {
    const path = resolve(__dirname, '../../webapp/frontend/js/app.js');
    return readFileSync(path, 'utf8');
}

describe('D0 NAVIGATE_ALIASES map', () => {
    it('app.js defines a NAVIGATE_ALIASES constant', () => {
        const src = loadAppJsSource();
        expect(src).toContain('NAVIGATE_ALIASES');
        expect(src).toMatch(/const\s+NAVIGATE_ALIASES\s*=\s*\{/);
    });

    it('app.js defines a resolveNavigationTarget function', () => {
        const src = loadAppJsSource();
        expect(src).toContain('resolveNavigationTarget');
        expect(src).toMatch(/function\s+resolveNavigationTarget\s*\(/);
    });

    it('app.js defines a _readPersistedTarget helper for D0.3 backwards-compat', () => {
        const src = loadAppJsSource();
        expect(src).toContain('_readPersistedTarget');
    });

    it('NAVIGATE_ALIASES contains entries for all 10 current tabs', () => {
        const src = loadAppJsSource();
        // Extract just the NAVIGATE_ALIASES block to avoid matching tab
        // names mentioned elsewhere in the 21K-line file
        const match = src.match(/const NAVIGATE_ALIASES = \{[\s\S]*?\n\};/);
        expect(match).not.toBeNull();
        const block = match[0];
        for (const tab of ['dashboard', 'configuration', 'deployment', 'deployments',
                           'tools', 'aws-check', 'architecture', 'beacon', 'terminal', 'settings']) {
            expect(block).toContain(`'${tab}'`);
        }
    });

    it('All alias values are currently passthrough (subPill: null) — D0 introduces no behavior change', () => {
        const src = loadAppJsSource();
        const match = src.match(/const NAVIGATE_ALIASES = \{[\s\S]*?\n\};/);
        expect(match).not.toBeNull();
        const block = match[0];
        // No non-null subPill values yet — those land in D3.6 / D4.6 when the
        // merged parent tabs exist
        expect(block).not.toContain("subPill: 'configure'");
        expect(block).not.toContain("subPill: 'deploy'");
        expect(block).not.toContain("subPill: 'manage'");
    });

    it('APP object declares currentSubPill state field', () => {
        const src = loadAppJsSource();
        expect(src).toMatch(/currentSubPill:\s*null/);
    });
});
