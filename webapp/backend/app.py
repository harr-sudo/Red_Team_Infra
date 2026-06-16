#!/usr/bin/env python3
"""
Red Team Infrastructure Dashboard Server
Centralized web interface for managing red team infrastructure deployment.
Access via SSH tunnel only — Flask binds to loopback, loopback guard rejects all other sources.
"""

import os
import sys
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Frontend path
frontend_path = Path(__file__).parent.parent / 'frontend'

from flask import Flask, g, render_template, jsonify, request, send_from_directory, make_response, redirect
from flask_cors import CORS
from webapp.backend.routes import config, deploy, aws_check, health, goad, architecture, tools, profiles, costs, setup_check, beacon, terminal, runtime_probes
from webapp.backend.routes import operators as operators_routes
from webapp.backend.routes import audit as audit_routes
from webapp.backend.routes import bolton as bolton_routes
from webapp.backend.routes import palette as palette_routes
from webapp.backend.routes import presence as presence_routes
from webapp.backend.routes import test_lab as test_lab_routes
from webapp.backend.routes import settings as settings_routes
from webapp.backend.services import operator_service
from webapp.backend.services import identity_token, peercred_identity

_logger = logging.getLogger(__name__)

# Task #54 — guard against misconfigured test-isolation env var. If an
# operator sets DASHBOARD_STATE_DIR to a path that contains the real
# ~/.dashboard segment they've defeated the isolation we wanted. Emit a
# warning at startup so the misconfiguration is visible — never a hard
# error, since some debug loops legitimately point at the live store.
_dashboard_state_dir = os.environ.get("DASHBOARD_STATE_DIR")
if _dashboard_state_dir:
    _real_home = str(Path.home() / ".dashboard")
    if _real_home in _dashboard_state_dir:
        _logger.warning(
            "DASHBOARD_STATE_DIR=%s overlaps the live operator store at %s — "
            "test runs will pollute production data. Use /tmp/playwright-dashboard-state "
            "or similar.",
            _dashboard_state_dir,
            _real_home,
        )

# --- Versioning helpers (P1 #7.6) -----------------------------------------
# Resolve the VERSION file at repo root. Works whether the app is run from
# the venv locally or from systemd on the dashboard EC2 — both cases reach
# the repo root via three .parent hops from this file.
_VERSION_FILE = project_root / 'VERSION'


def _read_version_file():
    """Read the VERSION file. Returns 'unknown' on any failure so the app
    never fails to start because of versioning."""
    try:
        return _VERSION_FILE.read_text(encoding='utf-8').strip() or 'unknown'
    except (OSError, UnicodeDecodeError) as exc:
        _logger.warning("Could not read VERSION file at %s: %s", _VERSION_FILE, exc)
        return 'unknown'


