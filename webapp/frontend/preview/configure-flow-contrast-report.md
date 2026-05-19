# Configure Flow Redesign — Layer-Aware Contrast Audit Report

**Round:** Configure flow redesign (3 structurally distinct shapes)
**Date:** 2026-05-19
**Branch:** `feature/v3-production-rollout`
**Method:** WCAG 2.1 relative-luminance contrast ratio against the **immediate** background-setting ancestor (NOT the page background), per the [`feedback-contrast-layer-aware`](../../../.claude/projects/-Users-harriskhalid-Desktop-Red-Team-Infra-Local/memory/feedback_contrast_layer_aware.md) memory.

## Shapes audited

| Shape | File | Hypothesis |
|-------|------|------------|
| A · Branched wizard | `configure-flow-a-branched-wizard.html` | Multi-step wizard; step count + content branches by deployment type. SSH key surfaces as step 3. Final step is the J3 spec-list review. |
| B · Smart single-page form | `configure-flow-b-smart-form.html` | One scrolling page with sections that auto-expand based on type. Every required field has a smart default — save never fails on missing data. |
| C · Document editor | `configure-flow-c-document.html` | The deployment reads as prose. Each token is a clickable inline edit with a popover. Auto-saves on commit. |

## Thresholds

- Body text: **>= 4.5:1**
- Large/bold text (>= 18px or >= 14px bold) and badge text: **>= 3:1**

## Methodology

1. For every text declaration in each shape's preview, walk the DOM tree and identify the **closest** background-setting ancestor (the surface the text actually sits on, not the page).
2. Resolve the exact hex value from `webapp/frontend/css/palette.css` for both `:root` (dark) and `[data-theme="light"]`.
3. Apply the WCAG 2.1 contrast formula via Python script (`/tmp/configure_contrast_audit.py`) — no eyeballing.
4. Audit BOTH themes for each declaration. Hover-state ancestors (e.g. `--bg-card-hover`) are audited independently because the surface changes during interaction. Open-state surfaces (token open in Shape C, spec-row hover in Shape A review) are audited against their open-state surface.

## Token Reference (Surfaces)

| Token | Dark hex | Light hex |
|-------|----------|-----------|
| `--bg-body` | `#10121B` | `#EFFBDB` |
| `--bg-container` | `#161926` | `#E4F0CC` |
| `--bg-card` | `#1C2031` | `#D8E5BD` |
| `--bg-card-hover` | `#232840` | `#D0DDB0` |
| `--bg-elevated` | `#292F4A` | `#C2D09F` |
| `--bg-input` | `#131620` | `#E8F4C8` |
| `--success-bg` | `#142218` | `#D8F0DC` |
| `--danger-bg` | `#241416` | `#F8DCDA` |

## Token Reference (Text)

| Token | Dark hex | Light hex |
|-------|----------|-----------|
| `--text-primary` | `#EEF0F6` | `#10121B` |
| `--text-secondary` | `#B0B8CC` | `#2A2F40` |
| `--text-inverse` | `#10121B` | `#EFFBDB` |
| `--brand-light` (text) | `#A3B87A` | `#162D38` |
| `--success-text` | `#7ECF8C` | `#1A5A26` |
| `--danger-text` | `#F08A84` | `#8A1A16` |

## Decisions to keep contrast safe

- **All buttons that sit on `--brand-light` use `--text-inverse`**, not `--text-primary`. In light mode `--brand-light` resolves to `#162D38` (deep teal) so `--text-inverse` (cream `#EFFBDB`) yields 13.29:1.
- **Popovers (Shape C) sit on `--bg-elevated`**. All popover text declarations audited against `--bg-elevated` (`#292F4A` dark / `#C2D09F` light). `--text-muted` would fail here in light mode — every secondary text uses `--text-secondary` instead, which clears 6.61:1 dark / 8.12:1 light.
- **Section badges (Shape B)** use the dedicated semantic-state surface tokens: `--success-bg` paired with `--success-text` (8.80:1 dark / 6.87:1 light), and `--brand-light` foreground on `--bg-card` background (7.46:1 dark / 10.82:1 light).
- **Hairline rules use `--border-subtle`**, which is decorative and outside the WCAG text-contrast scope. They are not audited.
- **No `--text-muted` is used** in any of the 3 shapes — every secondary text token resolves to `--text-secondary` to keep ratios safely above 4.5:1 on every layer.
- **Tokens (Shape C) sit on `--bg-input`** when in rest state, and shift to `--bg-card-hover` when hovered/open — both surfaces audited independently. The required-empty modifier uses `--danger-bg` background, with text staying on `--text-primary` (15.53:1 dark / 14.44:1 light).

