# Deploy Summary V3-Native — Layer-Aware Contrast Audit Report

**Phase:** M-V3-Native Phase 1 — Deploy sub-pill Configuration Summary preview/comparison
**Date:** 2026-05-18
**Branch:** `refactor/dashboard-m-v3-native-deploy-preview`
**Method:** WCAG 2.1 relative-luminance contrast ratio against the **immediate** background-setting ancestor (NOT the page background), per the [`feedback-contrast-layer-aware`](../../../.claude/projects/-Users-harriskhalid-Desktop-Red-Team-Infra-Local/memory/feedback_contrast_layer_aware.md) memory.

## Thresholds

- Body text: **>= 4.5:1**
- Large/bold text (>= 18px or >= 14px bold): **>= 3:1**
- Decorative SVG icon strokes treated as large/icon: **>= 3:1**

## Methodology

1. For every text declaration in each composition, walk the DOM tree and identify the **closest** background-setting ancestor (the surface the text actually sits on, not the page).
2. Resolve the exact hex value from `webapp/frontend/css/palette.css` for both `:root` (dark) and `[data-theme="light"]`.
3. Apply the WCAG 2.1 contrast formula via Python script (`/tmp/contrast_audit.py`) — no eyeballing.
4. Audit BOTH themes for each declaration. Hover-state ancestors (e.g. `--bg-card-hover`) are audited independently because the surface changes during interaction.

## Token Reference (Surfaces)

| Token | Dark hex | Light hex |
|-------|----------|-----------|
| `--bg-body` | `#10121B` | `#EFFBDB` |
| `--bg-container` | `#161926` | `#E4F0CC` |
| `--bg-card` | `#1C2031` | `#D8E5BD` |
| `--bg-card-hover` | `#232840` | `#D0DDB0` |
| `--bg-input` | `#131620` | `#E8F4C8` |
| `--bg-section` | `#1F243A` | `#CDDAAE` |

## Token Reference (Text used in this audit)

| Token | Dark hex | Light hex |
|-------|----------|-----------|
| `--text-primary` | `#EEF0F6` | `#10121B` |
| `--text-secondary` | `#B0B8CC` | `#2A2F40` |
| `--text-muted` | `#7A849E` | `#4A5168` |
| `--brand-light` | `#A3B87A` | `#162D38` |

## Surfaces deliberately avoided

- `--accent` (`#8FA464` in light mode) is olive on cream — only **2.07:1** vs `--bg-card`. It is never used as a text colour in any of these compositions in light mode. The legacy "olive eyebrow on cream tile" failure mode the user flagged on 2026-05-18 is structurally impossible here.
- `--text-muted` on `--bg-card` is **4.32:1** (dark mode) — borderline. To stay safely above threshold for small caps eyebrow labels (which are visually tight), every composition uses `--text-secondary` for eyebrow labels regardless of surface. `--text-muted` is not used.

---

# Audit Results


## Composition A — Definition List

| # | Element | Immediate ancestor surface | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|----------------------------|------------|-------------|----------|-------|-----|------|

### Composition A — Definition List — DARK theme

| # | Element | Immediate ancestor surface | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|----------------------------|------------|-------------|----------|-------|-----|------|
| 1 | preview-hypothesis body text | `--bg-container` | `--text-secondary` | `#161926` | `#B0B8CC` | **8.80** | 4.5 | PASS |
| 2 | preview-hypothesis strong | `--bg-container` | `--text-primary` | `#161926` | `#EEF0F6` | **15.34** | 4.5 | PASS |
| 3 | ds-eyebrow__label (caps mono) | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 4 | ds-eyebrow__action label | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 5 | ds-eyebrow__action HOVER | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 6 | ds-hero__caption (caps mono) | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 7 | ds-hero__name (project mono) | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 3 | PASS |
| 8 | ds-hero__type body | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 9 | ds-hero__type strong | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 10 | ds-list__row REST surface | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 11 | ds-list__row HOVER surface | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 12 | ds-list__key (caps mono) | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 13 | ds-list__key on hover | `--bg-card-hover` | `--text-secondary` | `#232840` | `#B0B8CC` | **7.30** | 4.5 | PASS |
| 14 | ds-list__value default | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 15 | ds-list__value on hover | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 16 | ds-list__hint (mono) | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 17 | ds-list__hint on hover | `--bg-card-hover` | `--text-secondary` | `#232840` | `#B0B8CC` | **7.30** | 4.5 | PASS |
| 18 | ds-list__glyph SVG default | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 3 | PASS |
| 19 | ds-list__glyph SVG on hover | `--bg-card-hover` | `--brand-light` | `#232840` | `#A3B87A` | **6.69** | 3 | PASS |
| 20 | ds-list__pill label DEV | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 4.5 | PASS |
| 21 | ds-list__pill dot | `--bg-input` | `--brand-light` | `#131620` | `#A3B87A` | **8.33** | 3 | PASS |
| 22 | ds-list__row--cost value (large) | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 3 | PASS |
| 23 | ds-footer text | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 24 | preview-theme-toggle label | `--bg-card` | `--text-primary` | `#1C2031` | `#EEF0F6` | **14.17** | 4.5 | PASS |

