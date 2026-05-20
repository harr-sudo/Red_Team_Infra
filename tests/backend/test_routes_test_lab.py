"""Smoke tests for /api/test_lab/* routes.

Verifies the contract the frontend depends on:

  - GET  /api/test_lab/hosts/<project>       — shape + enabled flag
  - GET  /api/test_lab/status/<project>      — idle/running/success/failed
  - POST /api/test_lab/provision/<project>   — 400 when disabled, 404 missing

We don't drive a real SSH session — that path is exercised in the
manual end-to-end flow against the live c2_adhoc deployment. These
tests cover the wiring: route handler, state lookup, tfvars flag read,
and the YAML-shape helpers exposed for the test lab.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def _seed_project(tmp_path, monkeypatch, *, project, enable_test_lab, host_inventory=None):
    """Lay down a fake project state + tfvars inside tmp_path and point
    the test_lab module's directory constants at them."""
    from webapp.backend.routes import test_lab as tl

    state_dir = tmp_path / "logs" / "deployment_state"
    configs_dir = tmp_path / "configs"
    workspace = tmp_path / "logs" / "testlab_workspace"
    state_dir.mkdir(parents=True)
    configs_dir.mkdir(parents=True)
    workspace.mkdir(parents=True)

    outputs = {
        "deployment_type": {"value": "c2-adhoc"},
        "bastion_public_ip": {"value": "203.0.113.5"},
    }
    if host_inventory is not None:
        outputs["test_lab_host_inventory"] = {"value": host_inventory}
    state_file = state_dir / f"{project}.state.json"
    state_file.write_text(json.dumps({"status": "success", "output": outputs}))

    tfvars_file = configs_dir / f"{project}.tfvars"
    flag = "true" if enable_test_lab else "false"
    tfvars_file.write_text(
        f'project_name = "{project}"\n'
        f'enable_test_lab = {flag}\n'
        f'test_lab_subnet_cidr = "10.0.20.0/24"\n'
    )

    monkeypatch.setattr(tl, "STATE_DIR", state_dir)
    monkeypatch.setattr(tl, "CONFIGS_DIR", configs_dir)
    monkeypatch.setattr(tl, "TESTLAB_WORKSPACE", workspace)


SAMPLE_INVENTORY = {
    "tldc01":    {"private_ip": "10.0.20.10", "role": "domain_controller", "os_family": "windows", "instance_id": "i-aaa"},
    "tlms01":    {"private_ip": "10.0.20.11", "role": "member_server",     "os_family": "windows", "instance_id": "i-bbb"},
    "tlws01":    {"private_ip": "10.0.20.12", "role": "workstation",       "os_family": "windows", "instance_id": "i-ccc"},
    "tllinux01": {"private_ip": "10.0.20.13", "role": "linux_member",      "os_family": "linux",   "instance_id": "i-ddd"},
}


# ----------------------------------------------------------------------------
# GET /api/test_lab/hosts/<project>
# ----------------------------------------------------------------------------


def test_hosts_404_when_project_unknown(flask_client, tmp_path, monkeypatch):
    from webapp.backend.routes import test_lab as tl
    monkeypatch.setattr(tl, "STATE_DIR", tmp_path / "no-such-dir")
    monkeypatch.setattr(tl, "CONFIGS_DIR", tmp_path / "no-such-cfg")
    resp = flask_client.get("/api/test_lab/hosts/does_not_exist")
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["success"] is False


def test_hosts_returns_empty_when_disabled(flask_client, tmp_path, monkeypatch):
    _seed_project(tmp_path, monkeypatch,
                  project="proj_disabled",
                  enable_test_lab=False,
                  host_inventory=SAMPLE_INVENTORY)
    resp = flask_client.get("/api/test_lab/hosts/proj_disabled")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["enabled"] is False
    assert body["hosts"] == []


def test_hosts_returns_inventory_shape_when_enabled(flask_client, tmp_path, monkeypatch):
    _seed_project(tmp_path, monkeypatch,
                  project="proj_lab",
                  enable_test_lab=True,
                  host_inventory=SAMPLE_INVENTORY)
    resp = flask_client.get("/api/test_lab/hosts/proj_lab")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["enabled"] is True
    hosts = body["hosts"]
    assert len(hosts) == 4
    names = sorted(h["name"] for h in hosts)
    assert names == ["tldc01", "tllinux01", "tlms01", "tlws01"]
    # Each host must have the contract fields
    for h in hosts:
        assert set(h.keys()) >= {"name", "role", "os_family", "private_ip", "instance_id"}


def test_hosts_returns_empty_payload_when_outputs_not_yet_in_state(flask_client, tmp_path, monkeypatch):
    """enable_test_lab=true but state.json doesn't have the output yet —
    we surface a success:true / hosts:[] / message: hint payload."""
    _seed_project(tmp_path, monkeypatch,
                  project="proj_pending",
                  enable_test_lab=True,
                  host_inventory=None)
    from webapp.backend.routes import test_lab as tl
    # Block the terraform fallback so we don't actually shell out.
    monkeypatch.setattr(tl, "_fetch_host_inventory_via_terraform", lambda: None)
    resp = flask_client.get("/api/test_lab/hosts/proj_pending")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["enabled"] is True
    assert body["hosts"] == []
    assert "host_inventory" in (body.get("message") or "").lower()


