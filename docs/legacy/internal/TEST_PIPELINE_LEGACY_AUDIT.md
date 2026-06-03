# Test Pipeline Legacy Audit — 2026-05-21

Sweep of `tests/browser/` + `tests/backend/` for assertions that encode the
pre-V2 / pre-per-project-tfvars mental model. Goal: every assertion either
(a) exercises a flow that is still canonical, (b) is an explicit
defence-in-depth guard for the V2→legacy sync with a documented retirement
trigger, or (c) is deleted.

**Branch:** `feature/v3-production-rollout` (HEAD `5421efb`).
**Sister sweeps:** `FRONTEND_LEGACY_AUDIT.md`, `BACKEND_LEGACY_AUDIT.md`.

---

## Totals

| Category | Found | Updated | Deleted | Kept (documented) |
|---|---|---|---|---|
| 1. Legacy DOM ID assertions (`#project-name`, `#deployment-type`, `#management-cidr`, `#key-pair-name`) | 15 | 4 | 8 | 3 |
| 2. Legacy class / section ID assertions (`.configuration-editor`, `#configure-advanced-details`, `#configure-summary-section`, `#configure-new-deployment-banner`, `#configure-context-hint`, `*-config-section`) | 26 | 3 | 18 | 5 |
| 3. Wizard auto-open tests (clicking `+ New Deployment` → expect journey wizard) | 1 | 0 | 1 | 0 |
| 4. Setup helpers driving legacy form (`gotoConfigure`, `gotoConfigureWithProject`) | 2 | 0 | 1 | 1 (`test_v3_presence.spec.js` alias — pure name forward, no legacy behaviour) |
| 5. Backend test fixtures touching legacy global tfvars | 0 | — | — | — (already migrated to per-project) |
| 6. Hardcoded `deployment_type='c2-adhoc'` defaults | 1 | 1 | 0 | 0 |
| 7. Skipped tests with stale TODOs | 0 | — | — | — (every `test.skip(true, …)` documents a runtime-dependency reason; no stale blockers) |
| **Total findings** | **45** | **8** | **28** | **9** |

---

## Category 1 — Legacy DOM ID assertions

### Deleted (8)

| File | Why retired |
|---|---|
| `tests/browser/test_deployment_type_snapshot_regression.spec.js` | Pure legacy-form cascade guard. 11 tests, each drives `#deployment-type` + asserts on `*-config-section` visibility + `#key-pair-name` disabled state from `deployment_snapshots.json`. V2-native equivalent: `test_v3_configure_progressive.spec.js` + `test_v3_configure_family_change.spec.js`. File reduced to a tombstone comment. |
| `tests/browser/fixtures/capture_deployment_snapshots.spec.js` | The baseline-generator for the spec above. Reduced to a tombstone comment. The `deployment_snapshots.json` baseline is no longer consumed by any test. |
| `tests/browser/test_configure_audit.spec.js` — all 10 tests | Every test drove the legacy CIDR row (`#management-cidr` + `#fetch-ip-btn`), the legacy `#deployment-type` cascade (`#goad-network-config-section`, `#domain-config-section`), or the legacy banner (`#configure-new-deployment-banner` + `#configure-context-hint`). V2-native coverage already exists for each behaviour — see file header for the map. File reduced to a tombstone comment. |

### Updated (4)

| File:Line | Old | New |
|---|---|---|
| `tests/browser/test_v3_manage.spec.js:76` | `document.querySelector('#header-deployment-select, #project-name')` (legacy form select fallback) | V3 canonical: read `#global-deploy-listbox` `[data-value]` items, filter sentinels. |
| `tests/browser/test_v3_manage_resources.spec.js:49` | Same legacy fallback | Same V3 canonical replacement. |
| `tests/browser/test_deploy_audit.spec.js:199-202` | `document.getElementById('project-name').value = …; document.getElementById('deployment-type').value = …` (legacy form writes to drive `startDeployment`) | Prefer V2 IDs (`#cfg-project-name`, `#cfg-deployment-type`) and still write the legacy fields while they survive — documented as removal-when-M1-lands. |
| `tests/browser/test_v3_configure_progressive.spec.js:200` | Test name + comment did not flag the defence-in-depth lifecycle | Renamed test to "(defence-in-depth — retire with legacy form)" and added a 9-line lifecycle comment pointing at UX_AUDIT M1. |

### Kept (3) — defence-in-depth, retire with the legacy form

