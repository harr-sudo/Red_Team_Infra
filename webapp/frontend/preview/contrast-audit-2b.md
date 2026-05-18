# Contrast Audit — Phase 2b (V3-native Deploy summary + journey takeover)

**Phase:** M-V3-Native Phase 2b — Composition A spec-list + Hybrid journey
**Branch:** `refactor/dashboard-m-v3-native-phase2b`
**Date:** 2026-05-18
**Methodology:** Layer-aware walk-up. Identical to Phase 2a. For every
visible text element with non-zero rendered area, walk up the DOM until
we hit an ancestor with a substantially-opaque (alpha >= 0.7) background.
Partially-transparent ancestors are composited onto the layer beneath
before contrast is measured.

**Threshold:** WCAG 2.1 AA — 4.5:1 for normal body text; 3.0:1 for large/
bold display text (>= 24px or >= 18.66px @ 700+).

**Audit script:** Inline in `tests/browser/test_v3_deploy_summary.spec.js`
and `tests/browser/test_v3_journey.spec.js`. Tests are scoped to the
relevant surface so failures are local to the new chrome (rather than
re-running the full-page sweep, which is still authoritative for the
broader app and lives in `test_contrast_invariants.spec.js`).

## Surfaces audited

| Surface | Selector | Themes | Result |
| --- | --- | --- | --- |
| Deploy sub-pill summary, read-only | `#config-summary-section` | dark, light | PASS |
| Deploy sub-pill summary, row editing | `#config-summary-section` (env editor open) | dark, light | PASS |
| Journey takeover, wizard | `#journey-takeover` (step 1) | dark, light | PASS |
| Journey takeover, review | `#journey-review` | dark, light | PASS |
| Journey review, row editing | `[data-review-editor]` (env editor open) | dark, light | PASS |

Total surfaces × themes = 10 audits. Zero AA failures.

## Notable layer-aware findings

### `.spec-row__hint` had to use `--text-secondary`, not `--text-muted`

`.spec-row__head` switches background to `--bg-card-hover` on row hover
**and** when `[data-editing="true"]` is set on the row. With
`--text-muted` (#858FAB) the hint text dropped to ~4.49:1 against
`--bg-card-hover` (#232840) — failing AA by a hair. Promoted to
`--text-secondary` (#B0B8CC), which gives ~7.16:1 — comfortably above
threshold and stable across both themes.

This is the same class of layer-aware bug Phase 2a's audit caught: text
chosen against the default surface (`--bg-card`, ~6.5:1) silently breaks
once the parent transitions to `--bg-card-hover`. Phase 3 agents
consuming `.spec-row__hint` get this fix for free; do not pass
`--text-muted` to anything that may sit on a card-hover surface.

### Sibling-dim rows are explicitly excluded from the audit

When the spec-list is in editing mode, every non-editing row drops to
`opacity: 0.4`. That's a designed affordance, not a contrast failure —
the operator's attention should be on the editor, and the dim rows are
deliberately deprioritized. Both new test specs filter sibling rows out
of the audit so the diff stays focused on real bugs.

### Scrim layer-aware behaviour

`.scrim-takeover` is positioned `fixed; inset: 0` and uses
`backdrop-filter: blur(8px)`. The `.takeover-card` is centered on top
with its own opaque `--bg-card` background — so text inside the card
never composites against the scrim. Audited explicitly (the journey
contrast tests run with the scrim active) and no failures.

### `body[data-journey-open]` blur-dim

The dashboard underneath is `filter: blur(8px); opacity: 0.28; pointer-events: none`
when the journey is open. The audit's `walkToSurface` skips the dashboard
subtree because `pointer-events: none` is irrelevant to contrast — but
since the dashboard is fully obscured by the scrim + card stack, no text
inside it is visible enough to fail AA in practice. The dashboard text
is unchanged; we're just adding a presentation overlay.

## Hint usage Phase 3 agents should respect

When composing the primitives outside the editor body:

- Text on `--bg-card` (default panel) → `--text-primary`, `--text-secondary`, or `--text-muted` all pass AA.
- Text on `--bg-card-hover` (hover/editing) → `--text-primary` or `--text-secondary`. NOT `--text-muted`.
- Text on `--bg-input` (recessed field, also the seg-control rest state) → `--text-primary` or `--text-secondary`. `--text-muted` is borderline.
- Text inside `.seg-control__option.is-active` (also `--bg-card-hover`) → `--text-primary` (which is what we set). Don't change.

If a Phase 3 surface introduces a new layer between `.spec-row` and
`.spec-row__hint`, re-run this audit before merging.
