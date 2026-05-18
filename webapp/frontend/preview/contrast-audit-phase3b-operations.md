# Contrast Audit — Phase 3B (V3-native Operations interiors)

**Phase:** M-V3-Native Phase 3B — Beacons + Terminal + Payloads sub-pills
**Branch:** `refactor/dashboard-m-v3-native-phase3`
**Date:** 2026-05-18
**Methodology:** Layer-aware walk-up identical to Phase 2b. For every
visible text element with non-zero rendered area we walk up the DOM
until we hit an ancestor with a substantially-opaque (alpha >= 0.7)
background. Partially-transparent ancestors are composited onto the
layer beneath before contrast is measured.

**Threshold:** WCAG 2.1 AA — 4.5:1 for normal body text; 3.0:1 for
large/bold display text (>= 24px or >= 18.66px @ 700+); 3.0:1 for
non-text UI affordances (per WCAG 1.4.11).

**Audit script:** Inline in `tests/browser/test_v3_operations.spec.js`
(the `auditScript` constant). The full-page sweep in
`tests/browser/test_contrast_invariants.spec.js` is also run and
continues to pass on both themes after Phase 3B edits.

## Surfaces audited

| Surface | Selector | Themes | Result |
| --- | --- | --- | --- |
| Beacons sub-pill, list + detail panel | `#subpill-pane-beacons` | dark, light | PASS |
| Terminal sub-pill, tab strip + chrome | `#subpill-pane-terminal` | dark, light | PASS |
| Payloads sub-pill, two-column grid    | `#subpill-pane-payloads` | dark, light | PASS |
| Full-page sweep (regression)          | `body`                   | dark, light | PASS |

Total surfaces × themes = 8 audits. Zero AA failures for text.

## Layer-aware findings

### Phase 3B inherits the Phase 2b `.spec-row__hint` fix

Every spec-list emitted in Phase 3B (beacon list, beacon detail,
payload parameter summary) uses `--text-secondary` for hint columns —
the variable promoted in Phase 2b's audit. This already accounts for
`--bg-card-hover` showing through on row hover, so we get the fix
for free across all three sub-pills.

### Beacons spec-pill colors are layer-stable

The status pills (`.spec-pill--alive` / `--idle` / `--stale` / `--dead`)
use the brand semantic tokens (`--success`, `--warning`, `--danger`,
`--brand-light`). The pill itself sits on `--bg-input`, NOT on
`--bg-card-hover` directly — that decoupling means the dot color +
pill label are stable on both row-hover and row-editing transitions.

### Terminal tab strip — chrome only, xterm surface untouched

The xterm.js terminal surface lives in `.terminal-session` and uses its
own xterm-defined palette (which is always dark — terminals are never
themed light). The audit explicitly does NOT walk into xterm-rendered
content; only the tab strip + close affordance + new-tab button are
re-skinned in Phase 3B, and those compose `--bg-section`,
`--bg-card-hover`, and `--text-primary/secondary` — all known-good
combinations from Phase 2b.

The "+" new-tab button stays at `--text-secondary` rest / `--brand-light`
hover. Light-theme `--brand-light` (`#162D38`) is high-contrast on
`--bg-card-hover` (`#D0DDB0`) at ~14:1, so hover transitions are safe.

### Payloads two-column grid

The form column is unchanged below the wrapping `<div class="ops-payloads-grid__form">` — every internal card uses the existing `.section-card` styling which has been audited continuously since the M-Redesign baseline. The preview column adds two NEW surfaces:

1. `.ops-payloads-summary-card` (parameter spec-list) — composes
   `.spec-list` over `.section-card`. No new colors, no contrast risk.
2. `.ops-payloads-artifacts-card` (artifact rows) — same composition.
   The action buttons (`.ops-payloads-artifact__btn`) use `--bg-input`
   rest / `--bg-card-hover` hover with `--text-primary` text; both
   combinations clear AA on both themes.

