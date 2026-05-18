# Deploy Journey V3-Native — Layer-Aware Contrast Audit Report

**Phase:** M-V3-Native Phase 1b — "+ New Deployment" journey preview (J1/J2/J3)
**Date:** 2026-05-18
**Branch:** `refactor/dashboard-m-v3-native-deploy-preview`
**Method:** WCAG 2.1 relative-luminance contrast ratio against the **immediate** background-setting ancestor (NOT the page background), per the [`feedback-contrast-layer-aware`](../../../.claude/projects/-Users-harriskhalid-Desktop-Red-Team-Infra-Local/memory/feedback_contrast_layer_aware.md) memory.

## Thresholds

- Body text: **>= 4.5:1**
- Large/bold text (>= 18px or >= 14px bold): **>= 3:1**
- Decorative SVG icon strokes treated as large/icon: **>= 3:1**

## Methodology

1. For every text declaration in each journey preview, walk the DOM tree and identify the **closest** background-setting ancestor (the surface the text actually sits on, not the page).
2. Resolve the exact hex value from `webapp/frontend/css/palette.css` for both `:root` (dark) and `[data-theme="light"]`.
3. Apply the WCAG 2.1 contrast formula via Python script (`/tmp/journey_contrast_audit.py`) — no eyeballing.
4. Audit BOTH themes for each declaration. Hover-state ancestors (e.g. `--bg-card-hover`) are audited independently because the surface changes during interaction. Editor-open states inside J3 are audited against their open-state surface (`--bg-card-hover` since the row brightens during edit).

## Token Reference (Surfaces)

| Token | Dark hex | Light hex |
|-------|----------|-----------|
| `--bg-body` | `#10121B` | `#EFFBDB` |
| `--bg-container` | `#161926` | `#E4F0CC` |
| `--bg-card` | `#1C2031` | `#D8E5BD` |
| `--bg-card-hover` | `#232840` | `#D0DDB0` |
| `--bg-input` | `#131620` | `#E8F4C8` |

## Token Reference (Text used in this audit)

| Token | Dark hex | Light hex |
|-------|----------|-----------|
| `--text-primary` | `#EEF0F6` | `#10121B` |
| `--text-secondary` | `#B0B8CC` | `#2A2F40` |
| `--text-inverse` | `#10121B` | `#EFFBDB` |
| `--brand-light` (surface) | `#A3B87A` | `#162D38` |

## Decisions to keep contrast safe

- **Wizard/journey buttons that sit on `--brand-light` use `--text-inverse`**, not `--text-primary`. In light theme `--brand-light` resolves to `#162D38` (deep teal) so `--text-inverse` (cream `#EFFBDB`) yields 13.29:1.
- **All cards sit directly on `--bg-body`** (not on `--bg-card`). The hairline borders + segmented surface come from the `gap: 1px` + `background: var(--border-subtle)` trick (J1 cards) or explicit `border` (J2/J3). This keeps text-on-surface contrast identical for cards and the surrounding takeover.
- **Editor-open J3 rows brighten to `--bg-card-hover`** while editing; every text declaration inside the inline editor is therefore audited against `--bg-card-hover`, not the rest-state `--bg-body`.
- **Hairline rules use `--border-subtle`**, which is decorative and outside the WCAG text-contrast scope. They are not audited.
- **Light-mode `--text-muted` is never used** in any journey — every secondary text uses `--text-secondary` even on `--bg-card-hover`, where it still measures 7.30:1 (dark) / 9.28:1 (light).

---

# Audit Results

## Summary

| Journey | Theme | Total | Pass | Fail |
|---------|-------|-------|------|------|
| Journey J1 — Linear Wizard | dark | 31 | 31 | 0 |
| Journey J1 — Linear Wizard | light | 31 | 31 | 0 |
| Journey J2 — Progressive Page | dark | 28 | 28 | 0 |
| Journey J2 — Progressive Page | light | 28 | 28 | 0 |
| Journey J3 — Spec List Editor | dark | 40 | 40 | 0 |
| Journey J3 — Spec List Editor | light | 40 | 40 | 0 |
| Hybrid — Wizard + Spec-edit review | dark | 66 | 66 | 0 |
| Hybrid — Wizard + Spec-edit review | light | 66 | 66 | 0 |
| **TOTAL** | — | **330** | **330** | **0** |


