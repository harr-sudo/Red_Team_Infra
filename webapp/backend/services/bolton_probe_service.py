"""Bolt-on detection probe service — Phase 1 stub (Agent D reconcile).

Trigger a vuln's synthetic exploit probe and correlate with Elastic alerts.
Phase 1 ships a stub that immediately returns a fake "probe job" — Phase 2
will SSH to the attack box, run the descriptor's ``trigger_probe`` script,
and query Elastic's `/_security/detection/rule/_find` for matching alerts
within the probe window.

Public API:

  - ``run_probe(vuln_id, lab, host, window_seconds=None, actor=None)``
      → ``{probe_job_id, status, ...}``
  - ``get_probe(probe_job_id)`` → dict or None

Raises ``KeyError`` when the descriptor has no ``trigger_probe`` block.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ──────────────────────────────────────────────────────────────────────
# Storage
# ──────────────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROBES_ROOT = _PROJECT_ROOT / "webapp" / "state" / "bolton" / "probes"


def _probe_path(probe_id: str) -> Path:
    return PROBES_ROOT / f"{probe_id}.json"


def _write_probe(probe_id: str, payload: dict[str, Any]) -> None:
    PROBES_ROOT.mkdir(parents=True, exist_ok=True)
    path = _probe_path(probe_id)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    os.replace(tmp, path)


def _read_probe(probe_id: str) -> Optional[dict[str, Any]]:
    try:
        return json.loads(_probe_path(probe_id).read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


# ──────────────────────────────────────────────────────────────────────
# Descriptor lookup
# ──────────────────────────────────────────────────────────────────────

def _descriptor_has_probe_block(vuln_id: str) -> bool:
    """Check whether the descriptor has a ``trigger_probe`` block.

    Phase 1 doesn't actually enforce a separate ``trigger_probe`` field —
    the schema bundles synthetic-exploit verification under
    ``patch.exploit_probe_after_patch``. We treat presence of that field
    as evidence of a probe block.
    """
    from webapp.backend.services import bolton_catalog_service
    descriptor = bolton_catalog_service.get(vuln_id)
    if descriptor is None:
        return False
    patch = (descriptor or {}).get("patch") or {}
    if (patch or {}).get("exploit_probe_after_patch"):
        return True
    # Schema field name compat — earlier drafts called it ``trigger_probe``.
    if (descriptor or {}).get("trigger_probe"):
        return True
    return False


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

def run_probe(
    vuln_id: str,
    lab: str,
    host: str,
    window_seconds: Optional[int] = None,
    actor: Optional[str] = None,
) -> dict[str, Any]:
    """Kick off a synthetic-exploit probe. Returns immediately with the
    probe_job_id; caller polls ``get_probe(probe_job_id)`` for status.

    Phase 1 stub: writes a fake probe record marked ``status='DONE'``,
    ``result='probe-only'`` so callers get a deterministic shape.
    """
    if not _descriptor_has_probe_block(vuln_id):
        raise KeyError(f"vuln '{vuln_id}' has no trigger_probe")

    probe_id = f"probe_{uuid.uuid4().hex[:12]}"
    record = {
        "probe_job_id": probe_id,
        "vuln_id": vuln_id,
        "lab": lab,
        "host": host,
        "actor": actor or "unknown",
        "window_seconds": window_seconds or 300,
        "status": "DONE",
        "result": "probe-only",
        "probe_stdout": "[STUB] Phase 1 — Phase 2 will run actual probe over SSH.",
        "alerts_received": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "stubbed": True,
    }
    _write_probe(probe_id, record)
    return {"probe_job_id": probe_id, "status": "QUEUED", "stubbed": True}


def get_probe(probe_job_id: str) -> Optional[dict[str, Any]]:
    """Return the probe record, or None when unknown."""
    return _read_probe(probe_job_id)
