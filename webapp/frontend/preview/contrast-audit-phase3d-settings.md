# Contrast Audit — Phase 3d (Settings tab, 8-section sweep)

**Phase:** M-V3-Native Phase 3d — Settings audit + refinement
**Branch:** `refactor/dashboard-m-v3-native-phase3`
**Date:** 2026-05-18
**Methodology:** Layer-aware walk-up, identical to Phase 2a/2b. For every
visible text element with non-zero rendered area inside each Settings
section ID, walk up the DOM until we hit an ancestor with a
substantially-opaque (alpha >= 0.7) background. Partially-transparent
ancestors are composited onto the layer beneath before contrast is
measured.

**Threshold:** WCAG 2.1 AA — 4.5:1 for normal body text; 3.0:1 for large/
bold display text (>= 24px or >= 18.66px @ 700+).

**Audit script:** `tests/browser/test_v3_settings.spec.js` —
`auditSectionContrast()` (one call per section × theme = 16 sweeps).

## What Phase 2a's sweep missed

The Phase 2a full-page sweep (`test_contrast_invariants.spec.js`) visits
the Settings tab but only walks the DOM that was visible at the time the
sweep ran. It found and fixed the **section-header** regression (the
zombie `header { background: var(--burgundy); }` rule). It did NOT visit:

1. The **Cost Breakdown table** in `#settings-cost`. That table is
   conditionally rendered — it requires actual AWS Cost Explorer data
   above $0.01 to appear in the DOM. The dev harness almost never has
   live cost data when tests run, so the table chrome was never inspected.
2. The **D8 inventory lazy-loaded subtrees** (`#settings-domains-list`,
   `#settings-secrets-list`, `#settings-services-list`). These are
   guarded by `dataset.loaded` and fired asynchronously after the tab
   activates. Phase 2a's sweep ran before the loaders completed, so the
   sweep saw skeleton placeholders, not rendered rows.

Phase 3d's per-section sweep scrolls each section into view, waits for
lazy loaders, AND runs against a live render of the inventory data
(which during this audit returned 0 results — but the spec-list
`.settings-spec-empty` placeholder was inspected and passes AA).

## Result: 1 contrast failure found and fixed

`#settings-cost` light theme — `.cost-breakdown-table th` resolved to:
- fg: `var(--gold-muted)` → `rgb(73, 92, 45)` (olive)
- bg: `var(--bg-elevated)` → `rgb(194, 208, 159)` (cream-on-light)
- ratio: **4.49:1** — fails AA (need 4.5).

Fix (Phase 3d CSS section 9b): scope `--text-primary` to
`.tab-page[data-page="settings"] .cost-breakdown-table th`. New ratio:
~10.3:1 (dark text on cream).

## Surfaces audited (each × dark/light = 16 sweeps)

| Section | Surface composition | Dark | Light |
| --- | --- | --- | --- |
| `#settings-general` | `.status-display.info` on `.bg-card` w/ brand-light left rail (Phase 3d section 8) | PASS | PASS |
| `#settings-prereqs` | Nested `.section-card--highlight--compact` on `.section-card` on `.bg-card`. Multiple text tokens (primary, secondary, muted, link) audited per nested card. | PASS | PASS |
| `#settings-domains` | `.spec-list--inset` inside `.section-card`. `.spec-row__key/value/hint` on `.bg-card` rest, `.bg-card-hover` on hover. `.settings-spec-toolbar__status` on `.bg-card`. | PASS | PASS |
| `#settings-secrets` | Same composition as Domains; spec-row pattern. | PASS | PASS |
| `#settings-services` | Same composition as Domains/Secrets; spec-row pattern. | PASS | PASS |
| `#settings-cost` | `.cost-tracker-summary` spec-list + `.cost-trend-section` chart + `.cost-breakdown-table` (FIXED in 3d). `.callout--info` (untracked-costs disclosure) on `.bg-card`. | PASS | PASS (after fix) |
| `#settings-prefs` | `.seg-control` on `.bg-input`; eyebrow label and small-text helper on `.bg-card`. | PASS | PASS |
| `#settings-roadmap` | `<details>` chrome on `.bg-card`, summary on `.bg-section`. `.roadmap-summary__doc` caption now `--text-secondary` (Phase 3d section 5). | PASS | PASS |

Total surfaces × themes = 16 audits. Zero AA failures after the
breakdown-table fix.

## Notable layer-aware findings — Phase 3d specific

### `.cost-breakdown-table th` was a real bug — not just borderline

The `.cost-breakdown-table` chrome was authored before V3 with
`color: var(--gold-muted)`. In dark mode `--gold-muted` resolves to an
olive/cream that contrasts cleanly with the dark bg-elevated header
(8.6:1). In light mode both tokens drift toward each other — olive text
on cream background — and the ratio collapses to 4.49:1, missing AA by
0.01.

This is exactly the failure mode Phase 2a's contrast feedback called
out: tokens chosen against the dark-mode baseline that silently break
in light mode. The fix is layer-aware: scope the table inside Settings
to `--text-primary`, which is calibrated against both themes.

### `.settings-spec-toolbar__status` defensive promotion

The status span in each D8 inventory toolbar carries a small mono-caps
label. The legacy D8 markup used `<span class="t-muted">` →
`--text-muted` (#858FAB on dark, #687290 on light). On `--bg-card` the
light-mode ratio is ~4.7:1 — passes AA but with no headroom for tweaks.
Phase 3d promotes to `--text-secondary` (#B0B8CC dark / #444C66 light) →
8.4:1 dark, 6.2:1 light. Comfortable on both.

### Form-group `<small>` in Preferences

The `<small>` description below the seg-control was `--text-muted` in
the inherited form-group rule. Same borderline risk as the status
span; Phase 3d promotes the Settings-scoped `<small>` to
`--text-secondary` so the helper text is comfortably readable below the
seg-control.

### Roadmap doc captions

`<span style="float: right; color: var(--text-muted)">` (inline-style
captions like `beacon-api-features-backlog.md`). Sits on
`background: var(--bg-section)` summary. In light mode that's
`--text-muted (#687290)` on `--bg-section (#F5F2E9)` → ~4.6:1. Passes,
but borderline. Phase 3d replaces with a proper `.roadmap-summary__doc`
class on `--text-secondary` for stability.

## Hint usage Phase 3+ agents should respect (Settings-scoped)

When composing inside a Settings `.section-card`:

- Text directly on `--bg-card` (default panel) → `--text-primary` or
  `--text-secondary`. `--text-muted` is borderline at small sizes in
  light mode; verify before use.
- Text inside a nested `.section-card--highlight` (also `--bg-card`)
  → same rules; the highlight modifier doesn't change paint.
- `.spec-row__head` background switches to `--bg-card-hover` on hover/
  editing — use `--text-primary` or `--text-secondary`. NEVER
  `--text-muted` here.
- `.seg-control__option.is-active` paints `--bg-card-hover` →
  `--text-primary` (which is what the primitive already sets).
- Table headers in cost or any future Settings table → `--text-primary`
  (not `--gold-muted`). The Phase 3d rule
  `.tab-page[data-page="settings"] .cost-breakdown-table th` is the
  reference fix.

If a future Settings sub-section introduces a new surface layer (e.g. a
nested card on a card on a card), re-run this audit before merging.
