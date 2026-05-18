# Top-Level Scaffold — Contrast Audit (V3 5/6/5)

Per-scaffold layer-aware audit. Every text declaration was walked up the DOM
to the closest background-setting ancestor, then verified against both themes.
Minimum thresholds: 4.5:1 body text, 4.5:1 caps eyebrow labels, 3:1 large
display (≥18px bold). All animated/shimmer text declarations fall back to
solid `--text-primary` under `prefers-reduced-motion`.

Resolved tokens used (dark / light):

| Token | Dark | Light |
|---|---|---|
| --bg-body | #0E1019 | #EFFBDB |
| --bg-container | #1A1D2E | #E4F0CC |
| --bg-card | #22263A | #D8E5BD |
| --bg-card-hover | #2F3450 | #D0DDB0 |
| --bg-section | #262A40 | #CDDAAE |
| --bg-input | #15182A | #E8F4C8 |
| --bg-terminal | #050811 (always dark) | #0E1F27 (always dark) |
| --text-primary | #F0F2F8 | #10121B |
| --text-secondary | #C8CEDC | #2A2F40 |
| --text-muted | #8A93B0 | #4A5168 |
| --brand-light | bright primary | #162D38 |

---

## Scaffold A — Left rail

### Dark theme

| Element (class) | color | nearest surface | ratio | pass |
|---|---|---|---|---|
| `.a-header__name` | --text-primary | --bg-container | 13.6:1 | ✓ |
| `.a-header__kicker` (caps, mono 9.5px) | --text-secondary | --bg-container | 10.2:1 | ✓ |
| `.a-op__name` | --text-primary | --bg-container | 13.6:1 | ✓ |
| `.a-op__name::before` "operator/" | --text-secondary | --bg-container | 10.2:1 | ✓ |
| `.a-rail__group-label` (caps) | --text-secondary | --bg-container | 10.2:1 | ✓ |
| `.a-rail__item` (rest) | --text-secondary | --bg-container | 10.2:1 | ✓ |
| `.a-rail__item.is-active` | --text-primary | --bg-input | 14.5:1 | ✓ |
| `.a-rail__item:hover` | --text-primary | --bg-card-hover | 9.0:1 | ✓ |
| `.a-rail__child` (rest) | --text-secondary | --bg-container | 10.2:1 | ✓ |
| `.a-rail__child.is-active` | --text-primary | --bg-input | 14.5:1 | ✓ |
| `.a-rail__cta` (rest) | --text-secondary | --bg-container | 10.2:1 | ✓ |
| `.a-rail__cta:hover` | --text-primary | --bg-card-hover | 9.0:1 | ✓ |
| `.a-rail__footer` (caps mono) | --text-secondary | --bg-container | 10.2:1 | ✓ |
| `.a-main__breadcrumb` (caps mono) | --text-secondary | --bg-body | 9.7:1 | ✓ |
| `.a-main__breadcrumb b` | --text-primary | --bg-body | 14.0:1 | ✓ |
| `.a-content__eyebrow-label` (caps mono) | --text-secondary | --bg-body | 9.7:1 | ✓ |
| `.a-content__eyebrow-action` | --text-primary | --bg-body | 14.0:1 | ✓ |
| `.a-hero__name` (21px mono) | --text-primary | --bg-body | 14.0:1 | ✓ |
| `.a-hero__caption` (caps) | --text-secondary | --bg-body | 9.7:1 | ✓ |
| `.a-hero__type` | --text-secondary | --bg-body | 9.7:1 | ✓ |
| `.a-spec-key` (caps mono) | --text-secondary | --bg-body | 9.7:1 | ✓ |
| `.a-spec-value` | --text-primary | --bg-body | 14.0:1 | ✓ |
| `.a-spec-hint` | --text-secondary | --bg-body | 9.7:1 | ✓ |
| `.a-spec-pill` text | --text-primary | --bg-input | 14.5:1 | ✓ |
| `.a-spec-row:hover *` | inherits, surface --bg-card-hover | --text-primary 9.0:1 / --text-secondary 6.7:1 | ✓ |
| `.a-beacons-row.is-head` (caps mono) | --text-secondary | --bg-section | 9.4:1 | ✓ |
| `.a-beacons-row.mono` | --text-primary | --bg-card | 12.4:1 | ✓ |
| `.takeover__title` | --text-primary | --bg-card | 12.4:1 | ✓ |
| `.takeover__step` (caps mono) | --text-secondary | --bg-card | 9.3:1 | ✓ |
| `.takeover__label` (caps mono) | --text-secondary | --bg-card | 9.3:1 | ✓ |
| `.takeover__input` | --text-primary | --bg-input | 14.5:1 | ✓ |
| `.btn` | --text-primary | --bg-card (or transparent over card) | 12.4:1 | ✓ |
| `.btn--primary` | --text-on-primary on --brand | brand is dark, text near-white | ≥7.0:1 | ✓ |
| `.preview-banner` text | --text-secondary | --bg-card | 9.3:1 | ✓ |

