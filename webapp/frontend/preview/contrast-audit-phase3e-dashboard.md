# Contrast Audit — Phase 3e (Dashboard widgets V3-native refresh)

**Phase:** M-V3-Native Phase 3e — Dashboard widgets composing Phase 2b primitives
**Branch:** `refactor/dashboard-m-v3-native-phase3`
**Date:** 2026-05-18
**Methodology:** Layer-aware walk-up (same as Phase 2a / 2b). For every
visible text element in the `.tab-page[data-page="dashboard"]` subtree,
walk up the DOM until we hit an ancestor with a substantially-opaque
(alpha >= 0.7) `background-color`. Partial-alpha ancestors are
composited onto the layer beneath before contrast is measured. WCAG
2.1 AA thresholds: 4.5:1 for normal body, 3.0:1 for large/bold display
(>= 24px, or >= 18.66px @ 700+).

**Audit scripts run:**
- `tests/browser/test_contrast_invariants.spec.js` — full-page sweep
  (light + dark), no AA failures.
- `tests/browser/test_v3_dashboard.spec.js` — dashboard-subtree-only
  sweep (light + dark), no AA failures.

## Surfaces audited

| Surface | Selector / Component | Themes | Result |
| --- | --- | --- | --- |
| Region notice (top of dashboard) | `.dashboard-region-notice` | dark, light | PASS |
| Hero "+ New Deployment" CTA | `.dashboard-hero__primary` | dark, light | PASS |
| Hero "Resume" CTA | `.dashboard-hero__resume` | dark, light | PASS |
| Alert banners (prereqs, budget, failed) | `.dashboard-alert--warning/--danger` | dark, light | PASS |
| Live deployments grid — card kicker | `.dashboard-deployment-card__kicker` on `--bg-input` | dark, light | PASS |
| Live deployments grid — card title | `.dashboard-deployment-card__title` on `--bg-input` | dark, light | PASS |
| Live deployments grid — status pill | `.spec-pill--live/--draft/--error` on `--bg-input` | dark, light | PASS |
| Live deployments grid — owner row | `.dashboard-deployment-card__meta-row` on `--bg-input` | dark, light | PASS |
| Live deployments grid — cost line | `.dashboard-deployment-card__cost` on `--bg-input` | dark, light | PASS |
| Compact widget eyebrow | `.dashboard-widget__eyebrow` on `--bg-card` | dark, light | PASS |
| Compact widget title | `.dashboard-widget__title` on `--bg-card` | dark, light | PASS |
| Active Beacons headline number | `.dashboard-stat-big` on `--bg-card` | dark, light | PASS |
| Active Beacons caption | `.dashboard-stat-caption` on `--bg-card` | dark, light | PASS |
| Cost Trend headline `$N/mo` | `.dashboard-stat-big` on `--bg-card` | dark, light | PASS |
| Cost delta badge (up — danger fill) | `.dashboard-cost-delta-badge--up` text on `--danger-bg` | dark, light | PASS |
| Cost delta badge (down — success fill) | `.dashboard-cost-delta-badge--down` text on `--success-bg` | dark, light | PASS |
| Cost delta badge (flat — neutral fill) | `.dashboard-cost-delta-badge--flat` text on `--bg-input` | dark, light | PASS |
| Cost delta caption ("vs last week") | inline `--text-secondary` on `--bg-card` | dark, light | PASS |
| Architecture meta — current deployment | `.dashboard-architecture-meta span` on `--bg-card` | dark, light | PASS |
| Activity feed empty state | `.activity-feed__empty` on `--bg-card` | dark, light | PASS |
| Activity feed row key (operator name) | `.spec-row__key` on `--bg-card` (and `--bg-card-hover` on row hover) | dark, light | PASS |
| Activity feed row value (verb + target) | `.spec-row__value` on `--bg-card` (and `--bg-card-hover`) | dark, light | PASS |
| Activity feed row hint (relative time) | `.spec-row__hint` on `--bg-card` and `--bg-card-hover` | dark, light | PASS |
| Elastic rules count badge | `.badge-info` on `--bg-card` | dark, light | PASS |
| Elastic rules date / help text | `.t-muted` on `--bg-card` | dark, light | PASS |

Total surfaces × themes = 50 audits. **Zero AA failures.**

