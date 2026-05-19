"""task #33 — presence_service + /api/presence tests.

Validates the soft "who else is here" surface used by the simultaneous-
editing banner. Per Decision #23: no locking, no blocking — these tests
only verify the read/write loop, the recency filter, the staleness
sweeper, and the route's response shape.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from webapp.backend.services import presence_service, operator_service


# ──────────────────────────────────────────────────────────────────────
# Isolation — every test gets its own state directory and a fresh
# operator store so the autouse fixture in conftest doesn't pollute the
# real ~/.dashboard between runs.
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolate_presence_state(tmp_path, monkeypatch):
    state_dir = tmp_path / "presence"
    state_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(presence_service, "STATE_DIR", state_dir)
    yield state_dir


# ──────────────────────────────────────────────────────────────────────
# Service-level behavior
# ──────────────────────────────────────────────────────────────────────

def test_heartbeat_persists_entry(_isolate_presence_state):
    presence_service.heartbeat("harris", "c2-adhoc-01", "configure")
    entries = presence_service.list_active("c2-adhoc-01")
    assert len(entries) == 1
    assert entries[0].operator_id == "harris"
    assert entries[0].project == "c2-adhoc-01"
    assert entries[0].page == "configure"


def test_heartbeat_dedups_by_operator(_isolate_presence_state):
    """Two heartbeats from the same operator for the same project leave
    exactly one entry — the second replaces the first (updated page +
    timestamp)."""
    presence_service.heartbeat("harris", "c2-adhoc-01", "configure")
    presence_service.heartbeat("harris", "c2-adhoc-01", "manage")
    entries = presence_service.list_active("c2-adhoc-01")
    assert len(entries) == 1
    assert entries[0].page == "manage"


def test_heartbeat_multiple_operators_same_project(_isolate_presence_state):
    presence_service.heartbeat("harris", "c2-adhoc-01", "configure")
    presence_service.heartbeat("alice", "c2-adhoc-01", "configure")
    presence_service.heartbeat("bob", "c2-adhoc-01", "manage")
    entries = presence_service.list_active("c2-adhoc-01")
    assert {e.operator_id for e in entries} == {"harris", "alice", "bob"}


def test_heartbeat_isolated_per_project(_isolate_presence_state):
    presence_service.heartbeat("harris", "project-a", "configure")
    presence_service.heartbeat("alice", "project-b", "manage")
    a = presence_service.list_active("project-a")
    b = presence_service.list_active("project-b")
    assert [e.operator_id for e in a] == ["harris"]
    assert [e.operator_id for e in b] == ["alice"]


def test_heartbeat_ignores_empty_inputs(_isolate_presence_state):
    """Defensive guard — empty operator_id or project must not crash and
    must not write a file."""
    presence_service.heartbeat("", "c2-adhoc-01", "configure")
    presence_service.heartbeat("harris", "", "configure")
    assert list(_isolate_presence_state.glob("*.yaml")) == []


def test_heartbeat_sanitizes_project_name_for_path(_isolate_presence_state):
    """Path-traversal defense — slashes/dot-dots in a project name must
    not let us escape STATE_DIR."""
    presence_service.heartbeat("harris", "../../etc/passwd", "configure")
    # File must live under STATE_DIR, not anywhere else on disk.
    written = list(_isolate_presence_state.rglob("*.yaml"))
    assert len(written) == 1
    assert _isolate_presence_state in written[0].parents


def test_list_active_filters_stale_entries(_isolate_presence_state, monkeypatch):
    """An entry older than the freshness window is not returned even
    though it's still on disk."""
    presence_service.heartbeat("harris", "c2-adhoc-01", "configure")

    # Walk the on-disk timestamp back 5 minutes — older than the 60s
    # default freshness threshold.
    path = _isolate_presence_state / "c2-adhoc-01.yaml"
    raw = path.read_text()
    old_ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    # Replace the heartbeat timestamp; YAML round-trip is finicky so we
    # just substring-replace the ISO field.
    import re
    raw = re.sub(r"last_heartbeat: .*", f"last_heartbeat: '{old_ts}'", raw)
    path.write_text(raw)

    assert presence_service.list_active("c2-adhoc-01") == []
    # ... but with a generous window the entry IS returned.
    assert len(presence_service.list_active("c2-adhoc-01", since_seconds=3600)) == 1


def test_list_active_sorted_most_recent_first(_isolate_presence_state):
    """Multiple operators are returned in descending heartbeat order."""
    presence_service.heartbeat("alice", "c2-adhoc-01", "configure")
    # Force second heartbeat to be measurably later than the first.
    import time
    time.sleep(0.01)
    presence_service.heartbeat("harris", "c2-adhoc-01", "manage")
    entries = presence_service.list_active("c2-adhoc-01")
    assert entries[0].operator_id == "harris"
    assert entries[1].operator_id == "alice"


def test_list_active_unknown_project_returns_empty(_isolate_presence_state):
    assert presence_service.list_active("never-existed") == []


