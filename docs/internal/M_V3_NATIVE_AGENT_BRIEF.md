# M-V3-Native — Agent Brief (Phase 1: Deploy Sub-pill Preview/Comparison)

**Status:** Drafted 2026-05-18. Dispatch the instant M-Operators (`v2.3.0`) is committed — agents share `index.html`, `style.css`, `app.js` so parallel work guaranteed conflicts.

**Trigger condition:** branch `refactor/dashboard-m-operators` merged/tagged; new branch `refactor/dashboard-m-v3-native-deploy-preview` checked out from that.

---

## The reframe (user feedback 2026-05-18)

> *"the ui updates we've made so far have been constrained by the existing top level layout and designs for certain section — this is what we need to break free from using the new TASTE design. Look at the demoes of taste, they had already broken free and looked great."*

> *"Double check the contrast, some text is against the wrong colour and not readable — you must consider the direct layer behind / around any text and how it is layered."*

What we've shipped (D1 → M-Redesign): V3 applied to the shell — header, nav, modals, sub-pills, motion utils. What we've NOT done: V3 applied to **page interiors**. Tile-grid layouts, dropdown patterns, summary cards, form columns, list rows — all still carry the legacy skeleton. Retrofitting V3 chrome over that produces incoherent pages. The Deploy sub-pill "Configuration Summary" screenshot is the canonical example.

This brief covers **Phase 1 only**: a preview/comparison agent that produces 3 V3-native compositions for the Deploy sub-pill Configuration Summary view, side-by-side, behind a feature flag. User picks the direction. Phase 2 (a separate brief, after pick) applies that direction to all sub-pill interiors and ships as `v2.4.0`.

---

## Agent prompt (paste-ready)

