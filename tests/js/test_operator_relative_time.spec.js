/**
 * M-Operators (Decision #23) — _relativeTime + _activityVerb unit tests.
 *
 * app.js is the same 21K+-line monolith referenced in
 * tests/js/test_navigate_aliases.spec.js — no ES exports, every function
 * lives on `window`. To unit-test the small pure helpers added by
 * M-Operators (`_relativeTime`, `_activityVerb`), we read the source and
 * extract just those two functions via regex, eval them in jsdom, and
 * assert on the resulting globals.
 *
 * This is the same pattern used by test_navigate_aliases.spec.js
 * (source-scrape + assertion). Real DOM behavior is covered by the
 * Playwright suite in tests/browser/test_operator_chip.spec.js.
 */

import { describe, it, expect, beforeAll } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

function loadAppJsSource() {
    const path = resolve(__dirname, '../../webapp/frontend/js/app.js');
    return readFileSync(path, 'utf8');
}

// Pull just the named function bodies out of the monolith so we can eval
// them in isolation. Regex anchors on `^function ${name}` (column 0) so
// it picks the module-scope definition, not any inner copies introduced
// by later agents inside IIFEs. Matches up to the closing brace at
// column 0 (matches the file's actual formatting).
function extractFn(src, name) {
    const re = new RegExp(`^function ${name}\\b[\\s\\S]*?^\\}`, 'm');
    const m = src.match(re);
    if (!m) throw new Error(`Could not extract function ${name} from app.js`);
    return m[0];
}

let _relativeTime;
let _activityVerb;

beforeAll(() => {
    const src = loadAppJsSource();
    // eslint-disable-next-line no-new-func
    const factory = new Function(
        `${extractFn(src, '_relativeTime')}\n${extractFn(src, '_activityVerb')}\n` +
        `return { _relativeTime, _activityVerb };`
    );
    const exported = factory();
    _relativeTime = exported._relativeTime;
    _activityVerb = exported._activityVerb;
});

describe('M-Operators _relativeTime', () => {
    it('returns empty string for falsy input', () => {
        expect(_relativeTime('')).toBe('');
        expect(_relativeTime(null)).toBe('');
        expect(_relativeTime(undefined)).toBe('');
    });

    it('returns empty string for invalid ISO string', () => {
        expect(_relativeTime('not-a-date')).toBe('');
    });

    it('returns "Ns ago" for sub-minute durations', () => {
        const iso = new Date(Date.now() - 15_000).toISOString();
        expect(_relativeTime(iso)).toMatch(/^\d+s ago$/);
    });

    it('returns "Nm ago" for minute durations', () => {
        const iso = new Date(Date.now() - 5 * 60_000).toISOString();
        expect(_relativeTime(iso)).toMatch(/^\d+m ago$/);
    });

    it('returns "Nh ago" for hour durations', () => {
        const iso = new Date(Date.now() - 3 * 60 * 60_000).toISOString();
        expect(_relativeTime(iso)).toMatch(/^\d+h ago$/);
    });

    it('returns "Nd ago" for multi-day durations', () => {
        const iso = new Date(Date.now() - 4 * 24 * 60 * 60_000).toISOString();
        expect(_relativeTime(iso)).toMatch(/^\d+d ago$/);
    });

    it('clamps future timestamps to 0s (does not return negative)', () => {
        const iso = new Date(Date.now() + 5_000).toISOString();
        // 0s ago is the floor — never negative.
        expect(_relativeTime(iso)).toBe('0s ago');
    });
});

describe('M-Operators _activityVerb', () => {
    it('maps known actions to human verbs', () => {
        expect(_activityVerb('deploy.apply')).toBe('deployed');
        expect(_activityVerb('deploy.destroy')).toBe('destroyed');
        expect(_activityVerb('beacon.exec')).toBe('ran a command on');
        expect(_activityVerb('operator.add')).toBe('added operator');
        expect(_activityVerb('operator.switch')).toBe('switched to');
    });

    it('returns the raw action for unknown actions', () => {
        expect(_activityVerb('unknown.action')).toBe('unknown.action');
    });

    it('returns empty string for falsy input (no NPE)', () => {
        expect(_activityVerb(undefined)).toBe('');
        expect(_activityVerb(null)).toBe('');
        expect(_activityVerb('')).toBe('');
    });
});
