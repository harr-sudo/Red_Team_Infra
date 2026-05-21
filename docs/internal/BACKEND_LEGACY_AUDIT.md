# Backend Legacy-Path Audit — 2026-05-21

Comprehensive sweep of `webapp/backend/` for pre-V2 / pre-per-project-tfvars
patterns that survived the `f95e1f7` "Configure → Deploy → Manage per-project"
migration. Goal: every terraform-touching route resolves the correct
per-project tfvars file and workspace.

**Branch:** `feature/v3-production-rollout` (HEAD `5421efb`).

## Totals

| Category | Findings | Fixed | Documented (left as-is) |
|---|---|---|---|
| 1. Hardcoded global `terraform.tfvars` reads | 22 | 16 | 6 |
| 2. `workspace_name = "default"` pinning | 0 | — | — |
| 3. Routes accepting `project_name` but ignoring it | 0 | — | — |
| 4. Routes that should accept `project_name` but didn't | 7 | 7 | — |
| 5. Test fixture drift | 0 | — | — |
| 6. Cost endpoint guardrails | 0 | — | All clean |
| 7. Deprecated / orphan routes | 12 | 11 deleted | 1 kept as 410 Gone |
| 8. Trust boundary / operator-resolution bypass | 0 | — | — |
| **Total** | **41** | **34** | **7** |

## Files touched

- `webapp/backend/routes/deploy.py` — bulk of the migration; added per-project
  helpers (`_project_tfvars_for`, `_read_project_config`) and threaded
  per-project tfvars through every route that touches AWS state.
- `webapp/backend/routes/goad.py` — `/start`, `/stop`, `/instance-status`,
  `/provision` all now resolve per-project tfvars from `?project=` /
  body `project_name`.
- `webapp/backend/routes/tools.py` — `/transfer` reads region from per-project
  tfvars; orphan `/projects` route deleted.
- `tests/backend/test_no_legacy_paths.py` — new regression suite (21 tests).

---

## Category 1 — Hardcoded global `terraform.tfvars` reads (22)

### Fixed (16)

| File:Line | Function | Was | Fix |
|---|---|---|---|
| `routes/deploy.py:234` | `_get_aws_region` | Hardcoded global tfvars region | Accept `project_param`, use `_read_project_config` |
| `routes/deploy.py:466` | `query_remaining_resources` | Hardcoded global tfvars for AWS region | Use `_read_project_config(project_name)` |
| `routes/deploy.py:1762` | `check_project_name` | Hardcoded global tfvars for AWS region | Use `_read_project_config(project_name)` |
| `routes/deploy.py:4205` | `stop_infrastructure` | Hardcoded global tfvars for region | Accept `?project=`, use per-project tfvars |
| `routes/deploy.py:4293` | `start_infrastructure` | Hardcoded global tfvars for region | Accept `?project=`, use per-project tfvars |
| `routes/deploy.py:4379` | `get_instance_status` | Hardcoded global tfvars for region | Use per-project tfvars when `?project=` set |
| `routes/deploy.py:5022` | `get_terraform_outputs` | Hardcoded global tfvars for region/config | Honor `?project=` for tfvars lookup |
| `routes/deploy.py:5269` | `get_sg_rules` | Hardcoded global tfvars for region | Use `_read_project_config(project_name)` |
| `routes/deploy.py:5387` | `get_ssl_status` (project fallback) | Hardcoded global tfvars to recover project_name | Use `_read_project_config(None)` helper |
| `routes/deploy.py:5437` | `get_ssl_status` (EC2 region) | Hardcoded global tfvars for AWS region | Use per-project tfvars |
| `routes/deploy.py:5578` | `toggle_redirector` | Hardcoded global tfvars for domain/region | Use `_read_project_config(project_name)` |
| `routes/deploy.py:5682` | `get_redirector_dns_status` | Hardcoded global tfvars for domain/region | Use `_read_project_config(project_name)` |
| `routes/tools.py:404` | `start_transfer` | Hardcoded global tfvars for region | Use `resolve_tfvars_path(project, ...)` |
| `routes/goad.py:351` | `provision_goad` | Hardcoded global tfvars for ip_range/ssh_key/region | Accept `?project=` or body `project_name`; per-project resolution |
| `routes/goad.py:1077, 1149, 1221` | `start_goad`/`stop_goad`/`get_goad_instance_status` | Hardcoded global tfvars for region/project name | Accept `?project=`, use per-project resolution |

### Documented / kept (6)