> You are executing **M-V3-Native Phase 1 — Deploy sub-pill Configuration Summary preview/comparison** for `/Users/harriskhalid/Desktop/Red_Team_Infra_Local`.
>
> ### Context
> - User-facing feedback memory: `~/.claude/projects/-Users-harriskhalid-Desktop-Red-Team-Infra-Local/memory/feedback_v3_native_rebuild.md` and `feedback_contrast_layer_aware.md`. **Read both before doing anything.**
> - The current Configuration Summary view is at the top of the Deploy sub-pill in `webapp/frontend/index.html`. Find it by searching for "Configuration Summary".
> - It currently renders a 5-tile row + 2-tile row layout with emoji icons, multi-colored left-border stripes, and a `<details>` disclosure. The user's screenshot is described in the conversation that produced this brief.
> - The V3 design DNA lives in `webapp/frontend/preview/header-taste-v3.html`, `header-taste.html`, `header-taste-v2.html`. **Read all three before designing.** They "broke free" of the legacy header design — internalize how, not what.
>
> ### Goal
> Produce **THREE distinct V3-native compositions** of the Configuration Summary view, plus a comparison page mirroring the D1 header-compare pattern. Production code is NOT touched in this phase — everything lives under `webapp/frontend/preview/`.
>
> ### Hard rules (the user will check)
> 1. **No retrofitting.** Do not start from the current 7-tile grid and remove the bad parts. Start from a blank canvas with the V3 design DNA and ask: what is the right shape for this content? Permitted answers include — definition list, two-column rhythm, hero + spec sheet, left-rail summary with right-column detail, vertical timeline, none of the above. Different alternatives should explore different *shapes*, not three minor color variations.
> 2. **No emoji icons.** Anti-emoji per CLAUDE.md. If iconography is needed, inline SVG monochrome line glyphs at 14-16px stroked with `currentColor`, or pure typography.
> 3. **Layer-aware contrast — mandatory pre-commit step.** Before declaring done, produce a markdown report at `webapp/frontend/preview/deploy-summary-contrast-report.md` with one section per composition × per theme, listing every text declaration paired with the immediate-ancestor surface and the computed contrast ratio. Use `tinycolor` or a small inline JS contrast calculator — do NOT eyeball. Fail anything < 4.5:1 (body) or < 3:1 (large/bold) and fix it before producing the comparison page.
> 4. **Both themes.** Each composition must work in `[data-theme="light"]` and the default dark theme. The comparison page must have a theme toggle.
> 5. **Realistic data.** Use a long project name that forces an overflow decision (`goad_mini_dev_harriss_macbook_pro`) and a non-default CIDR (`82.35.149.127/32`). Use real config keys: deployment type, project name, environment, AWS region, management CIDR, SSH keys, est. monthly cost.
> 6. **Palette tokens only.** No raw hex (except SVG `stroke="currentColor"`). Use existing variables from `palette.css`. If you need a new token, add it as a `--temp-*` variable inside the preview file's `<style>` block — do NOT modify `palette.css`.
> 7. **Motion fluidity (5/6/5).** Use `280ms cubic-bezier(0.4, 0, 0.2, 1)` on hover/focus/state changes. Stagger any list enter. Respect `prefers-reduced-motion: reduce`.
> 8. **Density.** Type rhythm: 13px body, 9.5px mono caps for labels, 18-22px for hero/title, 11px for help/meta. Tabular numerics for costs.
>
> ### Files to produce
> All under `webapp/frontend/preview/`:
>
> 1. `deploy-summary-v3-a.html` — Composition A (give it a name describing its concept, e.g. "Definition list"). One sentence at the top describes the design hypothesis. Self-contained (loads `/css/palette.css` + `/css/style.css` + inline `<style>` for the preview-only bits).
> 2. `deploy-summary-v3-b.html` — Composition B (e.g. "Hero + spec sheet").
> 3. `deploy-summary-v3-c.html` — Composition C (a deliberately different shape from A and B).
> 4. `deploy-summary-compare.html` — Comparison page. 3-pane iframe grid (or 2x2 with one slot blank). Top bar with: title, variant selector buttons (highlight current), theme toggle that flips both panes, link back to each individual preview.
> 5. `deploy-summary-contrast-report.md` — Per-composition per-theme contrast audit.
>
> ### Mounting the previews
> Flask serves `/preview/<file>` already (the D1 header previews work). Verify routes exist; if any are missing, add a minimal blueprint addition to `webapp/backend/routes/preview.py` (if it exists) or wherever the header previews are served from. Do NOT change unrelated routes.
>
> ### Don't do
> - Do NOT modify the live Configuration Summary view in `index.html` — that comes in Phase 2 after the user picks.
> - Do NOT touch backend routes other than the preview blueprint (if needed).
> - Do NOT modify `style.css` or `palette.css`.
> - Do NOT add tests yet — Phase 2 will add Playwright coverage for whatever direction wins.
> - Do NOT commit. Leave the working tree dirty so I can review and the user can pick.
>
> ### Report back (under 600 words)
> 1. The three compositions named + the one-sentence hypothesis for each
> 2. What you discarded — at least one shape you considered and rejected, and why
> 3. The contrast audit summary — total text declarations checked per composition × per theme, total passes, total fails (should be 0 — if not, fix and re-audit before reporting)
> 4. URLs to open: `http://localhost:5050/preview/deploy-summary-compare.html`
> 5. Any token gaps — variables you wished existed but used a `--temp-*` workaround for

---

## What I'll do when the agent returns

1. Open the comparison page in both themes
2. Skim the contrast report
3. Send the user the three URLs + a 2-sentence summary of each direction (no opinion yet — user picks)
4. Once the user picks, I draft Phase 2 brief: apply the winning direction to the live Deploy sub-pill, then propagate the pattern language to Configure / Manage / Operations interiors / Cleanup interiors

## Decision #24 (to be added to STATUS_DEEP_DIVE after Phase 1)

**M-V3-Native is a re-author, not a retouch** (per user 2026-05-18: *"this is what we need to break free from using the new TASTE design. Look at the demoes of taste, they had already broken free and looked great"*). Page interiors are re-derived from V3 design DNA on a blank canvas; existing layout choices are treated as legacy. Mandatory pre-commit step: layer-aware contrast audit using the immediate-ancestor surface, not the page bg. Phase 1 = Deploy sub-pill preview/comparison (3 alternative shapes, user picks). Phase 2 = apply winning shape across all sub-pill interiors, ship as `v2.4.0`. Replaces the earlier "M-Subviews" scope which was framed as tile cleanup.
