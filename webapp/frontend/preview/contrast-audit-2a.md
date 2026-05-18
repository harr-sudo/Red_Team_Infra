# Contrast Audit — Phase 2a (Layer-Aware)

**Phase:** M-V3-Native Phase 2a — Theming foundation + layer-aware contrast sweep
**Branch:** `refactor/dashboard-m-v3-native-phase2a`
**Date:** 2026-05-18
**Methodology:** Layer-aware. For every visible text element, walk up the
DOM until we find an ancestor with a substantially-opaque background
(alpha >= 0.7); for partly-transparent overlays we composite. Contrast
ratio is computed via WCAG sRGB → relative luminance → ratio.

**Threshold:** 4.5:1 for normal body text; 3.0:1 for large/bold display
text (>= 24px or >= 18.66px bold), per WCAG 2.1 AA.

**Audit script:** `tests/browser/test_contrast_invariants.spec.js`
(Full-page sweep tests). Runs via `make test-browser` or
`npx playwright test tests/browser/test_contrast_invariants.spec.js`.

---

## Settings header D8 bug — root cause

**Symptom (2026-05-18):** On the Settings tab, the headers of the three
D8 cards (Domains & DNS, Secrets Manager, Infrastructure Services)
showed dark text on a dark background in light mode. The eyebrow,
title, and description text were nearly invisible.

**Walk-up:**

```
<span class="settings-section__eyebrow">          color: var(--text-muted)
   ↑
<header class="settings-section__header">         background: var(--burgundy) ← BUG
   ↑
<section id="settings-services" class="settings-section">
   ↑
<main class="settings-content">
   ↑
<div class="settings-layout">
   ↑
<div class="tab-page" data-page="settings">
   ↑
<div class="container">                            background: var(--bg-container)
```

The DOM identified `<header class="settings-section__header">` as the
nearest background-setting ancestor. The CSS rule

```css
header {
    background: var(--burgundy);
    color: var(--text-primary);
    ...
}
```

at `webapp/frontend/css/style.css:72` was a bare-element selector
(intended for `architecture.html`). It matches EVERY `<header>` tag in
the DOM, including content-wrapper `<header>` elements like
`.settings-section__header`. In light mode `--burgundy` resolves to
`#0E1F27` (dark teal), and the descendant text was using
`--text-muted` (`#4A5168`) and `--text-primary` (`#10121B`) — both
dark, producing 1–2:1 contrast against the surface.

**Fix:**
1. Scope the bare-element rule to direct body children
   (`body > header { ... }`) so it only applies to the
   `architecture.html` page banner it was authored for.
2. Add explicit `background: transparent; color: inherit;` to
   `.settings-section__header` as a defensive overlap.

Both fixes are in `webapp/frontend/css/style.css` and live behind the
new regression test
`tests/browser/test_contrast_invariants.spec.js` (the "Settings
section headers pass contrast" dark/light cases).

---

## Audit run — final result

| Suite                                    | Result    |
|------------------------------------------|-----------|
| Settings section headers (dark)          | PASS      |
| Settings section headers (light)         | PASS      |
| Dashboard widget titles (dark)           | PASS      |
| Dashboard widget titles (light)          | PASS      |
| Global header chip labels (dark)         | PASS      |
| Global header chip labels (light)        | PASS      |
| Full-page contrast sweep (dark)          | PASS — 0 failures |
| Full-page contrast sweep (light)         | PASS — 0 failures |

The full-page sweep visits Dashboard + Settings in both themes, walks
every visible element with direct text content (skipping terminal/code
surfaces, which are correctly dark-by-design in both themes), and
checks contrast against the composited surface. No failures.

---

## Token-pairing fixes made during the sweep

| Token            | Before        | After         | Why                                                                                                                            |
|------------------|---------------|---------------|--------------------------------------------------------------------------------------------------------------------------------|
| `--color-neutral-300` (dark `--text-muted`) | `#7A849E` | `#858FAB` | Dark text-muted on `--bg-card` was 4.32:1 (fail). New value is 5.01:1.                                                          |
| `--color-primary-dim` (dark `--brand-dark`) | `#6B7D4A` | `#4D5C32` | Active tab cream-on-olive was 2.54:1 (fail). New `--brand-dark` fill brings cream-on-dark-olive to 6.74:1.                       |
| `--color-success` | `#4A9A56` | `#3D8047` | White-on-success button was 3.47:1 (fail). 4.80:1 now.                                                                          |
| `--color-info`    | `#5088C0` | `#2A6FB0` | White-on-info button was 3.73:1 (fail). 5.25:1 now.                                                                             |
| `--color-danger`  | `#C43B34` | `#B82E28` | Tightened to match light-mode value and improve AA margin.                                                                       |
| Light `--accent` / `--accent-muted` | `#6B7D4A` / `#5A6C3C` | `#495C2D` | `<a>` links on `--bg-card` were 4.35:1 (fail). 5.56:1 now.                                                                       |
| `.btn-warning { color: #fff }` | `var(--text-on-primary)` (`#fff`) | `var(--color-neutral-950)` (dark) | Amber bg cannot pair with white text at AA — must use dark text. Now 6.59:1.                                                  |
| `.tab-btn.active` background | `var(--brand)` | `var(--brand-dark)` | See above — needed darker fill for AA pairing with cream text.                                                                  |

All changes apply uniformly to both themes; no body-rule layer
required theme-conditional overrides beyond what was already in
`palette.css`.

---

## Surfaces affirmed correct (no changes needed)

- `--bg-terminal` / `--text-terminal` and the `--terminal-*` palette —
  always dark, always bright on top, both themes. Audit excludes
  terminal/code surfaces from the sweep.
- `--bg-input` (recessed form field) — `--text-primary` reads
  comfortably in both themes.
- Modal scrim (`--scrim-dark` / `--scrim-light`) — backdrop only, no
  text on it.
- Architecture diagram frame — white background by design (diagram PNGs
  have white backgrounds). Excluded from the sweep.

---

## How to re-run

```bash
# All contrast tests (regression net + full-page sweep)
npx playwright test tests/browser/test_contrast_invariants.spec.js

# Full test suite (133 + 8 new browser cases = 141)
make test
```