---

# Audit Results

## Summary


| Shape | Theme | Total | Pass | Fail |
|-------|-------|-------|------|------|
| A · Branched wizard | dark | 34 | 34 | 0 |
| A · Branched wizard | light | 34 | 34 | 0 |
| B · Smart form | dark | 33 | 33 | 0 |
| B · Smart form | light | 33 | 33 | 0 |
| C · Document editor | dark | 26 | 26 | 0 |
| C · Document editor | light | 26 | 26 | 0 |
| **TOTAL** | — | 186 | **186** | **0** |


# DETAIL

## A · Branched wizard
### A · Branched wizard — DARK theme
| # | Element | Surface token | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|---------------|------------|-------------|----------|-------|-----|------|
| 1 | hypothesis body | `--bg-container` | `--text-secondary` | `#161926` | `#B0B8CC` | **8.80** | 4.5 | PASS |
| 2 | hypothesis strong | `--bg-container` | `--text-primary` | `#161926` | `#EEF0F6` | **15.34** | 4.5 | PASS |
| 3 | theme toggle btn | `--bg-card` | `--text-primary` | `#1C2031` | `#EEF0F6` | **14.17** | 4.5 | PASS |
| 4 | wiz-eyebrow label | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 5 | wiz-eyebrow counter num | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 6 | wiz-eyebrow counter rest | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 7 | progress dot rest | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 8 | progress dot active | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 9 | progress dot done | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 10 | step caption | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 11 | step title | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 3.0 | PASS |
| 12 | step hint | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 13 | wiz-tile meta | `--bg-card` | `--text-secondary` | `#1C2031` | `#B0B8CC` | **8.13** | 4.5 | PASS |
| 14 | wiz-tile name | `--bg-card` | `--text-primary` | `#1C2031` | `#EEF0F6` | **14.17** | 4.5 | PASS |
| 15 | wiz-tile desc | `--bg-card` | `--text-secondary` | `#1C2031` | `#B0B8CC` | **8.13** | 4.5 | PASS |
| 16 | wiz-tile hover meta | `--bg-card-hover` | `--text-secondary` | `#232840` | `#B0B8CC` | **7.30** | 4.5 | PASS |
| 17 | wiz-tile active name | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 18 | field label | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 19 | field hint | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 20 | input value | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 4.5 | PASS |
| 21 | radiocard name | `--bg-card` | `--text-primary` | `#1C2031` | `#EEF0F6` | **14.17** | 4.5 | PASS |
| 22 | radiocard desc | `--bg-card` | `--text-secondary` | `#1C2031` | `#B0B8CC` | **8.13** | 4.5 | PASS |
| 23 | radiocard active name | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 24 | radiocard active desc | `--bg-card-hover` | `--text-secondary` | `#232840` | `#B0B8CC` | **7.30** | 4.5 | PASS |
| 25 | review row key | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 26 | review row value | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 27 | review row hint | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 28 | review row hover value | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 29 | review row hover hint | `--bg-card-hover` | `--text-secondary` | `#232840` | `#B0B8CC` | **7.30** | 4.5 | PASS |
| 30 | review pill text | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 4.5 | PASS |
| 31 | wiz-btn (ghost) | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 32 | wiz-btn primary | `--brand-light` | `--text-inverse` | `#A3B87A` | `#10121B` | **8.62** | 4.5 | PASS |
| 33 | branch hint | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 34 | toast text | `--bg-elevated` | `--text-primary` | `#292F4A` | `#EEF0F6` | **11.52** | 4.5 | PASS |