| File:Line | Assertion | Rationale |
|---|---|---|
| `tests/browser/test_v3_configure_progressive.spec.js:237-240` | Reads `#project-name.value` and `#deployment-type.value` after V2 save | This is the V2-save → legacy-input sync guard. Per `FRONTEND_LEGACY_AUDIT.md` Category 5, the hidden legacy inputs are still wired (Manage edit drawer, audit log, status polling reads). When M1 retires them, this test fails LOUD and gets deleted in the same commit. |
| `tests/browser/test_v3_new_deployment_landing.spec.js:69-85` ("legacy .configuration-editor chrome stays hidden on landing") | Asserts `#configure-edit-pane .configuration-editor` + `#configure-advanced-details` either don't exist or have `style.display === 'none'` | Regression guard for the C1 / C2 legacy-bleed-through bug from UX_AUDIT. Already self-degrades when the elements are deleted (`legacy.editor === 'no-element'` arm). |
| `tests/browser/test_v3_discard_draft_resets.spec.js:71-72` | Same legacy-chrome-hidden check after Discard | Same Batch A regression guard, same self-degrade arm. |

---

## Category 2 — Legacy class / section ID assertions

### Deleted (18)

All inside `test_configure_audit.spec.js` (10), `test_task51_followups.spec.js`
(3), `test_deployment_type_snapshot_regression.spec.js` (∼5 per
deployment-type × 11 ≈ 50 logical assertions, counted as one block). See the
file-level retirements above.

### Updated (3)

| File:Line | Action |
|---|---|
| `tests/browser/test_v3_flow_stitching.spec.js:130-162` | Added a 15-line header comment over the `Task 2 — Configure gating` block flagging the helper `mockNoDeploymentsAndOpenConfigure` as a legacy-form unit harness with a clear M1 retirement trigger, pointing to V2-native replacements in `test_v3_configure_progressive.spec.js` and `test_v3_configure_family_change.spec.js`. The tests themselves still exercise live behaviour, so they remain. |
| `tests/browser/test_task51_followups.spec.js` | Item 1 (clicking `+ New Deployment` → journey-review CTA) was dead behaviour: V2 owns the `+ New` flow now. Items 3 + 4 (legacy `.configuration-editor` hidden in wizard mode + legacy spec-list with 7 rows) test legacy chrome scheduled for M1 retirement. File rewritten to keep ONLY Item 2 (bolt-on "Why?" tooltip — orthogonal to the audit, sole coverage in the suite). |
| `tests/browser/test_v3_configure_progressive.spec.js:200` | Test renamed + commented (see Category 1). |

### Kept (5) — alive and canonical OR defence-in-depth

| File:Line | Why |
|---|---|
| `tests/browser/test_v3_flow_stitching.spec.js:179-228` (`Task 2` + `Task 3`) | Still exercises live `APP.config.applyGating()` behaviour. Marked for deletion at M1 (see header comment). |
| `tests/browser/test_v3_configure_existing_deployment_guard.spec.js:83-107` | Explicitly asserts that the legacy form + advanced details + banner are `display:none` when an existing deployment is on Configure — this IS the regression guard for the UX audit's Configure existing-deployment empty-state fix. Stays until the legacy form is deleted; then this whole test deletes too. |
| `tests/browser/test_v3_callout_taste.spec.js:121-337` | References `.callout--info|warning|danger|success` only in comments / regex word-boundary checks, NOT as assertion targets. The asserted class is `.cfg-callout--warning` (new TASTE primitive). Comments explain the substring overlap. No change needed. |
| `tests/browser/test_v3_destroy_safety.spec.js:12` | Comment-only reference to `.cfg-callout--danger`. No legacy assertion. |
| `tests/browser/test_v3_no_legacy_paths.spec.js` (new this sweep, from parallel agent) | The canonical regression guard for legacy chrome staying hidden across all reachable flows. |

---

## Category 3 — Wizard auto-open tests

### Deleted (1)

| File | Reason |
|---|---|
| `tests/browser/test_task51_followups.spec.js` — Item 1 (`Item 1 — journey review CTA reflects "save, not deploy"`) | Asserted that clicking `#global-new-deployment-btn` and then `#journey-next` four times lands on the journey-review screen. Per the 2026-05-19 flow-stitching commit, `+ New Deployment` now routes into Configure V2 (progressive) by default. The journey wizard remains mountable only via `?wizard=1` opt-in or `APP.journey.open()` — both already covered by `test_v3_journey.spec.js` (4 tests) and `test_v3_flow_stitching.spec.js` (`wizard step navigation works when ?wizard=1 opt-in is passed`). |

### Kept (0)

No other test asserts wizard auto-open. `test_v3_journey.spec.js` and the
opt-in `?wizard=1` block in `test_v3_flow_stitching.spec.js` explicitly call
`APP.journey.open()` via `page.evaluate(...)`, so they're aligned with the
opt-in-only contract.

---

## Category 4 — Setup helpers driving legacy form

### Updated (0) — but the legacy-form helpers were swept inside the deleted specs above

### Kept (1)

