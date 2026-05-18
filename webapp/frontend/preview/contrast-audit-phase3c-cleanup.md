# Contrast Audit — Phase 3c (V3-native Cleanup sub-pill)

**Phase:** M-V3-Native Phase 3c — Deployments → Cleanup sub-pane
**Branch:** `refactor/dashboard-m-v3-native-phase3`
**Date:** 2026-05-18
**Methodology:** Layer-aware walk-up, identical to Phase 2b. For every
visible text element with non-zero rendered area inside the cleanup
subtree, walk up the DOM until we hit an ancestor with a
substantially-opaque (alpha ≥ 0.7) background. Partially-transparent
ancestors are composited onto the layer beneath before contrast is
measured.

**Threshold:** WCAG 2.1 AA — 4.5:1 for normal body text; 3.0:1 for
large/bold display text (≥ 24px or ≥ 18.66px @ 700+).

**Audit script:** Inline in `tests/browser/test_v3_cleanup.spec.js`
(`Cleanup sub-pill passes contrast (dark theme)` /
`Cleanup sub-pill passes contrast (light theme)`). Scope is
`#subpill-pane-cleanup` so failures localize to the new chrome. The
full-page sweep in `tests/browser/test_contrast_invariants.spec.js`
remains the authoritative net for the dashboard at large.

## Surfaces audited

| Surface | Selector | Themes | Result |
| --- | --- | --- | --- |
| Cleanup eyebrow (title + description + refresh) | `.cleanup-v3__eyebrow` | dark, light | PASS |
| Summary stat tiles (4 numbers) | `.cleanup-v3-summary__tile` | dark, light | PASS |
| Group card header + count chip | `.cleanup-group__header` | dark, light | PASS |
| Spec-row inside cleanup group (key / value / actions) | `.cleanup-row .spec-row__head` | dark, light | PASS |
| Marked-known attribution + draft pill | `.cleanup-row[data-marked-known]` | dark, light | PASS |
| Empty state (no orphans) | `.empty-state` | dark, light | PASS |
| Spec-edit-btn--danger destroy variant | `.spec-edit-btn--danger` | dark, light | PASS |
| Full-page sweep (regression net) | `tests/browser/test_contrast_invariants.spec.js` | dark, light | PASS |

Total Phase 3c surfaces × themes = 14 audits. Plus 8 full-page sweep
assertions. Zero AA failures.

## Notable layer-aware findings

### `.cleanup-row__attribution` follows the same `--text-secondary` rule as `.spec-row__hint`

The attribution caption ("marked by Alice · 3d ago") sits inside
`.spec-row__head` which switches to `--bg-card-hover` on hover. We
deliberately chose `--text-secondary` (not `--text-muted`) for the
attribution text and the relative-time string — same threshold issue
Phase 2b documented for `.spec-row__hint`. The attribution color dot
itself is the operator's brand color (inline `background:`), so it never
inherits a text token and is exempt from the text-contrast pass.

### Marked-known rows: line-through plus opacity 0.78

`.cleanup-row[data-marked-known="true"] .spec-row__head` runs at
`opacity: 0.78`. The audit walker treats elements with opacity ≥ 0.7 as
in-scope for contrast (anything dimmer is treated as a designed
affordance — same rule we apply to spec-list sibling-dim at 0.4). At
0.78 every text token still composites comfortably above 4.5:1 against
both card and card-hover surfaces in both themes.

The line-through decoration uses
`text-decoration-color: color-mix(in srgb, var(--text-muted) 60%, transparent)`
— this only affects the strike line, not the text color, so contrast of
the underlying value text is unchanged.

### `.spec-edit-btn--danger` against `--bg-card`

The Destroy button has `color: var(--danger-text)` against `--bg-card`.
In dark mode that's `#F08A84` on `#232840` (≈ 5.8:1 — passes). In light
mode it's `#8A1A16` on `#F5F3EF` (≈ 8.9:1 — passes). On hover the
background becomes `--danger-bg` (`#241416` dark / `#F8DCDA` light) so
the same foreground still passes (≈ 7.4:1 dark, ≈ 6.5:1 light). No
border-color contrast is required at the AA level since borders are
decorative chrome, not content.

### Summary stat tile labels

`.cleanup-v3-summary__label` uses `--text-secondary` on `--bg-card`.
Caps at `--font-size-xs` is the same combination Phase 2b's
`.spec-row__key` uses — proven AA in both themes. The big number above
uses `--text-primary` which is the highest-contrast text token; trivially
passes at any tile size.

### `.cleanup-v3__refreshed-at` mono caps hint

Lives at the right of the eyebrow strip alongside the Refresh button. On
`--bg-body` (the eyebrow strip has no background of its own, inheriting
from `.subpill-pane`) `--text-secondary` is comfortably above threshold
in both themes. Sized at 10px caps with the 0.14em letter-spacing rule
used throughout V3 — readability matches the eyebrow label primitive.

## Hint usage for Phase 3 follow-ups

When adding new chrome to the cleanup pane:

- Text on `--bg-body` / `--bg-card` (default) → `--text-primary`, `--text-secondary`, `--text-muted` all pass AA.
- Text on `--bg-card-hover` (row hover, row marked-known) → `--text-primary` or `--text-secondary` only. NOT `--text-muted`.
- Danger variant buttons → use the `--danger-text` token, NOT raw `var(--danger)` (the latter is the underlying brand red and dips below threshold on the light-mode card surface).
- Attribution dots paint the operator's brand color directly — exempt from text-contrast but DO confirm the dot meets the 3:1 non-text contrast threshold against the card surface (the operator color palette in `OPERATOR_COLORS` is hand-tuned for this).

## Regression net

The pre-existing `tests/browser/test_contrast_invariants.spec.js`
full-page sweep was re-run after Phase 3c — zero failures in both
themes. The Phase 3c styles do not introduce new global selectors that
could leak contrast bugs to other panes.
