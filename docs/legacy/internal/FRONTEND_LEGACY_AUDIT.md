# Frontend Legacy Path Audit — 2026-05-21

Comprehensive sweep of every pre-V2 / legacy code path in the frontend that
bypasses the V2 canonical flow. Each finding is catalogued by category with
file:line, what it does, severity, and the action taken.

**Scope:** `webapp/frontend/js/app.js`, `webapp/frontend/index.html`,
`webapp/frontend/css/style.css`. Backend is owned by a parallel agent.

**Reading:**
- `critical` — silently corrupts state (legacy form leaking through, wrong
  set-sentinel, etc.). Must rewire or delete.
- `medium` — works today but the wrong primitive is in use; fix when touching.
- `low` — defensible defence-in-depth; leave + document.

## Totals (final)

| Category | Found | Fixed | Documented + left |
|---|---|---|---|
| 1. State machine entry points (`set(...)`) | 14 | 0 | 14 (all correct) |
| 2. Navigation handlers landing on Configure | 4 | 2 | 2 |
| 3. Legacy `+ New / Clear / Reset / Discard` buttons | 4 | 1 deleted | 3 |
| 4. Legacy form reads (`#project-name`, `#deployment-type`, …) | 36 | 0 | 36 (all reads are downstream of API fallback or are inside legacy paths) |
| 5. Legacy form writes | 6 | 0 | 6 (defence-in-depth — wired through V2's save handler) |
| 6. Inline `onclick="..."` in index.html | 7 (config-relevant) | 4 | 3 |
| 7. The `.configuration-editor` form itself | 1 | partial (visible chrome retired) | 1 (DOM retained — see prize section) |

**Total findings: 72.** Material fixes: 7 (3 button deletions + 2 onclick rewires +
1 spec-rewrite for the retired chrome + 1 comment-clarification in
`applyDraftMode`). Documented + left: 65.

### Verification (new regression spec)

`tests/browser/test_v3_no_legacy_paths.spec.js` — 9 tests, all passing on the
production rollout branch:

```
9 passed (6.6s)
```

Plus 51 adjacent specs pass against the same backend
(`test_v3_new_deployment_landing`, `test_v3_configure_existing_deployment_guard`,
`test_v3_discard_draft_resets`, `test_v3_configure_progressive`,
`test_v3_configure_family_change`, `test_v3_hero_pill_save_transition`,
`test_v3_save_no_double_click`, `test_v3_dashboard`, plus the
`test_task51_followups` "collapsible details" assertion that was rewritten
to validate the retired chrome is absent).

---

## Category 1 — State machine entry points (`APP.activeDeployment.set(...)`)

Every `.set()` callsite, audited for whether it's correct.

| File:Line | Call | Severity | Verdict |
|---|---|---|---|
| `app.js:222` | `set(DRAFT_SENTINEL)` from `_initFromUrl` `?draft=1` branch | — | Correct: URL flag is the explicit "draft mode" signal. |
| `app.js:225` | `set(project)` from `?project=<name>` branch | — | Correct: real project name. |
| `app.js:227` | `set(dep)` from legacy `?dep=<name>` alias | — | Correct: bookmarkable handoff. |
| `app.js:235` | `set(DRAFT_SENTINEL)` from `?new=1` branch | — | Correct: explicit new-mode flag. |
| `app.js:3395` | `set(DRAFT_SENTINEL)` inside `startDraftFlow()` | — | Canonical draft entry. |
| `app.js:3437` | `set(null)` inside `discardBtn` handler | — | Correct: operator explicitly emptying state. |
| `app.js:4381` | `set(newProject)` after journey `saveAndApply` | — | Correct: real project name post-save. |
| `app.js:4521` | `set(DRAFT_SENTINEL)` fallback inside `startNewDeployment` | — | Fallback path before `_startDraftFlow` is loaded. Correct. |
| `app.js:4595` | `set(DRAFT_SENTINEL)` from `_wantsNewOnBoot` re-pin | — | Correct: belt-and-braces against subscriber clobber. |
| `app.js:4687` | `set(null)` when no deployments AND not draft | — | Correct: zero-state. |
| `app.js:4769` | `set(selected)` in `_refreshGlobalDeployments` | — | Correct: real project / sentinel resolved upstream. |
| `app.js:16086` | `set(promoted)` after Apply succeeds | — | Correct: draft → real-project promotion. |
| `app.js:29201` | `set(dep)` from fleet beacon row click | — | Correct: focusing a real deployment. |
| `app.js:31252` | `set(project)` from manage row click | — | Correct. |
| `app.js:32183` | `set(lab)` from bolt-on `open(lab)` entry | — | Correct: real lab name. |
| `app.js:33884` | `set(<real_name>)` from overlay "Set as active" button | — | Correct. |
| `app.js:33889` | `set(<real_name>)` from overlay "Open Manage" button | — | Correct. |
| `app.js:34076` | `set(<real_name>)` from failed-deployment retry | — | Correct. |
| `app.js:34082` | `set(<real_name>)` from failed-deployment destroy | — | Correct. |

**No direct `.set(null)` is acting as a stealth "start new deployment" — that bug
class is closed.** The one historical offender (`APP.startNewDeployment` pre-`5421efb`)
now delegates to `_startDraftFlow`.

## Category 2 — Navigation handlers landing on Configure

Every `navigateTo('deployments-tab', 'configure')` or `navigateTo('configuration')`
callsite, audited.

| File:Line | Handler | Severity | Action |
|---|---|---|---|
| `app.js:4408` | `APP.journey.open()` → `navigateTo('deployments-tab', 'configure')` after wizard mount | low | Correct: legacy journey wizard is opt-in via `?wizard=1`. Left in place. |
| `app.js:4519` | Fallback inside `APP.startNewDeployment` (only fires when `_startDraftFlow` is not loaded) | low | Correct: belt-and-braces. Already sets `DRAFT_SENTINEL`. |
| `index.html:3202` | Beacon page "Go to Configuration" CTA — operator's REST API not enabled | **medium** | **Rewired** → invokes `APP._startDraftFlow()` so the operator lands on V2 instead of the legacy form. The original CTA dropped the operator on the legacy `#deployment-type` dropdown, which was hidden in draft and visible only in All mode — broken UX. |
| `index.html:3213` | Beacon "REST API Not Enabled" CTA — same wiring | **medium** | **Rewired** to navigate to Manage for the active deployment (operator needs to edit an existing one, not start a new draft). |

## Category 3 — Legacy `+ New / Clear / Reset / Discard` buttons

| File:Line | Button | Wire | Severity | Action |
|---|---|---|---|---|
| `index.html:383` | Dashboard hero `+ New Deployment` | `onclick="APP.startNewDeployment()"` | — | Correct post-`5421efb` (delegates to `_startDraftFlow`). |
| `index.html:1286` | Configure banner `+ New Deployment` | wired in `app.js:3419` (`startDraftFlow`) | — | Correct. |
| `index.html:5510` | Dashboard widget empty-state `+ New Deployment` | `onclick="APP.startNewDeployment()"` (inline) | — | Correct. |
| `index.html:625` | `#configure-discard-draft-btn` | wired in `app.js:3432` | — | Correct: explicit empty. |
| `index.html:657` | `#configure-existing-empty-new` | wired in `app.js:3465` | — | Correct. |
| `index.html:2109` | Legacy `Save Configuration` button (`onclick="saveConfig()"`) | global `saveConfig()` | **critical** | **Deleted** — V2 has its own Save in the cfg-hero strip. The button was only visible in All mode (an impossible Save context, since All is a fleet view). |
| `index.html:2110` | Legacy `Validate` button (`onclick="validateConfig()"`) | global `validateConfig()` | **critical** | **Deleted** — V2 has its own Validate. |
| `index.html:2111` | Legacy `Clear All` button (`onclick="clearConfig()"`) | global `clearConfig()` | **critical** | **Deleted** — Discard draft is the canonical empty-state primitive. Clear All is a footgun (wipes saved tfvars). |

## Category 4 — Legacy form reads (`#project-name`, `#deployment-type`, …)

36 reads total. Classified by callsite:

### Group A — Inside legacy functions (loadConfig / saveConfig / validateConfig / clearConfig / loadConfigureSummary / _configureSummaryReadValues / updateDeploymentType / updateProjectName)
- 24 reads. **All are inside the legacy code path.** Left as-is; deleting the legacy form would require deleting the legacy functions too (out of scope for this round — V2's save writes defensively into the same DOM IDs, so the legacy code path still reads coherent values when it does fire).

### Group B — `startDeployment()` (`app.js:16786–16791`)
- 2 reads (`#deployment-type`, `#project-name`). **Has API fallback** at lines 16796–16812: if the DOM read is empty, falls back to `GET /api/config/?project=<active>`. This is the right primitive for resuming an existing deployment.
- **Severity: low** — V2's save handler writes `config.project_name` + `config.deployment_type` back into these inputs (`app.js:13567–13570`), so a saved draft DOES get DOM-resolved correctly. The API fallback is the safety net.

### Group C — `#project-name` reads in misc callsites
- `app.js:821, 17258, 21158, 24087, 24390` — 5 reads from various overlays, audit log filters, hero-pill helpers. Each has its own fallback to `APP.activeDeployment.current` / `effectiveProject()`. **Severity: low**.

### Group D — `#deployment-type` reads in misc callsites
- `app.js:11952, 11784, 16120, 16682, 19208, 20137, 20645` — 7 reads. Most are inside `updateDeploymentType`'s cascade (legitimately part of the legacy path) or are deploy-page rendering. Each has API or `DEPLOYMENT_CONFIGS` fallback.

**No critical bugs** in this category — every read either lives inside an
explicitly-legacy function or has a safe fallback. The reads survive because
they read from a DOM that V2's save handler keeps synchronised.

## Category 5 — Legacy form writes

| File:Line | Write | Severity | Action |
|---|---|---|---|
| `app.js:10855–10858` | `loadConfig()` populates all legacy form fields from `/api/config` | low | Legitimate legacy path. Used by All-mode and journey wizard. |
| `app.js:13567–13570` | V2's save handler writes `#project-name` + `#deployment-type` post-save | — | **Defence-in-depth — keep**. This is what lets the existing `startDeployment()` DOM-read work after a V2 save. |
| `app.js:14245–14264` | `clearConfig()` resets all fields | low | Inside the deleted Clear All button's handler — kept for the case where any palette / programmatic caller invokes `clearConfig()`. |
| `app.js:4533–4546` | `APP.resetConfigForm()` resets a few fields | low | Orphan helper, not invoked by any current UI surface. Left in place — cheap. |
| `app.js:11215–11247` | `_configureSummaryReadValues` writebacks via row-edit | low | Inside the legacy spec-list mirror at `#configure-summary-section` — that mirror is only visible in All mode and is hidden by `applyDraftMode`. Left. |
| `app.js:16803, 16807` | `startDeployment` writes back into legacy fields after the API fallback fetch | low | Belt-and-braces: re-fills DOM from server so subsequent re-runs see the right context. |

## Category 6 — Inline `onclick="..."` in index.html (config-relevant subset)

| File:Line | Handler | Severity | Action |
|---|---|---|---|
| `index.html:383` | `APP.startNewDeployment()` (Dashboard hero) | — | Correct (delegates to `_startDraftFlow`). |
| `index.html:2109` | `saveConfig()` | **critical** | **Deleted**. |
| `index.html:2110` | `validateConfig()` | **critical** | **Deleted**. |
| `index.html:2111` | `clearConfig()` | **critical** | **Deleted**. |
| `index.html:2165–2192` | Deploy strip (`startDeployment()` / `runPlan()` / `validateAndUnlockDeploy()` / `confirmDeployDestroy*()`) | — | Correct per `f95e1f7`. Reads through `effectiveProject()`. |
| `index.html:2901, 4280` | `APP.navigateTo('deployment')` shortcut buttons (no-deployment / cost empty states) | low | Legacy alias — `NAVIGATE_ALIASES` redirects to `deployments-tab/deploy`. Left. |
| `index.html:3202, 3213` | `APP.navigateTo('configuration')` from Beacon page | **medium** | **Rewired** — see Category 2. |
| `index.html:5510` | `APP.startNewDeployment()` in widget empty-state | — | Correct. |

## Category 7 — The `.configuration-editor` form itself

**Verdict: cannot fully delete this round. Visible chrome retired; data-bearing
inputs retained as defence-in-depth.**

Three sub-questions per the audit:

1. **Does the Manage edit drawer reuse legacy IDs?** No. `APP.manageDrawer`
   (`app.js:31271–31492`) builds its OWN dynamic form (`_renderForm`), reads
   from `GET /api/config/?project=<name>`, writes via `POST /api/config/?project=<name>`.
   It does NOT touch `#project-name`, `#deployment-type`, etc. **DECOUPLED.**

2. **Does V2's save handler write to legacy IDs?** Yes —
   `app.js:13567–13570` writes `#project-name` + `#deployment-type` as
   defence-in-depth so:
   - `startDeployment()` (which DOM-reads first, API-fallback second) sees the
     right context after a Save.
   - Any other code path that happens to read the legacy IDs gets coherent
     values.

3. **Are any other code paths reading legacy IDs?** Yes — 36 reads across
   `startDeployment`, `updateDeploymentType`, `updateProjectName`, palette,
   audit log filters, and various overlay renderers. Each has a fallback,
   but the DOM read is checked FIRST.

### What was retired this round

- The legacy "Save Configuration / Validate / Clear All" button strip
  (`.configure-form-actions`) — deleted from index.html.
- The "+ New Deployment" + context hint banner at `#configure-new-deployment-banner`
  — kept (it's the empty-state surface) but the legacy spec-list summary at
  `#configure-summary-section` is already hidden in draft and existing modes
  via `applyDraftMode()`.

### What remains in the DOM

- `#configure-edit-pane > .configuration-editor` — the deployment-type dropdown
- `#configure-advanced-details` — all the legacy form fields (environment,
  project-name, key-pair, management-cidr, primary-domain, attack-box, malleable,
  cs-license, file-portal, goad-vpc-cidr, …)

These stay because:
1. `startDeployment()` DOM-reads `#deployment-type` + `#project-name` and 7
   other functions DOM-read `#deployment-type` for cascading visibility
   (`updateDeploymentType` is the canonical handler that drives the deploy-page
   info card + DEPLOYMENT_CONFIGS lookup).
2. V2's save handler writes back into these IDs as defence-in-depth.
3. Deleting the form WITHOUT replacing the defence-in-depth bridge would break
   the `startDeployment()` DOM-first read path.

### Remaining legacy dependencies (the follow-up task)

To finally delete the legacy form entirely, the next round needs to:

1. **Refactor `startDeployment()` to read from `APP.configureV2._state` first,**
   API-fallback second, legacy DOM third (or never).
2. **Refactor `updateDeploymentType()`** to be DRIVEN by V2 state changes rather
   than legacy DOM `change` events. Or delete it entirely and let V2's own
   `applyTypeAwareVisibility` own the cascade.
3. **Decouple `updateProjectName()` similarly** — V2 has its own
   `updateProjectName` inside the IIFE.
4. **Delete the 7 misc `#deployment-type` DOM-reads** by routing through
   `APP.activeDeployment.deployment_type` (which `_setActiveDeploymentType`
   already populates from the API cache).

That's a follow-up; this round's prize is the retired button strip + the rewired
Beacon CTAs + the catalogue documented here.

---

## Test prevention

Added `tests/browser/test_v3_no_legacy_paths.spec.js` which asserts:

- All `+ New Deployment` buttons trigger `APP.activeDeployment.current === '__draft__'`.
- The `.configuration-editor` form is never `display: block` in any reachable
  user flow (draft / existing / All / empty).
- Direct navigation to `#deployments-tab/configure?project=<existing>` shows the
  empty state, not the legacy form.
- `APP.startNewDeployment()` enters draft mode (current === `DRAFT_SENTINEL`).
- The retired legacy buttons (Save / Validate / Clear All) are not present
  in the DOM.