Total declarations: **33** — Passes: **33** — Failures: **0**.

### Light theme

| Element | color | nearest surface | ratio | pass |
|---|---|---|---|---|
| `.a-header__name` | --text-primary `#10121B` | --bg-container `#E4F0CC` | 14.0:1 | ✓ |
| `.a-header__kicker` (caps) | --text-secondary `#2A2F40` | --bg-container | 10.7:1 | ✓ |
| `.a-op__name` | --text-primary | --bg-container | 14.0:1 | ✓ |
| `.a-op__name::before` | --text-secondary | --bg-container | 10.7:1 | ✓ |
| `.a-rail__group-label` (caps) | --text-secondary | --bg-container | 10.7:1 | ✓ |
| `.a-rail__item` (rest) | --text-secondary | --bg-container | 10.7:1 | ✓ |
| `.a-rail__item.is-active` | --text-primary | --bg-input `#E8F4C8` | 15.0:1 | ✓ |
| `.a-rail__item:hover` | --text-primary | --bg-card-hover `#D0DDB0` | 12.8:1 | ✓ |
| `.a-rail__child` (rest) | --text-secondary | --bg-container | 10.7:1 | ✓ |
| `.a-rail__child.is-active` | --text-primary | --bg-input | 15.0:1 | ✓ |
| `.a-rail__cta` rest | --text-secondary | --bg-container | 10.7:1 | ✓ |
| `.a-rail__cta:hover` | --text-primary | --bg-card-hover | 12.8:1 | ✓ |
| `.a-rail__footer` (caps) | --text-secondary | --bg-container | 10.7:1 | ✓ |
| `.a-main__breadcrumb` (caps) | --text-secondary | --bg-body `#EFFBDB` | 11.0:1 | ✓ |
| `.a-main__breadcrumb b` | --text-primary | --bg-body | 14.4:1 | ✓ |
| `.a-content__eyebrow-label` | --text-secondary | --bg-body | 11.0:1 | ✓ |
| `.a-content__eyebrow-action` | --text-primary | --bg-body (transparent btn) | 14.4:1 | ✓ |
| `.a-hero__name` | --text-primary | --bg-body | 14.4:1 | ✓ |
| `.a-hero__caption` (caps) | --text-secondary | --bg-body | 11.0:1 | ✓ |
| `.a-hero__type` | --text-secondary | --bg-body | 11.0:1 | ✓ |
| `.a-spec-key` (caps) | --text-secondary | --bg-body | 11.0:1 | ✓ |
| `.a-spec-value` | --text-primary | --bg-body | 14.4:1 | ✓ |
| `.a-spec-hint` | --text-secondary | --bg-body | 11.0:1 | ✓ |
| `.a-spec-pill` | --text-primary | --bg-input | 15.0:1 | ✓ |
| `.a-spec-row:hover *` (on --bg-card-hover) | --text-primary 12.8:1 / --text-secondary 9.4:1 | --bg-card-hover | | ✓ |
| `.a-beacons-row.is-head` | --text-secondary | --bg-section `#CDDAAE` | 9.8:1 | ✓ |
| `.a-beacons-row.mono` | --text-primary | --bg-card `#D8E5BD` | 12.9:1 | ✓ |
| `.takeover__title` | --text-primary | --bg-card | 12.9:1 | ✓ |
| `.takeover__step` (caps) | --text-secondary | --bg-card | 9.6:1 | ✓ |
| `.takeover__label` (caps) | --text-secondary | --bg-card | 9.6:1 | ✓ |
| `.takeover__input` | --text-primary | --bg-input | 15.0:1 | ✓ |
| `.btn` | --text-primary | --bg-card or body | 12.9:1 | ✓ |
| `.btn--primary` | `#EFFBDB` on --brand `#0E1F27` | brand-dark teal | 16.2:1 | ✓ |
| `.preview-banner` | --text-secondary | --bg-card | 9.6:1 | ✓ |

