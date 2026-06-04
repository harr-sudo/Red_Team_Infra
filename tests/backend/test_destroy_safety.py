"""Pre-destroy foreign-module safety system.

Covers four surfaces of the deploy-safety feature shipped 2026-05-19:

1. ``expected_modules_for`` — pure function, deterministic taxonomy.
2. ``GET /api/deploy/state-summary/<project>`` — read-only probe.
3. ``POST /api/deploy/detach-foreign/<project>`` — recovery action.
4. ``POST /api/deploy/destroy`` — refusal path (HTTP 409) + force override.

The shell-out path through ``TerraformService`` is mocked at the boundary
— we never invoke real terraform here. The point of these tests is to
pin the safety policy + endpoint contract, NOT to re-test terraform
itself.

All tests run under the autouse ``_isolate_dashboard_stores`` fixture
from ``tests/backend/conftest.py`` so audit writes land in a tmpdir.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from webapp.backend.utils.destroy_safety import (
    expected_modules_for,
    parse_top_level_modules,
    compute_foreign_modules,
)
from webapp.backend.routes import deploy as deploy_route


# ---------------------------------------------------------------------------
# 1. expected_modules_for() — taxonomy
# ---------------------------------------------------------------------------

def test_goad_mini_expected_modules_excludes_c2():
    """goad-mini deployments should NOT carry any C2 modules — destroying
    one must not flag goad as foreign if it's there, AND must NOT silently
    accept c2_team_server as expected."""
    expected = expected_modules_for("goad-mini")
    assert "goad" in expected
    assert "vpc" in expected
    assert "security" in expected
    assert "cs_storage" in expected
    assert "attack_box" in expected
    assert "c2_team_server" not in expected
    assert "proxy_redirector" not in expected
    assert "bastion" not in expected
    assert "vpc_peering" not in expected
    # dashboard_server NEVER belongs — that's the bug this whole system exists for.
    assert "dashboard_server" not in expected


def test_c2_adhoc_expected_modules_includes_c2_chain():
    expected = expected_modules_for("c2-adhoc")
    for m in ("vpc", "security", "c2_team_server", "proxy_redirector", "bastion", "dns", "certificates", "domain_fronting"):
        assert m in expected, f"{m} missing from c2-adhoc expected modules"
    assert "goad" not in expected
    assert "vpc_peering" not in expected


def test_combined_includes_both_halves_and_peering():
    expected = expected_modules_for("combined-adhoc-mini")
    assert "vpc_peering" in expected
    assert "goad" in expected
    assert "c2_team_server" in expected
    assert "bastion" in expected


def test_test_lab_flag_adds_test_lab_module_only_when_enabled():
    base = expected_modules_for("c2-adhoc", enable_test_lab=False)
    enabled = expected_modules_for("c2-adhoc", enable_test_lab=True)
    assert "test_lab" not in base
    assert "test_lab" in enabled


def test_unknown_deployment_type_returns_base_set():
    """An unknown deployment_type returns the base set, NOT an empty set
    — defensive: over-flag rather than silently allow foreign modules."""
    expected = expected_modules_for("totally-unknown")
    assert "vpc" in expected
    assert "security" in expected
    # No type-specific modules.
    assert "goad" not in expected
    assert "c2_team_server" not in expected


def test_empty_deployment_type_does_not_raise():
    expected = expected_modules_for("")
    assert "vpc" in expected
    expected = expected_modules_for(None)
    assert "vpc" in expected


# ---------------------------------------------------------------------------
# 2. parse_top_level_modules() — handles count + for_each indexing
# ---------------------------------------------------------------------------

def test_parse_strips_count_index():
    out = parse_top_level_modules(
        "module.vpc[0].aws_vpc.main\n"
        "module.dashboard_server[0].aws_dynamodb_table.tflock\n"
    )
    assert out == {"vpc", "dashboard_server"}


def test_parse_strips_for_each_index():
    out = parse_top_level_modules(
        'module.goad[0].module.windows_vm["dc01"].aws_instance.win\n'
    )
    assert out == {"goad"}


def test_parse_ignores_root_resources():
    """Root-level resources (no module prefix) are never foreign — they
    live in main.tf, not a module."""
    out = parse_top_level_modules(
        "aws_key_pair.deployer[0]\n"
        "random_password.team_server[0]\n"
        "module.vpc[0].aws_vpc.main\n"
    )
    assert out == {"vpc"}


def test_parse_skips_blank_lines_and_comments():
    out = parse_top_level_modules(
        "\n# header\nmodule.security[0].aws_security_group.bastion\n\n"
    )
    assert out == {"security"}


# ---------------------------------------------------------------------------
# 3. compute_foreign_modules()
# ---------------------------------------------------------------------------

def test_compute_foreign_modules_flags_dashboard_server_on_goad_mini():
    foreign = compute_foreign_modules(
        "goad-mini",
        ["vpc", "security", "attack_box", "cs_storage", "goad", "dashboard_server"],
    )
    assert foreign == ["dashboard_server"]


def test_compute_foreign_modules_returns_sorted_list():
    foreign = compute_foreign_modules(
        "c2-adhoc",
        ["vpc", "security", "z_foreign", "a_foreign"],
    )
    assert foreign == ["a_foreign", "z_foreign"]


def test_compute_foreign_modules_empty_when_clean():
    foreign = compute_foreign_modules(
        "goad-mini",
        ["vpc", "security", "attack_box", "cs_storage", "goad"],
    )
    assert foreign == []


# ---------------------------------------------------------------------------
# Shared fixture — wire deploy_route with a tmp configs/ + mocked service
# ---------------------------------------------------------------------------

@pytest.fixture
def safety_routes_isolated(monkeypatch, tmp_path):
    """Stage a per-project tfvars under a tmp configs/ + mock the
    project's TerraformService so state_list / state_rm return controlled
    fixtures. Lets us drive the destroy guard + the two new endpoints
    end-to-end through Flask's test_client without shelling out."""

    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()

    # Plant a goad-mini tfvars matching the real-world bug scenario.
    (configs_dir / "goad_mini_lab.tfvars").write_text(
        'project_name = "goad_mini_lab"\n'
        'deployment_type = "goad-mini"\n'
    )
    # And a clean c2-adhoc workspace for negative-control tests.
    (configs_dir / "c2_clean.tfvars").write_text(
        'project_name = "c2_clean"\n'
        'deployment_type = "c2-adhoc"\n'
    )

    monkeypatch.setattr(deploy_route, "project_root", tmp_path)

    # Default mock service — tests override state_list / state_rm per-case.
    mock_service = MagicMock()
    mock_service.workspace_name = "goad_mini_lab"
    mock_service.tfvars_file = configs_dir / "goad_mini_lab.tfvars"
    mock_service.state_list.return_value = {
        "success": True,
        "exit_code": 0,
        "stdout": "",
        "stderr": "",
        "addresses": [],
        "workspace": "goad_mini_lab",
    }
    mock_service.state_rm.return_value = {
        "success": True,
        "exit_code": 0,
        "stdout": "Removed module.dashboard_server",
        "stderr": "",
        "workspace": "goad_mini_lab",
    }

    # Replace the factory so every get_service_for_project(...) call
    # returns this mock.
    monkeypatch.setattr(deploy_route, "get_service_for_project", lambda name: mock_service)

    # Reset deployment_state globals so the "already running" guard doesn't trip.
    monkeypatch.setattr(deploy_route, "deployment_state", deploy_route.create_empty_state())
    monkeypatch.setattr(deploy_route, "deployment_states", {})

    yield {
        "tmp_path": tmp_path,
        "configs_dir": configs_dir,
        "service": mock_service,
    }


