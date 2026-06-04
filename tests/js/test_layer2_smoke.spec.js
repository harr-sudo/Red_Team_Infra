/**
 * Layer 2 smoke test — Vitest + jsdom.
 *
 * Purpose: prove the Vitest + jsdom test layer is wired and runnable.
 *
 * What this layer does NOT test (deliberately, see §26.3):
 *   webapp/frontend/js/app.js is a 21,187-line monolith with no ES module
 *   exports — every function lives on `window` and references global
 *   constants (APP, BEACON, TERMINAL, DEPLOYMENT_CONFIGS). Vitest can load
 *   it into jsdom but cannot import named exports for isolated unit testing.
 *
 *   App.js logic that NEEDS testing is exercised at Layer 3 (Playwright,
 *   tests/browser/) instead, where the real DOM + CSS + async behavior is
 *   already present.
 *
 *   When app.js is modularized in a future refactor (P3 #27), Layer 2 will
 *   acquire real unit tests for individual modules. Until then this file is
 *   the canary that proves the Vitest pipeline runs.
 */

import { describe, it, expect } from 'vitest';

describe('Layer 2 smoke', () => {
    it('vitest + jsdom is reachable', () => {
        expect(1 + 1).toBe(2);
    });

    it('jsdom DOM globals are available', () => {
        // If jsdom is configured correctly (vitest.config.js sets
        // environment: "jsdom"), `document` and `window` should exist.
        expect(typeof document).toBe('object');
        expect(typeof window).toBe('object');
    });

    it('can create and query DOM elements', () => {
        const div = document.createElement('div');
        div.id = 'smoke-test';
        div.textContent = 'hello';
        document.body.appendChild(div);
        const found = document.getElementById('smoke-test');
        expect(found).not.toBeNull();
        expect(found.textContent).toBe('hello');
        document.body.removeChild(div);
    });
});