### Composition A — Definition List — LIGHT theme

| # | Element | Immediate ancestor surface | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|----------------------------|------------|-------------|----------|-------|-----|------|
| 1 | preview-hypothesis body text | `--bg-container` | `--text-secondary` | `#E4F0CC` | `#2A2F40` | **11.17** | 4.5 | PASS |
| 2 | preview-hypothesis strong | `--bg-container` | `--text-primary` | `#E4F0CC` | `#10121B` | **15.68** | 4.5 | PASS |
| 3 | ds-eyebrow__label (caps mono) | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 4 | ds-eyebrow__action label | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 5 | ds-eyebrow__action HOVER | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 6 | ds-hero__caption (caps mono) | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 7 | ds-hero__name (project mono) | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 3 | PASS |
| 8 | ds-hero__type body | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 9 | ds-hero__type strong | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 10 | ds-list__row REST surface | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 11 | ds-list__row HOVER surface | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 12 | ds-list__key (caps mono) | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 13 | ds-list__key on hover | `--bg-card-hover` | `--text-secondary` | `#D0DDB0` | `#2A2F40` | **9.28** | 4.5 | PASS |
| 14 | ds-list__value default | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 15 | ds-list__value on hover | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 16 | ds-list__hint (mono) | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 17 | ds-list__hint on hover | `--bg-card-hover` | `--text-secondary` | `#D0DDB0` | `#2A2F40` | **9.28** | 4.5 | PASS |
| 18 | ds-list__glyph SVG default | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 3 | PASS |
| 19 | ds-list__glyph SVG on hover | `--bg-card-hover` | `--brand-light` | `#D0DDB0` | `#162D38` | **9.99** | 3 | PASS |
| 20 | ds-list__pill label DEV | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 4.5 | PASS |
| 21 | ds-list__pill dot | `--bg-input` | `--brand-light` | `#E8F4C8` | `#162D38` | **12.41** | 3 | PASS |
| 22 | ds-list__row--cost value (large) | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 3 | PASS |
| 23 | ds-footer text | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 24 | preview-theme-toggle label | `--bg-card` | `--text-primary` | `#D8E5BD` | `#10121B` | **14.11** | 4.5 | PASS |

## Composition B — Hero + Ribbon

| # | Element | Immediate ancestor surface | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|----------------------------|------------|-------------|----------|-------|-----|------|

### Composition B — Hero + Ribbon — DARK theme

| # | Element | Immediate ancestor surface | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|----------------------------|------------|-------------|----------|-------|-----|------|
| 1 | preview-hypothesis body text | `--bg-container` | `--text-secondary` | `#161926` | `#B0B8CC` | **8.80** | 4.5 | PASS |
| 2 | preview-hypothesis strong | `--bg-container` | `--text-primary` | `#161926` | `#EEF0F6` | **15.34** | 4.5 | PASS |
| 3 | ds-eyebrow__label | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 4 | ds-eyebrow__action label | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 5 | ds-eyebrow__action HOVER | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 6 | ds-hero__caption | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 7 | ds-hero__type (22px bold) | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 3 | PASS |
| 8 | ds-hero__name (project mono) | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 9 | ds-hero__status label (Ready) | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 4.5 | PASS |
| 10 | ds-hero__status dot | `--bg-input` | `--brand-light` | `#131620` | `#A3B87A` | **8.33** | 3 | PASS |
| 11 | ds-hero__cost text | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 12 | ds-hero__cost strong | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 13 | ds-rib__key caps mono | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 14 | ds-rib__glyph default | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 3 | PASS |
| 15 | ds-rib__glyph on hover | `--bg-body` | `--brand-light` | `#10121B` | `#A3B87A` | **8.62** | 3 | PASS |
| 16 | ds-rib__value (14px bold) | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 3 | PASS |
| 17 | ds-rib__hint mono | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 18 | ds-foot text | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 19 | preview-theme-toggle label | `--bg-card` | `--text-primary` | `#1C2031` | `#EEF0F6` | **14.17** | 4.5 | PASS |