# ---------------------------------------------------------------------------
# 4. GET /api/deploy/state-summary/<project>
# ---------------------------------------------------------------------------

def test_state_summary_flags_dashboard_server_on_goad_mini(flask_client, safety_routes_isolated):
    """The headline scenario: dashboard_server pinned to a goad-mini workspace."""
    svc = safety_routes_isolated["service"]
    svc.state_list.return_value = {
        "success": True,
        "stdout": (
            "module.vpc[0].aws_vpc.main\n"
            "module.security[0].aws_security_group.bastion\n"
            "module.attack_box[0].aws_instance.attack_box\n"
            "module.cs_storage[0].aws_s3_bucket.deployment\n"
            "module.goad[0].aws_instance.dc01\n"
            "module.dashboard_server[0].aws_dynamodb_table.tflock\n"
        ),
        "stderr": "",
        "addresses": [],
        "exit_code": 0,
        "workspace": "goad_mini_lab",
    }
    r = flask_client.get("/api/deploy/state-summary/goad_mini_lab")
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["success"] is True
    assert body["deployment_type"] == "goad-mini"
    assert "dashboard_server" in body["foreign_modules"]
    assert "goad" in body["actual_modules"]
    assert "goad" in body["expected_modules"]


def test_state_summary_clean_workspace_no_foreign_modules(flask_client, safety_routes_isolated):
    svc = safety_routes_isolated["service"]
    svc.state_list.return_value = {
        "success": True,
        "stdout": (
            "module.vpc[0].aws_vpc.main\n"
            "module.security[0].aws_security_group.bastion\n"
            "module.attack_box[0].aws_instance.attack_box\n"
            "module.cs_storage[0].aws_s3_bucket.deployment\n"
            "module.goad[0].aws_instance.dc01\n"
        ),
        "stderr": "",
        "addresses": [],
        "exit_code": 0,
        "workspace": "goad_mini_lab",
    }
    r = flask_client.get("/api/deploy/state-summary/goad_mini_lab")
    body = r.get_json()
    assert body["success"] is True
    assert body["foreign_modules"] == []


