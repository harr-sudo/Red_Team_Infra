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
    const state = {
        current: null,
        deployment_type: null,
        draftProject: null,
        // 2026-05-20 (UX audit Batch B · H2) — mirror the live module's
        // enable_test_lab tracking. Set true when /api/deploy/active
        // surfaces enable_test_lab=true for the active project; drives
        // Bolt-ons sub-pill visibility for c2-* deployments that opted
        // into the in-VPC test lab.
        enable_test_lab: false,
    };
    return {
        DRAFT_SENTINEL, ALL_SENTINEL,
        get current() { return state.current; },
        get deployment_type() { return state.deployment_type; },
        set deployment_type(v) { state.deployment_type = v || null; },
        get enable_test_lab() { return state.enable_test_lab; },
        set enable_test_lab(v) { state.enable_test_lab = v === true; },
        hasTestLab() { return state.enable_test_lab === true; },
        get draftProject() { return state.draftProject; },
        set draftProject(v) { state.draftProject = v || null; },
        isDraft() { return state.current === DRAFT_SENTINEL; },
        isAll() { return state.current === ALL_SENTINEL; },
        isExisting() {
            return !!state.current && state.current !== DRAFT_SENTINEL && state.current !== ALL_SENTINEL;
        },
        effectiveProject() {
            if (this.isDraft() && state.draftProject) return state.draftProject;
            if (this.isExisting()) return state.current;
            return null;
        },
        // 2026-05-19 — Sentinel filter for any code that renders the
        // active deployment name. Sentinels (`__draft__`, `__all__`) must
        // NEVER leak into UI text.
        // 2026-05-20 — "Draft: <name>" when draftProject is set.
        displayName(value) {
            const v = arguments.length > 0 ? value : state.current;
            if (v === DRAFT_SENTINEL) {
                return state.draftProject ? `Draft: ${state.draftProject}` : 'Draft (unnamed)';
            }
            if (v === ALL_SENTINEL)   return 'All deployments';
            return v || '';
        },
        set(v) {
            // Mirror the live module's reset semantics: any non-no-op .set()
            // that lands on a value other than the draft sentinel clears
            // draftProject. deployment_type is invalidated on every switch.
            if (state.current === v) return;
            if (v !== DRAFT_SENTINEL) state.draftProject = null;
            state.deployment_type = null;
            state.enable_test_lab = false;
            state.current = v || null;
        },
    };
})();

APP.computeVisibleSubPills = function(active) {
    const isDraft    = active.isDraft();
    const isAll      = active.isAll();
    const isExisting = active.isExisting();
    // 2026-05-20 — deployment-type-aware visibility. Bolt-ons hide for
    // c2-* (no AD lab to configure); Operations hides for goad-* (no C2).
    // Batch B · H2 — c2-* with enable_test_lab=true gets Bolt-ons back
    // because the test lab is the bolt-on target.
    const type = (active.deployment_type || '').toLowerCase();
    const isC2only   = isExisting && type.startsWith('c2-');
    const isGoadOnly = isExisting && type.startsWith('goad-');
    const isCombined = isExisting && type.startsWith('combined-');
    const hasTestLab = isExisting && active.hasTestLab && active.hasTestLab();
    const isC2WithLab = isC2only && hasTestLab;
    // Cleanup is universal — always available regardless of mode.
    const base = isDraft
        ? ['configure', 'deploy']
        : isAll
            ? ['manage']
            : (isGoadOnly || isCombined || isC2WithLab)
                ? ['manage', 'bolt-ons']
                : isC2only
                    ? ['manage']
                    : ['manage'];
    base.push('cleanup');
    return base;
};

