"""Bolt-on jobs query/cancel facade — Phase 1 (Agent D reconcile).

Read-side wrapper over ``bolton_install_service``. The install service
owns the job state machine; this module exposes the query / cancel /
log-stream surface the routes need, with the exact function names the
route handlers call.

Why a separate module? The install service is write-heavy (dispatch +
state transitions). Keeping the read side in its own import path lets
us (a) test the routes against a clean mock target, (b) later split a
SSE-streaming log tailer onto its own thread without touching the
dispatcher.

Public API:

  - ``list_jobs(lab=, host=, status=, action=, limit=) -> list[dict]``
  - ``get_job(job_id, log_since=0) -> dict | None``
  - ``job_exists(job_id) -> bool``
  - ``cancel(job_id) -> dict`` (raises ``NotCancellable`` on terminal-state cancel)
  - ``stream_log(job_id) -> Iterator[str]``

The route handler imports + catches ``NotCancellable`` from this module.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Iterator, Optional

from webapp.backend.services import bolton_install_service
from webapp.backend.services.bolton_install_service import (
    JobAction,
    JobStatus,
)


# ──────────────────────────────────────────────────────────────────────
# Custom exceptions (caught in routes)
# ──────────────────────────────────────────────────────────────────────

class NotCancellable(Exception):
    """Raised when a cancel is attempted against a terminal-state job."""


# ──────────────────────────────────────────────────────────────────────
# Serializers
# ──────────────────────────────────────────────────────────────────────

def _job_to_dict(job: Any, *, log_tail: str = "") -> dict[str, Any]:
    """Serialize a Job dataclass to the route response shape."""
    d = job.model_dump()
    # Route response uses ``job_id`` and ``status`` consistently; the
    # underlying Job uses ``id``. Alias here so the API stays stable.
    d["job_id"] = d.pop("id")
    if log_tail:
        d["log_tail"] = log_tail
    return d


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

def list_jobs(
    lab: Optional[str] = None,
    host: Optional[str] = None,
    status: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List jobs, optionally filtered."""
    status_enum: Optional[JobStatus] = None
    if status:
        try:
            status_enum = JobStatus(status.lower())
        except ValueError:
            status_enum = None
    jobs = bolton_install_service.list_jobs(
        lab=lab, host=host, status=status_enum,
    )
    if action:
        try:
            wanted_action = JobAction(action.lower())
            jobs = [j for j in jobs if j.action is wanted_action]
        except ValueError:
            pass
    out = [_job_to_dict(j) for j in jobs[: max(1, int(limit))]]
    return out


def _read_log_tail(log_path: Path, since: int = 0) -> str:
    """Read the job log starting at byte offset ``since``."""
    try:
        with open(log_path, "rb") as f:
            f.seek(max(0, since))
            return f.read().decode("utf-8", errors="replace")
    except (OSError, FileNotFoundError):
        return ""


def get_job(job_id: str, log_since: int = 0) -> Optional[dict[str, Any]]:
    """Return a job + its log tail (from ``log_since``), or None."""
    job = bolton_install_service.get_job(job_id)
    if job is None:
        return None
    log_tail = _read_log_tail(job.log_path, since=log_since)
    return _job_to_dict(job, log_tail=log_tail)


def job_exists(job_id: str) -> bool:
    return bolton_install_service.get_job(job_id) is not None


def cancel(job_id: str) -> dict[str, Any]:
    """Cancel a job. Raises KeyError if missing, NotCancellable if terminal."""
    job = bolton_install_service.get_job(job_id)
    if job is None:
        raise KeyError(f"job '{job_id}' not found")
    if job.status in {
        JobStatus.SUCCEEDED, JobStatus.FAILED,
        JobStatus.STUCK, JobStatus.AS_PATCHED_BUT_VULN,
    }:
        raise NotCancellable(
            f"job '{job_id}' is in terminal state {job.status.value}"
        )
    # The install service's cancel_job() returns the job; the route
    # surfaces status only.
    cancelled = bolton_install_service.cancel_job(job_id, operator="system")
    if cancelled is None:
        raise KeyError(f"job '{job_id}' not found")
    return {"status": "CANCELED", "job_id": job_id}


def stream_log(job_id: str) -> Iterator[str]:
    """Yield log lines (without trailing newlines) for SSE streaming.

    Phase 1: reads the existing log file once and yields each line.
    Phase 2 will tail-follow the file until the job hits a terminal
    state, mirroring goad.py's nohup PID watcher pattern.
    """
    job = bolton_install_service.get_job(job_id)
    if job is None:
        return iter([])
    try:
        with open(job.log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                yield line.rstrip("\n")
    except (OSError, FileNotFoundError):
        return
