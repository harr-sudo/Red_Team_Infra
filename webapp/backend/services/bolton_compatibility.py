"""Bolt-on catalog-time compatibility evaluator — Phase 1 (Agent B).

Implements the eight-state classifier specified in
``docs/internal/BOLTON_REFINEMENT_compatibility.md`` §3-§4. Given a single
host's facts and a descriptor, returns the first failing state in the
documented priority order, or ``INSTALLABLE`` when every gate passes.

Pure function — no I/O, no network. The whole catalog (~200 descriptors)
should evaluate in <100 ms per host. This is the *catalog-time*
classifier; the *install-time* DAG planner from master plan §5.2 is a
separate concern.

Descriptor shape
----------------
Agent A is producing ``webapp/bolton/schema.py`` (Pydantic v2). To avoid a
hard import dependency during Phase 1 development, this module accepts
*any* object that exposes the required fields via attribute access OR
``__getitem__``. The ``_get`` helper bridges both styles, so dicts and
Pydantic models both work.

Required descriptor fields (per the plan brief)
-----------------------------------------------
- ``id``
- ``targets.supported_os``     — list of OS family strings OR list of
  dicts ``{family, version|min_version|max_version}``
- ``targets.required_roles``   — list of role strings
- ``targets.required_services`` — list of service-name strings
- ``depends_on``               — list of bolt-on id strings (or objects
  with an ``id`` attribute)
- ``conflicts_with``           — list of bolt-on id strings
- ``cve`` (optional)           — list of CVE identifiers
- ``side_effects.global``      — list (used by callers, not by this
  classifier)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from webapp.backend.services.bolton_facts_service import HostFacts


# ──────────────────────────────────────────────────────────────────────
# State enum + result model
# ──────────────────────────────────────────────────────────────────────

class CompatibilityState(str, Enum):
    """Eight terminal states (BOLTON_REFINEMENT_compatibility.md §3.1).

    Note: ``__str__`` returns the bare value (e.g. ``"installable"``) so
    JSON serialization is stable for frontend consumption.
    """

    INSTALLABLE = "installable"
    INCOMPATIBLE_OS = "incompatible_os"
    INCOMPATIBLE_ROLE = "incompatible_role"
    MISSING_PREREQ = "missing_prereq"
    CONFLICTS_WITH_INSTALLED = "conflicts_with_installed"
    ALREADY_INSTALLED = "already_installed"
    MISSING_SOFTWARE = "missing_software"
    PATCHED = "patched"


@dataclass
class CompatibilityResult:
    state: CompatibilityState
    reason: str
    suggested_action: str
    blocking: bool = field(default=False)

    def model_dump(self, mode: str = "python") -> dict[str, Any]:  # noqa: ARG002
        d = asdict(self)
        d["state"] = self.state.value
        return d


# ──────────────────────────────────────────────────────────────────────
# Field-access shim (works for Pydantic models AND plain dicts)
# ──────────────────────────────────────────────────────────────────────

def _get(obj: Any, name: str, default: Any = None) -> Any:
    """Read ``obj.name`` falling back to ``obj[name]``.

    Used so a descriptor can be a Pydantic model OR a dict — the test
    suite passes dicts, runtime callers pass models.
    """
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _dotted(obj: Any, path: str, default: Any = None) -> Any:
    """``_dotted(d, 'targets.supported_os')`` walks both attribute and
    dict-key style accessors. Returns ``default`` if any hop is missing.
    """
    cur = obj
    for part in path.split("."):
        cur = _get(cur, part)
        if cur is None:
            return default
    return cur


def _descriptor_id(descriptor: Any) -> str:
    return str(_get(descriptor, "id", ""))


def _descriptor_name(descriptor: Any) -> str:
    return str(_get(descriptor, "name", _descriptor_id(descriptor)))


# ──────────────────────────────────────────────────────────────────────
# Per-gate helpers
# ──────────────────────────────────────────────────────────────────────

def _os_summary(supported: Any) -> str:
    """Render ``supported_os`` for a reason string."""
    if not supported:
        return "any OS"
    if isinstance(supported, list):
        bits = []
        for entry in supported:
            if isinstance(entry, str):
                bits.append(entry)
            elif isinstance(entry, dict):
                fam = entry.get("family", "?")
                ver = entry.get("version") or entry.get("min_version") or "*"
                bits.append(f"{fam} {ver}".strip())
            else:
                fam = _get(entry, "family", "?")
                ver = _get(entry, "version") or _get(entry, "min_version") or "*"
                bits.append(f"{fam} {ver}".strip())
        return ", ".join(bits)
    return str(supported)


def _enum_value(v: Any) -> str:
    """Coerce ``v`` to a lowercase string, transparently unwrapping
    string-valued Enum members. Pydantic ``Field(family: OSFamily)`` returns
    an Enum at attribute access; ``.value`` gives the underlying string.
    """
    if v is None:
        return ""
    if isinstance(v, Enum):
        return str(v.value).lower()
    return str(v).lower()


def _os_matches(supported: Any, facts: HostFacts) -> bool:
    """Return True iff host OS matches at least one supported_os entry.

    Supports two entry shapes:
      - bare strings like ``"windows"`` or ``"windows-2019"``
      - objects with ``family`` (string or Enum) and ``version``/``min_version``/``max_version``
        — either dicts or Pydantic models from ``webapp/bolton/schema.py``.
    """
    if not supported:
        return True  # No constraint
    if not isinstance(supported, list):
        supported = [supported]
    host_family = (facts.os_family or "").lower()
    host_version = str(facts.os_version or "").lower()
    for entry in supported:
        if isinstance(entry, str):
            e = entry.lower()
            if "-" in e:
                fam, _, ver = e.partition("-")
                if fam == host_family and (not ver or ver == host_version):
                    return True
            elif e == host_family:
                return True
        else:
            fam = _enum_value(_get(entry, "family"))
            if fam and fam != host_family:
                continue
            ver = _get(entry, "version")
            if ver and str(ver).lower() != host_version:
                # Try min/max bounds
                lo = _get(entry, "min_version")
                hi = _get(entry, "max_version")
                if lo is not None or hi is not None:
                    if not _version_in_range(host_version, lo, hi):
                        continue
                else:
                    continue
            elif ver is None:
                # No exact version — fall back to min/max if present
                lo = _get(entry, "min_version")
                hi = _get(entry, "max_version")
                if lo is not None or hi is not None:
                    if not _version_in_range(host_version, lo, hi):
                        continue
            return True
    return False


def _version_in_range(version: str, lo: Any, hi: Any) -> bool:
    """Best-effort numeric comparison; falls back to string compare."""
    def _num(v: Any) -> float | None:
        if v is None:
            return None
        try:
            return float(str(v))
        except (TypeError, ValueError):
            return None

    v = _num(version)
    lo_n = _num(lo)
    hi_n = _num(hi)
    if v is None:
        return False
    if lo_n is not None and v < lo_n:
        return False
    if hi_n is not None and v > hi_n:
        return False
    return True


def _normalize_dep_id(dep: Any) -> str:
    """``dep`` may be a string OR an object with an ``id`` attribute."""
    if isinstance(dep, str):
        return dep
    if isinstance(dep, dict):
        return dep.get("id", "")
    return _get(dep, "id", "")


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

def evaluate_compatibility(
    descriptor: Any,
    facts: HostFacts,
    installed_boltons_in_lab: dict[str, list[str]] | None = None,
) -> CompatibilityResult:
    """Classify ``descriptor`` against ``facts``.

    Priority order (BOLTON_REFINEMENT_compatibility.md §3.2):
      ALREADY_INSTALLED → INCOMPATIBLE_OS → INCOMPATIBLE_ROLE →
      MISSING_SOFTWARE → PATCHED → MISSING_PREREQ →
      CONFLICTS_WITH_INSTALLED → INSTALLABLE.

    NOTE: the brief lists MISSING_SOFTWARE before PATCHED while the
    refinement doc lists PATCHED before MISSING_SOFTWARE. We follow the
    brief (the user-facing instruction) — semantically equivalent for the
    common case since these gates are non-overlapping.
    """
    installed_boltons_in_lab = installed_boltons_in_lab or {}
    vuln_id = _descriptor_id(descriptor)
    vuln_name = _descriptor_name(descriptor)

    # ── 1. ALREADY_INSTALLED ─────────────────────────────────────────
    if vuln_id and vuln_id in facts.installed_boltons:
        return CompatibilityResult(
            state=CompatibilityState.ALREADY_INSTALLED,
            reason=f"{vuln_name} is already installed on {facts.host}.",
            suggested_action="re_verify",
            blocking=True,
        )

    # ── 2. INCOMPATIBLE_OS ───────────────────────────────────────────
    supported_os = _dotted(descriptor, "targets.supported_os", [])
    if supported_os and not _os_matches(supported_os, facts):
        return CompatibilityResult(
            state=CompatibilityState.INCOMPATIBLE_OS,
            reason=(
                f"Requires {_os_summary(supported_os)}; host runs "
                f"{facts.os_family.capitalize()} {facts.os_version}."
            ),
            suggested_action="pick_different_host",
            blocking=True,
        )

    # ── 3. INCOMPATIBLE_ROLE ─────────────────────────────────────────
    required_roles = _dotted(descriptor, "targets.required_roles", []) or []
    if required_roles and facts.role not in required_roles:
        roles_str = ", ".join(required_roles) if len(required_roles) > 1 else required_roles[0]
        return CompatibilityResult(
            state=CompatibilityState.INCOMPATIBLE_ROLE,
            reason=(
                f"Requires role: {roles_str}; host role: {facts.role}"
            ),
            suggested_action="pick_different_host",
            blocking=True,
        )

    # ── 4. MISSING_SOFTWARE ──────────────────────────────────────────
    required_services = _dotted(descriptor, "targets.required_services", []) or []
    missing = [s for s in required_services if s not in facts.installed_services]
    if missing:
        return CompatibilityResult(
            state=CompatibilityState.MISSING_SOFTWARE,
            reason=(
                f"Missing required service(s): {', '.join(missing)} on {facts.host}."
            ),
            suggested_action="install_software_bolton",
            blocking=True,
        )

    # ── 5. PATCHED ───────────────────────────────────────────────────
    cves = _get(descriptor, "cve") or []
    if cves:
        unpatched = [c for c in cves if c not in facts.patched_cves]
        if not unpatched:
            cve_list = ", ".join(cves)
            kbs = ", ".join(facts.applied_kbs) if facts.applied_kbs else "applied patches"
            return CompatibilityResult(
                state=CompatibilityState.PATCHED,
                reason=(
                    f"Underlying CVE {cve_list} patched on host ({kbs}); "
                    f"install would not take effect."
                ),
                suggested_action="view_alternatives",
                blocking=True,
            )

    # ── 6. MISSING_PREREQ ────────────────────────────────────────────
    depends_on = _get(descriptor, "depends_on") or []
    missing_deps: list[str] = []
    for dep in depends_on:
        dep_id = _normalize_dep_id(dep)
        if not dep_id:
            continue
        if dep_id not in facts.installed_boltons:
            missing_deps.append(dep_id)
    if missing_deps:
        # Reason follows the brief example: "currently INSTALLABLE on <host>"
        first = missing_deps[0]
        return CompatibilityResult(
            state=CompatibilityState.MISSING_PREREQ,
            reason=(
                f"Requires bolt-on {first} first (currently INSTALLABLE on {facts.host})."
                if len(missing_deps) == 1
                else (
                    f"Requires bolt-ons: {', '.join(missing_deps)} "
                    f"(currently not installed on {facts.host})."
                )
            ),
            suggested_action="install_prereq_first",
            blocking=True,
        )

    # ── 7. CONFLICTS_WITH_INSTALLED ──────────────────────────────────
    conflicts_with = _get(descriptor, "conflicts_with") or []
    # Same-host conflicts
    same_host_conflicts = [c for c in conflicts_with if c in facts.installed_boltons]
    if same_host_conflicts:
        c = same_host_conflicts[0]
        return CompatibilityResult(
            state=CompatibilityState.CONFLICTS_WITH_INSTALLED,
            reason=(
                f"Conflicts with {c} already installed on {facts.host} in this lab."
            ),
            suggested_action="uninstall_conflicting",
            blocking=True,
        )
    # Cross-host conflicts (only flagged for "global side-effect" bolt-ons;
    # we conservatively flag any cross-host conflict whose ID appears in
    # installed_boltons_in_lab for another host).
    for other_host, ids in installed_boltons_in_lab.items():
        if other_host == facts.host:
            continue
        for c in conflicts_with:
            if c in ids:
                return CompatibilityResult(
                    state=CompatibilityState.CONFLICTS_WITH_INSTALLED,
                    reason=(
                        f"Conflicts with {c} already installed on {other_host} in this lab."
                    ),
                    suggested_action="uninstall_conflicting",
                    blocking=True,
                )

    # ── 8. INSTALLABLE ───────────────────────────────────────────────
    return CompatibilityResult(
        state=CompatibilityState.INSTALLABLE,
        reason="All compatibility requirements met.",
        suggested_action="install",
        blocking=False,
    )


def evaluate_catalog_for_host(
    catalog: dict[str, Any],
    facts: HostFacts,
    installed_boltons_in_lab: dict[str, list[str]] | None = None,
) -> dict[str, CompatibilityResult]:
    """Evaluate every descriptor in the catalog against one host.

    Returns ``{bolton_id: CompatibilityResult}``. Used by the
    ``GET /api/bolton/labs/<lab>/hosts/<host>/catalog`` endpoint to render
    the host-contextualised card grid.
    """
    results: dict[str, CompatibilityResult] = {}
    for bid, descriptor in catalog.items():
        results[bid] = evaluate_compatibility(
            descriptor, facts, installed_boltons_in_lab
        )
    return results