### Composition B — Hero + Ribbon — LIGHT theme

| # | Element | Immediate ancestor surface | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|----------------------------|------------|-------------|----------|-------|-----|------|
| 1 | preview-hypothesis body text | `--bg-container` | `--text-secondary` | `#E4F0CC` | `#2A2F40` | **11.17** | 4.5 | PASS |
| 2 | preview-hypothesis strong | `--bg-container` | `--text-primary` | `#E4F0CC` | `#10121B` | **15.68** | 4.5 | PASS |
| 3 | ds-eyebrow__label | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 4 | ds-eyebrow__action label | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 5 | ds-eyebrow__action HOVER | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 6 | ds-hero__caption | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 7 | ds-hero__type (22px bold) | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 3 | PASS |
| 8 | ds-hero__name (project mono) | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 9 | ds-hero__status label (Ready) | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 4.5 | PASS |
| 10 | ds-hero__status dot | `--bg-input` | `--brand-light` | `#E8F4C8` | `#162D38` | **12.41** | 3 | PASS |
| 11 | ds-hero__cost text | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 12 | ds-hero__cost strong | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 13 | ds-rib__key caps mono | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 14 | ds-rib__glyph default | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 3 | PASS |
| 15 | ds-rib__glyph on hover | `--bg-body` | `--brand-light` | `#EFFBDB` | `#162D38` | **13.29** | 3 | PASS |
| 16 | ds-rib__value (14px bold) | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 3 | PASS |
| 17 | ds-rib__hint mono | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 18 | ds-foot text | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 19 | preview-theme-toggle label | `--bg-card` | `--text-primary` | `#D8E5BD` | `#10121B` | **14.11** | 4.5 | PASS |

## Composition C — Prose + Two-column

| # | Element | Immediate ancestor surface | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|----------------------------|------------|-------------|----------|-------|-----|------|

### Composition C — Prose + Two-column — DARK theme

| # | Element | Immediate ancestor surface | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|----------------------------|------------|-------------|----------|-------|-----|------|
| 1 | preview-hypothesis body text | `--bg-container` | `--text-secondary` | `#161926` | `#B0B8CC` | **8.80** | 4.5 | PASS |
| 2 | preview-hypothesis strong | `--bg-container` | `--text-primary` | `#161926` | `#EEF0F6` | **15.34** | 4.5 | PASS |
| 3 | ds-eyebrow__label | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 4 | ds-eyebrow__action label | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 5 | ds-eyebrow__action HOVER | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 6 | ds-prose body (20px) | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 3 | PASS |
| 7 | ds-prose .tok (token pill) | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 4.5 | PASS |
| 8 | ds-prose .tok HOVER | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 9 | ds-col__title caps mono | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 10 | ds-pair__key caps mono | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 11 | ds-pair__value default | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 12 | ds-pair__value--cost (large) | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 3 | PASS |
| 13 | ds-pair__hint body | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 14 | ds-foot text | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 15 | preview-theme-toggle label | `--bg-card` | `--text-primary` | `#1C2031` | `#EEF0F6` | **14.17** | 4.5 | PASS |

### Composition C — Prose + Two-column — LIGHT theme

