"""M-Operators Agent A — middleware + routes integration tests.

Uses the existing flask_client fixture. Verifies:
- /api/operators GET returns list + current
- The before_request hook resolves g.operator from the dashboard_operator cookie
- /api/operators/switch sets the cookie
- /api/operators POST + DELETE behave correctly
- /api/audit returns most-recent-first entries
"""
import pytest

from webapp.backend.services import operator_service, audit_service


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Redirect operator + audit storage to a tmpdir for every test in
    this module so we never touch the real ~/.dashboard/."""
    op_path = tmp_path / "operators.json"
    audit_path = tmp_path / "audit.log"
    monkeypatch.setattr(operator_service, "_STORE_PATH", op_path)
    monkeypatch.setattr(audit_service, "_LOG_PATH", audit_path)
    yield


def test_operators_list_returns_seeded_default(flask_client):
    resp = flask_client.get("/api/operators")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert isinstance(data["operators"], list)
    assert len(data["operators"]) >= 1
    assert data["current"]["id"] == data["default"]


def test_operators_resolve_default_without_cookie(flask_client):
    """Hitting any endpoint without a cookie sets g.operator to default."""
    resp = flask_client.get("/api/operators")
    assert resp.status_code == 200
    data = resp.get_json()
    # current must equal default when no cookie set
    assert data["current"]["id"] == data["default"]


def test_operators_resolve_from_cookie(flask_client):
    operator_service.add("harris", "Harris K", "#a31621")
    flask_client.set_cookie("dashboard_operator", "harris", domain="localhost")
    resp = flask_client.get("/api/operators")
    data = resp.get_json()
    assert data["current"]["id"] == "harris"


def test_operators_unknown_cookie_falls_back_to_default(flask_client):
    flask_client.set_cookie("dashboard_operator", "ghost", domain="localhost")
    resp = flask_client.get("/api/operators")
    data = resp.get_json()
    # Unknown id → falls back to default
    assert data["current"]["id"] == data["default"]


def test_operators_add_endpoint(flask_client):
    resp = flask_client.post(
        "/api/operators",
        json={"id": "alice", "display": "Alice", "color": "#3b82f6"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["operator"]["id"] == "alice"

    # Audit log should contain the add event
    entries = audit_service.read_recent()
    assert any(e["action"] == "operator.add" and e["target"] == "alice" for e in entries)


def test_operators_add_duplicate_returns_400(flask_client):
    flask_client.post("/api/operators", json={"id": "alice"})
    resp = flask_client.post("/api/operators", json={"id": "alice"})
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_operators_add_invalid_id_returns_400(flask_client):
    resp = flask_client.post("/api/operators", json={"id": "has spaces"})
    assert resp.status_code == 400


def test_operators_remove_endpoint(flask_client):
    flask_client.post("/api/operators", json={"id": "alice"})
    resp = flask_client.delete("/api/operators/alice")
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    entries = audit_service.read_recent()
    assert any(e["action"] == "operator.remove" and e["target"] == "alice" for e in entries)


def test_operators_switch_sets_cookie(flask_client):
    flask_client.post("/api/operators", json={"id": "harris"})
    resp = flask_client.post("/api/operators/switch", json={"id": "harris"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["current"]["id"] == "harris"

    # Verify cookie set on response
    cookies = resp.headers.getlist("Set-Cookie")
    assert any("dashboard_operator=harris" in c for c in cookies)


def test_operators_switch_unknown_id_returns_400(flask_client):
    resp = flask_client.post("/api/operators/switch", json={"id": "ghost"})
    assert resp.status_code == 400


def test_audit_endpoint_returns_recent_entries(flask_client):
    audit_service.write("harris", "deploy.apply", project="c2-adhoc-01")
    audit_service.write("alice", "deploy.plan")
    resp = flask_client.get("/api/audit")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["count"] == 2
    # Most-recent-first
    assert data["entries"][0]["action"] == "deploy.plan"


def test_audit_endpoint_respects_limit(flask_client):
    for i in range(10):
        audit_service.write("harris", f"deploy.step.{i}")
    resp = flask_client.get("/api/audit?limit=3")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 3


def test_audit_endpoint_filters_by_op(flask_client):
    audit_service.write("harris", "deploy.apply")
    audit_service.write("alice", "deploy.plan")
    resp = flask_client.get("/api/audit?op=harris")
    data = resp.get_json()
    assert data["count"] == 1
    assert data["entries"][0]["op"] == "harris"


def test_audit_endpoint_filters_by_action_prefix(flask_client):
    audit_service.write("harris", "deploy.apply")
    audit_service.write("harris", "beacon.exec")
    resp = flask_client.get("/api/audit?action_prefix=deploy.")
    data = resp.get_json()
    assert data["count"] == 1
    assert data["entries"][0]["action"].startswith("deploy.")
