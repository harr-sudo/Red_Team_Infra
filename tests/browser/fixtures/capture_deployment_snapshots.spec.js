/**
 * Snapshot capture — retired 2026-05-21 (legacy-audit sweep).
 *
 * Generated `deployment_snapshots.json`, the baseline consumed by
 * `tests/browser/test_deployment_type_snapshot_regression.spec.js`. Both
 * the regression spec and this capture script were tied to the legacy
 * `.configuration-editor` cascade (`#deployment-type` + `*-config-section`
 * + `#key-pair-name`), which is being retired per UX_AUDIT 2026-05-20 (M1).
 *
 * V2-native section-visibility coverage lives in
 * `tests/browser/test_v3_configure_progressive.spec.js` and
 * `tests/browser/test_v3_configure_family_change.spec.js`. There is no
 * equivalent baseline file in V2 because the V2 section list is fully
 * deterministic from the family + type pickers — no cascade needed.
 *
 * The file is preserved (without exported tests) so the retirement context
 * is reachable via `git log`. The baseline JSON beside it is no longer
 * read by anything.
 */
