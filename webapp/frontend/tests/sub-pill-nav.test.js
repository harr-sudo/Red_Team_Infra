#!/usr/bin/env node
/**
 * Node-runnable test for sub-pill nav pure-logic.
 * No DOM, no browser — exercises the visibility mapping and hash parser.
 *
 * Run:  node webapp/frontend/tests/sub-pill-nav.test.js
 */

'use strict';

// ----- Inline the pure-logic slice under test -----
const APP = {};

APP.activeDeployment = (function() {
    const DRAFT_SENTINEL = '__draft__';
    const ALL_SENTINEL = '__all__';
    const state = { current: null };
    return {
        DRAFT_SENTINEL, ALL_SENTINEL,
        get current() { return state.current; },
        isDraft() { return state.current === DRAFT_SENTINEL; },
        isAll() { return state.current === ALL_SENTINEL; },
        isExisting() {
            return !!state.current && state.current !== DRAFT_SENTINEL && state.current !== ALL_SENTINEL;
        },
        // 2026-05-19 — Sentinel filter for any code that renders the
        // active deployment name. Sentinels (`__draft__`, `__all__`) must
        // NEVER leak into UI text.
        displayName(value) {
            const v = arguments.length > 0 ? value : state.current;
            if (v === DRAFT_SENTINEL) return 'Draft (unnamed)';
            if (v === ALL_SENTINEL)   return 'All deployments';
            return v || '';
        },
        set(v) { state.current = v || null; },
    };
})();

APP.computeVisibleSubPills = function(activeDeployment) {
    const isDraft    = activeDeployment.isDraft();
    const isAll      = activeDeployment.isAll();
    const isExisting = activeDeployment.isExisting();
    // Cleanup is universal — always available regardless of mode.
    const base = isDraft
        ? ['configure', 'deploy']
        : isAll
            ? ['manage']
            : isExisting
                ? ['manage', 'bolt-ons']
                : ['manage'];
    base.push('cleanup');
    return base;
};

