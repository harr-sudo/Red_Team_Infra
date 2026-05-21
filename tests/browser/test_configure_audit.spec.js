/**
 * 2026-05-19 — Configure sub-pill audit (Production v3 rollout).
 *
 * 2026-05-21 legacy-audit sweep: this file's tests all exercise the legacy
 * `.configuration-editor` form (`#management-cidr`, `#fetch-ip-btn`,
 * `#project-name`, `#deployment-type`, `#configure-new-deployment-banner`,
 * `#configure-context-hint`, `#domain-config-section`,
 * `#goad-network-config-section`) and the auto-open journey wizard from
 * `+ New Deployment`. Both are slated for retirement:
 *
 *   - The legacy form is scheduled for deletion per UX_AUDIT 2026-05-20 (M1).
 *   - `+ New Deployment` no longer auto-opens the journey wizard; it routes
 *     into Configure V2 (progressive). The journey wizard is opt-in only via
 *     `?wizard=1` or explicit `APP.journey.open()`.
 *
 * V2-equivalent coverage already exists elsewhere:
 *
 *   - Use my IP (V2 button #cfg-use-my-ip)            → not yet covered;
 *     flagged in the audit report as a coverage gap once V2 replaces the
 *     legacy CIDR row.
 *   - Configure context / hero state                  → test_v3_new_deployment_landing.spec.js,
 *                                                       test_v3_hero_pill_save_transition.spec.js
 *   - Deployment-type-aware section gating            → test_v3_configure_progressive.spec.js,
 *                                                       test_v3_configure_family_change.spec.js
 *   - Existing-deployment Configure empty state       → test_v3_configure_existing_deployment_guard.spec.js
 *   - Journey wizard end-to-end (opt-in)              → test_v3_journey.spec.js,
 *                                                       test_v3_flow_stitching.spec.js
 *   - Configure surface contrast (both themes)        → test_contrast_invariants.spec.js,
 *                                                       test_v3_configure_progressive.spec.js
 *
 * No tests are exported from this file. It is preserved as a tombstone so
 * `git log -- tests/browser/test_configure_audit.spec.js` still surfaces the
 * retirement context.
 */
