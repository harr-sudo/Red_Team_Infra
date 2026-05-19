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
        set(v) { state.current = v || null; },
    };
})();

APP.computeVisibleSubPills = function(activeDeployment) {
    const isDraft    = activeDeployment.isDraft();
    const isAll      = activeDeployment.isAll();
    const isExisting = activeDeployment.isExisting();
    return isDraft
        ? ['configure', 'deploy']
        : isAll
            ? ['manage']
            : isExisting
                ? ['manage', 'bolt-ons']
                : ['manage'];
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
eq('unset → [manage]', APP.computeVisibleSubPills(APP.activeDeployment), ['manage']);
ok('unset → !isDraft', !APP.activeDeployment.isDraft());

APP.activeDeployment.set('__draft__');
ok('draft sentinel → isDraft', APP.activeDeployment.isDraft());
eq('draft → [configure, deploy]', APP.computeVisibleSubPills(APP.activeDeployment), ['configure', 'deploy']);

APP.activeDeployment.set('__all__');
ok('all sentinel → isAll', APP.activeDeployment.isAll());
eq('all → [manage]', APP.computeVisibleSubPills(APP.activeDeployment), ['manage']);

APP.activeDeployment.set('c2_adhoc_dev_harriss_macbook_pro_01');
ok('existing → isExisting', APP.activeDeployment.isExisting());
eq('existing → [manage, bolt-ons]', APP.computeVisibleSubPills(APP.activeDeployment), ['manage', 'bolt-ons']);

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
