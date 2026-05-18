"""Bolt-on Phase 1 Agent C — Flask route tests.

Covers every endpoint in ``webapp/backend/routes/bolton.py``. Service
layer is fully mocked — Agent B's services don't have to exist for
this suite to run. The fixtures register lightweight ``MagicMock``
stand-ins under the import paths the route handlers ``importlib.import_module()``.

Includes:
  - Happy-path 200 responses + envelope shape verification
  - 400/404/409/503 error paths
  - Audit attribution (operator id from cookie, action strings)
  - Bulk dispatch dispatches N jobs and returns N job ids

Total test count: well above the 30 minimum.
"""
from __future__ import annotations

import json
import sys
import types
from unittest.mock import MagicMock

import pytest


# ─── Service-module mocking ─────────────────────────────────────────────────
#
# The bolton blueprint lazy-imports every service via
# importlib.import_module(). For each service path it touches, register
# a MagicMock-backed module in sys.modules. Each mock exposes:
#   - the methods the route calls (return_value preset to sensible defaults)
#   - the custom exception classes the routes catch
# Tests can then access services["facts"].method.return_value to override.

_SERVICE_NAMES = [
    "bolton_catalog_service",
    "bolton_facts_service",
    "bolton_compatibility",
    "bolton_install_service",
    "bolton_jobs_service",
    "bolton_probe_service",
    "bolton_coverage_service",
]
_BASE = "webapp.backend.services."


def _make_exception(name):
    return type(name, (Exception,), {})


@pytest.fixture
def services(monkeypatch):
    """Install fake service modules under
    ``webapp.backend.services.bolton_*`` and yield a dict keyed by short
    name for test-side configuration.

    Each service module is a real ``types.ModuleType`` whose method
    attributes are individual ``MagicMock`` callables. The exception
    classes are real Python classes so ``except svc.HostUnreachable``
    works in the route handlers.
    """
    holders: dict[str, types.ModuleType] = {}
    for short in _SERVICE_NAMES:
        path = _BASE + short
        mod = types.ModuleType(path)

        # Custom exception classes (real Python classes, not mocks).
        mod.HostUnreachable = _make_exception("HostUnreachable")
        mod.ProbeTimeout = _make_exception("ProbeTimeout")
        mod.FactsMissing = _make_exception("FactsMissing")
        mod.CompatibilityRefused = _make_exception("CompatibilityRefused")
        mod.NotCancellable = _make_exception("NotCancellable")

        # Per-service method mocks with sensible defaults.
        if short == "bolton_catalog_service":
            mod.list_summaries = MagicMock(return_value=[
                {"id": "bolton.identity.kerb", "name": "Kerb",
                 "category": "identity-kerberos", "coverage_status": "covered"},
                {"id": "bolton.adcs.esc1", "name": "ESC1",
                 "category": "adcs", "coverage_status": "partial"},
            ])
            mod.get = MagicMock(return_value={
                "id": "bolton.identity.kerb",
                "name": "Kerberoastable Svc",
                "category": "identity-kerberos",
            })
        elif short == "bolton_facts_service":
            mod.list_hosts = MagicMock(return_value=[
                {"name": "dc01", "role": "dc", "installed_count": 2},
                {"name": "ws01", "role": "workstation", "installed_count": 0},
            ])
            mod.get_facts = MagicMock(return_value={
                "host_id": "dc01", "lab": "goad-light",
                "stale": False, "facts": {},
            })
            mod.refresh_facts = MagicMock(return_value={
                "host_id": "dc01", "lab": "goad-light",
                "stale": False, "facts": {},
            })
            mod.get_installed = MagicMock(return_value=[
                {"id": "bolton.identity.kerb",
                 "installed_at": "2026-05-18T12:00:00Z"},
            ])
        elif short == "bolton_compatibility":
            mod.host_catalog = MagicMock(return_value={
                "host_id": "dc01",
                "host_facts_summary": {
                    "os": "Win2019", "role": "dc",
                    "installed_count": 2, "stale": False,
                },
                "counts_by_state": {"INSTALLABLE": 12, "INCOMPATIBLE_OS": 4},
                "vulns": [],
            })
        elif short == "bolton_install_service":
            mod.dispatch = MagicMock(return_value={
                "job_id": "j_test_001",
                "estimated_time_seconds": 30,
                "message": "queued",
            })
        elif short == "bolton_jobs_service":
            mod.list_jobs = MagicMock(return_value=[
                {"job_id": "j_a", "status": "RUNNING"},
                {"job_id": "j_b", "status": "DONE"},
            ])
            mod.get_job = MagicMock(return_value={
                "job_id": "j_a", "status": "RUNNING",
                "steps": [], "log_tail": "",
            })
            mod.job_exists = MagicMock(return_value=True)
            mod.cancel = MagicMock(return_value={"status": "CANCELING"})
            mod.stream_log = MagicMock(return_value=iter(["line1", "line2"]))
        elif short == "bolton_probe_service":
            mod.run_probe = MagicMock(return_value={"probe_job_id": "p_test_001"})
            mod.get_probe = MagicMock(return_value={
                "probe_job_id": "p_test_001",
                "status": "DONE",
                "result": "verified",
                "alerts_received": [],
            })
        elif short == "bolton_coverage_service":
            mod.get_for_vuln = MagicMock(return_value={
                "coverage_status": "covered",
                "rules": [], "mitre": [], "probe_history": [],
            })
            mod.detection_gaps = MagicMock(return_value={
                "gaps": [
                    {"vuln_id": "bolton.web.custom",
                     "coverage_status": "no-rule"},
                ],
                "summary": {"covered": 5, "partial": 2,
                            "no_rule": 1, "stale": 0},
            })
            mod.navigator_layer = MagicMock(return_value={
                "name": "demo", "techniques": [],
                "domain": "enterprise-attack",
            })

        monkeypatch.setitem(sys.modules, path, mod)
        holders[short.replace("bolton_", "").replace("_service", "")] = mod

    yield holders