def test_state_summary_invalid_project_name_returns_400(flask_client, safety_routes_isolated):
    """The sanitizer turns reserved/empty inputs into "" → 400."""
    r = flask_client.get("/api/deploy/state-summary/__draft__")
    # __draft__ sanitizes to "" → invalid_project_name.
    assert r.status_code == 400
    body = r.get_json()
    assert body["success"] is False
    assert body["error"] == "invalid_project_name"


# ---------------------------------------------------------------------------
# 5. POST /api/deploy/destroy — refusal path
# ---------------------------------------------------------------------------

def test_destroy_refuses_when_foreign_modules_present(flask_client, safety_routes_isolated, monkeypatch):
    svc = safety_routes_isolated["service"]
    svc.state_list.return_value = {
        "success": True,
        "stdout": (
            "module.vpc[0].aws_vpc.main\n"
            "module.security[0].aws_security_group.bastion\n"
            "module.attack_box[0].aws_instance.attack_box\n"
            "module.cs_storage[0].aws_s3_bucket.deployment\n"
            "module.goad[0].aws_instance.dc01\n"
            "module.dashboard_server[0].aws_dynamodb_table.tflock\n"
        ),
        "stderr": "",
        "addresses": [],
        "exit_code": 0,
        "workspace": "goad_mini_lab",
    }
    # No-op the destroy thread so we don't actually fire terraform if
    # the guard regresses.
    monkeypatch.setattr(
        deploy_route.threading,
        "Thread",
        lambda *a, **kw: MagicMock(start=MagicMock(), daemon=False),
    )

    r = flask_client.post(
        "/api/deploy/destroy",
        json={"project_name": "goad_mini_lab", "confirm": "DESTROY"},
    )
    assert r.status_code == 409
    body = r.get_json()
    assert body["success"] is False
    assert body["error"] == "foreign_modules_in_state"
    assert "dashboard_server" in body["foreign_modules"]
    assert body["deployment_type"] == "goad-mini"
    # Both recovery actions exposed to the UI.
    action_ids = {a["id"] for a in body["actions"]}
    assert action_ids == {"detach-foreign", "force-anyway"}