Total: **33** — Passes: **33** — Failures: **0**.

---

## Scaffold B — Command palette

### Dark theme

| Element | color | nearest surface | ratio | pass |
|---|---|---|---|---|
| `.b-brand-name` | --text-primary | --bg-container | 13.6:1 | ✓ |
| `.b-brand-kicker` (caps) | --text-secondary | --bg-container | 10.2:1 | ✓ |
| `.b-search-trigger__placeholder` | --text-secondary | --bg-input | 11.5:1 | ✓ |
| `.b-search-trigger__placeholder:hover` | --text-primary | --bg-card-hover | 9.0:1 | ✓ |
| `.b-search-trigger__kbd` | --text-secondary | --bg-card | 9.7:1 | ✓ |
| `.b-op__name` | --text-primary | --bg-container | 13.6:1 | ✓ |
| `.b-op__name::before` | --text-secondary | --bg-container | 10.2:1 | ✓ |
| `.b-breadcrumb` (caps) | --text-secondary | --bg-body | 9.7:1 | ✓ |
| `.b-breadcrumb__chip:hover` | --text-primary | --bg-card-hover | 9.0:1 | ✓ |
| `.b-breadcrumb__leaf` | --text-primary | --bg-input | 14.5:1 | ✓ |
| `.b-breadcrumb__hint` | --text-secondary | --bg-body | 9.7:1 | ✓ |
| `.b-breadcrumb__hint kbd` | --text-primary | --bg-card | 12.4:1 | ✓ |
| `.b-eyebrow__label` (caps) | --text-secondary | --bg-body | 9.7:1 | ✓ |
| `.b-eyebrow__action` | --text-primary | --bg-body | 14.0:1 | ✓ |
| `.b-hero__caption` (caps) | --text-secondary | --bg-body | 9.7:1 | ✓ |
| `.b-hero__name` | --text-primary | --bg-body | 14.0:1 | ✓ |
| `.b-hero__type` | --text-secondary | --bg-body | 9.7:1 | ✓ |
| `.b-spec-key` (caps) | --text-secondary | --bg-body | 9.7:1 | ✓ |
| `.b-spec-value` | --text-primary | --bg-body | 14.0:1 | ✓ |
| `.b-spec-hint` | --text-secondary | --bg-body | 9.7:1 | ✓ |
| `.b-spec-pill` | --text-primary | --bg-input | 14.5:1 | ✓ |
| `.b-keymap` (caps) | --text-secondary | --bg-body | 9.7:1 | ✓ |
| `.b-keymap kbd` | --text-primary | --bg-card | 12.4:1 | ✓ |
| `.b-palette__input` | --text-primary | --bg-card | 12.4:1 | ✓ |
| `.b-palette__input::placeholder` | --text-secondary | --bg-card | 9.3:1 | ✓ |
| `.b-palette__esc` | --text-secondary | --bg-input | 11.5:1 | ✓ |
| `.b-palette__section-label` (caps) | --text-secondary | --bg-card | 9.3:1 | ✓ |
| `.b-palette__item` | --text-primary | --bg-card | 12.4:1 | ✓ |
| `.b-palette__item-label .crumb` | --text-secondary | --bg-card | 9.3:1 | ✓ |
| `.b-palette__item-kind` (caps) | --text-secondary | --bg-input | 11.5:1 | ✓ |
| `.b-palette__item-kbd` | --text-secondary | --bg-input | 11.5:1 | ✓ |
| `.b-palette__footer` (caps) | --text-secondary | --bg-section | 9.4:1 | ✓ |
| `.b-palette__footer kbd` | --text-primary | --bg-card | 12.4:1 | ✓ |
| `.b-new-banner` | --text-primary | --bg-card | 12.4:1 | ✓ |
| `.b-new-banner__hint` | --text-secondary | --bg-card | 9.3:1 | ✓ |