def _read_git_sha():
    """Return short (7-char) git SHA, or 'unknown' if git is unavailable or
    this is not a git checkout. Captured once at startup — do not call per
    request."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short=7', 'HEAD'],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            sha = result.stdout.strip()
            if sha:
                return sha[:7]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        _logger.warning("git rev-parse failed: %s", exc)
    return 'unknown'


# Capture once at startup — module-level constants (no per-request cost).
_VERSION = _read_version_file()
_GIT_SHA = _read_git_sha()
_BUILT_AT = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def get_version_info():
    """Return cached version metadata for /api/ and /api/version."""
    return {
        'version': _VERSION,
        'git_sha': _GIT_SHA,
        'built_at': _BUILT_AT,
    }
# --------------------------------------------------------------------------

# Initialize Flask app
app = Flask(__name__, 
            static_folder=str(frontend_path),
            static_url_path='',
            template_folder=str(frontend_path))
CORS(app, origins=["http://127.0.0.1:5000", "http://localhost:5000"])

# Configure file upload limits
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size


# Defense-in-depth: reject requests not from loopback (SSH tunnel delivers from 127.0.0.1)
@app.before_request
def enforce_loopback():
    if request.remote_addr != '127.0.0.1':
        return jsonify({"error": "Access denied - connect via SSH tunnel"}), 403


# Resolve the current operator on every request and bind to flask.g.operator.
# The dashboard_operator cookie holds an HMAC-signed identity token bound to the
# operator's SSH-authenticated Linux user (SO_PEERCRED-minted); resolve_from_request
# verifies the signature and, in prod, trusts ONLY a valid token. See M-Operators
# + services/identity_token.py.
@app.before_request
def _resolve_operator():
    g.operator = operator_service.resolve_from_request(request)

# Register blueprints
app.register_blueprint(config.bp, url_prefix='/api/config')
app.register_blueprint(deploy.bp, url_prefix='/api/deploy')
app.register_blueprint(aws_check.bp, url_prefix='/api/aws')
app.register_blueprint(health.bp, url_prefix='/api/health')
app.register_blueprint(goad.bp)  # GOAD routes at /api/goad
app.register_blueprint(architecture.bp)  # Architecture docs at /api/architecture
app.register_blueprint(tools.bp, url_prefix='/api/tools')
app.register_blueprint(profiles.bp, url_prefix='/api/profiles')
app.register_blueprint(costs.bp, url_prefix='/api/costs')
app.register_blueprint(setup_check.bp, url_prefix='/api/setup-check')
app.register_blueprint(runtime_probes.bp, url_prefix='/api/health/probes')  # Mission Control runtime probes
app.register_blueprint(beacon.bp, url_prefix='/api/beacon')
app.register_blueprint(terminal.bp)
app.register_blueprint(operators_routes.bp)
app.register_blueprint(audit_routes.bp)
app.register_blueprint(bolton_routes.bp)  # Vulnerable-lab bolt-on feature
app.register_blueprint(palette_routes.bp)  # v3 — ⌘K command palette (Agent B)
app.register_blueprint(presence_routes.bp)  # task #33 — soft presence banner
app.register_blueprint(test_lab_routes.bp)  # Test lab — bolt-on validation lab (TESTLAB_DESIGN.md)
app.register_blueprint(settings_routes.bp)  # Dashboard settings — Dashboard Server EIP get/override

# Initialize WebSocket support for terminal
terminal.init_sock(app)

# Start the SO_PEERCRED identity minter — authenticates operators by their
# SSH-bound uid and mints signed identity tokens. Prod/Linux only; no-op in dev.
peercred_identity.start()


@app.route('/login')
def operator_login():
    """One-time identity handoff: the connect helper opens this URL with a
    single-use code (?c=) minted by the SO_PEERCRED socket. We redeem the code
    EXACTLY once (so a leaked URL/log line is near-worthless), then mint the real
    12h signed token and set it as the HttpOnly, SameSite=Strict cookie."""
    code = request.args.get('c', '')
    op_id = identity_token.redeem_handoff(code)
    if not op_id:
        return jsonify({"error": "invalid, expired, or already-used login code"}), 401
    token = identity_token.mint(op_id)
    resp = make_response(redirect('/'))
    resp.set_cookie('dashboard_operator', token,
                    max_age=identity_token.TTL_DEFAULT,
                    httponly=True, samesite='Strict', path='/')
    return resp


@app.route('/api/identity/dev-login', methods=['POST'])
def dev_login():
    """Dev-only: mint a signed token for the local user so a laptop instance
    uses the same secure cookie path. Disabled in production (where operators
    must obtain their token from the SO_PEERCRED socket via the connect helper)."""
    if not operator_service.is_dev_mode():
        return jsonify({"error": "dev-login is disabled in production"}), 403
    import pwd
    try:
        raw = pwd.getpwuid(os.getuid()).pw_name
    except Exception:
        raw = "operator"
    # Canonicalize to the shared operator-id grammar so the stored id and the
    # minted token id match (same normalization the SO_PEERCRED minter applies).
    name = operator_service.canonical_id(raw) or "operator"
    if not operator_service.get(name):
        try:
            operator_service.add(name, raw.capitalize(), "#1b4965")
        except Exception:
            pass
    token = identity_token.mint(name)
    resp = make_response(jsonify({"success": True, "operator": name}))
    resp.set_cookie('dashboard_operator', token,
                    max_age=identity_token.TTL_DEFAULT,
                    httponly=True, samesite='Strict', path='/')
    return resp


@app.route('/api/whoami', methods=['GET'])
def whoami():
    """Current operator identity — resolved SERVER-SIDE on every request from the
    signed identity token (SO_PEERCRED-minted, bound to the SSH-authenticated
    Linux user), never from a client-supplied value. Replaces the old, spoofable
    ss/ps SSH-trace heuristic. Returns 'unknown' in prod when the cookie is
    missing/invalid."""
    op = getattr(g, 'operator', None) or operator_service._unknown()
    return jsonify({"operator": op.get("id", "unknown"),
                    "display": op.get("display"),
                    "color": op.get("color")})

# Serve frontend
#
# 2026-05-22 — cache-busting version stamp. Browsers (especially Chrome
# and Safari) prefer their in-memory copy of JS/CSS on soft reloads even
# when the server sends `Cache-Control: no-cache`. The only reliable
# bust is a fresh URL. We compute a short hash from the JS+CSS mtimes
# on every index render, expose it as `?v=<hash>` on each asset URL,
# AND surface it via `/api/version/assets` so the frontend can detect
# version drift and force a hard reload when stale.

def _asset_version() -> str:
    """Short hex of the max-mtime across app.js, style.css, index.html.

    Recomputed per index render so a developer save triggers a new URL
    immediately — the browser fetches the fresh file because the URL is
    new, not because of a cache header that the browser may ignore.
    """
    import hashlib
    parts = []
    for rel in ('js/app.js', 'css/style.css', 'css/palette.css', 'index.html'):
        p = frontend_path / rel
        try:
            parts.append(f'{rel}:{p.stat().st_mtime_ns}')
        except OSError:
            pass
    if not parts:
        return '0'
    return hashlib.sha1('|'.join(parts).encode()).hexdigest()[:10]


@app.route('/')
def index():
    """Serve main application page with a cache-bust query string on assets."""
    return render_template('index.html', asset_version=_asset_version())


@app.route('/api/version/assets', methods=['GET'])
def api_asset_version():
    """Return the current asset version hash so the frontend can poll for
    drift and prompt a hard reload when its loaded version is stale.
    """
    return jsonify({'success': True, 'asset_version': _asset_version()})


@app.route('/css/<path:filename>')
def serve_css(filename):
    """Serve CSS files"""
    response = send_from_directory(str(frontend_path / 'css'), filename)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/js/<path:filename>')
def serve_js(filename):
    """Serve JavaScript files"""
    response = send_from_directory(str(frontend_path / 'js'), filename)
    # Disable caching for development
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/assets/<path:filename>')
def serve_assets(filename):
    """Serve asset files"""
    return send_from_directory(str(frontend_path / 'assets'), filename)

@app.route('/api/')
def api_info():
    """API information endpoint"""
    return jsonify({
        'name': 'Red Team Infrastructure API',
        'version': get_version_info()['version'],
        'endpoints': {
            'config': '/api/config',
            'deploy': '/api/deploy',
            'aws': '/api/aws',
            'goad': '/api/goad',
            'costs': '/api/costs'
        }
    })


@app.route('/api/version')
def api_version():
    """Version metadata: VERSION file content + git SHA + startup timestamp."""
    return jsonify(get_version_info())


# Preview routes (P1 #7.7 — T1 design pilot)
# These are temporary — slated for removal at D1 completion per §17/§24.
_PREVIEW_DIR = project_root / 'webapp' / 'frontend' / 'preview'


@app.route('/preview/header')
def preview_header_compare():
    """Side-by-side compare of header-baseline.html and header-taste*.html.
    Honors ?variant=baseline|taste|taste-v2|taste-v3|taste-v4|both (default both)."""
    variant = request.args.get('variant', 'both')
    if variant == 'baseline':
        return send_from_directory(str(_PREVIEW_DIR), 'header-baseline.html')
    if variant == 'taste':
        return send_from_directory(str(_PREVIEW_DIR), 'header-taste.html')
    if variant == 'taste-v2':
        return send_from_directory(str(_PREVIEW_DIR), 'header-taste-v2.html')
    if variant == 'taste-v3':
        return send_from_directory(str(_PREVIEW_DIR), 'header-taste-v3.html')
    if variant == 'taste-v4':
        return send_from_directory(str(_PREVIEW_DIR), 'header-taste-v4.html')
    # Default: both side-by-side (compare view served from compare HTML below)
    return send_from_directory(str(_PREVIEW_DIR), 'header-compare.html')


@app.route('/preview/header/baseline')
def preview_header_baseline():
    return send_from_directory(str(_PREVIEW_DIR), 'header-baseline.html')


@app.route('/preview/header/taste')
def preview_header_taste():
    return send_from_directory(str(_PREVIEW_DIR), 'header-taste.html')


@app.route('/preview/header/taste-v2')
def preview_header_taste_v2():
    return send_from_directory(str(_PREVIEW_DIR), 'header-taste-v2.html')


@app.route('/preview/header/taste-v3')
def preview_header_taste_v3():
    return send_from_directory(str(_PREVIEW_DIR), 'header-taste-v3.html')


@app.route('/preview/header/taste-v4')
def preview_header_taste_v4():
    return send_from_directory(str(_PREVIEW_DIR), 'header-taste-v4.html')


# P1 #7.6 — serve the project CHANGELOG.md as plain-text (Markdown).
# The frontend version modal links here; users open in a new tab.
_CHANGELOG_FILE = project_root / 'CHANGELOG.md'


@app.route('/changelog')
def changelog():
    """Return the raw CHANGELOG.md content. 404 with JSON if missing."""
    try:
        content = _CHANGELOG_FILE.read_text(encoding='utf-8')
    except FileNotFoundError:
        return jsonify({'error': 'CHANGELOG.md not found'}), 404
    except (OSError, UnicodeDecodeError) as exc:
        _logger.warning("Could not read CHANGELOG.md at %s: %s", _CHANGELOG_FILE, exc)
        return jsonify({'error': 'Could not read CHANGELOG.md'}), 500
    return content, 200, {'Content-Type': 'text/markdown; charset=utf-8'}


# Serve internal design docs (read-only) so the dashboard can deep-link to
# specs like TESTLAB_DESIGN.md from inline help links. Allowlisted to keep
# this from accidentally turning into an arbitrary-file read endpoint.
_ALLOWED_DOCS = {
    'internal/TESTLAB_DESIGN.md',
}


@app.route('/docs/<path:doc_path>')
def serve_doc(doc_path):
    """Return one of a small allowlist of read-only docs as text/markdown."""
    if doc_path not in _ALLOWED_DOCS:
        return jsonify({'error': 'doc not allowlisted'}), 404
    target = project_root / 'docs' / doc_path
    try:
        content = target.read_text(encoding='utf-8')
    except FileNotFoundError:
        return jsonify({'error': f'{doc_path} not found'}), 404
    except (OSError, UnicodeDecodeError) as exc:
        _logger.warning("Could not read %s: %s", target, exc)
        return jsonify({'error': 'read error'}), 500
    return content, 200, {'Content-Type': 'text/markdown; charset=utf-8'}

if __name__ == '__main__':
    # Port defaults to 5000 (the SSH-tunnel convention); override with PORT for
    # local dev when 5000 is taken (e.g. macOS AirPlay Receiver).
    _port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print("Red Team Infrastructure Dashboard Server")
    print("=" * 60)
    print(f"Listening on 127.0.0.1:{_port} (SSH tunnel access)")
    print("Press Ctrl+C to stop the server")
    print("=" * 60)

    app.run(
        host='127.0.0.1',  # Localhost only — SSH tunnel provides external access
        port=_port,
        debug=False,
        threaded=True  # Allow concurrent requests (prevents one slow endpoint from blocking all others)
    )

