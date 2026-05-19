// Playwright global setup — task #54 test isolation.
//
// Wipes the Playwright dashboard state tmpdir before the browser suite
// runs, so stale operators / audit lines / presence YAML from previous
// runs don't bleed into the new run.
//
// This only touches the tmpdir pointed at by DASHBOARD_STATE_DIR; if
// the operator started Flask without that env var the suite is unsafe
// (will write to ~/.dashboard/) and we emit a loud warning so the
// breakage is visible in CI output. We do NOT abort — some local dev
// loops intentionally point at the live store to repro bugs.

const fs = require('fs');
const path = require('path');

const DEFAULT_TMP = '/tmp/playwright-dashboard-state';

module.exports = async () => {
  const envDir = process.env.DASHBOARD_STATE_DIR;
  if (!envDir) {
    // The Flask server was likely started without DASHBOARD_STATE_DIR.
    // Print a loud banner so the operator notices their live store is
    // about to be mutated.
    // eslint-disable-next-line no-console
    console.warn(
      '\n[playwright] DASHBOARD_STATE_DIR is NOT set. Flask may write to ' +
        '~/.dashboard/ and webapp/state/presence/. See playwright.config.js ' +
        'header for the recommended invocation.\n',
    );
    return;
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