| File:Line | Function | Why kept |
|---|---|---|
| `routes/aws_check.py:50` | `_scan_tfvars_for_domains` | Walks every config including the legacy global to build a domain→project map. Has to look at the literal name. |
| `routes/health.py:21, 167, 237` | global `tfvars_file` for `/domain-config`, `/route53-domains` | Read-only health/diagnostic endpoints; the global tfvars is the right default when no project is specified. |
| `routes/deploy.py:4957` | `get_all_project_resources` | Intentionally cross-project (Cleanup sub-pill); reads global tfvars for fallback region, not for state mutation. |
| `routes/deploy.py:1986, 2649` | `deploy` / `plan` | The `global_tfvars` variable is the fallback argument passed into `_resolve_project_tfvars` — that helper IS the per-project resolver. Not a direct read. |
| `routes/config.py:33` | `get_config` / `delete_config` / `update_config` module-level paths | These ARE the per-project endpoints. They use `_resolve_tfvars_path(project_param, config_dir, tfvars_file)` so the global is just the fallback. |
| `routes/deploy.py:5121` | `get_terraform_outputs` deployment-state comment | Just a comment referencing legacy fallback. Behaviour is per-project. |

### Helper functions added

```python
# webapp/backend/routes/deploy.py
def _project_tfvars_for(project_param):           # path resolver
def _read_project_config(project_param):           # parses tfvars into dict
def _get_aws_region(project_param=None):           # now accepts project param
```

All three call through `webapp.backend.utils.tfvars_path.resolve_tfvars_path`
so the path-traversal sanitiser is the only place name resolution lives.

---

## Category 2 — `workspace_name = "default"` pinning (0)

Sweep result: **no production route force-pins the workspace to `"default"`**.

The hits in `services/terraform_service.py` are constructor defaults / class-
internal cleanup (`workspace_delete` returns to `default` before destroying a
named workspace — legitimate). Routes that need a different workspace use
`service.workspace_select(resolved_workspace)` instead of mutating
`workspace_name` directly.

The only direct assignment found was in the deploy route's `plan()` handler
where `terraform_service.workspace_name = resolved_workspace` precedes a
`workspace_select()` call — but `resolved_workspace` is computed from the
per-project sanitizer, NOT hardcoded to `default`. This is correct.

Regression covered by `test_no_route_force_pins_workspace_to_default_for_state_mutation`.

---

## Category 3 — Routes that take `project_name` but ignore it (0)

None found. Every route that accepts `project_name` in body or `?project=`
in query now passes it through to either `get_service_for_project` (which
returns a workspace-targeted TerraformService) or `_read_project_config`
(which reads the per-project tfvars).

---

## Category 4 — Routes that should accept `project_name` but didn't (7)

| Route | Symptom | Fix |
|---|---|---|
| `POST /api/deploy/stop` | Body had `project_name` but region was read from GLOBAL tfvars | Body wins; per-project config for region |
| `POST /api/deploy/start` | Same | Same |
| `POST /api/deploy/cancel` | Body had `project_name` but no query-param alternative | Now accepts both body and `?project=` |
| `GET /api/deploy/instance-status` | `?project=` accepted but region still came from global | Per-project tfvars for region |
| `POST /api/goad/start` | Hardcoded global tfvars for region + project_name | Now accepts `?project=` / body |
| `POST /api/goad/stop` | Same | Same |
| `GET /api/goad/instance-status` | Same | Same |

Routes that were ALREADY correctly per-project (no fix needed):
- `POST /api/deploy/deploy` (uses `_resolve_project_tfvars`)
- `GET /api/deploy/plan` (uses `_resolve_project_tfvars`)
- `POST /api/deploy/destroy` (uses sanitized project_name + state-summary guard)
- `POST /api/deploy/purge` (delegates to project state)
- `POST /api/deploy/detach-foreign/<project>` (path-bound)
- `GET /api/deploy/state-summary/<project>` (path-bound)
- `GET /api/deploy/resources/project/<project_name>` (path-bound)
- `POST /api/deploy/toggle-redirector` (body required `project`)
- `GET /api/deploy/redirector-dns-status` (query required `project`)
- `GET /api/deploy/sg-rules` (query required `project`)
- `GET /api/deploy/ssl-status` (query required `project`)
- `GET /api/tools/connection-info` (query required `project`)
- `POST /api/tools/transfer` (body required `project`)

Cobalt Strike upload endpoints (`/upload-cobalt-strike`, `/upload-cs-client`,
`/cobalt-strike-file`, `/cs-client-file`) intentionally write to a shared
per-host directory because the CS archive is the same across all deployments
on a given dashboard host. No per-project plumbing needed.

---

## Category 5 — Test fixture drift (0)

Backend tests were already migrated. `tests/backend/test_deploy_per_project.py`
covers the per-project Plan/Apply contract; `test_routes_config_perproject.py`
covers `/api/config?project=`; `test_destroy_safety.py` covers the foreign-
module guard. None of these encode the broken model.

