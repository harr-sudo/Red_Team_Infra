"""v3 PALETTE (Agent B) — backend tests.

Verifies the /api/palette index + selection endpoints:

  - GET /api/palette/index returns the full surface (routes + actions
    + dynamic kinds) in deterministic order
  - POST /api/palette/select dedupes, caps at 20, persists per-operator
  - Different operators see different `recently_used` (per-operator MRU)
  - Selection writes a `palette.select` audit entry

The autouse `_isolate_dashboard_stores` fixture in tests/backend/conftest.py
already redirects operators.json + audit.log to a tmpdir. We additionally
redirect the palette MRU directory here so palette_recent_<op>.json files
don't leak between tests / into the user's real home.
"""
from __future__ import annotations

import json

import pytest

from webapp.backend.routes import palette as palette_route
from webapp.backend.services import audit_service, operator_service


# ─── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolate_palette_mru(tmp_path, monkeypatch):
    """Redirect the palette MRU directory to a per-test tmpdir."""
    monkeypatch.setattr(palette_route, "_RECENT_DIR", tmp_path / "palette_mru")


@pytest.fixture
def two_operators(tmp_path):
    """Seed two operators so cookie-based switching can be exercised."""
    # operator_service is already pointed at a tmp operators.json via the
    # autouse fixture in conftest.py. Add two distinct profiles.
    operator_service.add("harris", "Harris", "#a31621")
    operator_service.add("alice", "Alice", "#3b82f6")
    return ["harris", "alice"]


# ─── GET /api/palette/index ────────────────────────────────────────────────


def test_index_returns_success_envelope(flask_client):
    r = flask_client.get("/api/palette/index")
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert isinstance(body["items"], list)
    assert "recently_used" in body
    assert "generated_at" in body


def test_index_includes_all_canonical_routes(flask_client):
    r = flask_client.get("/api/palette/index")
    items = r.get_json()["items"]
    ids = {it["id"] for it in items}
    # Spot-check core route ids that the JS dispatcher relies on.
    must_include = [
        "route:dashboard",
        "route:dep.configure",
        "route:dep.deploy",
        "route:dep.manage",
        "route:dep.cleanup",
        "route:ops.beacons",
        "route:ops.terminal",
        "route:ops.payloads",
        "route:settings",
        "route:settings.general",
        "route:settings.prereqs",
        "route:settings.domains",
        "route:settings.secrets",
        "route:settings.services",
        "route:settings.cost",
        "route:settings.prefs",
        "route:settings.roadmap",
    ]
    for needed in must_include:
        assert needed in ids, f"missing route id: {needed}"


def test_index_includes_primary_actions(flask_client):
    r = flask_client.get("/api/palette/index")
    items = r.get_json()["items"]
    ids = {it["id"] for it in items}
    for needed in [
        "action:new-deployment",
        "action:switch-theme",
        "action:add-operator",
        "action:run-health-check",
        "action:view-architecture",
    ]:
        assert needed in ids, f"missing action id: {needed}"


def test_index_items_all_have_required_fields(flask_client):
    r = flask_client.get("/api/palette/index")
    items = r.get_json()["items"]
    for it in items:
        assert "id" in it and isinstance(it["id"], str) and it["id"]
        assert "kind" in it and it["kind"]
        assert "label" in it and it["label"]
        assert "target" in it and isinstance(it["target"], dict)


def test_index_order_is_deterministic(flask_client):
    r1 = flask_client.get("/api/palette/index").get_json()["items"]
    r2 = flask_client.get("/api/palette/index").get_json()["items"]
    # Compare the route/action prefix (static items). Dynamic items may
    # appear / disappear across calls if the suite touches state but
    # the static head should always match between two back-to-back calls.
    head1 = [i["id"] for i in r1 if i["kind"] in ("route", "action")]
    head2 = [i["id"] for i in r2 if i["kind"] in ("route", "action")]
    assert head1 == head2


def test_index_includes_operator_items(flask_client, two_operators):
    r = flask_client.get("/api/palette/index")
    items = r.get_json()["items"]
    op_ids = {it["id"] for it in items if it["kind"] == "operator"}
    assert "operator:harris" in op_ids
    assert "operator:alice" in op_ids


def test_index_kinds_match_known_enum(flask_client, two_operators):
    """Every item must carry one of the documented kinds."""
    r = flask_client.get("/api/palette/index")
    items = r.get_json()["items"]
    allowed = {
        "route", "action", "deployment", "beacon", "session",
        "operator", "audit-entry", "vuln", "setting",
    }
    for it in items:
        assert it["kind"] in allowed, f"unexpected kind: {it['kind']}"


