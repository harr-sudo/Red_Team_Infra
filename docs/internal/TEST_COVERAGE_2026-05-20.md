# Test Coverage Map — 2026-05-20

Maps every user journey in `docs/internal/UX_AUDIT_2026-05-20.md` to existing
Playwright/pytest specs, and identifies coverage gaps. New specs landed this
pass to close the gaps for all Criticals + Highs.

**Suite status:** 18 journeys total · 6 Critical + 5 High in audit · all 11
covered (one journey requires Batch C — see notes).

---

## Per-journey coverage table

| # | Journey | Existing specs | Covered? | Gap closed by |
|---|---|---|---|---|
| 1 | First paint / hydration | `test_v3_shell.spec.js`, `test_bookmarkable_urls.spec.js` | yes | n/a — shell smoke + URL hydration already cover this |
| 2 | + New Deployment | `test_v3_flow_stitching.spec.js` (Task 1) | partial | **NEW** `test_v3_new_deployment_landing.spec.js` — clean landing state, family-picker focus, no stale draft project |
| 3 | Configure V2 fill | `test_v3_configure_progressive.spec.js`, `test_v3_test_lab_toggle.spec.js` | partial | **NEW** `test_v3_configure_family_change.spec.js` — family-switch resets confirmed sections |
| 4 | V2 Save | `test_v3_configure_progressive.spec.js`, `test_v3_test_lab_toggle.spec.js` (assembleConfig) | partial | **NEW** `test_v3_save_no_double_click.spec.js` + `test_v3_hero_pill_save_transition.spec.js` (H3 + M4) |
| 5 | Discard draft | `test_v3_discard_draft_resets.spec.js` (Batch A) | yes | already landed by Batch A (C2 + H1 + H4) |
| 6 | Deploy sub-pill (Plan/Validate/Apply) | `test_v3_deploy_summary.spec.js`, `test_deploy_audit.spec.js` | yes | n/a |
| 7 | Manage sub-pill (single deployment) | `test_v3_manage.spec.js`, `test_v3_manage_resources.spec.js`, `test_manage_audit.spec.js` | yes | n/a |
| 8 | Manage All mode (fleet) | `test_v3_fleet_no_sentinel.spec.js` (Batch A) | yes | already landed by Batch A (C4 + P2) |
| 9 | Bolt-ons sub-pill | `test_v3_bolton_host_filter.spec.js`, `test_v3_bolton_live.spec.js` | partial | **NEW** `test_v3_enable_test_lab_sync.spec.js` — H2 + M2 sub-pill visibility for `enable_test_lab` |
| 10 | Operations sub-pills | `test_v3_operations.spec.js`, `test_v3_agent_status.spec.js` | yes | n/a |
| 11 | Cleanup | `test_v3_cleanup.spec.js` | yes | n/a |
| 12 | Settings overlay (Prereqs) | `test_v3_overlay_loading_state.spec.js` (Batch A) | yes | already landed by Batch A (C3 + H5 + P1) |
| 13 | Dashboard widgets | `test_v3_dashboard.spec.js`, `test_v3_overlays.spec.js` | partial | **NEW** `test_v3_cost_overlay_ce_usage.spec.js` — Cost overlay CE-usage indicator (ok / warning / danger) |
| 14 | URL routing / bookmarks | `test_bookmarkable_urls.spec.js` | yes | n/a |
| 15 | Top-bar dropdown | `test_v3_reactivity_and_all_mode.spec.js`, `test_operator_chip.spec.js` | yes | M3 timeout is Batch B work — covered by extension in same file |
| 16 | + New button state | `test_v3_flow_stitching.spec.js` | yes | n/a |
| 17 | Test Lab toggle | `test_v3_test_lab_toggle.spec.js` | partial | **NEW** `test_v3_test_lab_combined.spec.js` — C6 verify Test Lab visibility extends to `combined-*` family |
| 18 | Theme toggle | `test_v3_dashboard.spec.js` (contrast pass) | yes | n/a |

---

## Critical issue coverage (operator-blocking)

