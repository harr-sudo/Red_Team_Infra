// Playwright global setup — task #54 test isolation.
//
// Wipes the Playwright dashboard state tmpdir before the browser suite
// runs, so stale operators / audit lines / presence YAML from previous
// runs don't bleed into the new run.
//
// 2026-05-22 — hardening: the warning-only mode (was: "print a banner
// then continue against the live ~/.dashboard/") let pollution bleed
// across runs and was the actual root cause of multiple "flaky" failures
// in the bolt-on / Settings / operations clusters. Now:
//   - If DASHBOARD_STATE_DIR isn't set AND we're outside CI: ABORT with
//     a copy-paste-able fix banner.
//   - If DASHBOARD_STATE_DIR isn't set AND we ARE in CI (CI=true env):
//     auto-set to /tmp/playwright-dashboard-state-<pid> so CI jobs don't
//     stall on operator config.
//   - Operator can opt out of the abort with ALLOW_LIVE_DASHBOARD_STORE=1
//     (rare — only for repro of a pollution-related bug).
// In every "did run" path the tmpdir is wiped before the suite starts.

const fs = require('fs');
const path = require('path');

const DEFAULT_TMP = '/tmp/playwright-dashboard-state';

module.exports = async () => {
  let envDir = process.env.DASHBOARD_STATE_DIR;
  if (!envDir) {
    if (process.env.CI === 'true' || process.env.CI === '1') {
      envDir = `${DEFAULT_TMP}-${process.pid}`;
      process.env.DASHBOARD_STATE_DIR = envDir;
      // eslint-disable-next-line no-console
      console.log(`[playwright] CI mode — auto-set DASHBOARD_STATE_DIR=${envDir}`);
    } else if (process.env.ALLOW_LIVE_DASHBOARD_STORE === '1') {
      // eslint-disable-next-line no-console
      console.warn('[playwright] ALLOW_LIVE_DASHBOARD_STORE=1 — running against live ~/.dashboard/. Pollution likely.');
      return;
    } else {
      const banner = `
[playwright] FATAL — DASHBOARD_STATE_DIR is not set.

Tests will pollute ~/.dashboard/operators.json + ~/.dashboard/audit.log
+ webapp/state/presence/ if we let them run. Stop now.

Canonical invocation:

    # one-time setup (any shell)
    export DASHBOARD_STATE_DIR=/tmp/playwright-dashboard-state

    # Flask
    rm -rf "$DASHBOARD_STATE_DIR"
    source venv/bin/activate
    flask --app webapp.backend.app run --debug --port 5050 --host 127.0.0.1

    # in another shell — same env var
    export DASHBOARD_STATE_DIR=/tmp/playwright-dashboard-state
    npx playwright test

To opt out of this check (rare — only when repro'ing a pollution bug),
set ALLOW_LIVE_DASHBOARD_STORE=1.
`;
      // eslint-disable-next-line no-console
      console.error(banner);
      throw new Error('DASHBOARD_STATE_DIR not set — see banner above');
    }
  }

  const target = path.resolve(envDir);
  // Defense-in-depth: never let this script rm-rf a non-tmp path. We
  // require either /tmp/ or os.tmpdir() prefix, or a path with the
  // literal "playwright" segment so an accidental
  // DASHBOARD_STATE_DIR=$HOME never nukes the user's home dir.
  const os = require('os');
  const tmpRoot = path.resolve(os.tmpdir());
  const isUnderTmp = target.startsWith(tmpRoot + path.sep) || target.startsWith('/tmp/');
  const looksLikePlaywrightDir = target.includes('playwright');
  if (!isUnderTmp && !looksLikePlaywrightDir) {
    // eslint-disable-next-line no-console
    console.warn(
      `[playwright] Refusing to wipe DASHBOARD_STATE_DIR=${target} — ` +
        'path is neither under tmpdir nor contains "playwright". Aborting reset.',
    );
    return;
  }

  try {
    fs.rmSync(target, { recursive: true, force: true });
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn(`[playwright] Could not reset ${target}: ${err.message}`);
  }
  fs.mkdirSync(target, { recursive: true });
};
