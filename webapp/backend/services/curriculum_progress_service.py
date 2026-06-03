"""Per-operator progress tracking for bolt-on curricula.

State layout (under ``DASHBOARD_STATE_DIR`` / ``~/.dashboard/``):

    curriculum/<operator_id>.json   — one JSON document per operator

Document shape:

    {
        "operator_id": "<id>",
        "vulns": {
            "<vuln_id>": {
                "started_at": <iso>,
                "completed_at": <iso|null>,
                "completed_steps": ["01-discover-spns", ...],
                "assessments": {
                    "<step_id>": {
                        "answer_index": int,
                        "correct": bool,
                        "answered_at": <iso>
                    }
                }
            }
        }
    }

Concurrency: a process-wide RLock guards reads/writes — matches the
pattern used by ``operator_service`` and ``audit_service``. Atomic
replace on save (write to ``.tmp``, then ``os.replace``) so partial
writes can't corrupt state.

Test isolation: respects ``DASHBOARD_STATE_DIR``; the global-setup
hook in ``tests/browser/global-setup.js`` wipes that directory before
each suite run.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _resolve_dashboard_home() -> Path:
    env = os.environ.get("DASHBOARD_STATE_DIR")
    if env:
        return Path(env)
    return Path.home() / ".dashboard"


_LOCK = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _state_dir() -> Path:
    p = _resolve_dashboard_home() / "curriculum"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _doc_path(operator_id: str) -> Path:
    safe = "".join(c for c in operator_id if c.isalnum() or c in ("-", "_", ".")).lower()
    if not safe:
        safe = "unknown"
    return _state_dir() / f"{safe}.json"


def _load(operator_id: str) -> dict[str, Any]:
    path = _doc_path(operator_id)
    if not path.exists():
        return {"operator_id": operator_id, "vulns": {}}
    try:
        with path.open("r", encoding="utf-8") as fh:
            doc = json.load(fh)
            if not isinstance(doc, dict):
                return {"operator_id": operator_id, "vulns": {}}
            doc.setdefault("operator_id", operator_id)
            doc.setdefault("vulns", {})
            return doc
    except (json.JSONDecodeError, OSError):
        return {"operator_id": operator_id, "vulns": {}}


def _save(operator_id: str, doc: dict[str, Any]) -> None:
    path = _doc_path(operator_id)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _ensure_vuln(doc: dict[str, Any], vuln_id: str) -> dict[str, Any]:
    vulns = doc.setdefault("vulns", {})
    if vuln_id not in vulns:
        vulns[vuln_id] = {
            "started_at": _now_iso(),
            "completed_at": None,
            "completed_steps": [],
            "assessments": {},
        }
    return vulns[vuln_id]


def get_progress(operator_id: str, vuln_id: str) -> dict[str, Any]:
    """Return the operator's progress for one vuln (creates an empty
    record if none exists yet — but does NOT persist that empty record).
    """
    with _LOCK:
        doc = _load(operator_id)
        vp = doc.get("vulns", {}).get(vuln_id)
        if vp is None:
            return {
                "operator_id": operator_id,
                "vuln_id": vuln_id,
                "started_at": None,
                "completed_at": None,
                "completed_steps": [],
                "assessments": {},
            }
        return {
            "operator_id": operator_id,
            "vuln_id": vuln_id,
            "started_at": vp.get("started_at"),
            "completed_at": vp.get("completed_at"),
            "completed_steps": list(vp.get("completed_steps", [])),
            "assessments": dict(vp.get("assessments", {})),
        }


def mark_step_complete(operator_id: str, vuln_id: str, step_id: str,
                       *, total_steps: int | None = None) -> dict[str, Any]:
    """Record that the operator finished one step. Idempotent — re-marking
    an already-complete step is a no-op. When ``total_steps`` is given and
    the count of completed steps reaches it, the curriculum is marked
    finished (``completed_at`` set).
    """
    with _LOCK:
        doc = _load(operator_id)
        vp = _ensure_vuln(doc, vuln_id)
        if step_id not in vp["completed_steps"]:
            vp["completed_steps"].append(step_id)
        if total_steps is not None and len(vp["completed_steps"]) >= total_steps:
            if not vp.get("completed_at"):
                vp["completed_at"] = _now_iso()
        _save(operator_id, doc)
        return get_progress(operator_id, vuln_id)


def unmark_step(operator_id: str, vuln_id: str, step_id: str) -> dict[str, Any]:
    """Roll back a step completion (debug / let-me-redo). Clears any
    cached ``completed_at`` so the curriculum is no longer "finished"."""
    with _LOCK:
        doc = _load(operator_id)
        vp = _ensure_vuln(doc, vuln_id)
        vp["completed_steps"] = [s for s in vp["completed_steps"] if s != step_id]
        vp["completed_at"] = None
        _save(operator_id, doc)
        return get_progress(operator_id, vuln_id)


def submit_assessment(operator_id: str, vuln_id: str, step_id: str,
                      answer_index: int, *, correct_index: int) -> dict[str, Any]:
    """Record one assessment answer. Returns the operator's full progress
    plus the boolean ``correct`` result on this submission."""
    with _LOCK:
        doc = _load(operator_id)
        vp = _ensure_vuln(doc, vuln_id)
        is_correct = (answer_index == correct_index)
        vp["assessments"][step_id] = {
            "answer_index": int(answer_index),
            "correct": is_correct,
            "answered_at": _now_iso(),
        }
        _save(operator_id, doc)
        snap = get_progress(operator_id, vuln_id)
        snap["latest_correct"] = is_correct
        snap["latest_step"] = step_id
        return snap


def reset_progress(operator_id: str, vuln_id: str) -> dict[str, Any]:
    """Erase progress for one vuln. The operator's document keeps existing
    progress on OTHER vulns."""
    with _LOCK:
        doc = _load(operator_id)
        if "vulns" in doc and vuln_id in doc["vulns"]:
            del doc["vulns"][vuln_id]
            _save(operator_id, doc)
        return get_progress(operator_id, vuln_id)


def _reset_for_tests() -> None:
    """Wipe every operator's progress directory. Tests only."""
    with _LOCK:
        d = _state_dir()
        if d.exists():
            for f in d.iterdir():
                if f.is_file():
                    f.unlink()
