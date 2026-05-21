"""Backend legacy-path retirement assertions.

This test file pins the contract established by the 2026-05-21
``BACKEND_LEGACY_AUDIT.md`` retirement sweep:

1. **No write-path handler reads the global ``configs/terraform.tfvars``
   directly.** Anything that mutates terraform state (Plan / Apply /
   Destroy / Purge / Detach) must resolve per-project tfvars via the
   shared sanitizer in ``utils.tfvars_path``.

2. **Every terraform-touching route accepts (and respects) ``project=``
   or body ``project_name``.** A request that targets a real per-project
   tfvars must NOT silently fall back to the global tfvars or the
   default workspace.

3. **Orphaned legacy routes return 404.** The routes deleted in the
   sweep (``/init``, ``/workspaces``, ``/connection-info`` family,
   ``/upload-to-s3``, ``/history/add``, ``/generate-project-name``,
   ``/status/all``, ``/goad-status``, ``/infrastructure/refresh``,
   ``/api/tools/projects``) must stay deleted.

4. **The destroy safety guard still fires for foreign modules.** The
   ``test_destroy_safety.py`` suite covers the runtime behaviour — this
   file just asserts the route exists and the import chain stays intact.

These checks run against the real Flask app (mounted on the
``flask_client`` fixture from tests/conftest.py).
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from webapp.backend.routes import deploy as deploy_route


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEPLOY_PY = REPO_ROOT / "webapp" / "backend" / "routes" / "deploy.py"
GOAD_PY = REPO_ROOT / "webapp" / "backend" / "routes" / "goad.py"
TOOLS_PY = REPO_ROOT / "webapp" / "backend" / "routes" / "tools.py"

# Handlers that MUTATE terraform state — these are the routes that must
# never hardcode the global tfvars without per-project resolution. The
# 2026-05-21 sweep eliminated all global-tfvars literal references that
# weren't either (a) wrapped in _resolve_project_tfvars /
# _project_tfvars_for, (b) inside _scan_tfvars_for_domains (which
# deliberately walks every config), or (c) inside the read-only
# /resources/all-projects cross-project view.
_ALLOWED_GLOBAL_TFVARS_CALLERS = {
    # Cross-project endpoints that intentionally read the global tfvars
    # for a region fallback (no single "active project" applies).
    "get_all_project_resources",
    # Walks every config including the legacy global to produce the
    # domain -> project map. Has to look at the literal name.
    "_scan_tfvars_for_domains",
}


# ---------------------------------------------------------------------------
# Category 7 — orphaned routes stay deleted
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path,method", [
    ("/api/deploy/init", "POST"),
    ("/api/deploy/workspaces", "GET"),
    ("/api/deploy/status/all", "GET"),
    ("/api/deploy/generate-project-name", "GET"),
    ("/api/deploy/connection-info", "GET"),
    ("/api/deploy/connection-info/quick", "GET"),
    ("/api/deploy/ssh-fingerprints", "GET"),
    ("/api/deploy/infrastructure/refresh", "POST"),
    ("/api/deploy/upload-to-s3", "POST"),
    ("/api/deploy/history/add", "POST"),
    ("/api/deploy/goad-status", "GET"),
    ("/api/tools/projects", "GET"),
])
def test_orphan_route_returns_404(flask_client, path, method):
    """Routes deleted in the legacy sweep MUST stay deleted.

    Accept either 404 (no route) or 405 (the path falls through to the
    Flask static-file handler, which only serves GETs — so a POST to a
    URL that doesn't exist as an API route surfaces as 405). Both mean
    "the API route is gone".
    """
    resp = flask_client.open(path, method=method)
    assert resp.status_code in (404, 405), (
        f"Expected 404/405 for retired route {method} {path}, got {resp.status_code}. "
        f"Did someone reintroduce the legacy handler?"
    )


# ---------------------------------------------------------------------------
# Category 1 — no terraform-write handler reads global tfvars directly
# ---------------------------------------------------------------------------

def test_deploy_py_does_not_hardcode_global_tfvars_for_writes():
    """Scan deploy.py for literal ``configs/terraform.tfvars`` reads.

    Allowed:
      * occurrences inside the helper functions ``_resolve_project_tfvars``,
        ``_project_tfvars_for``, ``_read_project_config``, ``_get_aws_region``
        — these ARE the per-project resolvers and SHOULD reference the
        legacy global as a fallback.
      * occurrences inside ``get_all_project_resources`` (cross-project
        cleanup view — see allowlist comment in the source).
      * lines that name the path as ``global_tfvars`` AND immediately
        pass it to ``_resolve_project_tfvars`` / ``_project_tfvars_for``
        as the fallback argument — the per-project resolver requires
        knowing where the legacy global lives.

    Anything else means a route is still reading the global config
    directly.
    """
    text = DEPLOY_PY.read_text()
    lines = text.splitlines()
    offenders = []

    current_func = None
    for idx, line in enumerate(lines, start=1):
        d = re.match(r"^def\s+([A-Za-z_][A-Za-z_0-9]*)", line)
        if d:
            current_func = d.group(1)
        if 'terraform.tfvars' not in line:
            continue
        # Strip false positives: comments / docstrings / error messages.
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # Match string-literal occurrences in docstrings ("""...""")
        # and error-message strings (``"Configuration file (terraform.tfvars)..."``)
        # — these are user-facing strings, not file reads.
        if stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        if re.search(r'"[^"]*terraform\.tfvars[^"]*"', stripped) and \
           '/' not in stripped.split('terraform.tfvars')[0].split('=', 1)[-1]:
            # Bare error-message strings (no path-join syntax around them).
            continue
        # Allowlisted helpers + cross-project endpoint.
        if current_func in _ALLOWED_GLOBAL_TFVARS_CALLERS:
            continue
        if current_func in {
            "_resolve_project_tfvars", "_project_tfvars_for",
            "_read_project_config", "_get_aws_region",
            # Helpers that take a tfvars path AS A PARAMETER — the
            # docstring references the name, the function never reads
            # the global path itself.
            "update_tfvars_cs_path", "update_tfvars_cs_client_path",
            "extract_and_inject_github_token",
        }:
            continue
        # Allowed: assigning to a `global_tfvars` variable that gets
        # passed straight into the resolver later in the same handler.
        if re.search(r"global_tfvars\s*=.*terraform\.tfvars", line):
            tail = "\n".join(lines[idx - 1:min(idx + 10, len(lines))])
            if "_resolve_project_tfvars(" in tail or "_project_tfvars_for(" in tail:
                continue
        offenders.append((idx, current_func, stripped))

    assert not offenders, (
        "Found global terraform.tfvars references in deploy.py write paths:\n"
        + "\n".join(f"  line {ln} in {fn}: {src}" for ln, fn, src in offenders)
        + "\nRoute the call through utils.tfvars_path.resolve_tfvars_path / "
          "_read_project_config instead."
    )


# ---------------------------------------------------------------------------
# Category 2 — terraform-write handlers respect ?project=
# ---------------------------------------------------------------------------

@pytest.fixture
def per_project_tfvars(monkeypatch, tmp_path):
    """Minimal per-project tfvars fixture for routing assertions."""
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    global_tfvars = configs_dir / "terraform.tfvars"
    global_tfvars.write_text(
        'project_name = "global_project"\n'
        'aws_region = "eu-west-1"\n'
        'deployment_type = "c2-adhoc"\n'
    )
    project_tfvars = configs_dir / "lab_beta.tfvars"
    project_tfvars.write_text(
        'project_name = "lab_beta"\n'
        'aws_region = "us-east-2"\n'
        'deployment_type = "goad-mini"\n'
        'primary_domain_name = ""\n'
    )
    monkeypatch.setattr(deploy_route, "project_root", tmp_path)

    mock_service = MagicMock()
    mock_service.terraform_dir = tmp_path / "terraform"
    (tmp_path / "terraform" / ".terraform").mkdir(parents=True, exist_ok=True)
    mock_service.workspace_name = "default"
    mock_service.tfvars_file = global_tfvars
    mock_service.init.return_value = {"success": True}
    mock_service.workspace_select.return_value = {"success": True, "workspace": "lab_beta"}
    mock_service.plan.return_value = {
        "success": True, "stdout": "", "stderr": "", "full_output": "",
        "exit_code": 0, "plan": {},
    }
    monkeypatch.setattr(deploy_route, "terraform_service", mock_service)
    return {
        "tmp_path": tmp_path,
        "configs_dir": configs_dir,
        "global_tfvars": global_tfvars,
        "project_tfvars": project_tfvars,
        "service": mock_service,
    }


def test_plan_routes_to_per_project_workspace(flask_client, per_project_tfvars):
    """``/api/deploy/plan?project=lab_beta`` must retarget the workspace.

    This is the canonical write-path contract — the destroy safety
    sweep depends on Plan/Apply/Destroy all picking the SAME workspace
    for a given project. If Plan goes to ``default`` while Destroy goes
    to ``lab_beta``, the safety guard's expected-vs-actual delta is
    meaningless.
    """
    resp = flask_client.get("/api/deploy/plan?project=lab_beta")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    svc = per_project_tfvars["service"]
    assert svc.workspace_name == "lab_beta", (
        f"Plan didn't move workspace to lab_beta, still on {svc.workspace_name}"
    )
    assert svc.tfvars_file == per_project_tfvars["project_tfvars"]


def test_instance_status_reads_per_project_region(flask_client, per_project_tfvars, monkeypatch):
    """``/instance-status?project=lab_beta`` must read region from lab_beta.tfvars.

    Regression for the legacy pattern where the route always read
    ``configs/terraform.tfvars`` for ``aws_region``, even when the caller
    explicitly named a per-project workspace.
    """
    import boto3
    seen_region = {}

    class _FakeEC2:
        def describe_instances(self, **kwargs):
            return {"Reservations": []}

    def _fake_client(name, region_name=None):
        seen_region["region"] = region_name
        return _FakeEC2()

    monkeypatch.setattr(boto3, "client", _fake_client)
    resp = flask_client.get("/api/deploy/instance-status?project=lab_beta")
    assert resp.status_code == 200
    # lab_beta.tfvars sets aws_region = us-east-2; legacy code would have
    # picked eu-west-1 from the global tfvars.
    assert seen_region.get("region") == "us-east-2", (
        f"instance-status used wrong region {seen_region.get('region')!r} — "
        "should be us-east-2 (from per-project tfvars)."
    )


def test_stop_endpoint_resolves_per_project_region(flask_client, per_project_tfvars, monkeypatch):
    """``POST /stop`` with ``project_name`` in body must use per-project region."""
    import boto3
    seen_region = {}

    class _FakeEC2:
        def describe_instances(self, **kwargs):
            return {"Reservations": []}

    def _fake_client(name, region_name=None):
        seen_region["region"] = region_name
        return _FakeEC2()

    monkeypatch.setattr(boto3, "client", _fake_client)
    resp = flask_client.post(
        "/api/deploy/stop",
        json={"project_name": "lab_beta"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert seen_region.get("region") == "us-east-2"


# ---------------------------------------------------------------------------
# Category 2 — workspace_name pinning audit
# ---------------------------------------------------------------------------

def test_no_route_force_pins_workspace_to_default_for_state_mutation():
    """Static scan: no terraform-write handler should assign
    ``workspace_name = "default"`` AFTER a project resolution.

    The legitimate occurrences are:
      * The TerraformService constructor default (services/terraform_service.py)
      * The workspace_select("default") call inside check_project_name
        (which intentionally restores the default workspace after probing
        a candidate per-project workspace).

    Anything in a route handler that resets the workspace to default
    before running terraform would silently target the wrong state file.
    """
    text = DEPLOY_PY.read_text()
    # Find pattern: "workspace_name = "default"" assignment inside this file
    matches = re.findall(
        r'\.workspace_name\s*=\s*"default"',
        text,
    )
    # The only allowed match is the restore inside check_project_name —
    # which uses workspace_select("default"), not direct assignment.
    assert len(matches) == 0, (
        f"Found {len(matches)} direct .workspace_name = \"default\" assignments "
        "in deploy.py. Use service.workspace_select(...) with the resolved "
        "per-project workspace instead."
    )


# ---------------------------------------------------------------------------
# Category 6 — cost endpoints + CE-guardrail audit
# ---------------------------------------------------------------------------

def test_cost_service_force_refresh_is_off_by_default():
    """The Cost Explorer guardrail relies on every caller defaulting
    ``force_refresh=False``. Audit the public surface."""
    import inspect
    from webapp.backend.services.cost_service import CostService

    sig = inspect.signature(CostService.get_aws_costs)
    assert sig.parameters["force_refresh"].default is False, (
        "CostService.get_aws_costs.force_refresh default must remain False — "
        "every CE call costs $0.01 and the daily-limit guard relies on this."
    )

    sig2 = inspect.signature(CostService.get_cost_summary)
    assert sig2.parameters["force_refresh"].default is False


def test_only_cost_service_calls_cost_explorer():
    """boto3.client('ce', ...) MUST live exclusively inside cost_service.py.

    Any other module that opens a CE client would bypass the daily call-
    counter guardrail (and could silently burn the operator's budget).
    """
    src_dir = REPO_ROOT / "webapp" / "backend"
    offenders = []
    for py in src_dir.rglob("*.py"):
        if "__pycache__" in str(py):
            continue
        text = py.read_text()
        # Match boto3.client("ce", ...) but not boto3.client("ec2",...)
        if re.search(r"boto3\.client\(\s*['\"]ce['\"]", text):
            if py.name != "cost_service.py":
                offenders.append(str(py.relative_to(REPO_ROOT)))
    assert not offenders, (
        "Cost Explorer clients found outside cost_service.py: "
        f"{offenders}. Route every CE call through CostService so the "
        "daily-limit guard fires."
    )


# ---------------------------------------------------------------------------
# Destroy safety — guard is still wired in (runtime tested in
# test_destroy_safety.py, this just smokes the import chain)
# ---------------------------------------------------------------------------

def test_destroy_route_imports_safety_helpers():
    """Sanity: deploy.py still imports the destroy-safety helpers.

    A refactor that accidentally drops the import would silently take
    the guard out of service. ``test_destroy_safety.py`` will still
    catch the runtime regression, but failing fast here gives a clearer
    error message ("you removed the import") than the later "AttributeError".
    """
    import webapp.backend.utils.destroy_safety  # noqa: F401
    from webapp.backend.routes.deploy import (  # noqa: F401
        _summarize_state_for_safety,
        _expected_modules_for,
        _parse_top_level_modules,
        _compute_foreign_modules,
    )


# ---------------------------------------------------------------------------
# Category 4 — GOAD lifecycle routes accept ?project=
# ---------------------------------------------------------------------------

def test_goad_lifecycle_routes_accept_project_param():
    """GOAD start/stop/instance-status used to hardcode global tfvars.

    They now accept ``?project=`` (and body ``project_name``) so the
    Manage sub-pill can target one GOAD lab even when multiple are
    present.
    """
    text = GOAD_PY.read_text()
    for route_fn in ("start_goad", "stop_goad", "get_goad_instance_status"):
        # Each handler should reference both request.args.get('project')
        # AND resolve_tfvars_path — this catches the most common
        # regression (someone deletes the per-project lookup).
        # We scan by function header to function end (next def).
        m = re.search(rf"def {route_fn}\b[\s\S]+?(?=\ndef |\Z)", text)
        assert m, f"GOAD handler {route_fn} not found"
        body = m.group(0)
        assert "request.args.get('project')" in body or 'request.args.get("project")' in body, (
            f"{route_fn} no longer reads ?project= — regression."
        )
        assert "resolve_tfvars_path" in body, (
            f"{route_fn} no longer routes through resolve_tfvars_path — "
            "may be reading the global tfvars again."
        )