# DETAIL


## Journey J1 — Linear Wizard

### Journey J1 — Linear Wizard — DARK theme

| # | Element | Immediate ancestor surface | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|----------------------------|------------|-------------|----------|-------|-----|------|
| 1 | preview-hypothesis body text | `--bg-container` | `--text-secondary` | `#161926` | `#B0B8CC` | **8.80** | 4.5 | PASS |
| 2 | preview-hypothesis strong | `--bg-container` | `--text-primary` | `#161926` | `#EEF0F6` | **15.34** | 4.5 | PASS |
| 3 | dash-trigger label | `--brand-light` | `--text-inverse` | `#A3B87A` | `#10121B` | **8.62** | 4.5 | PASS |
| 4 | wiz-progress dot label rest | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 5 | wiz-progress dot label active | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 6 | wiz-progress__close label | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 7 | wiz-progress__close HOVER | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 8 | wiz-step__eyebrow caps | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 9 | wiz-step__title display | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 3.0 | PASS |
| 10 | wiz-step__lede body | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 11 | wiz-card REST surface (inside hairline border) | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 12 | wiz-card HOVER | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 13 | wiz-card__title rest | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 14 | wiz-card__title hover | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 15 | wiz-card__desc rest | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 16 | wiz-card__desc hover | `--bg-card-hover` | `--text-secondary` | `#232840` | `#B0B8CC` | **7.30** | 4.5 | PASS |
| 17 | wiz-card__hint caps mono rest | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 18 | wiz-card__hint caps mono hover | `--bg-card-hover` | `--text-secondary` | `#232840` | `#B0B8CC` | **7.30** | 4.5 | PASS |
| 19 | wiz-field__label caps | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 20 | wiz-field__input value | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 4.5 | PASS |
| 21 | wiz-field__hint | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 22 | wiz-toggle__title | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 23 | wiz-toggle__desc | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 24 | wiz-foot__crumb caps | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 25 | wiz-btn label rest | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 26 | wiz-btn label HOVER | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 27 | wiz-btn--primary label | `--brand-light` | `--text-inverse` | `#A3B87A` | `#10121B` | **8.62** | 4.5 | PASS |
| 28 | wiz-summary__key caps | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 29 | wiz-summary__value body | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 30 | wiz-summary__hint | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 31 | preview-theme-toggle label | `--bg-card` | `--text-primary` | `#1C2031` | `#EEF0F6` | **14.17** | 4.5 | PASS |

### Journey J1 — Linear Wizard — LIGHT theme

| # | Element | Immediate ancestor surface | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|----------------------------|------------|-------------|----------|-------|-----|------|
| 1 | preview-hypothesis body text | `--bg-container` | `--text-secondary` | `#E4F0CC` | `#2A2F40` | **11.17** | 4.5 | PASS |
| 2 | preview-hypothesis strong | `--bg-container` | `--text-primary` | `#E4F0CC` | `#10121B` | **15.68** | 4.5 | PASS |
| 3 | dash-trigger label | `--brand-light` | `--text-inverse` | `#162D38` | `#EFFBDB` | **13.29** | 4.5 | PASS |
| 4 | wiz-progress dot label rest | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 5 | wiz-progress dot label active | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 6 | wiz-progress__close label | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 7 | wiz-progress__close HOVER | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 8 | wiz-step__eyebrow caps | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 9 | wiz-step__title display | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 3.0 | PASS |
| 10 | wiz-step__lede body | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 11 | wiz-card REST surface (inside hairline border) | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 12 | wiz-card HOVER | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 13 | wiz-card__title rest | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 14 | wiz-card__title hover | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 15 | wiz-card__desc rest | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 16 | wiz-card__desc hover | `--bg-card-hover` | `--text-secondary` | `#D0DDB0` | `#2A2F40` | **9.28** | 4.5 | PASS |
| 17 | wiz-card__hint caps mono rest | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 18 | wiz-card__hint caps mono hover | `--bg-card-hover` | `--text-secondary` | `#D0DDB0` | `#2A2F40` | **9.28** | 4.5 | PASS |
| 19 | wiz-field__label caps | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 20 | wiz-field__input value | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 4.5 | PASS |
| 21 | wiz-field__hint | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 22 | wiz-toggle__title | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 23 | wiz-toggle__desc | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 24 | wiz-foot__crumb caps | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 25 | wiz-btn label rest | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 26 | wiz-btn label HOVER | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 27 | wiz-btn--primary label | `--brand-light` | `--text-inverse` | `#162D38` | `#EFFBDB` | **13.29** | 4.5 | PASS |
| 28 | wiz-summary__key caps | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 29 | wiz-summary__value body | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 30 | wiz-summary__hint | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 31 | preview-theme-toggle label | `--bg-card` | `--text-primary` | `#D8E5BD` | `#10121B` | **14.11** | 4.5 | PASS |