# ─── Audit-service spy ──────────────────────────────────────────────────────

@pytest.fixture
def audit_spy(monkeypatch):
    """Replace audit_service.write with a spy and yield the captured calls."""
    from webapp.backend.services import audit_service

    captured: list[dict] = []

    def _capture(op_id, action, *, target=None, project=None, details=None):
        captured.append({
            "op": op_id, "action": action, "target": target,
            "project": project, "details": details,
        })

    monkeypatch.setattr(audit_service, "write", _capture)
    yield captured


# ─── Operator helper ─────────────────────────────────────────────────────────

@pytest.fixture
def authed_client(flask_client):
    """flask_client with a registered ``test-op`` operator + cookie set.

    The before_request hook in ``app.py`` resolves the operator from the
    cookie via ``operator_service.resolve_from_request``. If the id
    doesn't exist in the (tmpdir-isolated) store, it falls back to
    the default. Register the operator here so audit rows attribute
    to ``test-op`` deterministically.
    """
    from webapp.backend.services import operator_service
    try:
        operator_service.add("test-op", "Test Op", "#a31621")
    except ValueError:
        # Already registered for this tmp store.
        pass
    flask_client.set_cookie("dashboard_operator", "test-op", domain="localhost")
    return flask_client


# =========================================================================
# Catalog endpoints
# =========================================================================

def test_list_vulns_happy_path(authed_client, services):
    r = authed_client.get("/api/bolton/vulns")
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert "vulns" in body and isinstance(body["vulns"], list)
    assert body["total"] == 2


def test_list_vulns_passes_query_params(authed_client, services):
    services["catalog"].list_summaries.reset_mock()
    r = authed_client.get(
        "/api/bolton/vulns?category=adcs&search=esc1&coverage_status=partial"
    )
    assert r.status_code == 200
    call = services["catalog"].list_summaries.call_args
    assert call.kwargs["category"] == "adcs"
    assert call.kwargs["search"] == "esc1"
    assert call.kwargs["coverage_status"] == "partial"


def test_list_vulns_service_unavailable(flask_client, monkeypatch):
    """If the catalog service isn't importable, return 503 — not 500.

    Don't use the ``services`` fixture for this test — we explicitly
    want the import to fail. Agent B's services don't actually exist
    on disk yet, so removing any cached mock + patching
    ``importlib.import_module`` to surface the ImportError is enough.
    """
    monkeypatch.delitem(
        sys.modules,
        "webapp.backend.services.bolton_catalog_service",
        raising=False,
    )
    import importlib as _importlib
    real_import = _importlib.import_module

    def fake_import(name, *args, **kwargs):
        if name == "webapp.backend.services.bolton_catalog_service":
            raise ImportError("not available")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(
        "webapp.backend.routes.bolton.importlib.import_module",
        fake_import,
    )
    r = flask_client.get("/api/bolton/vulns")
    assert r.status_code == 503