| # | Element | Immediate ancestor surface | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|----------------------------|------------|-------------|----------|-------|-----|------|
| 1 | preview-hypothesis body text | `--bg-container` | `--text-secondary` | `#E4F0CC` | `#2A2F40` | **11.17** | 4.5 | PASS |
| 2 | preview-hypothesis strong | `--bg-container` | `--text-primary` | `#E4F0CC` | `#10121B` | **15.68** | 4.5 | PASS |
| 3 | ds-eyebrow__label | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 4 | ds-eyebrow__action label | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 5 | ds-eyebrow__action HOVER | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 6 | ds-prose body (20px) | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 3 | PASS |
| 7 | ds-prose .tok (token pill) | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 4.5 | PASS |
| 8 | ds-prose .tok HOVER | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 9 | ds-col__title caps mono | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 10 | ds-pair__key caps mono | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 11 | ds-pair__value default | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 12 | ds-pair__value--cost (large) | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 3 | PASS |
| 13 | ds-pair__hint body | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 14 | ds-foot text | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 15 | preview-theme-toggle label | `--bg-card` | `--text-primary` | `#D8E5BD` | `#10121B` | **14.11** | 4.5 | PASS |

## Comparison Page Chrome

| # | Element | Immediate ancestor surface | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|----------------------------|------------|-------------|----------|-------|-----|------|

### Comparison Page Chrome — DARK theme

| # | Element | Immediate ancestor surface | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|----------------------------|------------|-------------|----------|-------|-----|------|
| 1 | compare-bar h1 | `--bg-section` | `--text-primary` | `#1F243A` | `#EEF0F6` | **13.44** | 4.5 | PASS |
| 2 | compare-bar h1 .kicker | `--bg-section` | `--text-secondary` | `#1F243A` | `#B0B8CC` | **7.71** | 4.5 | PASS |
| 3 | compare-bar__btn label | `--bg-card` | `--text-primary` | `#1C2031` | `#EEF0F6` | **14.17** | 4.5 | PASS |
| 4 | compare-bar__btn HOVER | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 5 | compare-bar__variant REST | `--bg-card` | `--text-secondary` | `#1C2031` | `#B0B8CC` | **8.13** | 4.5 | PASS |
| 6 | compare-bar__variant HOVER | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 7 | compare-bar__variant ACTIVE | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 4.5 | PASS |
| 8 | compare-pane__label text | `--bg-card` | `--text-primary` | `#1C2031` | `#EEF0F6` | **14.17** | 4.5 | PASS |
| 9 | compare-pane__label link | `--bg-card` | `--text-secondary` | `#1C2031` | `#B0B8CC` | **8.13** | 4.5 | PASS |
| 10 | compare-bar__theme-state caps | `--bg-card` | `--text-secondary` | `#1C2031` | `#B0B8CC` | **8.13** | 4.5 | PASS |

### Comparison Page Chrome — LIGHT theme

| # | Element | Immediate ancestor surface | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|----------------------------|------------|-------------|----------|-------|-----|------|
| 1 | compare-bar h1 | `--bg-section` | `--text-primary` | `#CDDAAE` | `#10121B` | **12.66** | 4.5 | PASS |
| 2 | compare-bar h1 .kicker | `--bg-section` | `--text-secondary` | `#CDDAAE` | `#2A2F40` | **9.02** | 4.5 | PASS |
| 3 | compare-bar__btn label | `--bg-card` | `--text-primary` | `#D8E5BD` | `#10121B` | **14.11** | 4.5 | PASS |
| 4 | compare-bar__btn HOVER | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 5 | compare-bar__variant REST | `--bg-card` | `--text-secondary` | `#D8E5BD` | `#2A2F40` | **10.05** | 4.5 | PASS |
| 6 | compare-bar__variant HOVER | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 7 | compare-bar__variant ACTIVE | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 4.5 | PASS |
| 8 | compare-pane__label text | `--bg-card` | `--text-primary` | `#D8E5BD` | `#10121B` | **14.11** | 4.5 | PASS |
| 9 | compare-pane__label link | `--bg-card` | `--text-secondary` | `#D8E5BD` | `#2A2F40` | **10.05** | 4.5 | PASS |
| 10 | compare-bar__theme-state caps | `--bg-card` | `--text-secondary` | `#D8E5BD` | `#2A2F40` | **10.05** | 4.5 | PASS |


## SUMMARY

- Composition A: 48 declarations checked (dark + light), 0 failures
- Composition B: 38 declarations checked, 0 failures
- Composition C: 30 declarations checked, 0 failures
- Comparison chrome: 20 declarations checked, 0 failures