## Journey J2 — Progressive Page

### Journey J2 — Progressive Page — DARK theme

| # | Element | Immediate ancestor surface | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|----------------------------|------------|-------------|----------|-------|-----|------|
| 1 | preview-hypothesis body text | `--bg-container` | `--text-secondary` | `#161926` | `#B0B8CC` | **8.80** | 4.5 | PASS |
| 2 | preview-hypothesis strong | `--bg-container` | `--text-primary` | `#161926` | `#EEF0F6` | **15.34** | 4.5 | PASS |
| 3 | dash-trigger label | `--brand-light` | `--text-inverse` | `#A3B87A` | `#10121B` | **8.62** | 4.5 | PASS |
| 4 | j-header__eyebrow caps | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 5 | j-header__close label | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 6 | j-header__close HOVER | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 7 | j-hero__caption caps | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 8 | j-hero__title display | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 3.0 | PASS |
| 9 | j-hero__lede body | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 10 | j-section__eyebrow caps | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 11 | j-section__check caps | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 12 | j-card REST inside hairline border | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 13 | j-card HOVER | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 14 | j-card__title rest | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 15 | j-card__title hover/checked | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 16 | j-card__desc rest | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 17 | j-card__desc hover/checked | `--bg-card-hover` | `--text-secondary` | `#232840` | `#B0B8CC` | **7.30** | 4.5 | PASS |
| 18 | j-row__key caps mono | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 19 | j-input value mono | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 4.5 | PASS |
| 20 | j-select value mono | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 4.5 | PASS |
| 21 | j-seg__btn REST | `--bg-input` | `--text-secondary` | `#131620` | `#B0B8CC` | **9.09** | 4.5 | PASS |
| 22 | j-seg__btn HOVER | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 23 | j-seg__btn ACTIVE | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 24 | j-toggle__title | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 25 | j-toggle__desc | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 26 | j-foot__crumb caps | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 27 | j-btn label | `--brand-light` | `--text-inverse` | `#A3B87A` | `#10121B` | **8.62** | 4.5 | PASS |
| 28 | preview-theme-toggle label | `--bg-card` | `--text-primary` | `#1C2031` | `#EEF0F6` | **14.17** | 4.5 | PASS |

### Journey J2 — Progressive Page — LIGHT theme