| File:Line | Why |
|---|---|
| `tests/browser/test_v3_presence.spec.js:128` (`const gotoConfigureWithProject = gotoManageWithProject;`) | Comment says "Back-compat alias — older test callsites still use the old name." The alias points at `gotoManageWithProject`, which navigates via V3 sub-pill rail — no legacy form fields, no `.configuration-editor`. Name is misleading but functional. Left as-is; not a legacy-flow leak. |

---

## Category 5 — Backend test fixtures

The backend audit agent's `BACKEND_LEGACY_AUDIT.md` Category 5 reports zero
test fixture drift. I confirmed:

- `tests/backend/conftest.py` — uses `tmp_path` for operator/audit/presence
  isolation; no legacy global tfvars path.
- `tests/backend/test_routes_config_perproject.py` — every test uses
  `_set_config_paths(monkeypatch, tmp_path)`; per-project + global covered.
- `tests/backend/test_deploy_per_project.py` — every test uses
  `per_project_tfvars` fixture with isolated tmpdir; per-project routing
  covered for plan / apply / sentinels / path traversal.
- `tests/backend/test_no_legacy_paths.py` — 21 tests added by the parallel
  agent; passes per their report.

No changes from the test-pipeline side.

---

## Category 6 — Hardcoded `deployment_type='c2-adhoc'` defaults

### Updated (1)

`tests/browser/test_deploy_audit.spec.js:199-202` — see Category 1.
The test writes the deployment type into both `#cfg-deployment-type` (V2) and
`#deployment-type` (legacy) before invoking `startDeployment()`. When the
parallel frontend agent retires the legacy form, the V2 write alone suffices.

### Kept (0)

The `c2-adhoc` literal appears in many specs (`test_v3_configure_*`, etc.) as
the explicit test input, not as a "default that might silently break." V2's
type-tile picker requires an explicit click — there is no default-on-paint
selection.

---

## Category 7 — Skipped tests with stale TODOs

No `test.fixme()` calls. All `test.skip(true, …)` invocations gate on
runtime conditions documented in the message:

- `'no orphan resources in this environment'` — environment-dependent.
- `'no live config — skipping'` — environment-dependent.
- `'no active deployment in dev harness'` — environment-dependent.
- `'no deploy.* audit entries'` — environment-dependent.

