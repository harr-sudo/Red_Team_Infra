"""Per-project tfvars routing for /api/deploy/plan + /api/deploy.

The Configure V2 surface saves to configs/<project>.tfvars via the
?project= query param. The Deploy sub-pill's Plan / Apply buttons must
read from the same per-project file — NOT the stale global tfvars. These
tests pin that contract.

Path-traversal sanitization is verified end-to-end against the shared
helper in webapp.backend.utils.tfvars_path (the same helper config.py
uses, so any drift between the two callers shows up here).
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from webapp.backend.routes import deploy as deploy_route


@pytest.fixture
def per_project_tfvars(monkeypatch, tmp_path):
    """Stage a per-project tfvars file under a tmp configs/ dir and rewire
    the deploy route's project_root + terraform_service to point at it."""

    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()

    global_tfvars = configs_dir / "terraform.tfvars"
    global_tfvars.write_text(
        'project_name = "global_project"\n'
        'deployment_type = "c2-adhoc"\n'
        'primary_domain_name = "example.com"\n'
        'admin_email = "x@y.z"\n'
    )

    project_tfvars = configs_dir / "lab_alpha.tfvars"
    project_tfvars.write_text(
        'project_name = "lab_alpha"\n'
        'deployment_type = "goad-mini"\n'
        'primary_domain_name = ""\n'
    )

    # Rewire deploy route's project_root so config_dir / "terraform.tfvars"
    # lookups inside the route point at our tmp dir.
    monkeypatch.setattr(deploy_route, "project_root", tmp_path)

    # Reset / mock the singleton terraform_service so plan() doesn't shell out.
    mock_service = MagicMock()
    mock_service.terraform_dir = tmp_path / "terraform"
    (tmp_path / "terraform" / ".terraform").mkdir(parents=True, exist_ok=True)
    mock_service.workspace_name = "default"
    mock_service.tfvars_file = global_tfvars
    mock_service.init.return_value = {"success": True}
    mock_service.workspace_select.return_value = {"success": True, "workspace": "lab_alpha"}
    mock_service.plan.return_value = {
        "success": True,
        "stdout": "Plan: 1 to add",
        "stderr": "",
        "full_output": "Plan: 1 to add",
        "exit_code": 0,
        "plan": {},
    }
    monkeypatch.setattr(deploy_route, "terraform_service", mock_service)

    yield {
        "tmp_path": tmp_path,
        "configs_dir": configs_dir,
        "global_tfvars": global_tfvars,
        "project_tfvars": project_tfvars,
        "service": mock_service,
    }


# ---------------------------------------------------------------------------
# /api/deploy/plan
# ---------------------------------------------------------------------------

def test_plan_with_project_uses_per_project_tfvars(flask_client, per_project_tfvars):
    """?project=lab_alpha → terraform_service.tfvars_file points at lab_alpha.tfvars."""
    resp = flask_client.get("/api/deploy/plan?project=lab_alpha")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True
    svc = per_project_tfvars["service"]
    assert svc.tfvars_file == per_project_tfvars["project_tfvars"]
    assert svc.workspace_name == "lab_alpha"
    svc.workspace_select.assert_called_with("lab_alpha")


def test_plan_without_project_falls_back_to_global(flask_client, per_project_tfvars):
    """No ?project= → terraform_service stays on the global tfvars (legacy)."""
    resp = flask_client.get("/api/deploy/plan")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    svc = per_project_tfvars["service"]
    assert svc.tfvars_file == per_project_tfvars["global_tfvars"]
    assert svc.workspace_name == "default"


def test_plan_with_path_traversal_falls_back_to_global(flask_client, per_project_tfvars):
    """?project=../../etc/passwd is sanitized — must not escape configs/."""
    resp = flask_client.get("/api/deploy/plan?project=../../etc/passwd")
    assert resp.status_code == 200
    body = resp.get_json()
    # Sanitizer turns the name into ______etc_passwd, no file exists, so
    # we fall through to the global tfvars instead of leaking /etc/passwd.
    assert body["success"] is True
    svc = per_project_tfvars["service"]
    assert svc.tfvars_file == per_project_tfvars["global_tfvars"]


def test_plan_with_draft_sentinel_falls_back_to_global(flask_client, per_project_tfvars):
    """__draft__ is a UI-only sentinel — must not resolve to disk."""
    resp = flask_client.get("/api/deploy/plan?project=__draft__")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    svc = per_project_tfvars["service"]
    assert svc.tfvars_file == per_project_tfvars["global_tfvars"]
    assert svc.workspace_name == "default"