| # | Element | Immediate ancestor surface | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|----------------------------|------------|-------------|----------|-------|-----|------|
| 1 | preview-hypothesis body text | `--bg-container` | `--text-secondary` | `#E4F0CC` | `#2A2F40` | **11.17** | 4.5 | PASS |
| 2 | preview-hypothesis strong | `--bg-container` | `--text-primary` | `#E4F0CC` | `#10121B` | **15.68** | 4.5 | PASS |
| 3 | dash-trigger label | `--brand-light` | `--text-inverse` | `#162D38` | `#EFFBDB` | **13.29** | 4.5 | PASS |
| 4 | j-header__eyebrow caps | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 5 | j-header__close label | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 6 | j-header__close HOVER | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 7 | j-hero__caption caps | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 8 | j-hero__title display | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 3.0 | PASS |
| 9 | j-hero__lede body | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 10 | j-section__eyebrow caps | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 11 | j-section__check caps | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 12 | j-card REST inside hairline border | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 13 | j-card HOVER | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 14 | j-card__title rest | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 15 | j-card__title hover/checked | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 16 | j-card__desc rest | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 17 | j-card__desc hover/checked | `--bg-card-hover` | `--text-secondary` | `#D0DDB0` | `#2A2F40` | **9.28** | 4.5 | PASS |
| 18 | j-row__key caps mono | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 19 | j-input value mono | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 4.5 | PASS |
| 20 | j-select value mono | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 4.5 | PASS |
| 21 | j-seg__btn REST | `--bg-input` | `--text-secondary` | `#E8F4C8` | `#2A2F40` | **11.53** | 4.5 | PASS |
| 22 | j-seg__btn HOVER | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 23 | j-seg__btn ACTIVE | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 24 | j-toggle__title | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 25 | j-toggle__desc | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 26 | j-foot__crumb caps | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 27 | j-btn label | `--brand-light` | `--text-inverse` | `#162D38` | `#EFFBDB` | **13.29** | 4.5 | PASS |
| 28 | preview-theme-toggle label | `--bg-card` | `--text-primary` | `#D8E5BD` | `#10121B` | **14.11** | 4.5 | PASS |


## Journey J3 — Spec List Editor

### Journey J3 — Spec List Editor — DARK theme

| # | Element | Immediate ancestor surface | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|----------------------------|------------|-------------|----------|-------|-----|------|
| 1 | preview-hypothesis body text | `--bg-container` | `--text-secondary` | `#161926` | `#B0B8CC` | **8.80** | 4.5 | PASS |
| 2 | preview-hypothesis strong | `--bg-container` | `--text-primary` | `#161926` | `#EEF0F6` | **15.34** | 4.5 | PASS |
| 3 | dash-trigger label | `--brand-light` | `--text-inverse` | `#A3B87A` | `#10121B` | **8.62** | 4.5 | PASS |
| 4 | ds-eyebrow__label caps mono | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 5 | ds-eyebrow__close label | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 6 | ds-eyebrow__close HOVER | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 7 | ds-hero__caption caps | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 8 | ds-hero__name display mono | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 3.0 | PASS |
| 9 | ds-hero__type body | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 10 | ds-hero__type strong | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 11 | ds-row__head REST surface | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 12 | ds-key caps mono REST | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 13 | ds-value REST body | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 14 | ds-hint mono REST | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 15 | ds-row__head HOVER | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 16 | ds-key on hover | `--bg-card-hover` | `--text-secondary` | `#232840` | `#B0B8CC` | **7.30** | 4.5 | PASS |
| 17 | ds-value on hover | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 18 | ds-hint on hover | `--bg-card-hover` | `--text-secondary` | `#232840` | `#B0B8CC` | **7.30** | 4.5 | PASS |
| 19 | ds-row__edit SVG REST | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 3.0 | PASS |
| 20 | ds-row__edit SVG HOVER (bg-input chip) | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 3.0 | PASS |
| 21 | ds-pill DEV label | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 4.5 | PASS |
| 22 | ds-edit__label caps mono | `--bg-card-hover` | `--text-secondary` | `#232840` | `#B0B8CC` | **7.30** | 4.5 | PASS |
| 23 | ds-edit__input value | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 4.5 | PASS |
| 24 | ds-edit__hint | `--bg-card-hover` | `--text-secondary` | `#232840` | `#B0B8CC` | **7.30** | 4.5 | PASS |
| 25 | ds-type-group caps | `--bg-card-hover` | `--text-secondary` | `#232840` | `#B0B8CC` | **7.30** | 4.5 | PASS |
| 26 | ds-type-card REST | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 27 | ds-type-card HOVER/CHECKED | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 28 | ds-type-card__title rest | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 29 | ds-type-card__title hover | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 30 | ds-type-card__hint caps mono rest | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 31 | ds-type-card__hint caps mono hover | `--bg-card-hover` | `--text-secondary` | `#232840` | `#B0B8CC` | **7.30** | 4.5 | PASS |
| 32 | ds-seg__btn REST | `--bg-input` | `--text-secondary` | `#131620` | `#B0B8CC` | **9.09** | 4.5 | PASS |
| 33 | ds-seg__btn ACTIVE | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 34 | ds-pill-btn label | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 4.5 | PASS |
| 35 | ds-edit__btn label REST | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 36 | ds-edit__btn HOVER | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 37 | ds-edit__btn--save label | `--brand-light` | `--text-inverse` | `#A3B87A` | `#10121B` | **8.62** | 4.5 | PASS |
| 38 | ds-foot__crumb | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 39 | ds-foot__deploy label | `--brand-light` | `--text-inverse` | `#A3B87A` | `#10121B` | **8.62** | 4.5 | PASS |
| 40 | preview-theme-toggle label | `--bg-card` | `--text-primary` | `#1C2031` | `#EEF0F6` | **14.17** | 4.5 | PASS |