The known pre-existing failure
`test_state_isolation.py::test_env_var_writes_actually_land_in_tmpdir` is
unrelated to the legacy sweep — it fails because `~/.dashboard/operators.json`
has leaked `contrast_pw` from a previous unisolated test run. Out of scope
for this audit.

---

## Category 6 — Cost endpoint guardrails (clean)

All checks passed:

- `CostService.get_aws_costs.force_refresh` default is `False` (verified by
  `test_cost_service_force_refresh_is_off_by_default`).
- `CostService.get_cost_summary.force_refresh` default is `False`.
- `boto3.client('ce', ...)` appears only in `services/cost_service.py`
  (verified by `test_only_cost_service_calls_cost_explorer`). No other module
  hits Cost Explorer directly, so the daily-call counter is the only gate.
- `CE_DAILY_HARD_LIMIT = 10` enforced inside `get_aws_costs`.

`/api/costs/summary` accepts `?force=true` — wired only to the explicit
Refresh button per the comment in `cost_service.py`. No automated callers.

---

## Category 7 — Deprecated / orphan routes (12 → 11 deleted, 1 kept)

Frontend `webapp/frontend/js/app.js` was cross-referenced against every
`@bp.route` in `webapp/backend/routes/`. Orphan = no live frontend caller,
no script caller, no test caller.

### Deleted (11)

| Route | Replaced by | Notes |
|---|---|---|
| `POST /api/deploy/init` | inline in `run_deployment` / `plan` | Duplicate code path |
| `GET /api/deploy/workspaces` | `GET /api/deploy/active` | Debugging endpoint |
| `GET /api/deploy/status/all` | `GET /api/deploy/active` | Legacy single-deployment view |
| `GET /api/deploy/generate-project-name` | client-side composition + `/machine-info` | Frontend composes name |
| `GET /api/deploy/connection-info` | `/api/deploy/infrastructure` + `/outputs` | 350+ unused lines |
| `GET /api/deploy/connection-info/quick` | same | same |
| `GET /api/deploy/ssh-fingerprints` | TOFU on first SSH connect | Never surfaced in UI |
| `POST /api/deploy/infrastructure/refresh` | `?refresh=true` on `/resources/project/<name>` | Wrong workspace |
| `POST /api/deploy/upload-to-s3` | done inline by `run_deployment` | Never wired |
| `POST /api/deploy/history/add` | internal `add_history_entry()` only | Forgeable audit |
| `GET /api/deploy/goad-status` | `/api/goad/status` | Read wrong workspace |
| `GET /api/tools/projects` | `/api/deploy/active` | Only referenced from `app.js.bak` |

### Kept (1)

| Route | Status | Why |
|---|---|---|
| `GET /api/deploy/ssh-key/<key_type>` + `POST /ssh-key/download` | HTTP 410 Gone stub | Already returns a structured deprecation notice + migration guide. Operators may have bookmarked old URLs — better to keep the 410 than have them hit 404 with no breadcrumb. |

---

## Category 8 — Trust boundary / operator-resolution bypass (0)

`webapp/backend/app.py:127-129` registers `_resolve_operator` as a global
`before_request` hook. It's unconditional and runs for every request, so no
route can bypass it.

`enforce_loopback` at `app.py:117-121` runs first and rejects non-127.0.0.1
requests with HTTP 403 — that's the only check that can short-circuit before
operator resolution, which is correct (we don't want to attribute a denied
connection to a particular operator).

Audit log writes via `audit_service.write(_audit_actor(), ...)` happen
throughout `deploy.py` for state-mutating actions (apply, destroy,
detach_foreign, force_foreign, save_config, delete_config). Spot-check: every
new per-project handler added in this sweep audits with the resolved actor.

---

## Regression coverage

`tests/backend/test_no_legacy_paths.py` (new, 21 tests):

- 12 parametrised tests: each retired route returns 404/405.
- `test_deploy_py_does_not_hardcode_global_tfvars_for_writes` — static
  scan with an allowlist for helper functions / cross-project endpoints.
- `test_no_route_force_pins_workspace_to_default_for_state_mutation` —
  static scan.
- `test_plan_routes_to_per_project_workspace` — runtime contract.
- `test_instance_status_reads_per_project_region` — runtime contract.
- `test_stop_endpoint_resolves_per_project_region` — runtime contract.
- `test_cost_service_force_refresh_is_off_by_default` — guardrail.
- `test_only_cost_service_calls_cost_explorer` — guardrail.
- `test_destroy_route_imports_safety_helpers` — destroy safety wired in.
- `test_goad_lifecycle_routes_accept_project_param` — GOAD per-project.

Pre-existing suites (`test_deploy_per_project.py`, `test_destroy_safety.py`,
`test_routes_config_perproject.py`) all still pass.

**Suite result:** `474 passed, 1 failed (pre-existing, unrelated state-
isolation test), 1 skipped, 1 xfailed`.
