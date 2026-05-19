"""Task #54 — verify DASHBOARD_STATE_DIR isolates the dashboard state
files (operators, audit log, presence YAML) for Playwright / e2e runs.

The backend pytest conftest monkeypatches the path module-attributes
directly, so these tests use importlib.reload to exercise the
import-time resolver in a clean process state. The conftest fixture
still applies AFTER reload — it reassigns the same module-level names,
so the autouse isolation isn't undone here.
"""
import importlib
import os
from pathlib import Path

import pytest

from webapp.backend.services import audit_service, operator_service, presence_service


@pytest.fixture
def clean_env(monkeypatch):
    """Ensure DASHBOARD_STATE_DIR is unset before each isolation test."""
    monkeypatch.delenv("DASHBOARD_STATE_DIR", raising=False)
    yield


def test_operator_service_defaults_to_home_dashboard(clean_env):
    """Without DASHBOARD_STATE_DIR, _resolve_dashboard_home returns ~/.dashboard."""
    home = operator_service._resolve_dashboard_home()
    assert home == Path.home() / ".dashboard"


def test_audit_service_defaults_to_home_dashboard(clean_env):
    home = audit_service._resolve_dashboard_home()
    assert home == Path.home() / ".dashboard"


def test_presence_service_defaults_to_repo_state_dir(clean_env):
    state_dir = presence_service._resolve_state_dir()
    assert state_dir.parts[-2:] == ("state", "presence")
    # Default lives under webapp/state/presence in the repo, not ~/.dashboard.
    assert str(Path.home() / ".dashboard") not in str(state_dir)


def test_operator_service_honors_env_var(monkeypatch, tmp_path):
    """Setting DASHBOARD_STATE_DIR + reload pins _STORE_PATH under the tmpdir."""
    monkeypatch.setenv("DASHBOARD_STATE_DIR", str(tmp_path))
    reloaded = importlib.reload(operator_service)
    try:
        assert reloaded._STORE_PATH == tmp_path / "operators.json"
        assert reloaded._resolve_dashboard_home() == tmp_path
    finally:
        # Restore default path so the autouse conftest fixture for the
        # rest of the suite still operates against a sane baseline.
        monkeypatch.delenv("DASHBOARD_STATE_DIR", raising=False)
        importlib.reload(operator_service)


def test_audit_service_honors_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_STATE_DIR", str(tmp_path))
    reloaded = importlib.reload(audit_service)
    try:
        assert reloaded._LOG_PATH == tmp_path / "audit.log"
        assert reloaded._resolve_dashboard_home() == tmp_path
    finally:
        monkeypatch.delenv("DASHBOARD_STATE_DIR", raising=False)
        importlib.reload(audit_service)


def test_presence_service_honors_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("DASHBOARD_STATE_DIR", str(tmp_path))
    reloaded = importlib.reload(presence_service)
    try:
        assert reloaded.STATE_DIR == tmp_path / "presence"
        assert reloaded._resolve_state_dir() == tmp_path / "presence"
    finally:
        monkeypatch.delenv("DASHBOARD_STATE_DIR", raising=False)
        importlib.reload(presence_service)


def test_env_var_writes_actually_land_in_tmpdir(monkeypatch, tmp_path):
    """End-to-end: with DASHBOARD_STATE_DIR set, operator add/list goes
    to the tmpdir, not ~/.dashboard. This is the real reproducer for the
    bug Playwright triggered."""
    monkeypatch.setenv("DASHBOARD_STATE_DIR", str(tmp_path))
    reloaded = importlib.reload(operator_service)
    try:
        # Force _STORE_PATH off the conftest's monkeypatch and onto our
        # env-resolved value, then exercise the public add() API.
        assert str(tmp_path) in str(reloaded._STORE_PATH)
        reloaded.add("contrast_pw", "Contrast Pw", "#a31621")
        # The file landed under tmp_path, NOT under ~/.dashboard.
        assert reloaded._STORE_PATH.exists()
        assert reloaded._STORE_PATH.is_relative_to(tmp_path)
        # And ~/.dashboard/operators.json was NOT modified by this call
        # (sanity check — if the resolver is broken this could be true
        # only coincidentally, but importlib.reload guarantees the
        # module-level path picked up our env var).
        live_store = Path.home() / ".dashboard" / "operators.json"
        if live_store.exists():
            live = live_store.read_text()
            assert "contrast_pw" not in live, (
                "operator leaked into ~/.dashboard/operators.json — "
                "test isolation is BROKEN"
            )
    finally:
        monkeypatch.delenv("DASHBOARD_STATE_DIR", raising=False)
        importlib.reload(operator_service)