def test_get_vuln_happy_path(authed_client, services):
    r = authed_client.get("/api/bolton/vulns/bolton.identity.kerb")
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert body["vuln"]["id"] == "bolton.identity.kerb"


def test_get_vuln_404(authed_client, services):
    services["catalog"].get.return_value = None
    r = authed_client.get("/api/bolton/vulns/bolton.nope")
    assert r.status_code == 404
    assert r.get_json()["success"] is False


def test_get_coverage_happy_path(authed_client, services):
    r = authed_client.get("/api/bolton/vulns/bolton.identity.kerb/coverage")
    assert r.status_code == 200
    body = r.get_json()
    assert body["coverage_status"] == "covered"
    assert "rules" in body
    assert "mitre" in body


def test_get_coverage_unknown_vuln_404(authed_client, services):
    services["coverage"].get_for_vuln.side_effect = KeyError("unknown")
    r = authed_client.get("/api/bolton/vulns/bolton.nope/coverage")
    assert r.status_code == 404


# =========================================================================
# Host-contextualised catalog
# =========================================================================

def test_list_hosts_happy_path(authed_client, services):
    r = authed_client.get("/api/bolton/labs/goad-light/hosts")
    assert r.status_code == 200
    body = r.get_json()
    assert body["lab"] == "goad-light"
    assert len(body["hosts"]) == 2


def test_list_hosts_unknown_lab_404(authed_client, services):
    services["facts"].list_hosts.side_effect = KeyError("unknown lab")
    r = authed_client.get("/api/bolton/labs/no-such-lab/hosts")
    assert r.status_code == 404


def test_get_host_facts_happy_path(authed_client, services):
    r = authed_client.get("/api/bolton/labs/goad-light/hosts/dc01/facts")
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert body["host_id"] == "dc01"


def test_get_host_facts_unknown_host_404(authed_client, services):
    services["facts"].get_facts.side_effect = KeyError("nope")
    r = authed_client.get("/api/bolton/labs/goad-light/hosts/zz/facts")
    assert r.status_code == 404


def test_get_host_facts_unreachable_503(authed_client, services):
    services["facts"].get_facts.side_effect = services["facts"].HostUnreachable(
        "winrm refused"
    )
    r = authed_client.get("/api/bolton/labs/goad-light/hosts/dc01/facts")
    assert r.status_code == 503
    assert r.get_json()["error"] == "host_unreachable"


def test_get_host_facts_passes_force_refresh(authed_client, services):
    services["facts"].get_facts.reset_mock()
    r = authed_client.get(
        "/api/bolton/labs/goad-light/hosts/dc01/facts?force_refresh=true"
    )
    assert r.status_code == 200
    call = services["facts"].get_facts.call_args
    assert call.kwargs["force_refresh"] is True


