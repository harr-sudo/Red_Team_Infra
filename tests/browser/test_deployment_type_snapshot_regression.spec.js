/**
 * Layer 3 — Deployment-type cascade regression guard.
 *
 * 2026-05-21 legacy-audit sweep: retired.
 *
 * This file's tests exercised the legacy `.configuration-editor` cascade —
 * driving `<select id="deployment-type">` through all 11 deployment types
 * and asserting which `*-config-section` elements were visible/hidden via
 * the deployment_snapshots.json baseline. Per UX_AUDIT 2026-05-20 (M1), the
 * legacy form (`#deployment-type`, `#key-pair-name`, `*-config-section`)
 * is scheduled for deletion alongside the rest of `.configuration-editor`.
 * Asserting on those IDs encodes the wrong mental model for V2.
 *
 * V2-native coverage of the equivalent gating exists in:
 *
 *   - test_v3_configure_progressive.spec.js  — V2 section state machine
 *     (pending / active / confirmed) and assembleConfig() shape per
 *     deployment type.
 *   - test_v3_configure_family_change.spec.js — Family switch repaints the
 *     TOC rail with the right section list (C2 / GOAD / combined).
 *   - test_v3_test_lab_toggle.spec.js          — Test-lab section cost +
 *     visibility per family.
 *
 * The companion baseline-capture script `fixtures/capture_deployment_snapshots.spec.js`
 * and its `deployment_snapshots.json` baseline are also retired in this
 * sweep — they were only useful when the legacy cascade was canon.
 *
 * No tests are exported from this file.
 */
