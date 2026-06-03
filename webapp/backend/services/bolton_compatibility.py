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
      - objects with ``family`` (string or Enum), ``version`` / ``min_version`` /
        ``max_version``, and optional ``edition_in: [...]`` — either dicts
        or Pydantic models from ``webapp/bolton/schema.py``.

    2026-05-23 — fixed bugs:
      * ``edition_in`` was previously parsed but never checked.
      * ``min_version``/``max_version`` used ``float()`` parsing so any
        non-purely-numeric version ("2012R2", "8.1", "11 22H2") silently
        failed the range check. Now uses a Windows-aware comparator.
    """
    if not supported:
        return True  # No constraint
    if not isinstance(supported, list):
        supported = [supported]
    host_family = (facts.os_family or "").lower()
    host_version = str(facts.os_version or "").lower()
    host_edition = (facts.os_edition or "").lower() if hasattr(facts, "os_edition") else ""
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
            ver_ok = True
            if ver and str(ver).lower() != host_version:
                # Try min/max bounds
                lo = _get(entry, "min_version")
                hi = _get(entry, "max_version")
                if lo is not None or hi is not None:
                    if not _version_in_range(host_version, lo, hi):
                        ver_ok = False
                else:
                    ver_ok = False
            elif ver is None:
                # No exact version — fall back to min/max if present
                lo = _get(entry, "min_version")
                hi = _get(entry, "max_version")
                if lo is not None or hi is not None:
                    if not _version_in_range(host_version, lo, hi):
                        ver_ok = False
            if not ver_ok:
                continue
            # Edition gate — enforced 2026-05-23. Empty list means "any".
            editions = _get(entry, "edition_in") or _get(entry, "editions") or []
            if editions:
                allowed = [str(e).lower() for e in editions]
                # An unknown host edition (None / "") doesn't auto-fail —
                # we'd otherwise break every test_lab host whose facts
                # never set os_edition. Real production hosts populate it.
                if host_edition and host_edition not in allowed:
                    continue
            return True
    return False


# Windows version ordering — covers everything from XP through Server 2025.
# Anything not in the map falls back to numeric float parsing.
_WINDOWS_VERSION_ORDER = {
    "xp": 5.1, "vista": 6.0, "7": 6.1, "8": 6.2, "8.1": 6.3,
    "10": 10.0, "11": 11.0,
    "2003": 5.2, "2008": 6.0, "2008r2": 6.1, "2012": 6.2, "2012r2": 6.3,
    "2016": 10.0, "2019": 10.0, "2022": 10.0, "2025": 10.0,
}
# Year-style server versions need a secondary ordering since Windows shares
# the 10.0 NT kernel across 2016/2019/2022/2025. Sort by release year.
_WINDOWS_SERVER_YEAR = {"2003": 2003, "2008": 2008, "2008r2": 2008.5,
                       "2012": 2012, "2012r2": 2012.5,
                       "2016": 2016, "2019": 2019, "2022": 2022, "2025": 2025}


def _normalize_win_version(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip().lower()
    # Strip "server " prefix, "windows " prefix, build numbers like " 22h2".
    for prefix in ("windows server ", "windows ", "server "):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    # Take first token before space (drops " 22h2", " 1809", etc.)
    s = s.split()[0] if s else s
    return s or None


def _version_in_range(version: str, lo: Any, hi: Any) -> bool:
    """Compare ``version`` against ``[lo, hi]`` using Windows-aware ordering.

    Falls back to numeric float comparison for non-Windows or unknown
    version strings. Returns False for unparseable host versions so a
    badly-tagged host doesn't accidentally pass an OS gate.
    """
    nv = _normalize_win_version(version)
    nlo = _normalize_win_version(lo)
    nhi = _normalize_win_version(hi)
    if nv is None:
        return False

    # If host + bounds are all in the Windows server-year map, compare by year.
    if nv in _WINDOWS_SERVER_YEAR and (nlo in _WINDOWS_SERVER_YEAR or nlo is None) \
            and (nhi in _WINDOWS_SERVER_YEAR or nhi is None):
        v = _WINDOWS_SERVER_YEAR[nv]
        lo_n = _WINDOWS_SERVER_YEAR.get(nlo) if nlo else None
        hi_n = _WINDOWS_SERVER_YEAR.get(nhi) if nhi else None
        if lo_n is not None and v < lo_n:
            return False
        if hi_n is not None and v > hi_n:
            return False
        return True

    # Client (10/11/8.1/7) ordering via NT-version map.
    if nv in _WINDOWS_VERSION_ORDER and (nlo in _WINDOWS_VERSION_ORDER or nlo is None) \
            and (nhi in _WINDOWS_VERSION_ORDER or nhi is None):
        v = _WINDOWS_VERSION_ORDER[nv]
        lo_n = _WINDOWS_VERSION_ORDER.get(nlo) if nlo else None
        hi_n = _WINDOWS_VERSION_ORDER.get(nhi) if nhi else None
        if lo_n is not None and v < lo_n:
            return False
        if hi_n is not None and v > hi_n:
            return False
        return True

    # Numeric fallback (Linux versions like "22.04", "20.04").
    def _num(s: str | None) -> float | None:
        if s is None:
            return None
        try:
            return float(s)
        except (TypeError, ValueError):
            return None

    v = _num(nv)
    lo_n = _num(nlo)
    hi_n = _num(nhi)
    if v is None:
        return False
    if lo_n is not None and v < lo_n:
        return False
    if hi_n is not None and v > hi_n:
        return False
    return True


def _dfl_satisfied(required: str | None, facts: HostFacts) -> bool:
    """Check `required_domain_function_level` against the host's reported DFL.

    Year-based comparison ("2008" < "2012" < "2016" < "2019"). When facts
    don't carry a DFL we assume not-satisfied for DFL-gated descriptors
    (better safe — a real production gather would populate it).
    """
    if not required:
        return True
    host_dfl = getattr(facts, "domain_function_level", None)
    if not host_dfl:
        return False
    try:
        return int(str(host_dfl).rstrip("R2").strip()) >= int(str(required).rstrip("R2").strip())
    except (TypeError, ValueError):
        return str(host_dfl).lower() == str(required).lower()


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

    # ── 3b. DOMAIN FUNCTIONAL LEVEL (2026-05-23 — was YAML-only, never enforced) ─
    required_dfl = _dotted(descriptor, "targets.required_domain_function_level")
    if required_dfl and not _dfl_satisfied(required_dfl, facts):
        host_dfl = getattr(facts, "domain_function_level", None) or "unknown"
        return CompatibilityResult(
            state=CompatibilityState.INCOMPATIBLE_OS,  # fold into OS bucket for the UI
            reason=(
                f"Requires forest/domain functional level ≥ {required_dfl}; "
                f"host's domain reports {host_dfl}."
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


# ──────────────────────────────────────────────────────────────────────
# Route-facing wrapper (Agent D reconcile)
# ──────────────────────────────────────────────────────────────────────

class FactsMissing(Exception):
    """Raised by ``host_catalog`` when there are no cached facts.

    The route surfaces this as a 409 with a hint to POST to
    ``/facts/refresh`` first.
    """


def _row_for_vuln(descriptor: Any, result: CompatibilityResult) -> dict[str, Any]:
    """Serialize one (descriptor, compat-result) pair for the catalog row."""
    from webapp.backend.services.bolton_catalog_service import (
        _descriptor_to_dict,
        _summarise,
    )
    summary = _summarise(descriptor)
    raw = _descriptor_to_dict(descriptor)
    patch = raw.get("patch") or {}
    return {
        **summary,
        "state": result.state.value,
        "reason": result.reason,
        "suggested_action": result.suggested_action,
        "blocking": result.blocking,
        "rollback_supported": (patch or {}).get("rollback_supported", False),
        "estimated_time_seconds": ((raw.get("install") or {}) or {}).get(
            "estimated_time_seconds"
        ),
    }


def host_catalog(
    lab: str,
    host: str,
    category: str | None = None,
    states: list[str] | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    """Return the full catalog annotated with per-vuln compatibility state.

    Route-facing wrapper. Loads the catalog via ``bolton_catalog_service``,
    pulls host facts via ``bolton_facts_service``, and applies the
    optional ``category`` / ``states`` / ``search`` filters.
    """
    # Lazy imports — services may be substituted with mocks in route tests.
    from webapp.backend.services import (
        bolton_catalog_service,
        bolton_facts_service,
    )

    # Probe for facts (gather if cold — see facts_service.get_facts for
    # the unknown-host KeyError path).
    try:
        facts = bolton_facts_service.gather_facts(lab, host)
    except KeyError as e:
        raise KeyError(str(e)) from e
    if facts is None:
        raise FactsMissing(f"no facts cached for {host} in {lab}")

    catalog = bolton_catalog_service._load()
    installed_map = bolton_facts_service.build_installed_boltons_map(lab)
    results = evaluate_catalog_for_host(catalog, facts, installed_map)

    needle = (search or "").strip().lower()
    wanted_states = {s.upper() for s in (states or [])} if states else None

    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for vuln_id, descriptor in catalog.items():
        result = results[vuln_id]
        state_label = result.state.name  # e.g. INSTALLABLE
        counts[state_label] = counts.get(state_label, 0) + 1
        if category:
            from webapp.backend.services.bolton_catalog_service import _descriptor_to_dict
            if _descriptor_to_dict(descriptor).get("category") != category:
                continue
        if wanted_states and state_label not in wanted_states:
            continue
        if needle:
            from webapp.backend.services.bolton_catalog_service import _descriptor_to_dict
            raw = _descriptor_to_dict(descriptor)
            hay = " ".join([
                str(raw.get("id") or ""),
                str(raw.get("name") or ""),
                str(raw.get("description") or ""),
            ]).lower()
            if needle not in hay:
                continue
        rows.append(_row_for_vuln(descriptor, result))

    return {
        "host_id": host,
        "host_facts_summary": {
            "os": f"{facts.os_family} {facts.os_version}".strip(),
            "role": facts.role,
            "installed_count": len(facts.installed_boltons),
            "stale": not facts.is_fresh(),
            "collected_at": facts.gathered_at.isoformat(),
        },
        "counts_by_state": counts,
        "vulns": rows,
    }
