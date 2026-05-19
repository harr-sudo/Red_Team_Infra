"""Tests for the per-project ?project=<name> param on /api/config.

Verifies:
- GET without ?project= loads configs/terraform.tfvars (legacy behavior)
- GET with ?project=<name> loads configs/<name>.tfvars when it exists
- GET with a path-traversal attempt is sanitized
- POST with ?project=<name> writes to configs/<name>.tfvars
- POST without ?project= but with config.project_name uses that
- POST without either falls back to the global terraform.tfvars
- DELETE with ?project=<name> only removes that file
"""

from pathlib import Path

from webapp.backend.routes import config as config_route


def _set_config_paths(monkeypatch, tmp_path):
    """Redirect the config route's config_dir to a tmpdir."""
    monkeypatch.setattr(config_route, "config_dir", tmp_path)
    monkeypatch.setattr(config_route, "tfvars_file", tmp_path / "terraform.tfvars")
    monkeypatch.setattr(config_route, "tfvars_example", tmp_path / "terraform.tfvars.example")
    # An example file is required by GET when nothing exists.
    (tmp_path / "terraform.tfvars.example").write_text(
        'deployment_type = "c2-adhoc"\nproject_name = "example"\n'
    )


def test_get_without_project_loads_global_tfvars(flask_client, monkeypatch, tmp_path):
    _set_config_paths(monkeypatch, tmp_path)
    (tmp_path / "terraform.tfvars").write_text(
        'deployment_type = "c2-adhoc"\nproject_name = "global_project"\n'
    )
    response = flask_client.get("/api/config/")
    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert body["success"] is True
    assert body["config"]["project_name"] == "global_project"


def test_get_with_project_loads_per_project_tfvars(flask_client, monkeypatch, tmp_path):
    _set_config_paths(monkeypatch, tmp_path)
    (tmp_path / "terraform.tfvars").write_text(
        'project_name = "global_project"\n'
    )
    (tmp_path / "lab_alpha.tfvars").write_text(
        'deployment_type = "goad-mini"\nproject_name = "lab_alpha"\n'
    )
    response = flask_client.get("/api/config/?project=lab_alpha")
    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["config"]["project_name"] == "lab_alpha"
    assert body["project"] == "lab_alpha"
    assert "lab_alpha.tfvars" in body["tfvars_path"]


def test_get_with_unknown_project_falls_back_to_global(flask_client, monkeypatch, tmp_path):
    _set_config_paths(monkeypatch, tmp_path)
    (tmp_path / "terraform.tfvars").write_text(
        'project_name = "global_project"\n'
    )
    response = flask_client.get("/api/config/?project=does_not_exist")
    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    # Falls back to global tfvars when per-project file is missing.
    assert body["config"]["project_name"] == "global_project"


def test_get_with_path_traversal_is_sanitized(flask_client, monkeypatch, tmp_path):
    """A malicious ?project=../../etc/passwd must not escape the configs dir."""
    _set_config_paths(monkeypatch, tmp_path)
    (tmp_path / "terraform.tfvars").write_text(
        'project_name = "safe_project"\n'
    )
    response = flask_client.get("/api/config/?project=../../etc/passwd")
    assert response.status_code == 200
    body = response.get_json()
    # The sanitizer maps ../../etc/passwd to ______etc_passwd → file doesn't
    # exist → falls back to global tfvars. We DON'T leak /etc/passwd content.
    assert body["success"] is True
    assert body["config"]["project_name"] == "safe_project"


def test_get_with_draft_sentinel_uses_global(flask_client, monkeypatch, tmp_path):
    """__draft__ and __all__ are UI sentinels — they must not resolve to disk."""
    _set_config_paths(monkeypatch, tmp_path)
    (tmp_path / "terraform.tfvars").write_text(
        'project_name = "global"\n'
    )
    for sentinel in ("__draft__", "__all__"):
        response = flask_client.get(f"/api/config/?project={sentinel}")
        assert response.status_code == 200, sentinel
        body = response.get_json()
        assert body["config"]["project_name"] == "global", sentinel