def test_cleanup_stale_removes_old_entries(_isolate_presence_state):
    presence_service.heartbeat("harris", "c2-adhoc-01", "configure")
    presence_service.heartbeat("alice", "c2-adhoc-01", "configure")

    # Age the alice entry beyond the stale cutoff.
    path = _isolate_presence_state / "c2-adhoc-01.yaml"
    import yaml as _yaml
    data = _yaml.safe_load(path.read_text())
    data["entries"]["alice"]["last_heartbeat"] = (
        datetime.now(timezone.utc) - timedelta(hours=1)
    ).isoformat()
    path.write_text(_yaml.safe_dump(data, sort_keys=True))

    removed = presence_service.cleanup_stale(max_age_seconds=60)
    assert removed == 1
    remaining = presence_service.list_active("c2-adhoc-01", since_seconds=3600)
    assert [e.operator_id for e in remaining] == ["harris"]


def test_cleanup_stale_removes_empty_files(_isolate_presence_state):
    """If every entry in a project file is stale the file itself is
    deleted to avoid accumulating empty husks."""
    presence_service.heartbeat("alice", "c2-adhoc-01", "configure")
    path = _isolate_presence_state / "c2-adhoc-01.yaml"
    assert path.exists()

    import yaml as _yaml
    data = _yaml.safe_load(path.read_text())
    data["entries"]["alice"]["last_heartbeat"] = (
        datetime.now(timezone.utc) - timedelta(hours=1)
    ).isoformat()
    path.write_text(_yaml.safe_dump(data, sort_keys=True))

    removed = presence_service.cleanup_stale(max_age_seconds=60)
    assert removed == 1
    assert not path.exists()


def test_cleanup_stale_with_no_state_dir_is_noop(tmp_path, monkeypatch):
    """The sweeper must not crash when the state dir doesn't exist."""
    missing = tmp_path / "does-not-exist"
    monkeypatch.setattr(presence_service, "STATE_DIR", missing)
    assert presence_service.cleanup_stale() == 0


def test_others_excludes_caller(_isolate_presence_state):
    presence_service.heartbeat("harris", "c2-adhoc-01", "configure")
    presence_service.heartbeat("alice", "c2-adhoc-01", "configure")
    others = presence_service.others("harris", "c2-adhoc-01")
    assert [e.operator_id for e in others] == ["alice"]


# ──────────────────────────────────────────────────────────────────────
# Route-level behavior — exercises the blueprint + before_request hook.
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def two_operators(flask_client):
    """Seed an operator store with harris + alice so cookie-driven
    identity switching has something to switch to."""
    flask_client.post("/api/operators", json={"id": "harris", "display": "Harris"})
    flask_client.post("/api/operators", json={"id": "alice", "display": "Alice"})
    return ["harris", "alice"]


def test_route_heartbeat_returns_others_empty_on_first_call(flask_client, two_operators):
    flask_client.set_cookie("dashboard_operator", "harris", domain="localhost")
    resp = flask_client.post(
        "/api/presence/heartbeat",
        json={"project": "c2-adhoc-01", "page": "configure"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["entry"]["operator_id"] == "harris"
    assert data["others"] == []


def test_route_heartbeat_returns_other_operators(flask_client, two_operators):
    # Alice heartbeats first.
    flask_client.set_cookie("dashboard_operator", "alice", domain="localhost")
    flask_client.post(
        "/api/presence/heartbeat",
        json={"project": "c2-adhoc-01", "page": "configure"},
    )

    # Now Harris arrives.
    flask_client.set_cookie("dashboard_operator", "harris", domain="localhost")
    resp = flask_client.post(
        "/api/presence/heartbeat",
        json={"project": "c2-adhoc-01", "page": "configure"},
    )
    data = resp.get_json()
    assert data["success"] is True
    assert data["entry"]["operator_id"] == "harris"
    assert len(data["others"]) == 1
    assert data["others"][0]["operator_id"] == "alice"
    assert data["others"][0]["page"] == "configure"


def test_route_heartbeat_rejects_missing_project(flask_client):
    resp = flask_client.post("/api/presence/heartbeat", json={"page": "configure"})
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_route_get_project_returns_all_entries(flask_client, two_operators):
    flask_client.set_cookie("dashboard_operator", "harris", domain="localhost")
    flask_client.post("/api/presence/heartbeat", json={"project": "c2-adhoc-01", "page": "configure"})
    flask_client.set_cookie("dashboard_operator", "alice", domain="localhost")
    flask_client.post("/api/presence/heartbeat", json={"project": "c2-adhoc-01", "page": "manage"})

    resp = flask_client.get("/api/presence/c2-adhoc-01")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["count"] == 2
    assert {e["operator_id"] for e in data["entries"]} == {"harris", "alice"}


def test_route_get_unknown_project_returns_empty(flask_client):
    resp = flask_client.get("/api/presence/never-existed")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["entries"] == []
    assert data["count"] == 0


def test_route_heartbeat_does_not_audit(flask_client, two_operators):
    """Per Decision #23 + the route docstring — heartbeats must NOT write
    to the audit log (one tick every 30s would dwarf every other
    category)."""
    from webapp.backend.services import audit_service
    pre = len(audit_service.read_recent(limit=500))
    flask_client.set_cookie("dashboard_operator", "harris", domain="localhost")
    flask_client.post("/api/presence/heartbeat", json={"project": "c2-adhoc-01", "page": "configure"})
    post = len(audit_service.read_recent(limit=500))
    assert pre == post
