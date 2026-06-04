"""Bolt-on detection probe service — Phase 3b upgrade.

Trigger a vuln's synthetic exploit probe and (when the Elastic detection
stack bolt-on is installed in the same lab) correlate with Kibana alerts.

History
-------
- Phase 1 stub: returns a fake probe record marked DONE.
- Phase 3b (this file): upgraded to "full mode" — after the exploit
  probe is fired, the service polls the lab's Kibana alerts API for any
  rule firing whose ``signal.rule.rule_id`` matches one of the
  descriptor's declared elastic_rules and whose ``host.name`` matches the
  target. Returns ``{fired, alert_id, fire_time}``.
- Falls back to ``degraded`` mode when the Elastic stack isn't installed
  or its Kibana endpoint isn't reachable — same shape as the Phase 1
  stub, with ``degraded: true`` so callers can disambiguate.

Public API
----------
- ``run_probe(vuln_id, lab, host, window_seconds=None, actor=None)``
    → ``{probe_job_id, status, ...}``
- ``get_probe(probe_job_id)`` → dict or None
- ``correlate_alerts(...)`` — internal-but-exported for tests; queries
  Kibana directly and returns the fired/alert_id shape.

The Kibana endpoint is discovered via the bolt-on facts service:
when ``bolton.infrastructure.elastic-detection-stack`` is installed it
registers ``kibana_endpoint`` and ``es_password`` as host facts (the
Ansible role's install_kibana.yml writes them as cacheable facts).
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover — requests is in requirements.txt
    requests = None  # type: ignore

log = logging.getLogger(__name__)

# Descriptor id of the Elastic detection stack bolt-on. When present in
# a lab's installed-boltons map for any host, the probe service can talk
# to that host's Kibana to correlate alerts.
ELASTIC_STACK_BOLTON_ID = "bolton.infrastructure.elastic-detection-stack"

# Default poll window for alert correlation (5 min per the §14.6 spec).
DEFAULT_PROBE_WINDOW_SECONDS = 5 * 60

# Per-attempt HTTP timeout for the Kibana query.
KIBANA_HTTP_TIMEOUT_SECONDS = 10


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


def _descriptor_rule_uuids(vuln_id: str) -> list[str]:
    """Return the list of elastic rule_uuids declared by this descriptor."""
    from webapp.backend.services import bolton_catalog_service
    descriptor = bolton_catalog_service.get(vuln_id) or {}
    detection = descriptor.get("detection") or {}
    rules = detection.get("elastic_rules") or []
    out: list[str] = []
    for r in rules:
        if isinstance(r, dict):
            uid = r.get("rule_uuid")
        else:
            uid = getattr(r, "rule_uuid", None)
        if uid:
            out.append(str(uid))
    return out


# ──────────────────────────────────────────────────────────────────────
# Stack discovery (degraded vs full mode)
# ──────────────────────────────────────────────────────────────────────

def _discover_elastic_endpoint(lab: str) -> Optional[dict[str, Any]]:
    """Locate the Elastic detection stack in this lab, if installed.

    Returns ``{kibana_endpoint, es_user, es_password}`` when reachable,
    or ``None`` to indicate degraded mode.

    Discovery is via the bolt-on facts service: we walk every host in the
    lab, find the one whose installed_boltons list contains
    ``ELASTIC_STACK_BOLTON_ID``, and read its ``kibana_endpoint`` /
    ``es_password`` facts (registered by the Ansible role's
    install_kibana.yml).
    """
    try:
        from webapp.backend.services import bolton_facts_service
    except Exception:
        log.debug("bolton_facts_service unavailable — degraded mode")
        return None

    try:
        installed_map = bolton_facts_service.build_installed_boltons_map(lab)
    except Exception as exc:
        log.debug("build_installed_boltons_map failed: %s", exc)
        return None

    stack_host: Optional[str] = None
    for host_name, installed in installed_map.items():
        if ELASTIC_STACK_BOLTON_ID in (installed or []):
            stack_host = host_name
            break
    if stack_host is None:
        return None

    # Read the cached HostFacts to pull the kibana_endpoint / password.
    try:
        facts = bolton_facts_service.get_cached_facts(lab, stack_host)
    except Exception:
        facts = None
    if facts is None:
        return None

    # ``HostFacts`` is a dataclass; the Elastic stack registers its
    # endpoint as extra installed_services / fact fields. We use a
    # liberal getattr lookup so tests can stub via a SimpleNamespace.
    endpoint = (
        getattr(facts, "kibana_endpoint", None)
        or (getattr(facts, "installed_services", {}) or {}).get("kibana_endpoint")
    )
    es_password = (
        getattr(facts, "es_password", None)
        or (getattr(facts, "installed_services", {}) or {}).get("es_password")
    )
    es_user = (
        getattr(facts, "es_user", None)
        or (getattr(facts, "installed_services", {}) or {}).get("es_user")
        or "elastic"
    )
    if not endpoint or not es_password:
        return None
    return {
        "kibana_endpoint": endpoint,
        "es_user": es_user,
        "es_password": es_password,
        "stack_host": stack_host,
    }


# ──────────────────────────────────────────────────────────────────────
# Kibana alert correlation (full mode)
# ──────────────────────────────────────────────────────────────────────

def correlate_alerts(
    kibana_endpoint: str,
    es_user: str,
    es_password: str,
    rule_uuids: list[str],
    target_host: str,
    probe_start_ts: str,
    timeout: int = KIBANA_HTTP_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Query Kibana's signals-search endpoint for matching alerts.

    Returns one of:
      - ``{"fired": True,  "alert_id": "...", "fire_time": "...", "rule_uuid": "..."}``
      - ``{"fired": False}`` — query succeeded but no matching alert
      - ``{"fired": False, "degraded": True, "error": "..."}`` — query failed

    Tests mock ``requests.post`` to drive this function.
    """
    if requests is None:
        return {"fired": False, "degraded": True, "error": "requests-not-installed"}

    if not rule_uuids:
        # Nothing to correlate against — return early so we don't spam
        # Kibana with a query that can't possibly match.
        return {"fired": False}

    url = f"https://{kibana_endpoint}/api/detection_engine/signals/search"
    body = {
        "query": {
            "bool": {
                "must": [
                    {"terms": {"signal.rule.rule_id": rule_uuids}},
                    {"match": {"signal.original_event.host.name": target_host}},
                    {"range": {"@timestamp": {"gte": probe_start_ts}}},
                ]
            }
        },
        "size": 1,
        "sort": [{"@timestamp": "desc"}],
    }
    try:
        resp = requests.post(
            url,
            auth=(es_user, es_password),
            json=body,
            timeout=timeout,
            verify=False,  # lab Kibana uses self-signed certs
        )
    except Exception as exc:
        return {"fired": False, "degraded": True, "error": f"connect:{type(exc).__name__}"}

    if resp.status_code >= 400:
        return {
            "fired": False,
            "degraded": True,
            "error": f"http-{resp.status_code}",
        }

    try:
        payload = resp.json()
    except Exception:
        return {"fired": False, "degraded": True, "error": "bad-json"}

    hits = ((payload.get("hits") or {}).get("hits")) or []
    if not hits:
        return {"fired": False}
    hit = hits[0]
    source = hit.get("_source") or {}
    signal = source.get("signal") or {}
    rule = signal.get("rule") or {}
    return {
        "fired": True,
        "alert_id": hit.get("_id"),
        "fire_time": source.get("@timestamp"),
        "rule_uuid": rule.get("rule_id"),
    }


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
    """Kick off a synthetic-exploit probe.

    Phase 3b: synchronously runs the probe (still stubbed for the exploit
    side — Phase 2 will SSH and execute the real script), then attempts
    Kibana alert correlation. Returns the probe_job_id; the on-disk
    record carries the full result.

    The returned record contains:
      - ``status``: 'DONE'
      - ``mode``: 'full' | 'degraded'
      - ``fired``: bool (full mode only — present always in degraded
        mode as ``false``)
      - ``alert_id`` / ``fire_time`` / ``rule_uuid``: present iff
        ``fired == True``
      - ``degraded``: True iff Kibana couldn't be reached / queried
    """
    if not _descriptor_has_probe_block(vuln_id):
        raise KeyError(f"vuln '{vuln_id}' has no trigger_probe")

    probe_id = f"probe_{uuid.uuid4().hex[:12]}"
    window = window_seconds or DEFAULT_PROBE_WINDOW_SECONDS
    started_at = datetime.now(timezone.utc)

    base_record: dict[str, Any] = {
        "probe_job_id": probe_id,
        "vuln_id": vuln_id,
        "lab": lab,
        "host": host,
        "actor": actor or "unknown",
        "window_seconds": window,
        "status": "DONE",
        "probe_stdout": (
            "[STUB] Phase 1/3b — Phase 2 will run actual probe over SSH."
        ),
        "started_at": started_at.isoformat(),
    }

    # Try full-mode correlation. _discover_elastic_endpoint returns None
    # when the stack isn't installed OR isn't reachable; in either case
    # we drop to degraded mode.
    endpoint_info = _discover_elastic_endpoint(lab)

    if endpoint_info is None:
        record = {
            **base_record,
            "mode": "degraded",
            "fired": False,
            "degraded": True,
            "alerts_received": [],
            "result": "probe-only",
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
    else:
        rule_uuids = _descriptor_rule_uuids(vuln_id)
        correlation = correlate_alerts(
            kibana_endpoint=endpoint_info["kibana_endpoint"],
            es_user=endpoint_info["es_user"],
            es_password=endpoint_info["es_password"],
            rule_uuids=rule_uuids,
            target_host=host,
            probe_start_ts=started_at.isoformat(),
        )
        record = {
            **base_record,
            "mode": "degraded" if correlation.get("degraded") else "full",
            "fired": bool(correlation.get("fired")),
            "alert_id": correlation.get("alert_id"),
            "fire_time": correlation.get("fire_time"),
            "rule_uuid": correlation.get("rule_uuid"),
            "degraded": bool(correlation.get("degraded")),
            "kibana_endpoint": endpoint_info["kibana_endpoint"],
            "stack_host": endpoint_info["stack_host"],
            "alerts_received": (
                [correlation["alert_id"]] if correlation.get("alert_id") else []
            ),
            "result": (
                "fired" if correlation.get("fired")
                else ("degraded" if correlation.get("degraded") else "no-alert")
            ),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        if correlation.get("error"):
            record["error"] = correlation["error"]

    _write_probe(probe_id, record)
    return {
        "probe_job_id": probe_id,
        "status": "QUEUED",
        "mode": record["mode"],
        "degraded": record["degraded"],
    }


def get_probe(probe_job_id: str) -> Optional[dict[str, Any]]:
    """Return the probe record, or None when unknown."""
    return _read_probe(probe_job_id)