### Journey J3 — Spec List Editor — LIGHT theme

| # | Element | Immediate ancestor surface | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|----------------------------|------------|-------------|----------|-------|-----|------|
| 1 | preview-hypothesis body text | `--bg-container` | `--text-secondary` | `#E4F0CC` | `#2A2F40` | **11.17** | 4.5 | PASS |
| 2 | preview-hypothesis strong | `--bg-container` | `--text-primary` | `#E4F0CC` | `#10121B` | **15.68** | 4.5 | PASS |
| 3 | dash-trigger label | `--brand-light` | `--text-inverse` | `#162D38` | `#EFFBDB` | **13.29** | 4.5 | PASS |
| 4 | ds-eyebrow__label caps mono | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 5 | ds-eyebrow__close label | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 6 | ds-eyebrow__close HOVER | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 7 | ds-hero__caption caps | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 8 | ds-hero__name display mono | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 3.0 | PASS |
| 9 | ds-hero__type body | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 10 | ds-hero__type strong | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 11 | ds-row__head REST surface | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 12 | ds-key caps mono REST | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 13 | ds-value REST body | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 14 | ds-hint mono REST | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 15 | ds-row__head HOVER | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 16 | ds-key on hover | `--bg-card-hover` | `--text-secondary` | `#D0DDB0` | `#2A2F40` | **9.28** | 4.5 | PASS |
| 17 | ds-value on hover | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 18 | ds-hint on hover | `--bg-card-hover` | `--text-secondary` | `#D0DDB0` | `#2A2F40` | **9.28** | 4.5 | PASS |
| 19 | ds-row__edit SVG REST | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 3.0 | PASS |
| 20 | ds-row__edit SVG HOVER (bg-input chip) | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 3.0 | PASS |
| 21 | ds-pill DEV label | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 4.5 | PASS |
| 22 | ds-edit__label caps mono | `--bg-card-hover` | `--text-secondary` | `#D0DDB0` | `#2A2F40` | **9.28** | 4.5 | PASS |
| 23 | ds-edit__input value | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 4.5 | PASS |
| 24 | ds-edit__hint | `--bg-card-hover` | `--text-secondary` | `#D0DDB0` | `#2A2F40` | **9.28** | 4.5 | PASS |
| 25 | ds-type-group caps | `--bg-card-hover` | `--text-secondary` | `#D0DDB0` | `#2A2F40` | **9.28** | 4.5 | PASS |
| 26 | ds-type-card REST | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 27 | ds-type-card HOVER/CHECKED | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 28 | ds-type-card__title rest | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 29 | ds-type-card__title hover | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 30 | ds-type-card__hint caps mono rest | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 31 | ds-type-card__hint caps mono hover | `--bg-card-hover` | `--text-secondary` | `#D0DDB0` | `#2A2F40` | **9.28** | 4.5 | PASS |
| 32 | ds-seg__btn REST | `--bg-input` | `--text-secondary` | `#E8F4C8` | `#2A2F40` | **11.53** | 4.5 | PASS |
| 33 | ds-seg__btn ACTIVE | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 34 | ds-pill-btn label | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 4.5 | PASS |
| 35 | ds-edit__btn label REST | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 36 | ds-edit__btn HOVER | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 37 | ds-edit__btn--save label | `--brand-light` | `--text-inverse` | `#162D38` | `#EFFBDB` | **13.29** | 4.5 | PASS |
| 38 | ds-foot__crumb | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 39 | ds-foot__deploy label | `--brand-light` | `--text-inverse` | `#162D38` | `#EFFBDB` | **13.29** | 4.5 | PASS |
| 40 | preview-theme-toggle label | `--bg-card` | `--text-primary` | `#D8E5BD` | `#10121B` | **14.11** | 4.5 | PASS |



