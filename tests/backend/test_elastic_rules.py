"""Tests for the Elastic detection-rules update flow.

Covers:
  - scripts/utilities/update-elastic-rules.py runs cleanly in a subprocess
    against the live TOML corpus and emits a non-empty summary.
  - POST /api/config/update-elastic-rules returns success when the script
    succeeds and audits the action via audit_service.
  - The endpoint requires an authenticated operator (uses g.operator) and
    records the actor in the audit row.
  - The endpoint handles script failure gracefully (500 + JSON error,
    Flask does not crash).

Subprocess invocations of the generator are mocked at the route layer so
CI doesn't actually re-run the rules generator every time. The one place
the real subprocess runs is the dedicated "script integration" test.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from webapp.backend.services import audit_service, operator_service


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "utilities" / "update-elastic-rules.py"
CORPUS_DIR = PROJECT_ROOT / "Research" / "elastic-detection-rules" / "rules" / "windows"
ROUTE_PATH = "/api/config/update-elastic-rules"


# ─── Helpers ─────────────────────────────────────────────────────────


def _make_success_completed(stdout: str = "Generated: ok\nTotal rules: 128"):
    """Return a CompletedProcess for the JS-generator subprocess call."""
    cp = MagicMock()
    cp.returncode = 0
    cp.stdout = stdout
    cp.stderr = ""
    return cp


def _make_pull_completed(stdout: str = "Already up to date."):
    cp = MagicMock()
    cp.returncode = 0
    cp.stdout = stdout
    cp.stderr = ""
    return cp


def _make_failure_completed(stderr: str = "Error: corpus missing"):
    cp = MagicMock()
    cp.returncode = 1
    cp.stdout = ""
    cp.stderr = stderr
    return cp


def _route_subprocess_side_effect(pull_cp, gen_cp):
    """subprocess.run inside the route is called twice: once for git pull,
    once for the script. Return pull_cp first, then gen_cp."""
    calls = {"n": 0}

    def _side(*args, **kwargs):
        calls["n"] += 1
        return pull_cp if calls["n"] == 1 else gen_cp

    return _side


# ─── 1. Script integration — runs cleanly against the live corpus ─────


@pytest.mark.skipif(not CORPUS_DIR.is_dir(), reason="Elastic corpus not cloned in this checkout")
def test_update_script_subprocess_succeeds():
    """The generator script must exit 0 and print a non-empty summary."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(PROJECT_ROOT),
    )
    assert proc.returncode == 0, f"script failed: {proc.stderr}"
    assert proc.stdout.strip(), "expected non-empty stdout summary"
    # Sanity — emits the expected human-readable summary header.
    assert "Generated:" in proc.stdout
    assert "Total unique rules:" in proc.stdout


# ─── 2. Endpoint — success path returns 200 + audit row ───────────────


def test_endpoint_success_returns_200_and_results(flask_client):
    """Happy path: git pull + generator both succeed; response carries
    both stdout strings and success=True."""
    pull_cp = _make_pull_completed("Already up to date.")
    gen_cp = _make_success_completed("Generated: ok")
    with patch("webapp.backend.routes.config.subprocess.run",
               side_effect=_route_subprocess_side_effect(pull_cp, gen_cp)):
        resp = flask_client.post(ROUTE_PATH)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert "results" in body
    assert body["results"]["generate"]  # non-empty
    assert body["results"]["git_pull"]  # non-empty


def test_endpoint_success_writes_audit_entry(flask_client):
    """The success path must append a config.update_elastic_rules audit row."""
    pull_cp = _make_pull_completed()
    gen_cp = _make_success_completed()
    with patch("webapp.backend.routes.config.subprocess.run",
               side_effect=_route_subprocess_side_effect(pull_cp, gen_cp)):
        resp = flask_client.post(ROUTE_PATH)
    assert resp.status_code == 200
    entries = audit_service.read_recent(action_prefix="config.update_elastic_rules")
    assert len(entries) >= 1
    entry = entries[0]
    assert entry["action"] == "config.update_elastic_rules"
    # Details should mark the run successful.
    assert entry.get("details", {}).get("status") == "ok"


def test_endpoint_uses_operator_identity_for_audit(flask_client):
    """The audit row's op field must reflect the resolved operator (g.operator)."""
    operator_service.add("harris", "Harris K", "#a31621")
    flask_client.set_cookie("dashboard_operator", "harris", domain="localhost")
    pull_cp = _make_pull_completed()
    gen_cp = _make_success_completed()
    with patch("webapp.backend.routes.config.subprocess.run",
               side_effect=_route_subprocess_side_effect(pull_cp, gen_cp)):
        resp = flask_client.post(ROUTE_PATH)
    assert resp.status_code == 200
    entries = audit_service.read_recent(action_prefix="config.update_elastic_rules")
    assert any(e["op"] == "harris" for e in entries), \
        f"expected harris in audit log; got {[e['op'] for e in entries]}"


# ─── 3. Endpoint — script failure surfaces as 500 + audit row ─────────


def test_endpoint_returns_500_when_script_fails(flask_client):
    """If the generator returns non-zero, the endpoint must return 500
    with the stderr in the error field — Flask must not crash."""
    pull_cp = _make_pull_completed()
    gen_cp = _make_failure_completed("Error: corpus missing")
    with patch("webapp.backend.routes.config.subprocess.run",
               side_effect=_route_subprocess_side_effect(pull_cp, gen_cp)):
        resp = flask_client.post(ROUTE_PATH)
    assert resp.status_code == 500
    body = resp.get_json()
    assert body["success"] is False
    assert "Error: corpus missing" in body["error"]


def test_endpoint_failure_still_audits(flask_client):
    """Failed runs must still record an audit row — never silently mutate
    (or fail to mutate) state without a trail."""
    pull_cp = _make_pull_completed()
    gen_cp = _make_failure_completed("script blew up")
    with patch("webapp.backend.routes.config.subprocess.run",
               side_effect=_route_subprocess_side_effect(pull_cp, gen_cp)):
        flask_client.post(ROUTE_PATH)
    entries = audit_service.read_recent(action_prefix="config.update_elastic_rules")
    assert len(entries) >= 1
    assert entries[0]["details"]["status"] == "failed"


def test_endpoint_exception_returns_500_no_crash(flask_client):
    """If subprocess.run itself raises (timeout, OSError), the route must
    return 500 with the exception text — never bubble a 500 from the
    Flask error handler."""
    def _raise(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0] if args else "cmd", timeout=120)

    with patch("webapp.backend.routes.config.subprocess.run", side_effect=_raise):
        resp = flask_client.post(ROUTE_PATH)
    assert resp.status_code == 500
    body = resp.get_json()
    assert body["success"] is False
    assert body.get("error")


def test_endpoint_returns_404_when_repo_missing(flask_client, monkeypatch, tmp_path):
    """If the cloned corpus repo is absent, the route returns 404 with a
    helpful clone hint rather than running git pull on nothing."""
    # Repoint project_root at a tmpdir that has no Research/elastic-detection-rules.
    monkeypatch.setattr("webapp.backend.routes.config.project_root", tmp_path)
    resp = flask_client.post(ROUTE_PATH)
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["success"] is False
    assert "detection-rules" in body["error"]
