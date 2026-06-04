"""Bolt-on catalog service facade — Phase 1 (Agent D reconcile).

Thin wrapper around ``webapp.bolton.catalog.load_catalog`` that exposes the
two route-facing entry points:

  - ``list_summaries(...)`` — slim descriptor view for the list endpoint
  - ``get(vuln_id)`` — full descriptor for the detail endpoint

The actual descriptor loading + validation logic lives in
``webapp/bolton/catalog.py`` (loader) and ``webapp/bolton/schema.py``
(Pydantic models). This module is a stable import path the routes can
``importlib.import_module`` lazily, so route tests can still substitute a
MagicMock module without dragging the YAML loader into the import graph.

Caching
-------
The catalog is small (~200 descriptors at v3 plan) and pure YAML, so we
cache the loaded ``dict[str, BoltOnDescriptor]`` after the first call and
expose a ``_reset_for_tests`` helper for test isolation. Production callers
that mutate disk should also call ``_reset_for_tests`` so the next read
re-loads.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

# ──────────────────────────────────────────────────────────────────────
# Cache
# ──────────────────────────────────────────────────────────────────────

_CATALOG_CACHE: dict[str, Any] | None = None
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CATALOG_ROOT = _PROJECT_ROOT / "webapp" / "bolton" / "catalog"


def _load() -> dict[str, Any]:
    """Load the catalog (cached). Returns dict[id, BoltOnDescriptor]."""
    global _CATALOG_CACHE
    if _CATALOG_CACHE is not None:
        return _CATALOG_CACHE
    # Import lazily so route tests that mock this module don't pay the
    # Pydantic import cost.
    from webapp.bolton.catalog import load_catalog
    try:
        _CATALOG_CACHE = load_catalog(_CATALOG_ROOT)
    except FileNotFoundError:
        _CATALOG_CACHE = {}
    return _CATALOG_CACHE


def _reset_for_tests() -> None:
    """Drop the cache. Used by tests + after disk-mutating ops."""
    global _CATALOG_CACHE
    _CATALOG_CACHE = None


# ──────────────────────────────────────────────────────────────────────
# Descriptor → dict helpers
# ──────────────────────────────────────────────────────────────────────

def _descriptor_to_dict(d: Any) -> dict[str, Any]:
    """Convert a BoltOnDescriptor (or pre-coerced dict) to a JSON dict."""
    if isinstance(d, dict):
        return d
    if hasattr(d, "model_dump"):
        return d.model_dump(mode="json")
    if hasattr(d, "__dict__"):
        return dict(d.__dict__)
    return dict(d)


def _summarise(d: Any) -> dict[str, Any]:
    """Slim descriptor view for ``GET /api/bolton/vulns``."""
    raw = _descriptor_to_dict(d)
    detection = raw.get("detection") or {}
    mitre = raw.get("mitre") or {}
    technique = (mitre or {}).get("technique") if isinstance(mitre, dict) else None
    curriculum = raw.get("curriculum")
    curriculum_steps = ((curriculum or {}).get("steps") or []) if isinstance(curriculum, dict) else []
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "slug": raw.get("slug"),
        "category": raw.get("category"),
        "subcategory": raw.get("subcategory"),
        "tags": raw.get("tags") or [],
        "coverage_status": (detection or {}).get("coverage_status"),
        "cve": raw.get("cve") or [],
        "mitre_technique": (technique or {}).get("id") if isinstance(technique, dict) else None,
        "status": raw.get("status"),
        "description": (raw.get("description") or "")[:240],
        # Curriculum signal — drives the "Walkthrough" CTA on the row.
        "has_curriculum": bool(curriculum),
        "curriculum_step_count": len(curriculum_steps),
    }


# ──────────────────────────────────────────────────────────────────────
# Public API (route surface)
# ──────────────────────────────────────────────────────────────────────

def list_summaries(
    category: Optional[str] = None,
    target_os: Optional[str] = None,
    coverage_status: Optional[str] = None,
    search: Optional[str] = None,
) -> list[dict[str, Any]]:
    """List slim descriptor summaries with optional filtering.

    Filters AND together. ``search`` matches against id, name, and
    description (case-insensitive substring). ``target_os`` matches if any
    of ``targets.supported_os[].family`` equals the value.
    """
    catalog = _load()
    out: list[dict[str, Any]] = []
    needle = (search or "").strip().lower()
    for d in catalog.values():
        raw = _descriptor_to_dict(d)
        if category and raw.get("category") != category:
            continue
        if coverage_status:
            det = raw.get("detection") or {}
            if (det or {}).get("coverage_status") != coverage_status:
                continue
        if target_os:
            tgt = raw.get("targets") or {}
            supported = (tgt or {}).get("supported_os") or []
            matched = False
            for entry in supported:
                fam = entry.get("family") if isinstance(entry, dict) else getattr(entry, "family", None)
                if hasattr(fam, "value"):
                    fam = fam.value
                if str(fam or "").lower() == target_os.lower():
                    matched = True
                    break
            if not matched:
                continue
        if needle:
            hay = " ".join([
                str(raw.get("id") or ""),
                str(raw.get("name") or ""),
                str(raw.get("description") or ""),
            ]).lower()
            if needle not in hay:
                continue
        out.append(_summarise(d))
    return out


def get(vuln_id: str) -> Optional[dict[str, Any]]:
    """Return the full descriptor as a dict, or None when unknown."""
    catalog = _load()
    d = catalog.get(vuln_id)
    if d is None:
        return None
    return _descriptor_to_dict(d)


def get_descriptor(vuln_id: str) -> Any:
    """Return the BoltOnDescriptor instance (or None). Used by services
    that need the typed object (compatibility / install backstop)."""
    catalog = _load()
    return catalog.get(vuln_id)