APP.computeOperationsVisible = function(active) {
    if (!active.isExisting()) return false;
    const type = (active.deployment_type || '').toLowerCase();
    return type.startsWith('c2-') || type.startsWith('combined-');
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

APP.activeDeployment.set('c2_adhoc_demo_01');
ok('existing → isExisting', APP.activeDeployment.isExisting());
// 2026-05-20 — without a known deployment_type we fall through to the
// "unknown" branch (Manage + Cleanup only). Bolt-ons stay hidden until
// the deployment_type cache resolves to goad-* or combined-*.
eq('existing (no type) → [manage, cleanup]', APP.computeVisibleSubPills(APP.activeDeployment), ['manage', 'cleanup']);

// 2026-05-20 — deployment-type-aware visibility cases.
console.log('\n=== Deployment-type-aware sub-pill visibility ===');
APP.activeDeployment.set('proj_c2');
APP.activeDeployment.deployment_type = 'c2-adhoc';
eq('existing c2-* → [manage, cleanup]', APP.computeVisibleSubPills(APP.activeDeployment), ['manage', 'cleanup']);
ok('existing c2-* → Operations visible', APP.computeOperationsVisible(APP.activeDeployment) === true);

APP.activeDeployment.set('proj_goad');
APP.activeDeployment.deployment_type = 'goad-mini';
eq('existing goad-* → [manage, bolt-ons, cleanup]', APP.computeVisibleSubPills(APP.activeDeployment), ['manage', 'bolt-ons', 'cleanup']);
ok('existing goad-* → Operations hidden', APP.computeOperationsVisible(APP.activeDeployment) === false);

APP.activeDeployment.set('proj_combined');
APP.activeDeployment.deployment_type = 'combined-adhoc-mini';
eq('existing combined-* → [manage, bolt-ons, cleanup]', APP.computeVisibleSubPills(APP.activeDeployment), ['manage', 'bolt-ons', 'cleanup']);
ok('existing combined-* → Operations visible', APP.computeOperationsVisible(APP.activeDeployment) === true);

// 2026-05-20 (UX audit Batch B · H2) — c2-* WITH the test lab enabled
// re-gains Bolt-ons (the test lab IS the bolt-on target). Mirrors the
// live computeVisibleSubPills branch in app.js. Without enable_test_lab
// the same project hides Bolt-ons; setting the flag reactively flips it
// back on without re-selecting the project.
APP.activeDeployment.set('proj_c2_with_lab');
APP.activeDeployment.deployment_type = 'c2-adhoc';
eq('c2-* without test lab → [manage, cleanup]', APP.computeVisibleSubPills(APP.activeDeployment), ['manage', 'cleanup']);
APP.activeDeployment.enable_test_lab = true;
eq('c2-* with enable_test_lab=true → [manage, bolt-ons, cleanup]',
   APP.computeVisibleSubPills(APP.activeDeployment),
   ['manage', 'bolt-ons', 'cleanup']);
// hasTestLab() helper mirrors the live getter — surfaced for renderers.
ok('hasTestLab() returns true', APP.activeDeployment.hasTestLab() === true);
// Switching to a different project clears the flag (Batch B · _setActiveDeploymentType
// helper repopulates from the per-project cache; .set() invalidates first).
APP.activeDeployment.set('proj_other');
ok('switching project clears enable_test_lab', APP.activeDeployment.hasTestLab() === false);

// Sentinels never expose Operations regardless of any stale type.
APP.activeDeployment.set('__draft__');
ok('draft → Operations hidden', APP.computeOperationsVisible(APP.activeDeployment) === false);
APP.activeDeployment.set('__all__');
ok('all → Operations hidden', APP.computeOperationsVisible(APP.activeDeployment) === false);
APP.activeDeployment.set(null);
ok('empty → Operations hidden', APP.computeOperationsVisible(APP.activeDeployment) === false);

console.log('\n=== Draft-with-draftProject (saved-but-not-yet-Applied) ===');
APP.activeDeployment.set('__draft__');
APP.activeDeployment.draftProject = 'my_pending_lab';
ok('draft with draftProject → still isDraft', APP.activeDeployment.isDraft());
eq('draft with draftProject → [configure, deploy, cleanup]',
   APP.computeVisibleSubPills(APP.activeDeployment),
   ['configure', 'deploy', 'cleanup']);
eq('effectiveProject() returns draftProject', APP.activeDeployment.effectiveProject(), 'my_pending_lab');
eq('displayName surfaces "Draft: <name>"', APP.activeDeployment.displayName(), 'Draft: my_pending_lab');

// Picking a different dropdown option must wipe the draftProject.
APP.activeDeployment.set('other_real_project');
ok('picking real project → draftProject cleared', APP.activeDeployment.draftProject === null);
ok('picking real project → !isDraft', !APP.activeDeployment.isDraft());

// Picking All also wipes the draft.
APP.activeDeployment.set('__draft__');
APP.activeDeployment.draftProject = 'will_be_lost';
APP.activeDeployment.set('__all__');
ok('picking All → draftProject cleared', APP.activeDeployment.draftProject === null);

// effectiveProject() returns null when the operator is in an empty draft.
APP.activeDeployment.set('__draft__');
ok('empty draft → effectiveProject null', APP.activeDeployment.effectiveProject() === null);

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
APP.activeDeployment.draftProject = 'pending_lab';
eq('draft with draftProject → "Draft: pending_lab"', APP.activeDeployment.displayName(), 'Draft: pending_lab');
APP.activeDeployment.draftProject = null;
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

// 2026-05-20 — existing c2-* deployment hides Bolt-ons too.
APP.activeDeployment.set('myproj_c2');
APP.activeDeployment.deployment_type = 'c2-adhoc';
const existingC2Pills = ['configure', 'deploy', 'manage', 'cleanup', 'bolt-ons'].map(makePillStub);
applyVisibility(new Set(APP.computeVisibleSubPills(APP.activeDeployment)), existingC2Pills);
ok('existing c2: configure hidden', existingC2Pills[0].hasAttribute('hidden'));
ok('existing c2: deploy hidden', existingC2Pills[1].hasAttribute('hidden'));
ok('existing c2: manage visible', !existingC2Pills[2].hasAttribute('hidden'));
ok('existing c2: cleanup visible', !existingC2Pills[3].hasAttribute('hidden'));
ok('existing c2: bolt-ons hidden', existingC2Pills[4].hasAttribute('hidden'));

APP.activeDeployment.set('myproj_goad');
APP.activeDeployment.deployment_type = 'goad-mini';
const existingGoadPills = ['configure', 'deploy', 'manage', 'cleanup', 'bolt-ons'].map(makePillStub);
applyVisibility(new Set(APP.computeVisibleSubPills(APP.activeDeployment)), existingGoadPills);
ok('existing goad: manage visible', !existingGoadPills[2].hasAttribute('hidden'));
ok('existing goad: bolt-ons visible', !existingGoadPills[4].hasAttribute('hidden'));

APP.activeDeployment.set('__all__');
const allPills = ['configure', 'deploy', 'manage', 'cleanup', 'bolt-ons'].map(makePillStub);
applyVisibility(new Set(APP.computeVisibleSubPills(APP.activeDeployment)), allPills);
ok('all: manage visible', !allPills[2].hasAttribute('hidden'));
ok('all: cleanup visible', !allPills[3].hasAttribute('hidden'));
ok('all: configure hidden', allPills[0].hasAttribute('hidden'));
ok('all: deploy hidden', allPills[1].hasAttribute('hidden'));
ok('all: bolt-ons hidden', allPills[4].hasAttribute('hidden'));

// 2026-05-21 (Bug 1 — left rail visibility mirror)
// applyFromState() applies the SAME visibility logic to .app-rail__child
// nodes as it does to .subpill-nav__pill nodes. Simulate the rail-children
// pipeline with the same stub helper to lock the contract: an existing
// goad-* deployment must NOT show Configure / Deploy in the left rail.
console.log('\n=== Left-rail children visibility map (Bug 1) ===');
function railChildrenMap(active) {
    const visible = new Set(APP.computeVisibleSubPills(active));
    const names = ['configure', 'deploy', 'manage', 'bolt-ons', 'cleanup'];
    const stubs = names.map(makePillStub);
    applyVisibility(visible, stubs);
    const map = {};
    names.forEach((n, i) => {
        map[n] = stubs[i].hasAttribute('hidden') ? 'hidden' : 'visible';
    });
    return map;
}
APP.activeDeployment.set('goad_mini_demo');
APP.activeDeployment.deployment_type = 'goad-mini';
eq('existing goad → rail children {configure:hidden, deploy:hidden, manage:visible, bolt-ons:visible, cleanup:visible}',
   railChildrenMap(APP.activeDeployment),
   { configure: 'hidden', deploy: 'hidden', manage: 'visible', 'bolt-ons': 'visible', cleanup: 'visible' });

// c2-* without test lab — bolt-ons hidden.
APP.activeDeployment.set('c2_adhoc_demo_01');
APP.activeDeployment.deployment_type = 'c2-adhoc';
eq('existing c2 (no lab) → rail children {configure:hidden, deploy:hidden, manage:visible, bolt-ons:hidden, cleanup:visible}',
   railChildrenMap(APP.activeDeployment),
   { configure: 'hidden', deploy: 'hidden', manage: 'visible', 'bolt-ons': 'hidden', cleanup: 'visible' });

// c2-* WITH enable_test_lab — bolt-ons re-appears.
APP.activeDeployment.enable_test_lab = true;
eq('existing c2 + test lab → rail children {configure:hidden, deploy:hidden, manage:visible, bolt-ons:visible, cleanup:visible}',
   railChildrenMap(APP.activeDeployment),
   { configure: 'hidden', deploy: 'hidden', manage: 'visible', 'bolt-ons': 'visible', cleanup: 'visible' });

// Draft mode — only configure/deploy/cleanup show.
APP.activeDeployment.set('__draft__');
eq('draft → rail children {configure:visible, deploy:visible, manage:hidden, bolt-ons:hidden, cleanup:visible}',
   railChildrenMap(APP.activeDeployment),
   { configure: 'visible', deploy: 'visible', manage: 'hidden', 'bolt-ons': 'hidden', cleanup: 'visible' });

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