def test_post_with_project_writes_per_project_tfvars(flask_client, monkeypatch, tmp_path):
    _set_config_paths(monkeypatch, tmp_path)
    payload = {
        "config": {
            "deployment_type": "goad-mini",
            "project_name": "lab_bravo",
            "engagement_type": "",
            "primary_domain_name": "",
            "admin_email": "",
            "key_pair_name": "kp",
            "environment": "dev",
            "management_cidr_blocks": ["1.2.3.4/32"],
        }
    }
    response = flask_client.post("/api/config/?project=lab_bravo", json=payload)
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["success"] is True
    assert (tmp_path / "lab_bravo.tfvars").exists()
    # Global tfvars must NOT have been written.
    assert not (tmp_path / "terraform.tfvars").exists()
    assert "lab_bravo.tfvars" in body["tfvars_path"]


def test_post_without_project_param_uses_body_project_name(flask_client, monkeypatch, tmp_path):
    """If ?project= is missing but body.config.project_name is set, write
    per-project. This mirrors the deploy pipeline's expectation that
    each save lands in its own tfvars."""
    _set_config_paths(monkeypatch, tmp_path)
    payload = {
        "config": {
            "deployment_type": "c2-adhoc",
            "project_name": "lab_charlie",
            "engagement_type": "adhoc",
            "primary_domain_name": "example.com",
            "admin_email": "a@b.c",
            "key_pair_name": "kp",
            "environment": "dev",
            "management_cidr_blocks": ["1.2.3.4/32"],
        }
    }
    response = flask_client.post("/api/config/", json=payload)
    assert response.status_code == 200, response.get_json()
    assert (tmp_path / "lab_charlie.tfvars").exists()


def test_post_with_draft_sentinel_falls_back_to_global(flask_client, monkeypatch, tmp_path):
    _set_config_paths(monkeypatch, tmp_path)
    payload = {
        "config": {
            "deployment_type": "c2-adhoc",
            "project_name": "lab_draft",
            "engagement_type": "adhoc",
            "primary_domain_name": "example.com",
            "admin_email": "a@b.c",
            "key_pair_name": "kp",
            "environment": "dev",
            "management_cidr_blocks": ["1.2.3.4/32"],
        }
    }
    # When the UI is in draft mode the sentinel is sent — backend should
    # still write to a per-project file using body.config.project_name.
    response = flask_client.post("/api/config/?project=__draft__", json=payload)
    assert response.status_code == 200, response.get_json()
    # Sentinel resolves to global, but body.project_name wins as fallback.
    assert (tmp_path / "lab_draft.tfvars").exists()


def test_delete_with_project_only_removes_that_file(flask_client, monkeypatch, tmp_path):
    _set_config_paths(monkeypatch, tmp_path)
    (tmp_path / "terraform.tfvars").write_text('project_name = "global"\n')
    (tmp_path / "lab_delta.tfvars").write_text('project_name = "lab_delta"\n')

    response = flask_client.delete("/api/config/?project=lab_delta")
    assert response.status_code == 200
    assert not (tmp_path / "lab_delta.tfvars").exists()
    # Global tfvars survives.
    assert (tmp_path / "terraform.tfvars").exists()


def test_delete_without_project_removes_global(flask_client, monkeypatch, tmp_path):
    _set_config_paths(monkeypatch, tmp_path)
    (tmp_path / "terraform.tfvars").write_text('project_name = "global"\n')
    (tmp_path / "lab_echo.tfvars").write_text('project_name = "lab_echo"\n')

    response = flask_client.delete("/api/config/")
    assert response.status_code == 200
    assert not (tmp_path / "terraform.tfvars").exists()
    # Per-project tfvars survives.
    assert (tmp_path / "lab_echo.tfvars").exists()