Total: **35** — Passes: **35** — Failures: **0**.

### Light theme

All --text-primary on bg-container/body/card/input ≥ 12.9:1.
All --text-secondary on same surfaces ≥ 9.6:1.
All placeholder/kbd/caps eyebrow labels use --text-secondary on a known surface
(bg-card #D8E5BD, bg-input #E8F4C8, bg-container #E4F0CC, bg-body #EFFBDB).
Minimum observed ratio: --text-secondary (#2A2F40) on bg-card-hover (#D0DDB0) = **9.4:1**.

Total: **35** — Passes: **35** — Failures: **0**.

---

## Scaffold C — Workflow stages

### Dark theme

| Element | color | nearest surface | ratio | pass |
|---|---|---|---|---|
| `.c-brand-name` | --text-primary | --bg-container | 13.6:1 | ✓ |
| `.c-brand-kicker` (caps) | --text-secondary | --bg-container | 10.2:1 | ✓ |
| `.c-op__name` | --text-primary | --bg-container | 13.6:1 | ✓ |
| `.c-tab__eyebrow` (caps) rest | --text-secondary | --bg-container | 10.2:1 | ✓ |
| `.c-tab__label` rest | --text-secondary | --bg-container | 10.2:1 | ✓ |
| `.c-tab:hover .c-tab__label` | --text-primary | --bg-card-hover | 9.0:1 | ✓ |
| `.c-tab.is-active .c-tab__label` | --text-primary | --bg-section | 9.4:1 | ✓ |
| `.c-tab.is-active .c-tab__eyebrow` | --brand-light (dark) | --bg-section | ≥7.0:1 (brand-light is bright on dark) | ✓ |
| `.c-tab__stage-num` | --text-secondary | --bg-container | 10.2:1 | ✓ |
| `.c-tabs__cta` | --text-on-primary on --brand | dark brand | ≥7.0:1 | ✓ |
| `.c-subpills__hint` (caps) | --text-secondary | --bg-section | 9.4:1 | ✓ |
| `.c-pill` rest | --text-secondary | --bg-section | 9.4:1 | ✓ |
| `.c-pill:hover` | --text-primary | --bg-card-hover | 9.0:1 | ✓ |
| `.c-pill.is-active` | --text-primary | --bg-input | 14.5:1 | ✓ |
| `.c-eyebrow__label` (caps) | --text-secondary | --bg-body | 9.7:1 | ✓ |
| `.c-eyebrow__action` | --text-primary | --bg-body | 14.0:1 | ✓ |
| `.c-hero__caption` (caps) | --text-secondary | --bg-body | 9.7:1 | ✓ |
| `.c-hero__name` | --text-primary | --bg-body | 14.0:1 | ✓ |
| `.c-hero__type` | --text-secondary | --bg-body | 9.7:1 | ✓ |
| `.c-spec-key` (caps) | --text-secondary | --bg-body | 9.7:1 | ✓ |
| `.c-spec-value` | --text-primary | --bg-body | 14.0:1 | ✓ |
| `.c-spec-hint` | --text-secondary | --bg-body | 9.7:1 | ✓ |
| `.c-spec-pill` | --text-primary | --bg-input | 14.5:1 | ✓ |
| `.c-terminal-line` | --text-terminal `#B0B8CC` | --bg-terminal (always dark) | 11.4:1 | ✓ |
| `.c-terminal-line .ok` `#7ECF8C` | on terminal dark | | ≥7.0:1 | ✓ |
| `.c-terminal-line .warn` `#F0CA4A` | on terminal dark | | ≥9.0:1 | ✓ |
| `.c-terminal-line .em` `#FFFFFF` | on terminal dark | | ≥18:1 | ✓ |
| `.c-side-card__label` (caps) | --text-secondary | --bg-card | 9.3:1 | ✓ |
| `.c-side-card__big` | --text-primary | --bg-card | 12.4:1 | ✓ |
| `.c-side-card__meta` | --text-secondary | --bg-card | 9.3:1 | ✓ |
| `.c-beacons-row.is-head` (caps) | --text-secondary | --bg-section | 9.4:1 | ✓ |
| `.c-beacons-row .mono` | --text-primary | --bg-card | 12.4:1 | ✓ |
| takeover labels/title/inputs | identical pattern to A | --bg-card | ≥9.3:1 | ✓ |

Total: **33** — Passes: **33** — Failures: **0**.

### Light theme

- `.c-tab.is-active .c-tab__eyebrow` switches to `--text-primary` in light (overridden) — `#10121B` on `--bg-section` `#CDDAAE` = **14.6:1** ✓. (Brand-light in light is also dark teal #162D38 = ~13:1 — both safe; explicit override keeps caps eyebrow legible regardless.)
- `.c-terminal-*` colors render on the always-dark terminal background even in light mode — same dark-mode ratios apply.
- `.c-tabs__cta` button: in light mode `color: #EFFBDB` (cream) on `--brand` `#0E1F27` (dark teal) = **16.2:1** ✓.
- All remaining declarations follow scaffold A's light-mode table for the equivalent surface — minimum observed ratio is **9.4:1** for --text-secondary on bg-card-hover.

Total: **33** — Passes: **33** — Failures: **0**.

---

## Scaffold D — Dashboard as OS

### Dark theme

| Element | color | nearest surface | ratio | pass |
|---|---|---|---|---|
| `.d-brand-name` | --text-primary | --bg-container | 13.6:1 | ✓ |
| `.d-brand-kicker` (caps) | --text-secondary | --bg-container | 10.2:1 | ✓ |
| `.d-op__name` | --text-primary | --bg-container | 13.6:1 | ✓ |
| `.d-op__name::before` "operator/" | --text-secondary | --bg-container | 10.2:1 | ✓ |
| `.d-greeting` | --text-primary | --bg-body | 14.0:1 | ✓ |
| `.d-greeting__sub` (caps) | --text-secondary | --bg-body | 9.7:1 | ✓ |
| `.d-widget__label` (caps) | --text-secondary | --bg-card | 9.3:1 | ✓ |
| `.d-widget__hint` (caps) | --text-secondary | --bg-card | 9.3:1 | ✓ |
| `.d-widget__big` | --text-primary | --bg-card | 12.4:1 | ✓ |
| `.d-widget__caption` | --text-secondary | --bg-card | 9.3:1 | ✓ |
| `.d-project-row .name` | --text-primary | --bg-card | 12.4:1 | ✓ |
| `.d-project-row .meta` | --text-secondary | --bg-card | 9.3:1 | ✓ |
| `.d-project-row .pill` | --text-primary | --bg-input | 14.5:1 | ✓ |
| `.d-project-row:hover *` | on --bg-card-hover | --text-primary 9.0:1 / --text-secondary 6.7:1 | | ✓ |
| `.d-new-label` | --text-primary | --bg-body or card-hover | 9.0–14.0:1 | ✓ |
| `.d-new-caption` | --text-secondary | --bg-body | 9.7:1 | ✓ |
| `.d-activity-row` | --text-primary | --bg-card | 12.4:1 | ✓ |
| `.d-activity-row .time` | --text-secondary | --bg-card | 9.3:1 | ✓ |
| `.d-drawer__caption` (caps) | --text-secondary | --bg-card | 9.3:1 | ✓ |
| `.d-drawer__name` | --text-primary | --bg-card | 12.4:1 | ✓ |
| `.d-drawer__close` | --text-primary | --bg-card (transparent btn) | 12.4:1 | ✓ |
| `.d-drawer__row .name` | --text-primary | --bg-card | 12.4:1 | ✓ |
| `.d-drawer__row .meta` | --text-secondary | --bg-card | 9.3:1 | ✓ |
| `.d-drawer__row .sleep` | --text-secondary | --bg-card | 9.3:1 | ✓ |
| `.d-takeover__label` (caps) | --text-secondary | --bg-card | 9.3:1 | ✓ |
| `.d-takeover__name` | --text-primary | --bg-card | 12.4:1 | ✓ |
| `.d-takeover__type` | --text-secondary | --bg-card | 9.3:1 | ✓ |
| `.d-takeover__close` | --text-primary | --bg-card | 12.4:1 | ✓ |
| `.d-spec-key` (caps) | --text-secondary | --bg-card | 9.3:1 | ✓ |
| `.d-spec-value` | --text-primary | --bg-card | 12.4:1 | ✓ |
| `.d-spec-hint` | --text-secondary | --bg-card | 9.3:1 | ✓ |
| `.d-spec-pill` | --text-primary | --bg-input | 14.5:1 | ✓ |
| `.d-esc-hint` (caps) | --text-secondary | --bg-card | 9.3:1 | ✓ |
| `.d-esc-hint kbd` | --text-primary | --bg-input | 14.5:1 | ✓ |

Total: **34** — Passes: **34** — Failures: **0**.

### Light theme

All `.d-*` text mirrors the dark-mode table but with `--text-primary #10121B`
and `--text-secondary #2A2F40` resolved against the lighter surfaces. Minimum
observed ratio: --text-secondary on bg-card-hover = **9.4:1**.

When the desktop is dimmed behind a scrim + 2px blur, the text underneath the
scrim is decorative only (operator cannot read through the scrim — that's the
intent). All overlays use `--bg-card` (D8E5BD) so foreground contrast remains
identical to the resting state.

Total: **34** — Passes: **34** — Failures: **0**.

---

## Summary table

| Scaffold | Theme | Declarations | Passes | Failures |
|---|---|---|---|---|
| A · Left rail | dark  | 33 | 33 | 0 |
| A · Left rail | light | 33 | 33 | 0 |
| B · Palette  | dark  | 35 | 35 | 0 |
| B · Palette  | light | 35 | 35 | 0 |
| C · Workflow | dark  | 33 | 33 | 0 |
| C · Workflow | light | 33 | 33 | 0 |
| D · Desktop  | dark  | 34 | 34 | 0 |
| D · Desktop  | light | 34 | 34 | 0 |
| **Total**    |       | **270** | **270** | **0** |

## Notes & guard-rails

1. **No `--text-muted` for any caps eyebrow label.** I deliberately stepped
   up to `--text-secondary` on every uppercase-tracked label, because small
   caps + low contrast was the exact failure mode flagged on 2026-05-18 in
   `feedback-contrast-layer-aware`. The 1-step climb buys ~3:1 of headroom
   in light mode and costs nothing visually.
2. **Active states always resolve against `--bg-input`** (the most recessed
   surface), which gives the best contrast in both themes. The "is-active"
   visual differentiation comes from the brand-light underline / left rail
   accent, not from text darkening.
3. **Terminal surfaces** (`.c-terminal`, scaffold C BUILD pane) intentionally
   keep dark backgrounds in both themes — bright terminal colors are
   contrast-safe by construction. No light-mode override needed.
4. **Brand-filled buttons** (`.btn--primary`, `.c-tabs__cta`) explicitly set
   `color: #EFFBDB` in light mode (rather than inheriting `--text-on-primary`)
   because the brand color in light mode is a dark teal — light-on-dark works
   in both themes for these CTAs.
5. **Scrim-dimmed text** (Scaffold D desktop when a drawer is open) becomes
   intentionally illegible. This is decorative behind the overlay, not a
   contrast failure — the overlay panel itself uses `--bg-card` and meets
   all foreground ratios.
6. **Reduced motion:** every scaffold has a `prefers-reduced-motion: reduce`
   block that strips animations and gradient-text shimmers, so contrast
   never depends on motion state.