def test_index_caps_at_safety_limit(flask_client, monkeypatch):
    """The hard cap protects against runaway audit/catalog inflating the
    response. Set the cap low and prove items truncates."""
    monkeypatch.setattr(palette_route, "_MAX_ITEMS", 5)
    r = flask_client.get("/api/palette/index")
    items = r.get_json()["items"]
    assert len(items) <= 5


# ─── POST /api/palette/select ──────────────────────────────────────────────


def test_select_requires_id(flask_client):
    r = flask_client.post("/api/palette/select", json={})
    assert r.status_code == 400
    assert r.get_json()["success"] is False


def test_select_rejects_empty_id(flask_client):
    r = flask_client.post("/api/palette/select", json={"id": "   "})
    assert r.status_code == 400


def test_select_records_mru(flask_client, two_operators):
    flask_client.set_cookie("dashboard_operator", "harris", domain="localhost")
    flask_client.post("/api/palette/select", json={"id": "route:dashboard"})
    flask_client.post("/api/palette/select", json={"id": "action:new-deployment"})
    r = flask_client.get("/api/palette/index")
    recents = r.get_json()["recently_used"]
    # Most-recent first.
    assert recents[:2] == ["action:new-deployment", "route:dashboard"]


def test_select_dedupes_existing_id(flask_client, two_operators):
    flask_client.set_cookie("dashboard_operator", "harris", domain="localhost")
    flask_client.post("/api/palette/select", json={"id": "route:dashboard"})
    flask_client.post("/api/palette/select", json={"id": "route:settings"})
    flask_client.post("/api/palette/select", json={"id": "route:dashboard"})
    r = flask_client.get("/api/palette/index")
    recents = r.get_json()["recently_used"]
    # The repeat should bubble to the front, leaving exactly two entries.
    assert recents == ["route:dashboard", "route:settings"]


def test_select_caps_at_max_recent(flask_client, two_operators, monkeypatch):
    """MRU is capped — older entries fall off the bottom."""
    monkeypatch.setattr(palette_route, "_MAX_RECENT", 5)
    flask_client.set_cookie("dashboard_operator", "harris", domain="localhost")
    for i in range(10):
        flask_client.post("/api/palette/select", json={"id": f"id-{i}"})
    r = flask_client.get("/api/palette/index")
    recents = r.get_json()["recently_used"]
    assert len(recents) == 5
    # Most-recent (id-9) at the head, oldest in the cap (id-5) at the tail.
    assert recents[0] == "id-9"
    assert recents[-1] == "id-5"


def test_different_operators_see_different_recents(flask_client, two_operators):
    # Flask test_client.set_cookie REPLACES any cookie with the same
    # (name, path, domain) — no need to delete first.
    flask_client.set_cookie("dashboard_operator", "harris", domain="localhost")
    flask_client.post("/api/palette/select", json={"id": "route:dashboard"})

    flask_client.set_cookie("dashboard_operator", "alice", domain="localhost")
    flask_client.post("/api/palette/select", json={"id": "action:switch-theme"})

    # Each operator's GET reflects only their own MRU.
    flask_client.set_cookie("dashboard_operator", "harris", domain="localhost")
    harris_recents = flask_client.get("/api/palette/index").get_json()["recently_used"]

    flask_client.set_cookie("dashboard_operator", "alice", domain="localhost")
    alice_recents = flask_client.get("/api/palette/index").get_json()["recently_used"]

    assert harris_recents == ["route:dashboard"]
    assert alice_recents == ["action:switch-theme"]


def test_select_writes_audit_entry(flask_client, two_operators, tmp_path, monkeypatch):
    # Audit log already pointed at tmpdir by conftest autouse.
    flask_client.set_cookie("dashboard_operator", "harris", domain="localhost")
    flask_client.post("/api/palette/select", json={"id": "route:dashboard"})
    entries = audit_service.read_recent(limit=10)
    palette_rows = [e for e in entries if e.get("action") == "palette.select"]
    assert len(palette_rows) == 1
    assert palette_rows[0]["op"] == "harris"
    assert palette_rows[0]["target"] == "route:dashboard"


def test_select_path_traversal_is_neutralised(flask_client, monkeypatch):
    """The recent_path() builder must reject path-traversal characters in
    operator ids. We can't easily forge an arbitrary operator id (the
    middleware falls back to default for unknown ids), but the helper is
    used internally so test it directly."""
    p = palette_route._recent_path("../../etc/passwd")
    # The dangerous chars are stripped — only [A-Za-z0-9_-] remain.
    assert "etcpasswd" in p.name
    assert ".." not in p.name
    assert "/" not in p.name


def test_index_recently_used_is_empty_for_fresh_operator(flask_client, two_operators):
    flask_client.set_cookie("dashboard_operator", "harris", domain="localhost")
    r = flask_client.get("/api/palette/index")
    assert r.get_json()["recently_used"] == []