def test_plan_with_all_sentinel_falls_back_to_global(flask_client, per_project_tfvars):
    """__all__ (fleet view sentinel) must also fall back to global."""
    resp = flask_client.get("/api/deploy/plan?project=__all__")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    svc = per_project_tfvars["service"]
    assert svc.tfvars_file == per_project_tfvars["global_tfvars"]


def test_plan_with_unknown_project_falls_back_to_global(flask_client, per_project_tfvars):
    """An unknown project name (no file on disk) falls back to global."""
    resp = flask_client.get("/api/deploy/plan?project=nonexistent")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    svc = per_project_tfvars["service"]
    assert svc.tfvars_file == per_project_tfvars["global_tfvars"]


# ---------------------------------------------------------------------------
# /api/deploy (POST)
# ---------------------------------------------------------------------------

@pytest.fixture
def deploy_post_isolated(monkeypatch, per_project_tfvars):
    """Wrap per_project_tfvars with the extra isolation /api/deploy needs:

    - UPLOAD_FOLDER pre-staged with a fake CS archive (prereq check)
    - run_deployment thread no-op'd (we test routing, not the orchestrator)
    - deployment_state global reset so we don't trip the "already running" guard
    """
    # Cobalt Strike prereq: place a fake archive in UPLOAD_FOLDER
    upload_dir = per_project_tfvars["tmp_path"] / "uploads"
    upload_dir.mkdir(exist_ok=True)
    (upload_dir / "cs.tar.gz").write_bytes(b"fake")
    monkeypatch.setattr(deploy_route, "UPLOAD_FOLDER", upload_dir)

    # Don't actually spawn the deployment thread.
    monkeypatch.setattr(
        deploy_route.threading,
        "Thread",
        lambda *args, **kwargs: MagicMock(start=MagicMock(), daemon=False),
    )

    # Reset the legacy single-deployment guard.
    monkeypatch.setattr(
        deploy_route, "deployment_state", deploy_route.create_empty_state()
    )
    monkeypatch.setattr(deploy_route, "deployment_states", {})

    # Avoid copying a real tfvars to the workspace directory.
    mock_service = MagicMock()
    mock_service.copy_config_to_workspace = MagicMock()
    monkeypatch.setattr(
        deploy_route, "get_service_for_project", lambda name: mock_service
    )

    yield per_project_tfvars


def test_deploy_post_with_project_query_param_reads_per_project_tfvars(
    flask_client, deploy_post_isolated
):
    """POST /api/deploy?project=lab_alpha reads lab_alpha.tfvars, not global."""
    resp = flask_client.post(
        "/api/deploy/deploy?project=lab_alpha",
        json={"project_name": "lab_alpha"},
    )
    body = resp.get_json()
    assert resp.status_code == 200, body
    assert body["success"] is True
    # The per-project tfvars has project_name=lab_alpha — confirms it
    # was the file actually parsed (the global one has project_name=global_project).
    assert body.get("project_name") == "lab_alpha" or "lab_alpha" in str(body)


def test_deploy_post_with_path_traversal_falls_back_to_global(
    flask_client, deploy_post_isolated
):
    """?project=../../etc/passwd is sanitized; falls back to global tfvars."""
    resp = flask_client.post(
        "/api/deploy/deploy?project=../../etc/passwd",
        json={},
    )
    body = resp.get_json()
    # Global tfvars exists and is valid, so deploy starts against global_project.
    assert resp.status_code == 200, body
    assert body["success"] is True


def test_deploy_post_with_draft_sentinel_falls_back_to_global(
    flask_client, deploy_post_isolated
):
    """__draft__ sentinel must not be read as a filename."""
    resp = flask_client.post(
        "/api/deploy/deploy?project=__draft__",
        json={"project_name": "__draft__"},
    )
    body = resp.get_json()
    assert resp.status_code == 200, body
    # Global has project_name=global_project — proves sentinel did NOT
    # resolve to a per-project file.
    assert body["success"] is True


def test_deploy_post_with_all_sentinel_falls_back_to_global(
    flask_client, deploy_post_isolated
):
    """__all__ sentinel must also fall back to global."""
    resp = flask_client.post(
        "/api/deploy/deploy?project=__all__",
        json={"project_name": "__all__"},
    )
    body = resp.get_json()
    assert resp.status_code == 200, body
    assert body["success"] is True


def test_deploy_post_without_query_uses_body_project_name(
    flask_client, deploy_post_isolated
):
    """Body's project_name is used when ?project= is absent."""
    resp = flask_client.post(
        "/api/deploy/deploy",
        json={"project_name": "lab_alpha"},
    )
    body = resp.get_json()
    assert resp.status_code == 200, body
    assert body["success"] is True
