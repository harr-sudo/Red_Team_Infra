# Deployment Integrity — Foreign Modules in State

## What this is

A terraform workspace per deployment contains a state file. That state file
should only track the modules that match the deployment's declared
`deployment_type` (c2-adhoc, goad-mini, combined-adhoc-light, etc.).

If the state contains a module that doesn't belong — we call it a
**foreign module** — `terraform destroy` on that workspace will tear it
down along with everything else.

The dashboard guards against this BEFORE the destroy thread starts.

## Why it matters — the dashboard_server case

The dashboard server (the EC2 instance running this management UI) lives
in a shared `__dashboard__` workspace. It is provisioned ONCE and is
expected to outlive every deployment.

Early in the project, the dashboard server was provisioned by mistake
into the `goad_mini_dev_harriss_macbook_pro` workspace's state. The
state file for that workspace now contains:

```
module.dashboard_server[0]....
aws_dynamodb_table.tflock
```

Plus every legitimate `goad-mini` module (vpc, security, attack_box,
cs_storage, goad).

If an operator clicks **Destroy** in Manage for that deployment without
the safety check, terraform happily tears down `module.dashboard_server`
along with the GOAD lab. The dashboard goes offline. Worse, the
shared `tflock` DynamoDB table — used by every OTHER deployment's
remote state locking — is also wiped. Every other concurrent
deployment is now unable to acquire a state lock.

## Detection

`GET /api/deploy/state-summary/<project>` returns:

```json
{
  "expected_modules": ["vpc", "security", "attack_box", "cs_storage", "goad"],
  "actual_modules":   ["vpc", "security", "attack_box", "cs_storage", "goad", "dashboard_server"],
  "foreign_modules":  ["dashboard_server"]
}
```

The Manage page polls this on entry and surfaces a danger callout above
the hero when `foreign_modules` is non-empty.

`POST /api/deploy/destroy` returns HTTP 409 with `error: "foreign_modules_in_state"`
when an operator confirms destroy on a workspace with foreign modules.
The response includes a structured `actions` array describing the two
recovery paths.

## Recovery paths

### Recommended: Detach foreign modules from state

```
POST /api/deploy/detach-foreign/<project>
```

Runs `terraform state rm module.<name>` for each foreign module. State
tracking stops; the AWS resources keep running. The dashboard server
stays up, the shared tflock stays alive, and destroy on this workspace
is now safe.

### Last-resort: Force destroy (destroys foreign modules too)

```
POST /api/deploy/destroy?force_foreign=1
```

The URL flag is the only override. The override is recorded in the
audit log as `deploy.destroy.force_foreign` with the list of foreign
modules at decision time.

This is the right answer only if the foreign modules are no longer
needed and you've decided to delete them along with the rest of the
deployment. **Do not use this to destroy a goad/c2 deployment whose
state happens to contain dashboard_server.**

## Prevention

- Never `terraform apply` foreign modules into a deployment workspace.
  Use the dedicated `__dashboard__` workspace for management
  infrastructure (dashboard server, shared lock tables, shared S3
  state bucket).
- Per-project tfvars live under `configs/<project>.tfvars`. The
  deployment-type-conditional `count` blocks in `terraform/main.tf`
  determine which modules legitimately exist for a given
  `deployment_type`. If you add a new module to a deployment family,
  update `webapp/backend/utils/destroy_safety.py:_BASE_MODULES` or the
  type-specific set so the safety check knows about it.

## Code map

- Backend safety helper: `webapp/backend/utils/destroy_safety.py`
- Destroy guard: `webapp/backend/routes/deploy.py` → `@bp.route('/destroy')`
- State-summary endpoint: `webapp/backend/routes/deploy.py` → `@bp.route('/state-summary/<project>')`
- Detach endpoint: `webapp/backend/routes/deploy.py` → `@bp.route('/detach-foreign/<project>')`
- Frontend banner + handler: `webapp/frontend/js/app.js` — `APP.manage._renderForeignModulesBanner`, `APP.manage._handleForeignModulesError`
- Tests: `tests/backend/test_destroy_safety.py`, `tests/browser/test_v3_destroy_safety.spec.js`
