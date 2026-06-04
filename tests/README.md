# Tests

This directory contains the four-layer test suite for the Red Team Infrastructure dashboard. `tests/backend/` holds pytest-based Python tests (Flask routes, services, AWS interactions via moto) — Layer 1. `tests/cs_contract/` holds Cobalt Strike REST API OpenAPI contract tests (Layer 1.5) that validate request/response shapes against `docs/cobalt-strike-api/spec.js`. `tests/js/` holds Vitest unit tests for frontend JavaScript modules running in jsdom (Layer 2). `tests/browser/` holds Playwright end-to-end browser tests that drive the live dashboard UI (Layer 3). Run the full suite with `make test` from the repo root, or `make test-fast` to skip the slower browser layer.

## Browser test isolation (task #54)

Playwright drives the live Flask server on `:5050`, so without isolation it writes to the real `~/.dashboard/operators.json` + `~/.dashboard/audit.log` + `webapp/state/presence/`. Always start Flask with `DASHBOARD_STATE_DIR` pointing at a throwaway path:

```bash
export DASHBOARD_STATE_DIR=/tmp/playwright-dashboard-state
rm -rf "$DASHBOARD_STATE_DIR"
source venv/bin/activate && PYTHONPATH=. \
  python3 -m flask --app webapp.backend.app run --port 5050 --host 127.0.0.1
# in another shell:
npm run test:browser
```

`tests/browser/global-setup.js` wipes the tmpdir before each suite invocation. If you forget the env var, the globalSetup logs a warning but won't refuse to run — your live store WILL be polluted.

To clean residue from before this fix landed, run `scripts/utilities/reset-dashboard-state.sh`.