## Hybrid — Wizard + Spec-edit Review

This is the Phase 1c winner: J1 wizard for steps 1-4 (verbatim), J3 spec-edit shape for the review surface. Every wizard text declaration is identical to J1; every review text declaration is identical to J3. Two declarations are new and unique to the hybrid: the "From wizard" breadcrumb chip (text sits on `--bg-input`) and the review-foot secondary Cancel button (text sits on `--bg-body`). Both are explicitly audited below.

### Journey Hybrid — Wizard + Spec-edit Review — DARK theme

| # | Element | Immediate ancestor surface | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|----------------------------|------------|-------------|----------|-------|-----|------|
| 1 | preview-hypothesis body text | `--bg-container` | `--text-secondary` | `#161926` | `#B0B8CC` | **8.80** | 4.5 | PASS |
| 2 | preview-hypothesis strong | `--bg-container` | `--text-primary` | `#161926` | `#EEF0F6` | **15.34** | 4.5 | PASS |
| 3 | dash-trigger label | `--brand-light` | `--text-inverse` | `#A3B87A` | `#10121B` | **8.62** | 4.5 | PASS |
| 4 | wiz-progress dot label REST | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 5 | wiz-progress dot label ACTIVE | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 6 | wiz-progress__close label REST | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 7 | wiz-progress__close HOVER | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 8 | wiz-step__eyebrow caps | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 9 | wiz-step__title display | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 3.0 | PASS |
| 10 | wiz-step__lede body | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 11 | wiz-card REST | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 12 | wiz-card HOVER/CHECKED | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 13 | wiz-card__title REST | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 14 | wiz-card__title HOVER/CHECKED | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 15 | wiz-card__desc REST | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 16 | wiz-card__desc HOVER/CHECKED | `--bg-card-hover` | `--text-secondary` | `#232840` | `#B0B8CC` | **7.30** | 4.5 | PASS |
| 17 | wiz-card__hint caps mono REST | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 18 | wiz-card__hint caps mono HOVER | `--bg-card-hover` | `--text-secondary` | `#232840` | `#B0B8CC` | **7.30** | 4.5 | PASS |
| 19 | wiz-field__label caps | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 20 | wiz-field__input value | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 4.5 | PASS |
| 21 | wiz-field__hint | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 22 | wiz-foot__crumb caps | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 23 | wiz-btn label REST | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 24 | wiz-btn label HOVER | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 25 | wiz-btn--primary label | `--brand-light` | `--text-inverse` | `#A3B87A` | `#10121B` | **8.62** | 4.5 | PASS |
| 26 | ds-eyebrow__label caps mono | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 27 | ds-eyebrow__close label | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 28 | ds-eyebrow__close HOVER | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 29 | review-breadcrumb body (new) | `--bg-input` | `--text-secondary` | `#131620` | `#B0B8CC` | **9.09** | 4.5 | PASS |
| 30 | review-breadcrumb__link (new) | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 4.5 | PASS |
| 31 | ds-hero__caption caps | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 32 | ds-hero__name display mono | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 3.0 | PASS |
| 33 | ds-hero__type body | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 34 | ds-hero__type strong | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 35 | ds-row__head REST surface | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 36 | ds-key caps mono REST | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 37 | ds-value REST body | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 38 | ds-hint mono REST | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 39 | ds-row__head HOVER | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 40 | ds-key on hover | `--bg-card-hover` | `--text-secondary` | `#232840` | `#B0B8CC` | **7.30** | 4.5 | PASS |
| 41 | ds-value on hover | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 42 | ds-hint on hover | `--bg-card-hover` | `--text-secondary` | `#232840` | `#B0B8CC` | **7.30** | 4.5 | PASS |
| 43 | ds-row__edit SVG REST (icon) | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 3.0 | PASS |
| 44 | ds-row__edit SVG HOVER (bg-input chip) | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 3.0 | PASS |
| 45 | ds-pill DEV label | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 4.5 | PASS |
| 46 | ds-edit__label caps mono | `--bg-card-hover` | `--text-secondary` | `#232840` | `#B0B8CC` | **7.30** | 4.5 | PASS |
| 47 | ds-edit__input value | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 4.5 | PASS |
| 48 | ds-edit__hint | `--bg-card-hover` | `--text-secondary` | `#232840` | `#B0B8CC` | **7.30** | 4.5 | PASS |
| 49 | ds-type-group caps | `--bg-card-hover` | `--text-secondary` | `#232840` | `#B0B8CC` | **7.30** | 4.5 | PASS |
| 50 | ds-type-card REST | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 51 | ds-type-card HOVER/CHECKED | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 52 | ds-type-card__title REST | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 53 | ds-type-card__title HOVER | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 54 | ds-type-card__hint caps REST | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 55 | ds-type-card__hint caps HOVER | `--bg-card-hover` | `--text-secondary` | `#232840` | `#B0B8CC` | **7.30** | 4.5 | PASS |
| 56 | ds-seg__btn REST | `--bg-input` | `--text-secondary` | `#131620` | `#B0B8CC` | **9.09** | 4.5 | PASS |
| 57 | ds-seg__btn ACTIVE | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 58 | ds-pill-btn label | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 4.5 | PASS |
| 59 | ds-edit__btn label REST | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 60 | ds-edit__btn HOVER | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 61 | ds-edit__btn--save label | `--brand-light` | `--text-inverse` | `#A3B87A` | `#10121B` | **8.62** | 4.5 | PASS |
| 62 | ds-foot__crumb | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 63 | ds-foot__cancel label REST (new) | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 64 | ds-foot__cancel HOVER (new) | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 65 | ds-foot__deploy label | `--brand-light` | `--text-inverse` | `#A3B87A` | `#10121B` | **8.62** | 4.5 | PASS |
| 66 | preview-theme-toggle label | `--bg-card` | `--text-primary` | `#1C2031` | `#EEF0F6` | **14.17** | 4.5 | PASS |

