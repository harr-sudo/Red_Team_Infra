"""Pre-destroy safety: expected vs actual terraform-state modules.

When an operator clicks Destroy in Manage, we MUST refuse if the workspace's
terraform state contains modules that are not part of the deployment's
declared shape. That happens when an operator accidentally applied a
"foreign" module (e.g. the dashboard server, the shared tflock table) into
a deployment workspace at provisioning time — destroying that workspace
would nuke shared infrastructure used by other deployments AND by the
management UI itself.

This module is the single source of truth for:

  1) ``expected_modules_for(deployment_type, enable_test_lab=False)``
     Returns the SET of top-level terraform module names that *should*
     legitimately appear in the state for the given deployment_type.

  2) ``parse_top_level_modules(state_list_output)``
     Parses ``terraform state list`` output and returns the unique
     top-level module names (stripping ``[idx]`` / ``[\"k\"]`` indexing
     and any nested ``.module.<child>`` segments).

  3) ``compute_foreign_modules(deployment_type, actual_modules, enable_test_lab)``
     Convenience: ``actual_modules - expected_modules``, ignoring any
     module name that's not really a "first-class" module (data sources
     and resources at the root level live outside ``module.*`` and are
     never flagged here).

The destroy route uses these to short-circuit the destroy thread before
``terraform destroy`` ever runs — see ``webapp.backend.routes.deploy``.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Set


# --- Expected-modules taxonomy ------------------------------------------------
#
# These five modules are present in EVERY non-trivial deployment (c2-*,
# goad-*, combined-*). They get provisioned from the shared chrome in
# terraform/main.tf:
#
#   - vpc, security: foundational networking + SGs
#   - attack_box:    optional Windows attacker workstation
#                    (gated by var.enable_attack_box, but it's "expected
#                    if present" — never flag as foreign)
#   - cs_storage:    S3 deployment bucket + IAM roles (the directory is
#                    `modules/deployment_storage/` but the module is
#                    declared as `module "cs_storage"` in main.tf —
#                    the safety check follows the *declared* name)
#
# Note: there is NO module named ``deployment_storage`` in main.tf — the
# spec lists it because the underlying directory is called that. We accept
# both names defensively so a future rename does not silently re-introduce
# the bug we are trying to prevent.
_BASE_MODULES: Set[str] = {
    "vpc",
    "security",
    "attack_box",
    "cs_storage",
    "deployment_storage",
}

# c2-* and the C2 half of combined-* layouts.
_C2_MODULES: Set[str] = {
    "c2_team_server",
    "c2_phase_servers",
    "proxy_redirector",
    "bastion",
    "dns",
    "certificates",
    "domain_fronting",
}

# goad-* and the GOAD half of combined-* layouts.
_GOAD_MODULES: Set[str] = {
    "goad",
}

# combined-* only — VPC peering between the C2 and GOAD VPCs.
_COMBINED_MODULES: Set[str] = {
    "vpc_peering",
}

# enable_test_lab — c2-* only, gated separately.
_TEST_LAB_MODULES: Set[str] = {
    "test_lab",
}

# CCRTS-Lab modules. The single self-contained ``ccrts`` deployment
# gets ``ccrts_lab`` plus the BASE set (vpc / security / cs_storage).
# There is no C2 integration or combined mode.
_CCRTS_MODULES: Set[str] = {
    "ccrts_lab",
}


def expected_modules_for(
    deployment_type: str | None,
    enable_test_lab: bool = False,
) -> Set[str]:
    """Return the set of top-level module names expected for a deployment.

    Always returns at least ``_BASE_MODULES``. Returns the BASE set if
    ``deployment_type`` is unknown / empty — better to over-flag than to
    silently let foreign modules through. Callers should validate
    ``deployment_type`` separately if they need stricter behavior.
    """
    expected = set(_BASE_MODULES)
    dtype = (deployment_type or "").strip().lower()

    if dtype.startswith("c2-"):
        expected |= _C2_MODULES
        if enable_test_lab:
            expected |= _TEST_LAB_MODULES
    elif dtype.startswith("goad-"):
        expected |= _GOAD_MODULES
    elif dtype == "ccrts":
        # Self-contained CCRTS lab — only the lab module + BASE. No c2 /
        # goad / peering modules expected.
        expected |= _CCRTS_MODULES
    elif dtype.startswith("combined-"):
        expected |= _C2_MODULES
        expected |= _GOAD_MODULES
        expected |= _COMBINED_MODULES
        # test_lab is c2-only — combined-* deployments don't get it (see
        # main.tf locals.deploy_c2_infra gating).
        if enable_test_lab:
            expected |= _TEST_LAB_MODULES

    return expected


# Matches the first ``module.<name>`` segment in a ``terraform state list``
# address. Names allow alphanumerics + ``_`` + ``-``. The ``[ ... ]``
# indexing (``[0]`` for ``count``, ``[\"key\"]`` for ``for_each``) is
# stripped because it's a per-instance address, not a different module.
_MODULE_RE = re.compile(r"^module\.([A-Za-z0-9_\-]+)")


def parse_top_level_modules(state_list_output: str) -> Set[str]:
    """Parse ``terraform state list`` output → set of top-level module names.

    ``state_list_output`` is the raw stdout of ``terraform state list``.
    Each non-empty line is one resource address such as::

        module.dashboard_server[0].aws_dynamodb_table.tflock
        module.vpc[0].aws_vpc.main
        module.goad[0].module.windows_vm[\"dc01\"].aws_instance.win
        aws_key_pair.deployer[0]

    Only the FIRST ``module.<name>`` segment is collected — nested child
    modules are an implementation detail of the parent. Root-level
    resources (no ``module.`` prefix) are ignored entirely; they cannot be
    foreign by construction (they live in main.tf, not in a module).
    """
    found: Set[str] = set()
    if not state_list_output:
        return found
    for raw in state_list_output.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _MODULE_RE.match(line)
        if m:
            found.add(m.group(1))
    return found


def compute_foreign_modules(
    deployment_type: str | None,
    actual_modules: Iterable[str],
    enable_test_lab: bool = False,
) -> List[str]:
    """Return sorted list of modules present in state but NOT expected.

    Use this in the destroy + state-summary endpoints. Returns a sorted
    list (not a set) so the response payload is deterministic — handy
    for both test assertions and UI display.
    """
    expected = expected_modules_for(deployment_type, enable_test_lab=enable_test_lab)
    actual = set(actual_modules or [])
    return sorted(actual - expected)
