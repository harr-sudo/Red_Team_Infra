"""JSONL audit log writer.

Each line: {ts, op, action, target?, project?, details?}. Append-only.
Concurrent writes serialized by an RLock. Reads return most-recent-first
slices for the activity feed.
"""
import json
import threading
from datetime import datetime
from pathlib import Path

_LOG_PATH = Path.home() / ".dashboard" / "audit.log"
_LOCK = threading.RLock()
_MAX_READ_BYTES = 2 * 1024 * 1024  # cap reads at 2 MiB


def _ensure_log():
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _LOG_PATH.exists():
        _LOG_PATH.touch()


def write(op_id, action, *, target=None, project=None, details=None):
    """Append one audit line. Never raises — audit must never break a request."""
    try:
        _ensure_log()
        entry = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "op": op_id or "unknown",
            "action": action,
        }
        if target:
            entry["target"] = target
        if project:
            entry["project"] = project
        if details is not None:
            entry["details"] = details
        with _LOCK:
            with _LOG_PATH.open("a") as f:
                f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # never break a request because of audit


def read_recent(limit=50, *, op_filter=None, action_prefix=None, project_filter=None):
    """Return most-recent-first slice. Reads from the tail of the file.

    Optional filters (all AND-combined):
      op_filter         exact match on entry["op"]
      action_prefix     entry["action"] startswith
      project_filter    exact match on entry["project"] — added for Phase 3a
                        Manage sub-pill "last touched by [operator]" attribution
                        (see CLAUDE.md Phase 3a notes).
    """
    _ensure_log()
    with _LOCK:
        size = _LOG_PATH.stat().st_size
        with _LOG_PATH.open("rb") as f:
            if size > _MAX_READ_BYTES:
                f.seek(size - _MAX_READ_BYTES)
                f.readline()  # discard partial line
            data = f.read().decode("utf-8", errors="replace")
    lines = [l for l in data.splitlines() if l.strip()]
    out = []
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if op_filter and entry.get("op") != op_filter:
            continue
        if action_prefix and not entry.get("action", "").startswith(action_prefix):
            continue
        if project_filter and entry.get("project") != project_filter:
            continue
        out.append(entry)
        if len(out) >= limit:
            break
    return out