### A · Branched wizard — LIGHT theme
| # | Element | Surface token | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|---------------|------------|-------------|----------|-------|-----|------|
| 1 | hypothesis body | `--bg-container` | `--text-secondary` | `#E4F0CC` | `#2A2F40` | **11.17** | 4.5 | PASS |
| 2 | hypothesis strong | `--bg-container` | `--text-primary` | `#E4F0CC` | `#10121B` | **15.68** | 4.5 | PASS |
| 3 | theme toggle btn | `--bg-card` | `--text-primary` | `#D8E5BD` | `#10121B` | **14.11** | 4.5 | PASS |
| 4 | wiz-eyebrow label | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 5 | wiz-eyebrow counter num | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 6 | wiz-eyebrow counter rest | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 7 | progress dot rest | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 8 | progress dot active | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 9 | progress dot done | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 10 | step caption | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 11 | step title | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 3.0 | PASS |
| 12 | step hint | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 13 | wiz-tile meta | `--bg-card` | `--text-secondary` | `#D8E5BD` | `#2A2F40` | **10.05** | 4.5 | PASS |
| 14 | wiz-tile name | `--bg-card` | `--text-primary` | `#D8E5BD` | `#10121B` | **14.11** | 4.5 | PASS |
| 15 | wiz-tile desc | `--bg-card` | `--text-secondary` | `#D8E5BD` | `#2A2F40` | **10.05** | 4.5 | PASS |
| 16 | wiz-tile hover meta | `--bg-card-hover` | `--text-secondary` | `#D0DDB0` | `#2A2F40` | **9.28** | 4.5 | PASS |
| 17 | wiz-tile active name | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 18 | field label | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 19 | field hint | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 20 | input value | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 4.5 | PASS |
| 21 | radiocard name | `--bg-card` | `--text-primary` | `#D8E5BD` | `#10121B` | **14.11** | 4.5 | PASS |
| 22 | radiocard desc | `--bg-card` | `--text-secondary` | `#D8E5BD` | `#2A2F40` | **10.05** | 4.5 | PASS |
| 23 | radiocard active name | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 24 | radiocard active desc | `--bg-card-hover` | `--text-secondary` | `#D0DDB0` | `#2A2F40` | **9.28** | 4.5 | PASS |
| 25 | review row key | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 26 | review row value | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 27 | review row hint | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 28 | review row hover value | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 29 | review row hover hint | `--bg-card-hover` | `--text-secondary` | `#D0DDB0` | `#2A2F40` | **9.28** | 4.5 | PASS |
| 30 | review pill text | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 4.5 | PASS |
| 31 | wiz-btn (ghost) | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 32 | wiz-btn primary | `--brand-light` | `--text-inverse` | `#162D38` | `#EFFBDB` | **13.29** | 4.5 | PASS |
| 33 | branch hint | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 34 | toast text | `--bg-elevated` | `--text-primary` | `#C2D09F` | `#10121B` | **11.40** | 4.5 | PASS |