APP.parseDeploymentsHash = function(hash) {
    if (!hash) return null;
    const clean = hash.replace(/^#/, '');
    if (!clean.startsWith('deployments-tab')) return null;
    const rest = clean.slice('deployments-tab'.length);
    if (!rest) return { page: 'deployments', subPill: null, params: {} };
    const m = rest.match(/^\/([a-zA-Z0-9_-]+)(?:\?(.*))?$/);
    if (!m) return { page: 'deployments', subPill: null, params: {} };
    const subPill = m[1];
    const params = {};
    if (m[2]) {
        m[2].split('&').forEach(pair => {
            if (!pair) return;
            const [k, v] = pair.split('=');
            params[decodeURIComponent(k)] = v == null ? '' : decodeURIComponent(v);
        });
    }
    return { page: 'deployments', subPill, params };
};

// ----- Tiny test harness -----
let passed = 0, failed = 0;
function eq(name, actual, expected) {
    const same = JSON.stringify(actual) === JSON.stringify(expected);
    if (same) { passed++; console.log('  PASS  ' + name); }
    else      { failed++; console.log('  FAIL  ' + name + '\n        expected: ' + JSON.stringify(expected) + '\n        actual:   ' + JSON.stringify(actual)); }
}
function ok(name, cond) {
    if (cond) { passed++; console.log('  PASS  ' + name); }
    else      { failed++; console.log('  FAIL  ' + name); }
}

console.log('\n=== Sub-pill visibility ===');
APP.activeDeployment.set(null);
eq('unset → [manage, cleanup]', APP.computeVisibleSubPills(APP.activeDeployment), ['manage', 'cleanup']);
ok('unset → !isDraft', !APP.activeDeployment.isDraft());

APP.activeDeployment.set('__draft__');
ok('draft sentinel → isDraft', APP.activeDeployment.isDraft());
eq('draft → [configure, deploy, cleanup]', APP.computeVisibleSubPills(APP.activeDeployment), ['configure', 'deploy', 'cleanup']);

APP.activeDeployment.set('__all__');
ok('all sentinel → isAll', APP.activeDeployment.isAll());
eq('all → [manage, cleanup]', APP.computeVisibleSubPills(APP.activeDeployment), ['manage', 'cleanup']);

APP.activeDeployment.set('c2_adhoc_dev_harriss_macbook_pro_01');
ok('existing → isExisting', APP.activeDeployment.isExisting());
eq('existing → [manage, bolt-ons, cleanup]', APP.computeVisibleSubPills(APP.activeDeployment), ['manage', 'bolt-ons', 'cleanup']);

console.log('\n=== Draft state lifecycle ===');
APP.activeDeployment.set('__draft__');
ok('in draft', APP.activeDeployment.isDraft());
APP.activeDeployment.set('some-project');
ok('picking real → !isDraft', !APP.activeDeployment.isDraft());
ok('picking real → isExisting', APP.activeDeployment.isExisting());

APP.activeDeployment.set('__draft__');
APP.activeDeployment.set(null);
ok('discard → current null', APP.activeDeployment.current === null);
ok('discard → !isDraft', !APP.activeDeployment.isDraft());

console.log('\n=== Sentinel displayName ===');
APP.activeDeployment.set(null);
eq('null → ""', APP.activeDeployment.displayName(), '');
APP.activeDeployment.set('__draft__');
eq('draft → "Draft (unnamed)"', APP.activeDeployment.displayName(), 'Draft (unnamed)');
APP.activeDeployment.set('__all__');
eq('all → "All deployments"', APP.activeDeployment.displayName(), 'All deployments');
APP.activeDeployment.set('myproj');
eq('real → "myproj"', APP.activeDeployment.displayName(), 'myproj');
eq('explicit __draft__ arg → "Draft (unnamed)"', APP.activeDeployment.displayName('__draft__'), 'Draft (unnamed)');
eq('explicit __all__ arg → "All deployments"', APP.activeDeployment.displayName('__all__'), 'All deployments');

// 2026-05-19 (operator override) — out-of-mode sub-pills must be truly
// hidden (display:none) via the native `hidden` attribute, not just
// dimmed. The visibility logic in APP.subPills.applyFromState() uses
// computeVisibleSubPills() as the source of truth, then applies
// [hidden] to any pill not in the visible set. Simulate that pipeline
// here with a tiny DOM stub so the contract is testable without jsdom.
console.log('\n=== Pill [hidden] attribute (operator override) ===');
function makePillStub(name) {
    const attrs = {};
    const classes = new Set();
    return {
        dataset: { subpill: name },
        classList: {
            toggle(klass, on) { if (on) classes.add(klass); else classes.delete(klass); },
            contains(klass) { return classes.has(klass); },
        },
        setAttribute(k, v) { attrs[k] = v == null ? '' : String(v); },
        removeAttribute(k) { delete attrs[k]; },
        hasAttribute(k) { return Object.prototype.hasOwnProperty.call(attrs, k); },
        getAttribute(k) { return attrs[k]; },
    };
}
function applyVisibility(visibleSet, pills) {
    pills.forEach(pill => {
        const isVisible = visibleSet.has(pill.dataset.subpill);
        pill.classList.toggle('is-out-of-mode', !isVisible);
        if (isVisible) {
            pill.removeAttribute('hidden');
            pill.removeAttribute('aria-hidden');
        } else {
            pill.setAttribute('hidden', '');
            pill.setAttribute('aria-hidden', 'true');
        }
    });
}
APP.activeDeployment.set('__draft__');
const draftPills = ['configure', 'deploy', 'manage', 'cleanup', 'bolt-ons'].map(makePillStub);
applyVisibility(new Set(APP.computeVisibleSubPills(APP.activeDeployment)), draftPills);
ok('draft: configure visible (no [hidden])', !draftPills[0].hasAttribute('hidden'));
ok('draft: deploy visible (no [hidden])', !draftPills[1].hasAttribute('hidden'));
ok('draft: manage hidden', draftPills[2].hasAttribute('hidden'));
ok('draft: cleanup visible (no [hidden])', !draftPills[3].hasAttribute('hidden'));
ok('draft: bolt-ons hidden', draftPills[4].hasAttribute('hidden'));

APP.activeDeployment.set('myproj');
const existingPills = ['configure', 'deploy', 'manage', 'cleanup', 'bolt-ons'].map(makePillStub);
applyVisibility(new Set(APP.computeVisibleSubPills(APP.activeDeployment)), existingPills);
ok('existing: configure hidden', existingPills[0].hasAttribute('hidden'));
ok('existing: deploy hidden', existingPills[1].hasAttribute('hidden'));
ok('existing: manage visible', !existingPills[2].hasAttribute('hidden'));
ok('existing: cleanup visible', !existingPills[3].hasAttribute('hidden'));
ok('existing: bolt-ons visible', !existingPills[4].hasAttribute('hidden'));

APP.activeDeployment.set('__all__');
const allPills = ['configure', 'deploy', 'manage', 'cleanup', 'bolt-ons'].map(makePillStub);
applyVisibility(new Set(APP.computeVisibleSubPills(APP.activeDeployment)), allPills);
ok('all: manage visible', !allPills[2].hasAttribute('hidden'));
ok('all: cleanup visible', !allPills[3].hasAttribute('hidden'));
ok('all: configure hidden', allPills[0].hasAttribute('hidden'));
ok('all: deploy hidden', allPills[1].hasAttribute('hidden'));
ok('all: bolt-ons hidden', allPills[4].hasAttribute('hidden'));

console.log('\n=== URL hash parsing ===');
eq('empty', APP.parseDeploymentsHash(''), null);
eq('non-deployments', APP.parseDeploymentsHash('#dashboard'), null);
eq('bare', APP.parseDeploymentsHash('#deployments-tab'),
    { page: 'deployments', subPill: null, params: {} });
eq('draft', APP.parseDeploymentsHash('#deployments-tab/configure?draft=1'),
    { page: 'deployments', subPill: 'configure', params: { draft: '1' } });
eq('manage project', APP.parseDeploymentsHash('#deployments-tab/manage?project=myproj'),
    { page: 'deployments', subPill: 'manage', params: { project: 'myproj' } });
eq('manage all', APP.parseDeploymentsHash('#deployments-tab/manage?project=__all__'),
    { page: 'deployments', subPill: 'manage', params: { project: '__all__' } });
eq('url-encoded', APP.parseDeploymentsHash('#deployments-tab/manage?project=my%20proj'),
    { page: 'deployments', subPill: 'manage', params: { project: 'my proj' } });

console.log('\n=== Summary ===');
console.log('  Total:  ' + (passed + failed));
console.log('  Passed: ' + passed);
console.log('  Failed: ' + failed);
process.exit(failed === 0 ? 0 : 1);
