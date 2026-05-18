# Contrast Audit — Phase 3a (V3-native Manage sub-pill rebuild)

**Phase:** M-V3-Native Phase 3a — Manage sub-pill rebuild
**Branch:** `refactor/dashboard-m-v3-native-phase3`
**Date:** 2026-05-18
**Methodology:** Layer-aware walk-up. For every visible text element with
non-zero rendered area inside the Manage sub-pill, walk up the DOM until
we hit an ancestor with a substantially-opaque (alpha >= 0.7) background.
Partially-transparent ancestors are composited onto the layer beneath
before contrast is measured. Identical to Phase 2a/2b methodology.

**Threshold:** WCAG 2.1 AA — 4.5:1 for normal body text; 3.0:1 for large/
bold display text (>= 24px or >= 18.66px @ 700+).

**Audit harness:** Inline in `tests/browser/test_v3_manage.spec.js`
(`Manage sub-pill: passes layer-aware contrast (dark|light theme)`). Both
test runs filter to `#manage-view` so failures localise to the new
chrome and don't replay the full-page sweep, which is still authoritative
and lives in `test_contrast_invariants.spec.js`.

## Surfaces audited

| Surface | Selector | Themes | Result |
| --- | --- | --- | --- |
| Manage view chrome (hero + eyebrow + spec-list) | `#manage-view` | dark, light | PASS |
| Actions strip (.manage-action default state) | `#manage-actions` | dark, light | PASS |
| Inline output panel (terminal-safe) | `#manage-output` | dark, light | PASS |
| Empty state (.manage-empty) | `.manage-empty` | dark, light | PASS |

Total surfaces × themes = 8 audits. Zero AA failures observed in either
dedicated `test_v3_manage` runs or the full-page `test_contrast_invariants`
sweep (which also catches the new surface).

## Layer-aware findings (new for Phase 3a)

### `.manage-view__updated` uses `--text-secondary`, NOT `--text-muted`

The eyebrow strip's "last updated" caption sits on the page background
(`--bg-app` / `--bg-section`). In dark mode `--text-muted` would clear
AA against either, but the eyebrow is the closest neighbour to the
`.spec-pill` (which on hover lifts to `--bg-card-hover`). Two text
tokens visually adjacent at different contrast ratios reads as broken
hierarchy. Promoted to `--text-secondary` so the eyebrow's label and
the "Last updated" caption share the same readable token.

This mirrors the Phase 2B `.spec-row__hint` finding — when in doubt
about a small caps/mono token, prefer `--text-secondary`. The contrast
audit in CSS now carries an inline comment documenting this.

### `.manage-action--danger` uses tinted-border + tinted-bg-on-hover, never a solid red fill

The Destroy action is a destructive operation. We resist the visual
temptation to paint a solid `--danger` fill because:
  1. On a panel-level surface, a solid-fill destructive button competes
     with the deploy-button language elsewhere (which is green/brand).
  2. Operator interaction is gated by a confirm modal — the button
     itself is just an entry point, not a commit.
  3. Layer-aware contrast: a solid `--danger` fill needs `--text-inverse`
     for contrast, but `--text-inverse` in dark mode is `#FFFFFF` and
     in light mode is a near-black, which means the same class would
     resolve to two different tokens — a maintenance burden.

Instead the danger variant uses `color-mix(in srgb, var(--danger) 55%, var(--border))`
on the resting border and a `color-mix(in srgb, var(--danger) 12%, transparent)`
fill on hover. Text stays at `--text-primary` (which is safe on both
themes' card-hover layer).

### Terminal-safe variable used for `.manage-view__output`

The inline output panel for health-check results uses `--bg-terminal`
(always dark) + `--text-terminal` (always bright). This matches the
"terminal-safe variables" rule in CLAUDE.md: bright greens/cyans are
safe ONLY on terminal-dark surfaces. No layer-aware regression is
possible because the surface itself doesn't change with theme.

### `.manage-attr--unknown` lives on `.spec-row__value`

When no audit data exists, we render `<span class="manage-attr manage-attr--unknown">unknown operator</span>`
inside a `.spec-row__value`. The value cell sits on `.spec-row__head`,
which switches to `--bg-card-hover` on hover. `--text-secondary` (the
chosen colour for the unknown variant) is at ~7.16:1 against
`--bg-card-hover` — safe.

### `.manage-action` hover state matches the Phase 2B segmented control

When hovered, `.manage-action` sets `background: var(--bg-card-hover)`
+ `border-color: var(--border-light)` — the exact pattern that the
Phase 2B audit blessed for `.seg-control__option:hover`. Text stays at
`--text-primary` throughout; the icon colour shifts from
`--text-secondary` to `--text-primary` on hover, which is the same
neighbouring-token relationship Phase 2B verified.

## Hint usage downstream consumers should respect

The Phase 3a additions are read-only (no inline editor), so the
sibling-dim and `[data-editing="true"]` cases from Phase 2B do not
apply. New rules introduced here:

- Text on `.manage-view__output` background → use `--text-terminal`
  or one of the bright `--terminal-*` palette tokens; do NOT use the
  body-text tokens (they're tuned for `--bg-app`).
- Text on the Destroy action's hover background (12% danger tint over
  the page) → keep at `--text-primary`. The 12% tint is too faint to
  drag contrast below threshold.
- `.manage-view__hero-name` is large (22px) + bold (700) → falls
  under the "large text" 3.0:1 threshold rather than 4.5:1. Currently
  paints `--text-primary` on `--bg-app` (~16.4:1) — far above either
  threshold. Future hero variants must keep this token to avoid
  regression.

## Full-page sweep result

After adding the Manage sub-pill chrome and re-running the full-page
contrast sweep (`tests/browser/test_contrast_invariants.spec.js`), both
themes pass with zero AA failures. 8/8 contrast invariants pass.