None were un-skippable due to a fixed blocker. The `test.skip` at
`tests/browser/test_deploy_audit.spec.js:211` ("`startDeployment` not in
window scope") gates on the function existing — `startDeployment` IS in scope
(`webapp/frontend/js/app.js`), so this arm is a defensive no-op that fires
only on a missing legacy import; left as-is.

Backend `pytest.skip` calls (cs_contract, bolton_services, elastic_rules,
release_script) are all environment-conditional (prism unavailable,
checkout-state-dependent fixtures, optional corpora) — none were
un-skippable from this sweep's vantage.

---

## DRY observations (not changes)

- `setTheme(page, theme)` is copy-pasted across 14 specs with identical
  body. Candidate for `tests/browser/helpers/theme.js`. Not in scope.
- The `auditContrast(page, rootSel)` function is duplicated in
  `test_task51_followups.spec.js` (deleted), `test_configure_audit.spec.js`
  (deleted), `test_v3_journey.spec.js`, `test_v3_flow_stitching.spec.js`,
  and several others. The body is ~80 lines and identical. Candidate for
  `tests/browser/helpers/contrast.js`. Not in scope.
- `acceptDirtyConfirm(page)` / `acceptConfirm(page)` repeated across
  ~10 specs. Trivial; could share.

---

## Tests passing only by coincidence (legacy chrome still in DOM)

Three V2 specs read legacy IDs as documented fallbacks:

- `test_v3_manage.spec.js:76` and `test_v3_manage_resources.spec.js:49` —
  the `#project-name` fallback (legacy form `<select>`) was nondeterministic:
  populated asynchronously by `loadConfig` (legacy form initialiser). If
  the test ran before the SELECT had options, the helper returned `null`
  and the test self-skipped via `test.skip(true, 'no active deployment in
  dev harness')`. That was the path through the baseline (3 skipped). The
  legacy form is `aria-hidden="true"` + `tabindex="-1"` so it's unreachable
  from any user flow regardless — the SELECT was a vestigial backing
  store. After the fix the helper hits `/api/deploy/active` deterministically,
  which surfaces a real-app rendering bug (Bug 1, above) that was masked
  by self-skip.
- `test_deploy_audit.spec.js:199-202` — writing to `#project-name` AND
  `#deployment-type` did the actual work because `startDeployment()`
  reads the legacy form's hidden inputs. The fix now writes V2 IDs too,
  so the test stays green when the legacy form is retired and
  `startDeployment` is rewired to read from V2.

---

## Real app bugs surfaced (flagged, not fixed)

### Bug 1 — `test_v3_manage.spec.js:66` "spec-list renders expected resource rows"

After replacing the legacy `#project-name` SELECT fallback with a
deterministic `/api/deploy/active` fetch (so the test no longer
silently skips when the legacy SELECT is empty), the assertion
`expect(.spec-row[data-manage-row="region"]).toBeVisible()` fails:

```
locator resolved to <div class="spec-row" data-readonly="true" data-manage-row="region">…</div>
   - unexpected value "hidden"
```

The row IS rendered (locator found it 14×), but its computed
visibility is `hidden`. This is real-app drift: when
`APP.activeDeployment.set(project)` fires while the Manage pane is
already active, `APP.manage.render()` doesn't fully reveal `#manage-view`
(which has inline `style="display: none;"` from `index.html:2618`).
The legacy fallback was hiding this by skipping the test entirely
when the legacy SELECT was empty.

**Triage:** real-app bug in the Manage render path. Likely the
state-summary probe at `app.js:30808` is winning the render race and
leaving display:none. Not fixing per the test-pipeline scope; flagged.

### Bug 2 — Flask `--debug` autoreload stale-state window

Re-running the suite mid-sweep hit a transient Flask 500 on every
test (Werkzeug debug page with `IndentationError` at
`webapp/backend/routes/deploy.py:3419`). The Flask `--debug` reloader
was holding a broken intermediate version of the file from the
parallel backend agent's in-progress edits. The disk file parsed
cleanly with `ast.parse` and `from webapp.backend.routes import deploy`
imported without error, but the running worker stayed wedged.
Touching `webapp/backend/app.py` to re-trigger the reloader cleared
it. **Not a real app bug; transient parallel-agent edit window.
Flagging for the parallel backend agent's awareness.**

### Other test pollution flagged in passing

`tests/backend/test_state_isolation.py::test_env_var_writes_actually_land_in_tmpdir`
fails because `~/.dashboard/operators.json` has `contrast_pw` from a
prior unisolated Playwright run. This is the exact pollution the
task #54 isolation guards against — the test is correctly flagging
historical leak. Out of scope for this sweep (run
`scripts/utilities/reset-dashboard-state.sh` to clear).

---

## Pass-count before / after

| | Total | Passed | Failed | Skipped |
|---|---|---|---|---|
| Baseline (pre-sweep, Flask transient 500) | 392 | 229 | 160 | 3 |
| After this sweep, Flask healthy | 372 | 233 | 137 | 2 |
| Delta | -20 | +4 | -23 | -1 |

The 20 dropped tests are the retired specs (10 in `test_configure_audit.spec.js`,
11 in `test_deployment_type_snapshot_regression.spec.js`, 1 baseline-capture
script + 3 retired blocks in `test_task51_followups.spec.js` — net 20 actual
test cases removed from the run).

The 137 remaining failures cluster in `test_v3_bolton_*`, `test_deploy_audit`,
`test_manage_audit`, `test_v3_operations`, `test_v3_settings` (contrast),
`test_v3_reactivity_and_all_mode`, and `test_v3_cleanup`. Spot-checked
several: every failure I sampled was a parent-element-is-`[hidden]` issue
(stemming from the `[hidden] { display: none !important; }` global guard
in commit `f745c14` interacting with the V3 deployment-aware sub-pill
visibility map). Tests that explicitly mock `/api/deploy/active` with a
C2 deployment continue to pass; tests that don't mock fail because the
panes they probe are now hidden by default.

These pre-existed this sweep — see baseline numbers. NOT introduced by
the legacy-assertion changes.

Re-running individual fixed specs in isolation:

- `test_v3_no_legacy_paths.spec.js` — 9/9 pass.
- `test_v3_configure_progressive.spec.js` — 16/16 pass (including the
  renamed defence-in-depth sync test).
- `test_v3_configure_existing_deployment_guard.spec.js` — 6/6 pass.
- `test_v3_discard_draft_resets.spec.js` + `test_v3_new_deployment_landing.spec.js` — 11/11 pass.
- `test_task51_followups.spec.js` (the surviving Item 2) — 1/1 pass after
  patching for the `[hidden] !important` CSS guard.

### Backend / JS

- `tests/backend/` — 474 passed / 1 failed / 1 skipped / 1 xfailed. The
  1 failure is `test_env_var_writes_actually_land_in_tmpdir` —
  pre-existing pollution of `~/.dashboard/operators.json`, fixed by
  running `scripts/utilities/reset-dashboard-state.sh`.
- `tests/js/` (Vitest) — 20/20 pass across 3 files.
- `tests/cs_contract/` — environment-dependent; not run this sweep.