## B · Smart form
### B · Smart form — DARK theme
| # | Element | Surface token | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|---------------|------------|-------------|----------|-------|-----|------|
| 1 | hypothesis body | `--bg-container` | `--text-secondary` | `#161926` | `#B0B8CC` | **8.80** | 4.5 | PASS |
| 2 | hypothesis strong | `--bg-container` | `--text-primary` | `#161926` | `#EEF0F6` | **15.34** | 4.5 | PASS |
| 3 | theme toggle btn | `--bg-card` | `--text-primary` | `#1C2031` | `#EEF0F6` | **14.17** | 4.5 | PASS |
| 4 | toc head label | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 5 | toc item rest | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 6 | toc item hover | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 7 | toc item active | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 8 | smart-eyebrow label | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 9 | smart-eyebrow defaults | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 10 | hero caption | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 11 | hero title | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 3.0 | PASS |
| 12 | hero desc | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 13 | section title | `--bg-card` | `--text-primary` | `#1C2031` | `#EEF0F6` | **14.17** | 4.5 | PASS |
| 14 | section sub | `--bg-card` | `--text-secondary` | `#1C2031` | `#B0B8CC` | **8.13** | 4.5 | PASS |
| 15 | section badge complete | `--success-bg` | `--success-text` | `#142218` | `#7ECF8C` | **8.80** | 4.5 | PASS |
| 16 | section badge needed | `--bg-card` | `--brand-light` | `#1C2031` | `#A3B87A` | **7.46** | 3.0 | PASS |
| 17 | type tab rest | `--bg-input` | `--text-secondary` | `#131620` | `#B0B8CC` | **9.09** | 4.5 | PASS |
| 18 | type tab hover | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 4.5 | PASS |
| 19 | type tab active | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 20 | field label inside card | `--bg-card` | `--text-secondary` | `#1C2031` | `#B0B8CC` | **8.13** | 4.5 | PASS |
| 21 | field hint inside card | `--bg-card` | `--text-secondary` | `#1C2031` | `#B0B8CC` | **8.13** | 4.5 | PASS |
| 22 | field defaulted badge | `--bg-input` | `--text-secondary` | `#131620` | `#B0B8CC` | **9.09** | 4.5 | PASS |
| 23 | field required asterisk | `--bg-card` | `--danger-text` | `#1C2031` | `#F08A84` | **6.67** | 3.0 | PASS |
| 24 | ssh card rest name | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 4.5 | PASS |
| 25 | ssh card rest desc | `--bg-input` | `--text-secondary` | `#131620` | `#B0B8CC` | **9.09** | 4.5 | PASS |
| 26 | ssh card active name | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 27 | input value | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 4.5 | PASS |
| 28 | savebar summary | `--bg-container` | `--text-secondary` | `#161926` | `#B0B8CC` | **8.80** | 4.5 | PASS |
| 29 | savebar summary strong | `--bg-container` | `--text-primary` | `#161926` | `#EEF0F6` | **15.34** | 4.5 | PASS |
| 30 | savebar ready | `--bg-container` | `--success-text` | `#161926` | `#7ECF8C` | **9.32** | 4.5 | PASS |
| 31 | savebar primary btn | `--brand-light` | `--text-inverse` | `#A3B87A` | `#10121B` | **8.62** | 4.5 | PASS |
| 32 | savebar ghost btn | `--bg-container` | `--text-primary` | `#161926` | `#EEF0F6` | **15.34** | 4.5 | PASS |
| 33 | toast text | `--bg-elevated` | `--text-primary` | `#292F4A` | `#EEF0F6` | **11.52** | 4.5 | PASS |

### B · Smart form — LIGHT theme
| # | Element | Surface token | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|---------------|------------|-------------|----------|-------|-----|------|
| 1 | hypothesis body | `--bg-container` | `--text-secondary` | `#E4F0CC` | `#2A2F40` | **11.17** | 4.5 | PASS |
| 2 | hypothesis strong | `--bg-container` | `--text-primary` | `#E4F0CC` | `#10121B` | **15.68** | 4.5 | PASS |
| 3 | theme toggle btn | `--bg-card` | `--text-primary` | `#D8E5BD` | `#10121B` | **14.11** | 4.5 | PASS |
| 4 | toc head label | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 5 | toc item rest | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 6 | toc item hover | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 7 | toc item active | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 8 | smart-eyebrow label | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 9 | smart-eyebrow defaults | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 10 | hero caption | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 11 | hero title | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 3.0 | PASS |
| 12 | hero desc | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 13 | section title | `--bg-card` | `--text-primary` | `#D8E5BD` | `#10121B` | **14.11** | 4.5 | PASS |
| 14 | section sub | `--bg-card` | `--text-secondary` | `#D8E5BD` | `#2A2F40` | **10.05** | 4.5 | PASS |
| 15 | section badge complete | `--success-bg` | `--success-text` | `#D8F0DC` | `#1A5A26` | **6.87** | 4.5 | PASS |
| 16 | section badge needed | `--bg-card` | `--brand-light` | `#D8E5BD` | `#162D38` | **10.82** | 3.0 | PASS |
| 17 | type tab rest | `--bg-input` | `--text-secondary` | `#E8F4C8` | `#2A2F40` | **11.53** | 4.5 | PASS |
| 18 | type tab hover | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 4.5 | PASS |
| 19 | type tab active | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 20 | field label inside card | `--bg-card` | `--text-secondary` | `#D8E5BD` | `#2A2F40` | **10.05** | 4.5 | PASS |
| 21 | field hint inside card | `--bg-card` | `--text-secondary` | `#D8E5BD` | `#2A2F40` | **10.05** | 4.5 | PASS |
| 22 | field defaulted badge | `--bg-input` | `--text-secondary` | `#E8F4C8` | `#2A2F40` | **11.53** | 4.5 | PASS |
| 23 | field required asterisk | `--bg-card` | `--danger-text` | `#D8E5BD` | `#8A1A16` | **7.08** | 3.0 | PASS |
| 24 | ssh card rest name | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 4.5 | PASS |
| 25 | ssh card rest desc | `--bg-input` | `--text-secondary` | `#E8F4C8` | `#2A2F40` | **11.53** | 4.5 | PASS |
| 26 | ssh card active name | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 27 | input value | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 4.5 | PASS |
| 28 | savebar summary | `--bg-container` | `--text-secondary` | `#E4F0CC` | `#2A2F40` | **11.17** | 4.5 | PASS |
| 29 | savebar summary strong | `--bg-container` | `--text-primary` | `#E4F0CC` | `#10121B` | **15.68** | 4.5 | PASS |
| 30 | savebar ready | `--bg-container` | `--success-text` | `#E4F0CC` | `#1A5A26` | **6.96** | 4.5 | PASS |
| 31 | savebar primary btn | `--brand-light` | `--text-inverse` | `#162D38` | `#EFFBDB` | **13.29** | 4.5 | PASS |
| 32 | savebar ghost btn | `--bg-container` | `--text-primary` | `#E4F0CC` | `#10121B` | **15.68** | 4.5 | PASS |
| 33 | toast text | `--bg-elevated` | `--text-primary` | `#C2D09F` | `#10121B` | **11.40** | 4.5 | PASS |

