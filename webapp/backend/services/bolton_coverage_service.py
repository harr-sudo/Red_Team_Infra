"""Bolt-on detection-coverage facade — Phase 1 (Agent D reconcile).

Read-only view of coverage metadata for the catalog. Phase 1 derives
coverage straight from the descriptor's ``detection`` block. Phase 2 will
correlate against Elastic rule freshness (last_validated dates,
rule-store presence checks) and live probe history.

Public API:

  - ``get_for_vuln(vuln_id, host=None)`` → coverage detail dict
      (raises KeyError when vuln unknown)
  - ``detection_gaps(lab=None, state=None)`` → ``{gaps, summary}``
  - ``navigator_layer(lab=None, installed_only=True)`` → ATT&CK Navigator JSON

The frontend's detection-gaps + Navigator export views consume this.
"""
from __future__ import annotations

from typing import Any, Optional


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _descriptor_or_raise(vuln_id: str) -> dict[str, Any]:
    from webapp.backend.services import bolton_catalog_service
    descriptor = bolton_catalog_service.get(vuln_id)
    if descriptor is None:
        raise KeyError(f"vuln '{vuln_id}' not found")
    return descriptor


def _mitre_summary(descriptor: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the route's ``mitre`` array from the descriptor's mitre block."""
    block = descriptor.get("mitre") or {}
    if not block:
        return []
    out: list[dict[str, Any]] = []
    tactic = block.get("tactic")
    technique = block.get("technique")
    sub = block.get("subtechnique")
    if tactic:
        out.append({"kind": "tactic", **(tactic if isinstance(tactic, dict) else {})})
    if technique:
        out.append({"kind": "technique", **(technique if isinstance(technique, dict) else {})})
    if sub:
        out.append({"kind": "subtechnique", **(sub if isinstance(sub, dict) else {})})
    return out


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

def get_for_vuln(vuln_id: str, host: Optional[str] = None) -> dict[str, Any]:
    """Return coverage detail for a vuln. ``host`` filters probe_history."""
    descriptor = _descriptor_or_raise(vuln_id)
    detection = descriptor.get("detection") or {}
    rules = detection.get("elastic_rules") or []
    return {
        "vuln_id": vuln_id,
        "coverage_status": detection.get("coverage_status"),
        "rules": rules,
        "mitre": _mitre_summary(descriptor),
        "fallback_template": detection.get("fallback_rule_template"),
        "signal_sources": detection.get("signal_sources") or [],
        # Phase 1 stub — probe_history wired in Phase 2 when we
        # have a probe history store.
        "probe_history": [],
        "host_filter": host,
    }


def detection_gaps(
    lab: Optional[str] = None,
    state: Optional[str] = None,
) -> dict[str, Any]:
    """List bolt-ons whose coverage_status is not ``covered``.

    Phase 1 surfaces the gap backlog from the descriptor catalog. Phase 2
    will join this with the installed-bolt-on registry to scope gaps to
    "installed but unmonitored".
    """
    from webapp.backend.services import bolton_catalog_service
    summaries = bolton_catalog_service.list_summaries()
    counts = {"covered": 0, "partial": 0, "no_rule": 0, "stale": 0}
    gaps: list[dict[str, Any]] = []
    for s in summaries:
        status = (s.get("coverage_status") or "").lower()
        if status == "covered":
            counts["covered"] += 1
        elif status == "partial":
            counts["partial"] += 1
            gaps.append(s)
        elif status in ("no-rule", "no_rule"):
            counts["no_rule"] += 1
            gaps.append(s)
        elif status in ("rule-stale", "stale"):
            counts["stale"] += 1
            gaps.append(s)
    if state:
        wanted = state.lower().replace("_", "-")
        gaps = [g for g in gaps if (g.get("coverage_status") or "").lower() == wanted]
    return {
        "gaps": gaps,
        "summary": counts,
        "lab": lab,
    }


def navigator_layer(
    lab: Optional[str] = None,
    installed_only: bool = True,
) -> dict[str, Any]:
    """Build an ATT&CK Navigator JSON layer summarising lab coverage."""
    from webapp.backend.services import bolton_catalog_service
    catalog = bolton_catalog_service
    summaries = catalog.list_summaries()
    techniques: list[dict[str, Any]] = []
    for s in summaries:
        tech = s.get("mitre_technique")
        if not tech:
            continue
        # Map coverage to a 0..100 score; 100=covered, 50=partial, 0=no-rule.
        cov = (s.get("coverage_status") or "").lower()
        score = {"covered": 100, "partial": 50}.get(cov, 0)
        techniques.append({
            "techniqueID": tech,
            "score": score,
            "metadata": [
                {"name": "vuln_id", "value": s.get("id", "")},
                {"name": "coverage", "value": cov or "no-rule"},
            ],
        })
    return {
        "name": f"Red Team Infra bolt-on coverage — {lab or 'all labs'}",
        "domain": "enterprise-attack",
        "description": "Auto-generated from the bolt-on catalog.",
        "techniques": techniques,
        "gradient": {
            "colors": ["#a31621", "#fbbf24", "#10b981"],
            "minValue": 0,
            "maxValue": 100,
        },
        "lab": lab,
        "installed_only": installed_only,
    }