def test_destroy_allows_when_state_is_clean(flask_client, safety_routes_isolated, monkeypatch):
    svc = safety_routes_isolated["service"]
    svc.state_list.return_value = {
        "success": True,
        "stdout": (
            "module.vpc[0].aws_vpc.main\n"
            "module.security[0].aws_security_group.bastion\n"
            "module.attack_box[0].aws_instance.attack_box\n"
            "module.cs_storage[0].aws_s3_bucket.deployment\n"
            "module.goad[0].aws_instance.dc01\n"
        ),
        "stderr": "",
        "addresses": [],
        "exit_code": 0,
        "workspace": "goad_mini_lab",
    }
    monkeypatch.setattr(
        deploy_route.threading,
        "Thread",
        lambda *a, **kw: MagicMock(start=MagicMock(), daemon=False),
    )

    r = flask_client.post(
        "/api/deploy/destroy",
        json={"project_name": "goad_mini_lab", "confirm": "DESTROY"},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True


def test_destroy_force_foreign_url_flag_bypasses_safety_check(
    flask_client, safety_routes_isolated, monkeypatch
):
    svc = safety_routes_isolated["service"]
    svc.state_list.return_value = {
        "success": True,
        "stdout": (
            "module.vpc[0].aws_vpc.main\n"
            "module.dashboard_server[0].aws_dynamodb_table.tflock\n"
        ),
        "stderr": "",
        "addresses": [],
        "exit_code": 0,
        "workspace": "goad_mini_lab",
    }
    monkeypatch.setattr(
        deploy_route.threading,
        "Thread",
        lambda *a, **kw: MagicMock(start=MagicMock(), daemon=False),
    )

    r = flask_client.post(
        "/api/deploy/destroy?force_foreign=1",
        json={"project_name": "goad_mini_lab", "confirm": "DESTROY"},
    )
    body = r.get_json()
    assert r.status_code == 200, body
    assert body["success"] is True
    assert body.get("force_foreign") is True


def test_destroy_still_requires_confirm_word_even_with_force(
    flask_client, safety_routes_isolated, monkeypatch
):
    """The URL flag is the safety-check override only — it does NOT
    bypass the ``confirm: DESTROY`` requirement."""
    monkeypatch.setattr(
        deploy_route.threading,
        "Thread",
        lambda *a, **kw: MagicMock(start=MagicMock(), daemon=False),
    )
    r = flask_client.post(
        "/api/deploy/destroy?force_foreign=1",
        json={"project_name": "goad_mini_lab"},  # missing confirm
    )
    assert r.status_code == 400
    body = r.get_json()
    assert body["success"] is False
    assert "Confirmation required" in body["error"]


# ---------------------------------------------------------------------------
# 6. POST /api/deploy/detach-foreign/<project>
# ---------------------------------------------------------------------------

def test_detach_foreign_calls_state_rm_for_each_foreign_module(
    flask_client, safety_routes_isolated
):
    svc = safety_routes_isolated["service"]
    svc.state_list.return_value = {
        "success": True,
        "stdout": (
            "module.vpc[0].aws_vpc.main\n"
            "module.goad[0].aws_instance.dc01\n"
            "module.dashboard_server[0].aws_dynamodb_table.tflock\n"
            "module.security[0].aws_security_group.bastion\n"
            "module.attack_box[0].aws_instance.attack_box\n"
            "module.cs_storage[0].aws_s3_bucket.deployment\n"
        ),
        "stderr": "",
        "addresses": [],
        "exit_code": 0,
        "workspace": "goad_mini_lab",
    }

    r = flask_client.post("/api/deploy/detach-foreign/goad_mini_lab")
    body = r.get_json()
    assert r.status_code == 200, body
    assert body["success"] is True
    assert body["detached"] == ["dashboard_server"]
    # state_rm called exactly once with the foreign module's address.
    addrs_called = [c.args[0] for c in svc.state_rm.call_args_list]
    assert "module.dashboard_server" in addrs_called


def test_detach_foreign_no_op_when_state_is_clean(flask_client, safety_routes_isolated):
    svc = safety_routes_isolated["service"]
    svc.state_list.return_value = {
        "success": True,
        "stdout": (
            "module.vpc[0].aws_vpc.main\n"
            "module.security[0].aws_security_group.bastion\n"
            "module.attack_box[0].aws_instance.attack_box\n"
            "module.cs_storage[0].aws_s3_bucket.deployment\n"
            "module.goad[0].aws_instance.dc01\n"
        ),
        "stderr": "",
        "addresses": [],
        "exit_code": 0,
        "workspace": "goad_mini_lab",
    }
    r = flask_client.post("/api/deploy/detach-foreign/goad_mini_lab")
    body = r.get_json()
    assert r.status_code == 200
    assert body["success"] is True
    assert body["detached"] == []
    svc.state_rm.assert_not_called()


def test_detach_foreign_partial_failure_returns_207(flask_client, safety_routes_isolated):
    """If state_rm fails for one of N foreign modules, return 207
    Multi-Status so the UI can show partial success."""
    svc = safety_routes_isolated["service"]
    svc.state_list.return_value = {
        "success": True,
        "stdout": (
            "module.vpc[0].aws_vpc.main\n"
            "module.goad[0].aws_instance.dc01\n"
            "module.attack_box[0].aws_instance.attack_box\n"
            "module.cs_storage[0].aws_s3_bucket.deployment\n"
            "module.security[0].aws_security_group.bastion\n"
            "module.foo[0].aws_thing.x\n"
            "module.bar[0].aws_thing.y\n"
        ),
        "stderr": "",
        "addresses": [],
        "exit_code": 0,
        "workspace": "goad_mini_lab",
    }

    def state_rm_side_effect(addr):
        if "bar" in addr:
            return {"success": False, "stderr": "boom", "exit_code": 1, "address": addr, "workspace": "goad_mini_lab", "stdout": ""}
        return {"success": True, "stderr": "", "exit_code": 0, "address": addr, "workspace": "goad_mini_lab", "stdout": "removed"}

    svc.state_rm.side_effect = state_rm_side_effect

    r = flask_client.post("/api/deploy/detach-foreign/goad_mini_lab")
    assert r.status_code == 207
    body = r.get_json()
    assert body["success"] is False
    assert body["detached"] == ["foo"]
    assert any(e["module"] == "bar" for e in body["errors"])


def test_detach_foreign_invalid_project_name_returns_400(flask_client, safety_routes_isolated):
    r = flask_client.post("/api/deploy/detach-foreign/__all__")
    assert r.status_code == 400
    body = r.get_json()
    assert body["success"] is False
    assert body["error"] == "invalid_project_name"