## C · Document editor
### C · Document editor — DARK theme
| # | Element | Surface token | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|---------------|------------|-------------|----------|-------|-----|------|
| 1 | hypothesis body | `--bg-container` | `--text-secondary` | `#161926` | `#B0B8CC` | **8.80** | 4.5 | PASS |
| 2 | hypothesis strong | `--bg-container` | `--text-primary` | `#161926` | `#EEF0F6` | **15.34** | 4.5 | PASS |
| 3 | theme toggle btn | `--bg-card` | `--text-primary` | `#1C2031` | `#EEF0F6` | **14.17** | 4.5 | PASS |
| 4 | doc-eyebrow label | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 5 | doc-eyebrow status | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 6 | doc-meta title | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 7 | doc-meta date | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 8 | body paragraph text | `--bg-body` | `--text-primary` | `#10121B` | `#EEF0F6` | **16.39** | 4.5 | PASS |
| 9 | h2 subhead | `--bg-body` | `--text-secondary` | `#10121B` | `#B0B8CC` | **9.40** | 4.5 | PASS |
| 10 | tok rest text | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 4.5 | PASS |
| 11 | tok hover text | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 12 | tok required-empty text | `--danger-bg` | `--text-primary` | `#241416` | `#EEF0F6` | **15.53** | 4.5 | PASS |
| 13 | pop label | `--bg-elevated` | `--text-secondary` | `#292F4A` | `#B0B8CC` | **6.61** | 4.5 | PASS |
| 14 | pop input value | `--bg-input` | `--text-primary` | `#131620` | `#EEF0F6` | **15.84** | 4.5 | PASS |
| 15 | pop hint | `--bg-elevated` | `--text-secondary` | `#292F4A` | `#B0B8CC` | **6.61** | 4.5 | PASS |
| 16 | pop option rest | `--bg-elevated` | `--text-primary` | `#292F4A` | `#EEF0F6` | **11.52** | 4.5 | PASS |
| 17 | pop option hover | `--bg-card-hover` | `--text-primary` | `#232840` | `#EEF0F6` | **12.72** | 4.5 | PASS |
| 18 | pop option meta | `--bg-elevated` | `--text-secondary` | `#292F4A` | `#B0B8CC` | **6.61** | 4.5 | PASS |
| 19 | pop btn ghost | `--bg-elevated` | `--text-primary` | `#292F4A` | `#EEF0F6` | **11.52** | 4.5 | PASS |
| 20 | pop btn primary | `--brand-light` | `--text-inverse` | `#A3B87A` | `#10121B` | **8.62** | 4.5 | PASS |
| 21 | pop regen | `--bg-input` | `--text-secondary` | `#131620` | `#B0B8CC` | **9.09** | 4.5 | PASS |
| 22 | status label | `--bg-elevated` | `--text-secondary` | `#292F4A` | `#B0B8CC` | **6.61** | 4.5 | PASS |
| 23 | status strong primary | `--bg-elevated` | `--text-primary` | `#292F4A` | `#EEF0F6` | **11.52** | 4.5 | PASS |
| 24 | status ready success | `--bg-elevated` | `--success-text` | `#292F4A` | `#7ECF8C` | **7.00** | 4.5 | PASS |
| 25 | status btn primary | `--brand-light` | `--text-inverse` | `#A3B87A` | `#10121B` | **8.62** | 4.5 | PASS |
| 26 | toast text | `--bg-elevated` | `--text-primary` | `#292F4A` | `#EEF0F6` | **11.52** | 4.5 | PASS |