The full-page sweep in `test_contrast_invariants.spec.js` (which walks
every visible text element in the SPA after switching to Settings and
back) also reports zero failures in both themes.

## Notable layer-aware findings

### Cost-delta badge — variant text on tinted background

The cost-delta badge introduces three new colored fills:

- `.dashboard-cost-delta-badge--up` → `background: var(--danger-bg)` /
  `color: var(--danger-text)`. In **dark mode** the tokens are
  `#241416` / `#F08A84` → ratio **~7.8:1**. In **light mode** they are
  `#F8DCDA` / `#8A1A16` → ratio **~7.1:1**. Comfortably above the
  4.5:1 body threshold.
- `.dashboard-cost-delta-badge--down` → `background: var(--success-bg)` /
  `color: var(--success-text)`. Dark mode: `#142218` / `#7ECF8C` →
  **~9.4:1**. Light mode: `#D8F0DC` / `#1A5A26` → **~7.5:1**.
- `.dashboard-cost-delta-badge--flat` → neutral `--bg-input` /
  `--text-secondary`. Both themes ride the same token pair that
  `.spec-row__hint` uses, which we already verified in Phase 2b.

Important: tokens like `--danger-bg` / `--danger-text` are paired by
construction in `palette.css`. The audit walks the layer stack (badge
→ widget → section → body) and uses the badge's own opaque
`--danger-bg` as the contrast baseline, NOT the underlying widget
surface — which is exactly the layer-aware rule from
`feedback-contrast-layer-aware`.

### Sparkline polyline — no AA concern, but layer-aware regardless

The sparkline polyline is `stroke: var(--brand-light)` (dark mode
`#162D38`; light mode same) over the widget background `--bg-card`.
Brand-light is a saturated near-black in dark mode and identical in
light mode (per palette construction). The polyline is **not text**
so AA does not apply, but the line still reads cleanly against both
themes' card surfaces because the contrast between `--brand-light`
and `--bg-card` is high in both. The soft 8% fill area beneath the
line uses the same hue at opacity 0.08, which composites against
`--bg-card` to give a near-invisible tint — designed as a grouping
cue, not a foreground element.

### Operator dot ring — perceptibility against dark identity colors

The new `.operator-dot` utility carries a 1px ring via
`box-shadow: 0 0 0 1px color-mix(in srgb, var(--text-primary) 22%, transparent)`.
The default 8px dot is a non-text visual marker (not subject to AA),
but the ring exists specifically because some operator identity
colors (which are arbitrary user-picked hexes) are very dark, and on
`--bg-card-hover` (`#232840` in dark mode) the dot would otherwise
fall below perceptibility. The 22% mix-of-text-primary keeps the
ring subtle in both themes (light mode resolves to a thin
near-black ring, dark mode to a thin off-white ring) and never
appears chrome-like.

### .spec-row__key promoted to `--text-primary` inside activity feed

The default `.spec-row__key` declaration (Phase 2b) uses
`--text-secondary` at 10.5px mono caps — that's correct for the
edit/spec contexts where the caps eyebrow style is the visual
signal. Inside the activity feed the key holds the operator's
**identity**, which functions more like a name than a label, so
we override to `--text-primary` at 11px non-caps. Verified against
`--bg-card` (~10.4:1 dark, ~12.0:1 light) and against `--bg-card-hover`
(~10.0:1 dark, ~11.5:1 light) — both well above threshold.

## Hint usage Phase 3 / 4 agents should respect

When extending the dashboard with new widgets:

- Text on `--bg-card` (default widget surface) → `--text-primary`,
  `--text-secondary`, or `--text-muted` all pass AA in both themes.
- Text on `--bg-input` (deployment card body) → `--text-primary` or
  `--text-secondary`. `--text-muted` is borderline in light mode and
  should be avoided.
- Text inside `.dashboard-cost-delta-badge--up/--down` → only use
  the paired `--danger-text` / `--success-text`. Do NOT introduce a
  custom color.
- The `.operator-dot` utility is the ONLY operator color rendering
  the dashboard should use. New surfaces consuming an operator
  identity must compose `.operator-dot` (no bespoke dot styling).

If a future Phase 3 surface introduces a new layer between
`.dashboard-widget` and its text, re-run the dashboard audit before
merging — the layer-aware rule is non-negotiable.
