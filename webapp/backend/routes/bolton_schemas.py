"""Pydantic v2 request / response schemas for the bolt-on REST API.

Reusable models for the `/api/bolton/*` surface defined in
`docs/internal/VULNERABLE_LAB_BOLTON_PLAN.md` §9 and its three
refinement docs (compatibility, patch, ttp/elastic).

These schemas are deliberately permissive on the inbound side
(extra fields ignored) and exhaustive on the outbound side — they
document the contract the frontend and operator-facing curl users
will consume. The route layer (`bolton.py`) does the dispatch /
audit / error mapping; this file is pure data shape.

Pydantic is a soft dependency: if it's missing at import time the
module exposes lightweight stand-ins so the routes module can still
be imported (and the Flask app still boots). The route validation
falls back to manual `request.get_json()` shape checks in that case.
"""
from __future__ import annotations

from typing import Any, Optional

try:  # pragma: no cover - environment-dependent
    from pydantic import BaseModel, ConfigDict, Field
    HAS_PYDANTIC = True
except ImportError:  # pragma: no cover - exercised when pydantic is absent
    HAS_PYDANTIC = False

    class BaseModel:  # type: ignore[no-redef]
        """Minimal stand-in. Stores kwargs as attributes and exposes
        ``model_dump()`` for serialisation parity with pydantic v2."""

        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

        @classmethod
        def model_validate(cls, data: Any) -> "BaseModel":
            if not isinstance(data, dict):
                raise ValueError("expected dict")
            return cls(**data)

        def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def ConfigDict(**kwargs: Any) -> dict[str, Any]:  # type: ignore[no-redef]
        return dict(**kwargs)

    def Field(default: Any = None, **kwargs: Any) -> Any:  # type: ignore[no-redef]
        return default


# ─── Compatibility / host facts ─────────────────────────────────────────────

class HostOS(BaseModel):
    """OS slice of host facts (per BOLTON_REFINEMENT_compatibility.md §2.2)."""
    if HAS_PYDANTIC:
        model_config = ConfigDict(extra="allow")
    family: Optional[str] = None
    distribution: Optional[str] = None
    version: Optional[str] = None
    build: Optional[str] = None
    edition: Optional[str] = None
    architecture: Optional[str] = None


class HostFacts(BaseModel):
    """The cached host fact bundle returned by ``GET /facts``.

    Only the high-level keys are typed here — the inner ``services``,
    ``patches``, ``policies``, etc. nested structures pass through as
    untyped dicts/lists so we don't have to bind the schema before
    Agent A/B finalise their data layer.
    """
    if HAS_PYDANTIC:
        model_config = ConfigDict(extra="allow")
    host_id: str
    lab: str
    collected_at: Optional[str] = None
    collected_by: Optional[str] = None
    ttl_expires_at: Optional[str] = None
    stale: bool = False
    os: Optional[HostOS] = None
    role: Optional[str] = None
    domain: Optional[dict[str, Any]] = None
    services: list[dict[str, Any]] = Field(default_factory=list)
    patches: Optional[dict[str, Any]] = None
    network: Optional[dict[str, Any]] = None
    installed_boltons: list[dict[str, Any]] = Field(default_factory=list)
    policies: Optional[dict[str, Any]] = None
    agents: Optional[dict[str, Any]] = None


class FactsRefreshRequest(BaseModel):
    """Body for ``POST /facts/refresh``."""
    deep_probe: bool = False


# ─── Job dispatch ───────────────────────────────────────────────────────────

class InstallRequest(BaseModel):
    """Body for install / uninstall / patch / patch-revert.

    Service-layer behaviour for ``role_vars`` is opaque to the route — it's
    forwarded to Ansible verbatim. ``confirm_no_detection`` is the
    operator's explicit acknowledgement for ``coverage_status: no-rule``
    installs (per BOLTON_REFINEMENT_ttp_elastic.md §4.4).
    """
    if HAS_PYDANTIC:
        model_config = ConfigDict(extra="ignore")
    role_vars: Optional[dict[str, Any]] = None
    run_probe: bool = False
    confirm_no_detection: bool = False


class BulkOperationRequest(BaseModel):
    """Body for ``POST /labs/<lab>/bulk``.

    ``action`` is one of ``install`` / ``uninstall`` / ``patch`` /
    ``patch_revert``. ``hosts`` and ``vuln_ids`` are cross-producted —
    every (host, vuln) pair becomes one dispatched job.
    """
    if HAS_PYDANTIC:
        model_config = ConfigDict(extra="ignore")
    action: str
    hosts: list[str]
    vuln_ids: list[str]
    role_vars: Optional[dict[str, Any]] = None


class JobDispatchResponse(BaseModel):
    """Standard shape returned by every dispatch endpoint."""
    success: bool = True
    job_id: str
    action: Optional[str] = None
    lab: Optional[str] = None
    host: Optional[str] = None
    vuln_id: Optional[str] = None
    estimated_time_seconds: Optional[int] = None
    message: Optional[str] = None


class BulkDispatchResponse(BaseModel):
    """Returned by the bulk endpoint — one envelope, N child jobs."""
    success: bool = True
    job_count: int
    jobs: list[dict[str, Any]]
    errors: list[dict[str, Any]] = Field(default_factory=list)


# ─── Compatibility catalog ──────────────────────────────────────────────────

class HostFactsSummary(BaseModel):
    """Compact fact view shown in the catalog header."""
    if HAS_PYDANTIC:
        model_config = ConfigDict(extra="allow")
    os: Optional[str] = None
    role: Optional[str] = None
    installed_count: int = 0
    stale: bool = False
    collected_at: Optional[str] = None


class CompatibilityCatalogResponse(BaseModel):
    """Body of ``GET /labs/<lab>/hosts/<host>/catalog`` — full
    catalog × per-vuln compatibility state."""
    if HAS_PYDANTIC:
        model_config = ConfigDict(extra="allow")
    host_id: str
    host_facts_summary: HostFactsSummary
    counts_by_state: dict[str, int]
    vulns: list[dict[str, Any]]


# ─── Probe / detection ──────────────────────────────────────────────────────

class ProbeRequest(BaseModel):
    """Body for ``POST /vulns/<id>/probe``."""
    if HAS_PYDANTIC:
        model_config = ConfigDict(extra="ignore")
    lab: str
    host: str
    window_seconds: Optional[int] = None


class GenerateRuleRequest(BaseModel):
    """Body for ``POST /vulns/<id>/generate-rule``."""
    if HAS_PYDANTIC:
        model_config = ConfigDict(extra="allow")
    rule_inputs: Optional[dict[str, Any]] = None