### Journey Hybrid — Wizard + Spec-edit Review — LIGHT theme

| # | Element | Immediate ancestor surface | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|----------------------------|------------|-------------|----------|-------|-----|------|
| 1 | preview-hypothesis body text | `--bg-container` | `--text-secondary` | `#E4F0CC` | `#2A2F40` | **11.17** | 4.5 | PASS |
| 2 | preview-hypothesis strong | `--bg-container` | `--text-primary` | `#E4F0CC` | `#10121B` | **15.68** | 4.5 | PASS |
| 3 | dash-trigger label | `--brand-light` | `--text-inverse` | `#162D38` | `#EFFBDB` | **13.29** | 4.5 | PASS |
| 4 | wiz-progress dot label REST | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 5 | wiz-progress dot label ACTIVE | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 6 | wiz-progress__close label REST | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 7 | wiz-progress__close HOVER | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 8 | wiz-step__eyebrow caps | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 9 | wiz-step__title display | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 3.0 | PASS |
| 10 | wiz-step__lede body | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 11 | wiz-card REST | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 12 | wiz-card HOVER/CHECKED | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 13 | wiz-card__title REST | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 14 | wiz-card__title HOVER/CHECKED | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 15 | wiz-card__desc REST | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 16 | wiz-card__desc HOVER/CHECKED | `--bg-card-hover` | `--text-secondary` | `#D0DDB0` | `#2A2F40` | **9.28** | 4.5 | PASS |
| 17 | wiz-card__hint caps mono REST | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 18 | wiz-card__hint caps mono HOVER | `--bg-card-hover` | `--text-secondary` | `#D0DDB0` | `#2A2F40` | **9.28** | 4.5 | PASS |
| 19 | wiz-field__label caps | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 20 | wiz-field__input value | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 4.5 | PASS |
| 21 | wiz-field__hint | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 22 | wiz-foot__crumb caps | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 23 | wiz-btn label REST | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 24 | wiz-btn label HOVER | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 25 | wiz-btn--primary label | `--brand-light` | `--text-inverse` | `#162D38` | `#EFFBDB` | **13.29** | 4.5 | PASS |
| 26 | ds-eyebrow__label caps mono | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 27 | ds-eyebrow__close label | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 28 | ds-eyebrow__close HOVER | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 29 | review-breadcrumb body (new) | `--bg-input` | `--text-secondary` | `#E8F4C8` | `#2A2F40` | **11.53** | 4.5 | PASS |
| 30 | review-breadcrumb__link (new) | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 4.5 | PASS |
| 31 | ds-hero__caption caps | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 32 | ds-hero__name display mono | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 3.0 | PASS |
| 33 | ds-hero__type body | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 34 | ds-hero__type strong | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 35 | ds-row__head REST surface | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 36 | ds-key caps mono REST | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 37 | ds-value REST body | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 38 | ds-hint mono REST | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 39 | ds-row__head HOVER | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 40 | ds-key on hover | `--bg-card-hover` | `--text-secondary` | `#D0DDB0` | `#2A2F40` | **9.28** | 4.5 | PASS |
| 41 | ds-value on hover | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 42 | ds-hint on hover | `--bg-card-hover` | `--text-secondary` | `#D0DDB0` | `#2A2F40` | **9.28** | 4.5 | PASS |
| 43 | ds-row__edit SVG REST (icon) | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 3.0 | PASS |
| 44 | ds-row__edit SVG HOVER (bg-input chip) | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 3.0 | PASS |
| 45 | ds-pill DEV label | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 4.5 | PASS |
| 46 | ds-edit__label caps mono | `--bg-card-hover` | `--text-secondary` | `#D0DDB0` | `#2A2F40` | **9.28** | 4.5 | PASS |
| 47 | ds-edit__input value | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 4.5 | PASS |
| 48 | ds-edit__hint | `--bg-card-hover` | `--text-secondary` | `#D0DDB0` | `#2A2F40` | **9.28** | 4.5 | PASS |
| 49 | ds-type-group caps | `--bg-card-hover` | `--text-secondary` | `#D0DDB0` | `#2A2F40` | **9.28** | 4.5 | PASS |
| 50 | ds-type-card REST | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 51 | ds-type-card HOVER/CHECKED | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 52 | ds-type-card__title REST | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 53 | ds-type-card__title HOVER | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 54 | ds-type-card__hint caps REST | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 55 | ds-type-card__hint caps HOVER | `--bg-card-hover` | `--text-secondary` | `#D0DDB0` | `#2A2F40` | **9.28** | 4.5 | PASS |
| 56 | ds-seg__btn REST | `--bg-input` | `--text-secondary` | `#E8F4C8` | `#2A2F40` | **11.53** | 4.5 | PASS |
| 57 | ds-seg__btn ACTIVE | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 58 | ds-pill-btn label | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 4.5 | PASS |
| 59 | ds-edit__btn label REST | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 60 | ds-edit__btn HOVER | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 61 | ds-edit__btn--save label | `--brand-light` | `--text-inverse` | `#162D38` | `#EFFBDB` | **13.29** | 4.5 | PASS |
| 62 | ds-foot__crumb | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 63 | ds-foot__cancel label REST (new) | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 64 | ds-foot__cancel HOVER (new) | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 65 | ds-foot__deploy label | `--brand-light` | `--text-inverse` | `#162D38` | `#EFFBDB` | **13.29** | 4.5 | PASS |
| 66 | preview-theme-toggle label | `--bg-card` | `--text-primary` | `#D8E5BD` | `#10121B` | **14.11** | 4.5 | PASS |
