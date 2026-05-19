"""Presence service — soft information surface for simultaneous editing.

Per Decision #23: no locking, no blocking. When two operators land on the
same project's Configure or Manage view, both see a small banner telling
them another operator is also viewing the project.

Heartbeats are persisted at ``webapp/state/presence/<project>.yaml`` keyed
by operator id, so the file is small (one entry per operator per project)
and an atomic write avoids torn reads. The file is read on every
heartbeat to compute the response — there's no in-memory cache because
multiple gunicorn workers would diverge.

YAML schema:

    project: c2-adhoc-01
    entries:
      harris:
        operator_id: harris
        project: c2-adhoc-01
        page: configure
        last_heartbeat: 2026-05-19T10:32:01.123456+00:00
      alice:
        operator_id: alice
        project: c2-adhoc-01
        page: manage
        last_heartbeat: 2026-05-19T10:31:58.842310+00:00
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, NamedTuple

try:  # pragma: no cover - PyYAML is in requirements.txt
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

# ──────────────────────────────────────────────────────────────────────
# Storage paths
# ──────────────────────────────────────────────────────────────────────

# webapp/backend/services/presence_service.py → parents[3] is the repo root.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
STATE_DIR = _PROJECT_ROOT / "webapp" / "state" / "presence"

# Allowed page identifiers. Heartbeats with other values are still stored
# (the frontend is the source of truth for valid pages) but the service
# doesn't try to interpret them.
KNOWN_PAGES = ("configure", "manage", "deploy", "operations", "dashboard")

# Default freshness windows. Heartbeat ticks at 30s in the frontend, so
# 60s gives one missed tick of slack before an operator is considered
# stale; 300s is the cleanup threshold beyond which we delete the entry
# entirely.
DEFAULT_FRESH_SECONDS = 60
DEFAULT_STALE_SECONDS = 300

_LOCK = threading.RLock()


class PresenceEntry(NamedTuple):
    operator_id: str
    project: str
    page: str
    last_heartbeat: datetime


@dataclass
class _RawEntry:
    operator_id: str
    project: str
    page: str
    last_heartbeat: str  # ISO-8601 with TZ

    def to_public(self) -> PresenceEntry:
        try:
            ts = datetime.fromisoformat(self.last_heartbeat)
        except ValueError:
            ts = datetime.now(timezone.utc)
        # Normalize naive timestamps to UTC so callers can always compare.
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return PresenceEntry(
            operator_id=self.operator_id,
            project=self.project,
            page=self.page,
            last_heartbeat=ts,
        )


# ──────────────────────────────────────────────────────────────────────
# IO helpers
# ──────────────────────────────────────────────────────────────────────

def _project_path(project: str) -> Path:
    # Hard-defend against path traversal — project names can include
    # underscores, hyphens, alphanumerics. Anything else collapses to a
    # safe placeholder so we never write outside STATE_DIR.
    safe = "".join(c for c in project if c.isalnum() or c in ("_", "-")) or "_unknown"
    return STATE_DIR / f"{safe}.yaml"


def _serialize(payload: dict) -> str:
    if yaml is not None:
        return yaml.safe_dump(payload, sort_keys=True)
    # Fallback for environments without PyYAML — JSON is a valid YAML
    # subset so the file is still parseable when yaml is later installed.
    import json
    return json.dumps(payload, sort_keys=True, indent=2)


def _deserialize(text: str) -> dict:
    if not text.strip():
        return {}
    if yaml is not None:
        return yaml.safe_load(text) or {}
    import json
    try:
        return json.loads(text)
    except Exception:
        return {}


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    os.replace(tmp, path)


def _read_project_file(project: str) -> dict:
    path = _project_path(project)
    if not path.exists():
        return {"project": project, "entries": {}}
    try:
        data = _deserialize(path.read_text())
    except OSError:
        return {"project": project, "entries": {}}
    if not isinstance(data, dict):
        return {"project": project, "entries": {}}
    entries = data.get("entries")
    if not isinstance(entries, dict):
        entries = {}
    return {"project": data.get("project") or project, "entries": entries}


def _entries_from_raw(raw: dict) -> list[PresenceEntry]:
    out: list[PresenceEntry] = []
    for op_id, e in (raw.get("entries") or {}).items():
        if not isinstance(e, dict):
            continue
        try:
            out.append(_RawEntry(
                operator_id=e.get("operator_id") or op_id,
                project=e.get("project") or raw.get("project") or "",
                page=str(e.get("page") or "unknown"),
                last_heartbeat=str(e.get("last_heartbeat") or ""),
            ).to_public())
        except Exception:
            continue
    return out


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

def heartbeat(operator_id: str, project: str, page: str) -> None:
    """Record that ``operator_id`` is currently on ``project``/``page``.

    The entry replaces any previous heartbeat for the same operator on the
    same project (the file is one-entry-per-operator). Writes are atomic
    so a concurrent reader never observes a torn file.
    """
    if not operator_id or not project:
        # Malformed call — silently no-op. The route layer validates input
        # and returns 400 on its own; this guard is defense-in-depth.
        return
    with _LOCK:
        raw = _read_project_file(project)
        raw["project"] = project
        entries = raw.get("entries") or {}
        entries[operator_id] = {
            "operator_id": operator_id,
            "project": project,
            "page": page or "unknown",
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
        }
        raw["entries"] = entries
        _atomic_write(_project_path(project), _serialize(raw))


def list_active(project: str, since_seconds: int = DEFAULT_FRESH_SECONDS) -> list[PresenceEntry]:
    """Return all operators with a heartbeat newer than ``since_seconds``
    seconds ago for ``project``, sorted by most-recent-first.

    Stale entries are filtered but NOT deleted here — deletion is the job
    of :func:`cleanup_stale`. The frontend polls this once every 30s, so
    it's cheap to filter on read rather than purge on each call.
    """
    if not project:
        return []
    with _LOCK:
        raw = _read_project_file(project)
    cutoff = datetime.now(timezone.utc).timestamp() - max(0, int(since_seconds))
    fresh: list[PresenceEntry] = []
    for entry in _entries_from_raw(raw):
        if entry.last_heartbeat.timestamp() >= cutoff:
            fresh.append(entry)
    fresh.sort(key=lambda e: e.last_heartbeat, reverse=True)
    return fresh


def cleanup_stale(max_age_seconds: int = DEFAULT_STALE_SECONDS) -> int:
    """Remove entries older than ``max_age_seconds`` from every project
    file. Returns the total count of removed entries.

    Project files with zero remaining entries are deleted entirely so the
    state directory doesn't accumulate empty husks.
    """
    cutoff = datetime.now(timezone.utc).timestamp() - max(0, int(max_age_seconds))
    removed = 0
    with _LOCK:
        if not STATE_DIR.exists():
            return 0
        for path in STATE_DIR.glob("*.yaml"):
            try:
                raw = _deserialize(path.read_text())
            except OSError:
                continue
            if not isinstance(raw, dict):
                continue
            entries = raw.get("entries") or {}
            if not isinstance(entries, dict):
                entries = {}
            kept: dict[str, dict] = {}
            for op_id, e in entries.items():
                if not isinstance(e, dict):
                    removed += 1
                    continue
                try:
                    ts = datetime.fromisoformat(str(e.get("last_heartbeat") or ""))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                except ValueError:
                    removed += 1
                    continue
                if ts.timestamp() >= cutoff:
                    kept[op_id] = e
                else:
                    removed += 1
            if kept:
                raw["entries"] = kept
                _atomic_write(path, _serialize(raw))
            else:
                try:
                    path.unlink()
                except OSError:
                    pass
    return removed


def others(operator_id: str, project: str, since_seconds: int = DEFAULT_FRESH_SECONDS) -> list[PresenceEntry]:
    """Convenience: ``list_active`` minus the caller. Used by the
    heartbeat endpoint to return who ELSE is currently on this project.
    """
    return [e for e in list_active(project, since_seconds=since_seconds) if e.operator_id != operator_id]


def entry_to_dict(entry: PresenceEntry) -> dict:
    """Serialize a :class:`PresenceEntry` for JSON responses."""
    return {
        "operator_id": entry.operator_id,
        "project": entry.project,
        "page": entry.page,
        "last_heartbeat": entry.last_heartbeat.isoformat(),
    }


def entries_to_list(entries: Iterable[PresenceEntry]) -> list[dict]:
    return [entry_to_dict(e) for e in entries]