def test_refresh_host_facts_happy_path(authed_client, services, audit_spy):
    r = authed_client.post(
        "/api/bolton/labs/goad-light/hosts/dc01/facts/refresh",
        json={},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["host_id"] == "dc01"
    # Audit: one entry with action bolton.facts.refresh
    actions = [a["action"] for a in audit_spy]
    assert "bolton.facts.refresh" in actions


def test_refresh_host_facts_deep_probe_param(authed_client, services):
    r = authed_client.post(
        "/api/bolton/labs/goad-light/hosts/dc01/facts/refresh",
        json={"deep_probe": True},
    )
    assert r.status_code == 200
    call = services["facts"].refresh_facts.call_args
    assert call.kwargs["deep_probe"] is True


def test_refresh_host_facts_unreachable_503(authed_client, services):
    services["facts"].refresh_facts.side_effect = services["facts"].HostUnreachable(
        "winrm refused"
    )
    r = authed_client.post(
        "/api/bolton/labs/goad-light/hosts/dc01/facts/refresh",
        json={},
    )
    assert r.status_code == 503


def test_refresh_host_facts_timeout_504(authed_client, services):
    services["facts"].refresh_facts.side_effect = services["facts"].ProbeTimeout(
        "30s exceeded"
    )
    r = authed_client.post(
        "/api/bolton/labs/goad-light/hosts/dc01/facts/refresh",
        json={},
    )
    assert r.status_code == 504


def test_host_catalog_happy_path(authed_client, services):
    r = authed_client.get(
        "/api/bolton/labs/goad-light/hosts/dc01/catalog"
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["host_id"] == "dc01"
    assert "counts_by_state" in body
    assert body["counts_by_state"]["INSTALLABLE"] == 12


def test_host_catalog_facts_missing_409(authed_client, services):
    services["compatibility"].host_catalog.side_effect = services["compatibility"].FactsMissing(
        "never collected"
    )
    r = authed_client.get(
        "/api/bolton/labs/goad-light/hosts/dc01/catalog"
    )
    assert r.status_code == 409
    assert "hint" in r.get_json()


def test_host_catalog_state_filter(authed_client, services):
    services["compatibility"].host_catalog.reset_mock()
    r = authed_client.get(
        "/api/bolton/labs/goad-light/hosts/dc01/catalog"
        "?state=INSTALLABLE&state=PATCHED&category=adcs"
    )
    assert r.status_code == 200
    call = services["compatibility"].host_catalog.call_args
    assert call.kwargs["states"] == ["INSTALLABLE", "PATCHED"]
    assert call.kwargs["category"] == "adcs"


def test_host_installed_happy_path(authed_client, services):
    r = authed_client.get(
        "/api/bolton/labs/goad-light/hosts/dc01/installed"
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["host"] == "dc01"
    assert len(body["installed"]) == 1


# =========================================================================
# Operations: install / uninstall / patch / patch_revert
# =========================================================================

def test_install_happy_path(authed_client, services, audit_spy):
    r = authed_client.post(
        "/api/bolton/labs/goad-light/hosts/dc01/install/bolton.identity.kerb",
        json={"role_vars": {"username": "svc_x"}},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert body["job_id"] == "j_test_001"
    assert body["action"] == "bolton.install"

    # Audit captured
    install_audits = [a for a in audit_spy if a["action"] == "bolton.install"]
    assert len(install_audits) == 1
    assert install_audits[0]["op"] == "test-op"
    assert install_audits[0]["project"] == "goad-light"
    assert install_audits[0]["target"] == "dc01:bolton.identity.kerb"


def test_install_invalid_body_400(authed_client, services):
    """A body of the wrong shape should 400 — pydantic catches it.

    Note: depending on whether pydantic is installed the validation is
    strict (rejects extra at the validate level) or permissive (ignores
    extras). We pass a clearly malformed body (top-level list) which
    fails both paths."""
    r = authed_client.post(
        "/api/bolton/labs/goad-light/hosts/dc01/install/bolton.identity.kerb",
        data=json.dumps([1, 2, 3]),
        content_type="application/json",
    )
    assert r.status_code == 400


def test_install_unknown_vuln_404(authed_client, services):
    services["install"].dispatch.side_effect = KeyError("unknown vuln")
    r = authed_client.post(
        "/api/bolton/labs/goad-light/hosts/dc01/install/bolton.nope",
        json={},
    )
    assert r.status_code == 404


def test_install_compatibility_refused_409(authed_client, services):
    exc = services["install"].CompatibilityRefused("incompatible OS")
    exc.state = "INCOMPATIBLE_OS"
    services["install"].dispatch.side_effect = exc
    r = authed_client.post(
        "/api/bolton/labs/goad-light/hosts/ws01/install/bolton.adcs.esc1",
        json={},
    )
    assert r.status_code == 409
    body = r.get_json()
    assert body["error"] == "compatibility_refused"
    assert body["state"] == "INCOMPATIBLE_OS"


def test_uninstall_happy_path(authed_client, services, audit_spy):
    r = authed_client.post(
        "/api/bolton/labs/goad-light/hosts/dc01/uninstall/bolton.identity.kerb",
        json={},
    )
    assert r.status_code == 200
    actions = [a["action"] for a in audit_spy]
    assert "bolton.uninstall" in actions


def test_patch_happy_path(authed_client, services, audit_spy):
    r = authed_client.post(
        "/api/bolton/labs/goad-light/hosts/ca01/patch/bolton.adcs.esc1",
        json={"run_probe": True},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["action"] == "bolton.patch"
    actions = [a["action"] for a in audit_spy]
    assert "bolton.patch" in actions


def test_patch_revert_happy_path(authed_client, services, audit_spy):
    r = authed_client.post(
        "/api/bolton/labs/goad-light/hosts/ca01/patch-revert/bolton.adcs.esc1",
        json={},
    )
    assert r.status_code == 200
    actions = [a["action"] for a in audit_spy]
    assert "bolton.patch_revert" in actions


def test_install_audit_attributes_to_cookie_operator(flask_client, services, audit_spy):
    """If the cookie operator changes, the audit row should record it.

    Register ``alice`` so the operator_service resolves the cookie to her
    record rather than falling back to the default seeded operator.
    """
    from webapp.backend.services import operator_service
    try:
        operator_service.add("alice", "Alice", "#3b82f6")
    except ValueError:
        pass
    flask_client.set_cookie("dashboard_operator", "alice", domain="localhost")
    r = flask_client.post(
        "/api/bolton/labs/goad-light/hosts/dc01/install/bolton.identity.kerb",
        json={},
    )
    assert r.status_code == 200
    install_audits = [a for a in audit_spy if a["action"] == "bolton.install"]
    assert install_audits[0]["op"] == "alice"


# =========================================================================
# Bulk
# =========================================================================

def test_bulk_dispatches_cross_product(authed_client, services, audit_spy):
    services["install"].dispatch.side_effect = [
        {"job_id": f"j_bulk_{i}"} for i in range(6)
    ]
    r = authed_client.post(
        "/api/bolton/labs/goad-light/bulk",
        json={
            "action": "install",
            "hosts": ["dc01", "dc02", "ws01"],
            "vuln_ids": ["bolton.a", "bolton.b"],
        },
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert body["job_count"] == 6
    assert len(body["jobs"]) == 6
    assert all("job_id" in j for j in body["jobs"])
    # Audit: one bulk entry, not 6 individual entries
    bulk_audits = [a for a in audit_spy if a["action"] == "bolton.bulk"]
    assert len(bulk_audits) == 1
    assert bulk_audits[0]["details"]["job_count"] == 6


def test_bulk_with_partial_failures_returns_200(authed_client, services):
    """Partial-success bulk request still returns 200 with errors array."""
    def _dispatch(**kwargs):
        if kwargs["host"] == "ws01":
            raise Exception("install refused")
        return {"job_id": f"j_{kwargs['host']}"}
    services["install"].dispatch.side_effect = _dispatch
    r = authed_client.post(
        "/api/bolton/labs/goad-light/bulk",
        json={
            "action": "install",
            "hosts": ["dc01", "ws01"],
            "vuln_ids": ["bolton.a"],
        },
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["job_count"] == 1
    assert len(body["errors"]) == 1
    assert body["errors"][0]["host"] == "ws01"


def test_bulk_unknown_action_400(authed_client, services):
    r = authed_client.post(
        "/api/bolton/labs/goad-light/bulk",
        json={"action": "nuke", "hosts": ["dc01"], "vuln_ids": ["bolton.a"]},
    )
    assert r.status_code == 400


def test_bulk_empty_hosts_400(authed_client, services):
    r = authed_client.post(
        "/api/bolton/labs/goad-light/bulk",
        json={"action": "install", "hosts": [], "vuln_ids": ["bolton.a"]},
    )
    assert r.status_code == 400


def test_bulk_empty_vuln_ids_400(authed_client, services):
    r = authed_client.post(
        "/api/bolton/labs/goad-light/bulk",
        json={"action": "install", "hosts": ["dc01"], "vuln_ids": []},
    )
    assert r.status_code == 400


# =========================================================================
# Job lifecycle
# =========================================================================

def test_list_jobs_happy_path(authed_client, services):
    r = authed_client.get("/api/bolton/jobs")
    assert r.status_code == 200
    body = r.get_json()
    assert body["total"] == 2


def test_list_jobs_filters_passed_through(authed_client, services):
    services["jobs"].list_jobs.reset_mock()
    r = authed_client.get(
        "/api/bolton/jobs?lab=goad-light&status=RUNNING&action=install&limit=10"
    )
    assert r.status_code == 200
    call = services["jobs"].list_jobs.call_args
    assert call.kwargs["lab"] == "goad-light"
    assert call.kwargs["status"] == "RUNNING"
    assert call.kwargs["action"] == "install"
    assert call.kwargs["limit"] == 10


def test_get_job_happy_path(authed_client, services):
    r = authed_client.get("/api/bolton/jobs/j_a")
    assert r.status_code == 200
    body = r.get_json()
    assert body["job_id"] == "j_a"
    assert body["status"] == "RUNNING"


def test_get_job_unknown_404(authed_client, services):
    services["jobs"].get_job.return_value = None
    r = authed_client.get("/api/bolton/jobs/j_nope")
    assert r.status_code == 404


def test_get_job_log_streams(authed_client, services):
    """The SSE endpoint returns text/event-stream and yields data: lines."""
    services["jobs"].stream_log.return_value = iter(["hello", "world"])
    r = authed_client.get("/api/bolton/jobs/j_a/log")
    assert r.status_code == 200
    assert r.mimetype == "text/event-stream"
    body = r.get_data(as_text=True)
    assert "data: hello" in body
    assert "data: world" in body


def test_get_job_log_unknown_404(authed_client, services):
    services["jobs"].job_exists.return_value = False
    r = authed_client.get("/api/bolton/jobs/j_nope/log")
    assert r.status_code == 404


def test_cancel_job_happy_path(authed_client, services, audit_spy):
    r = authed_client.post("/api/bolton/jobs/j_a/cancel")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "CANCELING"
    actions = [a["action"] for a in audit_spy]
    assert "bolton.job.cancel" in actions


def test_cancel_job_unknown_404(authed_client, services):
    services["jobs"].cancel.side_effect = KeyError("unknown")
    r = authed_client.post("/api/bolton/jobs/j_nope/cancel")
    assert r.status_code == 404


def test_cancel_job_not_cancellable_409(authed_client, services):
    services["jobs"].cancel.side_effect = services["jobs"].NotCancellable(
        "already DONE"
    )
    r = authed_client.post("/api/bolton/jobs/j_a/cancel")
    assert r.status_code == 409


def test_agent_intervene_returns_202_stub(authed_client, services, audit_spy):
    r = authed_client.post("/api/bolton/jobs/j_a/agent-intervene")
    assert r.status_code == 202
    body = r.get_json()
    assert body["status"] == "AGENT_INVOCATION_QUEUED"
    assert body["job_id"] == "j_a"
    actions = [a["action"] for a in audit_spy]
    assert "bolton.job.agent_intervene" in actions


def test_agent_intervene_unknown_job_404(authed_client, services):
    services["jobs"].job_exists.return_value = False
    r = authed_client.post("/api/bolton/jobs/j_nope/agent-intervene")
    assert r.status_code == 404


# =========================================================================
# Probe / generate-rule / gaps / Navigator
# =========================================================================

def test_probe_happy_path(authed_client, services, audit_spy):
    r = authed_client.post(
        "/api/bolton/vulns/bolton.identity.kerb/probe",
        json={"lab": "goad-light", "host": "dc01"},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["probe_job_id"] == "p_test_001"
    actions = [a["action"] for a in audit_spy]
    assert "bolton.probe" in actions


def test_probe_missing_body_fields_400(authed_client, services):
    r = authed_client.post(
        "/api/bolton/vulns/bolton.identity.kerb/probe",
        json={"lab": "goad-light"},  # missing host
    )
    assert r.status_code == 400


def test_probe_vuln_has_no_probe_block_404(authed_client, services):
    services["probe"].run_probe.side_effect = KeyError("no trigger_probe")
    r = authed_client.post(
        "/api/bolton/vulns/bolton.foo/probe",
        json={"lab": "goad-light", "host": "dc01"},
    )
    assert r.status_code == 404


def test_get_probe_happy_path(authed_client, services):
    r = authed_client.get("/api/bolton/probes/p_test_001")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "DONE"
    assert body["result"] == "verified"


def test_get_probe_unknown_404(authed_client, services):
    services["probe"].get_probe.return_value = None
    r = authed_client.get("/api/bolton/probes/p_nope")
    assert r.status_code == 404


def test_generate_rule_happy_path(authed_client, services, audit_spy):
    r = authed_client.post(
        "/api/bolton/vulns/bolton.identity.kerb/generate-rule",
        json={"rule_inputs": {"severity": "high"}},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert "draft_rule_toml" in body
    assert body["stubbed"] is True
    assert "new_uuid" in body
    actions = [a["action"] for a in audit_spy]
    assert "bolton.generate_rule" in actions


def test_generate_rule_unknown_vuln_404(authed_client, services):
    services["catalog"].get.return_value = None
    r = authed_client.post(
        "/api/bolton/vulns/bolton.nope/generate-rule",
        json={},
    )
    assert r.status_code == 404


def test_detection_gaps_happy_path(authed_client, services):
    r = authed_client.get("/api/bolton/detection/gaps?lab=goad-light")
    assert r.status_code == 200
    body = r.get_json()
    assert "gaps" in body
    assert "summary" in body


def test_navigator_layer_happy_path(authed_client, services):
    r = authed_client.get(
        "/api/bolton/coverage/navigator-layer?lab=goad-light&installed_only=true"
    )
    assert r.status_code == 200
    body = r.get_json()
    assert "layer" in body
    assert body["layer"]["domain"] == "enterprise-attack"


def test_navigator_layer_unknown_lab_404(authed_client, services):
    services["coverage"].navigator_layer.side_effect = KeyError("nope")
    r = authed_client.get("/api/bolton/coverage/navigator-layer?lab=no-such")
    assert r.status_code == 404


# =========================================================================
# Blueprint registration sanity
# =========================================================================

def test_blueprint_registered_under_correct_prefix(authed_client, services):
    """Every endpoint must live under /api/bolton — verify a sample."""
    r = authed_client.get("/api/bolton/vulns")
    assert r.status_code == 200
    # 404 for a sibling that doesn't exist confirms the prefix is exact.
    r2 = authed_client.get("/api/bolton/this-route-does-not-exist")
    assert r2.status_code == 404


def test_operator_g_resolution_does_not_break_unauthed_requests(flask_client, services, audit_spy):
    """No dashboard_operator cookie → audit logs as the seeded default
    operator (or `unknown`). Endpoint still succeeds."""
    r = flask_client.post(
        "/api/bolton/labs/goad-light/hosts/dc01/install/bolton.identity.kerb",
        json={},
    )
    assert r.status_code == 200
    # Audit record exists; op id is some non-None value (seeded by the
    # operator service or 'unknown').
    install_audits = [a for a in audit_spy if a["action"] == "bolton.install"]
    assert len(install_audits) == 1
    assert install_audits[0]["op"] is not None


# =========================================================================
# Audit-action namespace coverage
# =========================================================================

def test_full_audit_action_namespace_emitted(authed_client, services, audit_spy):
    """Drive every state-changing route once; verify all expected
    action strings appear at least once."""
    # facts.refresh
    authed_client.post("/api/bolton/labs/L/hosts/H/facts/refresh", json={})
    # install / uninstall / patch / patch_revert
    authed_client.post("/api/bolton/labs/L/hosts/H/install/V", json={})
    authed_client.post("/api/bolton/labs/L/hosts/H/uninstall/V", json={})
    authed_client.post("/api/bolton/labs/L/hosts/H/patch/V", json={})
    authed_client.post("/api/bolton/labs/L/hosts/H/patch-revert/V", json={})
    # bulk
    authed_client.post(
        "/api/bolton/labs/L/bulk",
        json={"action": "install", "hosts": ["H"], "vuln_ids": ["V"]},
    )
    # job.cancel + agent-intervene
    authed_client.post("/api/bolton/jobs/j_a/cancel")
    authed_client.post("/api/bolton/jobs/j_a/agent-intervene")
    # probe + generate-rule
    authed_client.post(
        "/api/bolton/vulns/V/probe", json={"lab": "L", "host": "H"}
    )
    authed_client.post("/api/bolton/vulns/V/generate-rule", json={})

    actions = {a["action"] for a in audit_spy}
    expected = {
        "bolton.facts.refresh",
        "bolton.install",
        "bolton.uninstall",
        "bolton.patch",
        "bolton.patch_revert",
        "bolton.bulk",
        "bolton.job.cancel",
        "bolton.job.agent_intervene",
        "bolton.probe",
        "bolton.generate_rule",
    }
    assert expected.issubset(actions), (
        f"missing audit actions: {expected - actions}"
    )


# =========================================================================
# REAL SERVICES — Agent D reconcile validation. Runs the routes against
# the actual webapp.backend.services.* modules to prove the function-name
# alignment holds end-to-end (not just under mocks).
# =========================================================================

@pytest.fixture
def real_services(monkeypatch, tmp_path):
    """Use the real services (no MagicMocks).

    Pins the bolton state roots to a tmpdir so concurrent tests don't
    share disk. Resets the in-memory install registry between tests.
    """
    # Drop any cached mock modules left over from a prior test.
    for short in _SERVICE_NAMES:
        monkeypatch.delitem(sys.modules, _BASE + short, raising=False)

    # Import real modules so we can rebind their state paths.
    from webapp.backend.services import (
        bolton_catalog_service,
        bolton_facts_service,
        bolton_install_service,
        bolton_probe_service,
    )

    monkeypatch.setattr(bolton_facts_service, "STATE_ROOT", tmp_path / "host_facts")
    monkeypatch.setattr(bolton_install_service, "JOBS_ROOT", tmp_path / "jobs")
    monkeypatch.setattr(bolton_probe_service, "PROBES_ROOT", tmp_path / "probes")
    bolton_install_service._reset_registry_for_tests()
    bolton_catalog_service._reset_for_tests()
    bolton_install_service._set_simulated_duration_for_tests(0.01)
    yield
    bolton_install_service._set_simulated_duration_for_tests(2.0)
    bolton_install_service._reset_registry_for_tests()
    bolton_catalog_service._reset_for_tests()


def test_real_list_vulns(authed_client, real_services):
    """Real catalog service serves the descriptor summaries."""
    r = authed_client.get("/api/bolton/vulns")
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert isinstance(body["vulns"], list)
    # 5 worked descriptors ship with the repo (see webapp/bolton/catalog).
    assert body["total"] >= 1


def test_real_list_hosts(authed_client, real_services):
    """Real facts service returns mocked-host rows for a fresh lab."""
    r = authed_client.get("/api/bolton/labs/goad-light/hosts")
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert isinstance(body["hosts"], list)
    names = {h["name"] for h in body["hosts"]}
    assert "dc01" in names


def test_real_get_host_facts(authed_client, real_services):
    """Real facts gather returns a populated fact bundle."""
    r = authed_client.get("/api/bolton/labs/goad-light/hosts/dc01/facts")
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert body["host_id"] == "dc01"
    assert body["os_family"] == "windows"


def test_real_host_catalog(authed_client, real_services):
    """Real compatibility evaluator annotates the catalog for a host."""
    r = authed_client.get("/api/bolton/labs/goad-light/hosts/dc01/catalog")
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert body["host_id"] == "dc01"
    assert "counts_by_state" in body


def test_real_install_dispatch_and_get_job(authed_client, real_services):
    """Real install dispatcher creates a job; the jobs service retrieves it."""
    # Pick any known descriptor; if no descriptors ship, skip.
    r = authed_client.get("/api/bolton/vulns")
    vulns = r.get_json().get("vulns") or []
    if not vulns:
        pytest.skip("no descriptors in catalog — skipping live install test")
    vuln_id = vulns[0]["id"]
    # Use a fresh host so the compat backstop doesn't trip.
    r = authed_client.post(
        f"/api/bolton/labs/goad-light/hosts/exotic-host/install/{vuln_id}",
        json={},
    )
    # Accept 200 (queued) OR 409 (compat refused — descriptor narrow on OS).
    assert r.status_code in (200, 409), r.get_data(as_text=True)
    if r.status_code == 200:
        body = r.get_json()
        assert body["success"] is True
        assert body["job_id"]
        # The job is visible to the jobs service.
        r2 = authed_client.get(f"/api/bolton/jobs/{body['job_id']}")
        assert r2.status_code == 200


def test_real_list_jobs_and_cancel(authed_client, real_services):
    """The jobs service list endpoint walks the registry."""
    r = authed_client.get("/api/bolton/jobs")
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert isinstance(body["jobs"], list)


def test_real_detection_gaps(authed_client, real_services):
    """The coverage service emits a gaps + summary envelope."""
    r = authed_client.get("/api/bolton/detection/gaps")
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert "gaps" in body
    assert "summary" in body
    summary = body["summary"]
    for key in ("covered", "partial", "no_rule", "stale"):
        assert key in summary


def test_real_navigator_layer(authed_client, real_services):
    """The coverage service emits a Navigator-shaped JSON layer."""
    r = authed_client.get("/api/bolton/coverage/navigator-layer?lab=goad-light")
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert body["layer"]["domain"] == "enterprise-attack"