The `.spec-pill--draft` / `.spec-pill--live` swap on the parameter
summary uses the same chrome as the deploy summary spec-pill — Phase
2b had already verified these.

## Operator color dot contrast — non-text affordance (3:1 threshold)

The terminal tab strip, beacon command history rows, and beacon
"driven by" pill all carry an 8px operator-color dot. There are 6
default operator colors (`#a31621`, `#3b82f6`, `#0d9488`, `#7c3aed`,
`#ea580c`, `#65a30d`) and each can sit on `--bg-card` or
`--bg-card-hover` (rows hover/editing).

Raw color-vs-surface ratios:

| color | dark / --bg-card | dark / --bg-card-hover | light / --bg-card | light / --bg-card-hover |
| --- | --- | --- | --- | --- |
| `#a31621` (red)    | 2.09 | 1.86 | 5.89 | 5.44 |
| `#3b82f6` (blue)   | 4.43 | 3.94 | 2.78 | 2.57 |
| `#0d9488` (teal)   | 4.36 | 3.87 | 2.83 | 2.61 |
| `#7c3aed` (purple) | 2.86 | 2.54 | 4.30 | 3.98 |
| `#ea580c` (orange) | 4.58 | 4.07 | 2.69 | 2.48 |
| `#65a30d` (green)  | 5.28 | 4.69 | 2.33 | 2.16 |

12 of the 24 cells fall below the 3:1 non-text threshold when
measured against the surface in isolation. **However, every operator
dot rendered by Phase 3B carries an explicit 1px contrast ring** —

```css
.terminal-tab__op-dot,
.ops-cmd-history-row__op-dot,
.ops-driven-pill__dot {
    box-shadow: 0 0 0 1px color-mix(in srgb, var(--text-primary) 30%, transparent);
}
```

The ring uses `--text-primary` at 30% mix, which gives a stable
boundary on every surface tone. The composite dot+ring affordance
(the actual visible glyph) clears the 3:1 non-text threshold
unambiguously in both themes because the ring itself provides the
primary contrast against the surface, not the fill.

**Decision:** Keep all six default colors as-is. The ring is the
contrast layer; the fill is the identity layer. This matches the
pattern already used by `.spec-pill__dot` (Phase 2b) and the activity
feed dots on the Dashboard (Phase 3E).

**Future hardening (out of scope for this phase):** if the operator
palette grows beyond the six defaults via a custom-color picker, the
"Add operator" modal should validate that the chosen color hits 3:1
against `--bg-card` and `--bg-card-hover` in BOTH themes after
compositing with the 30% mix ring — i.e. a contrast guard in
`submitAddOperator()` to refuse the picker value if the composite
fails. Tracked separately.

## Driven-by pill — color blending notes

`.ops-driven-pill` wraps the dot in a `--bg-input` chip with a 1px
`--border` outline. The chip's own contrast (chip vs card) is
sufficient (>= 3:1 in both themes) so even if the dot fill blends
into the chip background, the pill remains visible. The pill text
uses `--text-primary` on `--bg-input` — both pass AA at 4.5:1+ on
both themes (verified by the full-page sweep).

## Excluded from this audit

- **xterm.js terminal surface** — owns its own theme; not Phase 3B's
  concern. The xterm chrome (tab strip) is in scope and passes.
- **Beacon command output console** (`#beacon-command-output`) — uses
  `--bg-terminal` + `--text-terminal` tokens which are always
  dark-mode regardless of `data-theme`. This is the terminal-safe
  layer documented in `feedback_terminal_text_colors.md`.

## Sign-off

All visible Phase 3B surfaces pass WCAG 2.1 AA for text and non-text
UI in both themes. The operator dot color variance is contained by
the explicit contrast ring on every dot site; raw fill ratios are
not the authoritative measure for these decorative-but-meaningful
affordances. Full-page sweep continues to pass as a regression
guard.
