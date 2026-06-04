"""JSONL audit log writer.

Each line: {ts, op, action, target?, project?, details?}. Append-only.
Concurrent writes serialized by an RLock. Reads return most-recent-first
slices for the activity feed.

Rotation: after each write, if audit.log exceeds _ROTATION_THRESHOLD_BYTES,
the file is rotated. Existing archives are shifted (audit.log.N.gz →
audit.log.(N+1).gz) and a fresh empty audit.log is created. Only the most
recent _MAX_ARCHIVES gzipped archives are retained; older archives are
dropped. read_recent() only reads the live audit.log — archives are
intentionally not surfaced through the API.
"""
import gzip
import json
import os
import shutil
import threading
from datetime import datetime
from pathlib import Path


def _resolve_dashboard_home() -> Path:
    """Honor DASHBOARD_STATE_DIR for test isolation; default to ~/.dashboard.

    Mirrors operator_service._resolve_dashboard_home — kept duplicated to
    avoid an import cycle between these peer modules. See task #54.
    """
    env = os.environ.get("DASHBOARD_STATE_DIR")
    if env:
        return Path(env)
    return Path.home() / ".dashboard"


_LOG_PATH = _resolve_dashboard_home() / "audit.log"
_LOCK = threading.RLock()
_MAX_READ_BYTES = 2 * 1024 * 1024  # cap reads at 2 MiB
_ROTATION_THRESHOLD_BYTES = 10 * 1024 * 1024  # 10 MiB — rotate when log exceeds this
_MAX_ARCHIVES = 3  # keep audit.log.1.gz .. audit.log.3.gz


def _ensure_log():
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _LOG_PATH.exists():
        _LOG_PATH.touch()


def _rotate_if_needed():
    """If the live log exceeds the threshold, rotate.

    Shifts existing audit.log.N.gz → audit.log.(N+1).gz, drops anything
    beyond _MAX_ARCHIVES, gzips the just-rotated audit.log → audit.log.1.gz,
    and creates a fresh empty audit.log. Must never raise — caller wraps
    in a broader try/except too.
    """
    try:
        st = _LOG_PATH.stat()
    except OSError:
        return
    if st.st_size <= _ROTATION_THRESHOLD_BYTES:
        return

    parent = _LOG_PATH.parent
    base = _LOG_PATH.name  # "audit.log"

    # Drop the oldest archive if it would exceed the retention cap, then
    # shift the remaining archives up by one slot.
    oldest = parent / f"{base}.{_MAX_ARCHIVES}.gz"
    if oldest.exists():
        try:
            oldest.unlink()
        except OSError:
            pass
    for n in range(_MAX_ARCHIVES - 1, 0, -1):
        src = parent / f"{base}.{n}.gz"
        dst = parent / f"{base}.{n + 1}.gz"
        if src.exists():
            try:
                src.rename(dst)
            except OSError:
                pass

    # Move the live log out of the way, gzip it into slot 1, then drop the
    # uncompressed intermediate.
    rotated = parent / f"{base}.1"
    try:
        _LOG_PATH.rename(rotated)
    except OSError:
        # Couldn't rename — give up and leave the live log in place.
        return
    try:
        with rotated.open("rb") as f_in, gzip.open(parent / f"{base}.1.gz", "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    except OSError:
        pass
    finally:
        try:
            rotated.unlink()
        except OSError:
            pass

    # Recreate a fresh empty live log for subsequent appends.
    try:
        _LOG_PATH.touch()
    except OSError:
        pass


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
            # Inline rotation check — cheap os.stat in the common case.
            try:
                _rotate_if_needed()
            except Exception:
                pass
    except Exception:
        pass  # never break a request because of audit


def read_recent(
    limit=50,
    *,
    op_filter=None,
    action_prefix=None,
    project_filter=None,
    target_filter=None,
):
    """Return most-recent-first slice. Reads from the tail of the file.

    Optional filters (all AND-combined):
      op_filter         exact match on entry["op"]
      action_prefix     entry["action"] startswith
      project_filter    exact match on entry["project"] — added for Phase 3a
                        Manage sub-pill "last touched by [operator]" attribution
                        (see CLAUDE.md Phase 3a notes).
      target_filter     exact match on entry["target"] — added for Polish B so
                        beacon "driven by" / per-bid command history can filter
                        server-side instead of pulling everything and filtering
                        in JS.
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
        if target_filter and entry.get("target") != target_filter:
            continue
        out.append(entry)
        if len(out) >= limit:
            break
    return out