# ----------------------------------------------------------------------------
# GET /api/test_lab/status/<project>
# ----------------------------------------------------------------------------


def test_status_404_when_project_unknown(flask_client, tmp_path, monkeypatch):
    from webapp.backend.routes import test_lab as tl
    monkeypatch.setattr(tl, "STATE_DIR", tmp_path / "no-such-dir")
    monkeypatch.setattr(tl, "CONFIGS_DIR", tmp_path / "no-such-cfg")
    resp = flask_client.get("/api/test_lab/status/does_not_exist")
    assert resp.status_code == 404


def test_status_idle_when_disabled(flask_client, tmp_path, monkeypatch):
    _seed_project(tmp_path, monkeypatch,
                  project="proj_disabled",
                  enable_test_lab=False)
    resp = flask_client.get("/api/test_lab/status/proj_disabled")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["enabled"] is False
    assert body["status"] == "idle"
    assert body["last_exit_code"] is None
    assert body["log_tail"] == ""


def test_status_idle_when_no_marker_yet(flask_client, tmp_path, monkeypatch):
    _seed_project(tmp_path, monkeypatch,
                  project="proj_fresh",
                  enable_test_lab=True,
                  host_inventory=SAMPLE_INVENTORY)
    resp = flask_client.get("/api/test_lab/status/proj_fresh")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "idle"


# ----------------------------------------------------------------------------
# POST /api/test_lab/provision/<project>
# ----------------------------------------------------------------------------


def test_provision_404_when_project_unknown(flask_client, tmp_path, monkeypatch):
    from webapp.backend.routes import test_lab as tl
    monkeypatch.setattr(tl, "STATE_DIR", tmp_path / "no-such-dir")
    monkeypatch.setattr(tl, "CONFIGS_DIR", tmp_path / "no-such-cfg")
    resp = flask_client.post("/api/test_lab/provision/does_not_exist")
    assert resp.status_code == 404


def test_provision_400_when_disabled(flask_client, tmp_path, monkeypatch):
    _seed_project(tmp_path, monkeypatch,
                  project="proj_off",
                  enable_test_lab=False,
                  host_inventory=SAMPLE_INVENTORY)
    resp = flask_client.post("/api/test_lab/provision/proj_off")
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["success"] is False
    assert "enable_test_lab" in body["error"]


def test_provision_409_when_outputs_pending(flask_client, tmp_path, monkeypatch):
    """enable_test_lab=true but the host inventory output isn't in state
    yet — the route must NOT try to SSH; it should return 409 so the UI
    can show a sensible error."""
    _seed_project(tmp_path, monkeypatch,
                  project="proj_pending",
                  enable_test_lab=True,
                  host_inventory=None)
    from webapp.backend.routes import test_lab as tl
    monkeypatch.setattr(tl, "_fetch_host_inventory_via_terraform", lambda: None)
    resp = flask_client.post("/api/test_lab/provision/proj_pending")
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["success"] is False


# ----------------------------------------------------------------------------
# YAML inventory shape (the contract the playbooks depend on)
# ----------------------------------------------------------------------------


def test_inventory_yaml_has_required_groups():
    from webapp.backend.routes.test_lab import _build_inventory_yaml
    import yaml
    raw = _build_inventory_yaml(SAMPLE_INVENTORY)
    parsed = yaml.safe_load(raw)
    children = parsed["all"]["children"]
    assert set(children.keys()) == {
        "domain_controllers", "member_servers", "workstations", "linux_members"
    }
    # Windows hosts get WinRM/NTLM, Linux gets SSH
    dc = children["domain_controllers"]["hosts"]["tldc01"]
    assert dc["ansible_connection"] == "winrm"
    assert dc["ansible_winrm_transport"] == "ntlm"
    assert dc["ansible_port"] == 5985
    linux = children["linux_members"]["hosts"]["tllinux01"]
    assert linux["ansible_connection"] == "ssh"


def test_inventory_yaml_skips_unknown_roles():
    from webapp.backend.routes.test_lab import _build_inventory_yaml
    import yaml
    inv = {
        "tldc01":  {"private_ip": "10.0.20.10", "role": "domain_controller", "os_family": "windows", "instance_id": "i-1"},
        "weird01": {"private_ip": "10.0.20.99", "role": "mystery_role",      "os_family": "windows", "instance_id": "i-2"},
    }
    parsed = yaml.safe_load(_build_inventory_yaml(inv))
    children = parsed["all"]["children"]
    assert "tldc01" in children["domain_controllers"]["hosts"]
    # weird01 must not leak into any group
    for group in children.values():
        assert "weird01" not in (group.get("hosts") or {})


def test_secrets_yaml_carries_the_two_vault_keys():
    from webapp.backend.routes.test_lab import _build_secrets_yaml
    import yaml
    parsed = yaml.safe_load(_build_secrets_yaml())
    assert parsed["vault_ansible_password"] == "Ansible123!"
    assert parsed["vault_domain_admin_password"] == "Password1!"