| Audit ID | Title | Spec |
|---|---|---|
| C1 | + New Deployment lands on Configure form, bypassing family wizard | `test_v3_new_deployment_landing.spec.js` |
| C2 | Discard draft leaves legacy form rendered alongside V2 | `test_v3_discard_draft_resets.spec.js` (Batch A) |
| C3 | AWS & SSH Prereqs overlay has no visible loading state | `test_v3_overlay_loading_state.spec.js` (Batch A) |
| C4 | `__draft__` sentinel leaks into Manage fleet table | `test_v3_fleet_no_sentinel.spec.js` (Batch A) |
| C5 | Configure sections don't reset when operator switches family | `test_v3_configure_family_change.spec.js` |
| C6 | Test Lab toggle missing from Combined family + cost doesn't recalculate | `test_v3_test_lab_combined.spec.js` |

## High issue coverage (clearly broken)

| Audit ID | Title | Spec |
|---|---|---|
| H1 | Discard draft banner visible when no draft exists | `test_v3_discard_draft_resets.spec.js` (Batch A) |
| H2 | Bolt-ons sub-pill visible for c2-* without test lab | `test_v3_enable_test_lab_sync.spec.js` |
| H3 | V2 Save button can be double-clicked → duplicate POST | `test_v3_save_no_double_click.spec.js` |
| H4 | Configure context banner doesn't refresh after Discard | `test_v3_discard_draft_resets.spec.js` (Batch A) |
| H5 | 6 overlays use `_loadingHost` but only 1 is timeout-protected | `test_v3_overlay_loading_state.spec.js` (Batch A — `_withAsyncBody` surface check) |

## Medium issue coverage (partial — focused on operator-visible ones)

| Audit ID | Title | Spec |
|---|---|---|
| M2 | enable_test_lab not persisted back into APP.activeDeployment from loaded tfvars | `test_v3_enable_test_lab_sync.spec.js` |
| M4 | Hero pill text doesn't transition on Save | `test_v3_hero_pill_save_transition.spec.js` |
| M5 | Cost line doesn't recalculate when Test Lab toggle changes | `test_v3_test_lab_combined.spec.js` (cost-row assertion) |

Other Mediums (M1, M3, M6, M7, M8, M9, M10, M11) deferred — most are Phase 2
work or copy polish. Low/L1-L5 deferred per audit recommendation.

---

## Backend test coverage

Backend tests live in `tests/backend/`. The audit is overwhelmingly frontend.
Relevant existing coverage:

| Audit area | Backend spec |
|---|---|
| `enable_test_lab` from tfvars → `/api/deploy/active` | `test_routes_test_lab.py`, `test_deploy_per_project.py` |
| Cost Explorer daily limit / CE usage endpoint | `test_routes_cost_aggregate.py` (touches `/api/costs/aggregate`); CE-usage shape is new — see frontend stub |
| Sentinel filter at backend layer | `test_routes_config_perproject.py` (project name validation) |

No new backend specs were added this pass — Batch A's surface area is purely
frontend reactivity. Cost-counter backend behavior is covered indirectly via
the frontend stub in `test_v3_cost_overlay_ce_usage.spec.js` against the live
endpoint shape.

---

## Notes on Batch B + C interleaving

Many of the bug fixes for Batch B (C5 reset, H3 disable, M4 hero pill) had
already landed at HEAD `fa06f0d` when this pass was authored — the specs
exercise those paths. C6 Test Lab visibility for combined-* was also already
in. The specs are written defensively: they probe the public API surface
(`window.APP.configureV2.assembleConfig`, `cfg-section[data-cfg-section]`),
not implementation details. If Batch B/C lands further refinements those
should not regress these tests.

Batch C (legacy form retirement) is a Phase 2 rewrite — no spec depends on it
landing because Batch A's `applyDraftMode` fix already hides legacy chrome on
Discard. Once the legacy block is deleted, `test_v3_discard_draft_resets.spec.js`'s
`legacyState.editor === 'no-element'` arm will fire naturally.