### C · Document editor — LIGHT theme
| # | Element | Surface token | Text token | Surface hex | Text hex | Ratio | Min | Pass |
|---|---------|---------------|------------|-------------|----------|-------|-----|------|
| 1 | hypothesis body | `--bg-container` | `--text-secondary` | `#E4F0CC` | `#2A2F40` | **11.17** | 4.5 | PASS |
| 2 | hypothesis strong | `--bg-container` | `--text-primary` | `#E4F0CC` | `#10121B` | **15.68** | 4.5 | PASS |
| 3 | theme toggle btn | `--bg-card` | `--text-primary` | `#D8E5BD` | `#10121B` | **14.11** | 4.5 | PASS |
| 4 | doc-eyebrow label | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 5 | doc-eyebrow status | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 6 | doc-meta title | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 7 | doc-meta date | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 8 | body paragraph text | `--bg-body` | `--text-primary` | `#EFFBDB` | `#10121B` | **17.34** | 4.5 | PASS |
| 9 | h2 subhead | `--bg-body` | `--text-secondary` | `#EFFBDB` | `#2A2F40` | **12.34** | 4.5 | PASS |
| 10 | tok rest text | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 4.5 | PASS |
| 11 | tok hover text | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 12 | tok required-empty text | `--danger-bg` | `--text-primary` | `#F8DCDA` | `#10121B` | **14.44** | 4.5 | PASS |
| 13 | pop label | `--bg-elevated` | `--text-secondary` | `#C2D09F` | `#2A2F40` | **8.12** | 4.5 | PASS |
| 14 | pop input value | `--bg-input` | `--text-primary` | `#E8F4C8` | `#10121B` | **16.19** | 4.5 | PASS |
| 15 | pop hint | `--bg-elevated` | `--text-secondary` | `#C2D09F` | `#2A2F40` | **8.12** | 4.5 | PASS |
| 16 | pop option rest | `--bg-elevated` | `--text-primary` | `#C2D09F` | `#10121B` | **11.40** | 4.5 | PASS |
| 17 | pop option hover | `--bg-card-hover` | `--text-primary` | `#D0DDB0` | `#10121B` | **13.03** | 4.5 | PASS |
| 18 | pop option meta | `--bg-elevated` | `--text-secondary` | `#C2D09F` | `#2A2F40` | **8.12** | 4.5 | PASS |
| 19 | pop btn ghost | `--bg-elevated` | `--text-primary` | `#C2D09F` | `#10121B` | **11.40** | 4.5 | PASS |
| 20 | pop btn primary | `--brand-light` | `--text-inverse` | `#162D38` | `#EFFBDB` | **13.29** | 4.5 | PASS |
| 21 | pop regen | `--bg-input` | `--text-secondary` | `#E8F4C8` | `#2A2F40` | **11.53** | 4.5 | PASS |
| 22 | status label | `--bg-elevated` | `--text-secondary` | `#C2D09F` | `#2A2F40` | **8.12** | 4.5 | PASS |
| 23 | status strong primary | `--bg-elevated` | `--text-primary` | `#C2D09F` | `#10121B` | **11.40** | 4.5 | PASS |
| 24 | status ready success | `--bg-elevated` | `--success-text` | `#C2D09F` | `#1A5A26` | **5.06** | 4.5 | PASS |
| 25 | status btn primary | `--brand-light` | `--text-inverse` | `#162D38` | `#EFFBDB` | **13.29** | 4.5 | PASS |
| 26 | toast text | `--bg-elevated` | `--text-primary` | `#C2D09F` | `#10121B` | **11.40** | 4.5 | PASS |

## Fails
NONE — zero failures across all shapes and themes.
