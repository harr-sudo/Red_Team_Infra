"""Bolt-on install dispatcher — Phase 1 (Agent B).

Owns the install / uninstall / patch / patch_revert job lifecycle. Jobs
are persisted as YAML under ``webapp/state/bolton/jobs/`` and run on a
background thread.

STUB / Phase 1 disclaimer
-------------------------
**Real Ansible playbook execution is OUT OF SCOPE for Phase 1.** The
dispatcher here simulates execution: it sleeps 2 s, writes a few fake log
lines, then transitions the job to ``SUCCEEDED`` (or ``FAILED`` if the
bolton id ends with ``-fail``, a test hook). Phase 2 replaces the
simulation with SSH-to-jumpbox + nohup + ``ansible-playbook``, mirroring
``webapp/backend/routes/goad.py::provision_goad``.

State machine
-------------
::

    QUEUED ─▶ RUNNING ─▶ SUCCEEDED                (happy path)
                   │
                   ├─▶ FAILED                      (Ansible exit != 0)
                   │
                   ├─▶ STUCK                       (verify probe failed,
                   │                                agent intervention)
                   │
                   └─▶ AS_PATCHED_BUT_VULN         (patch verified but
                                                    exploit_probe_after_patch
                                                    reports vulnerable)

Audit log
---------
Every state transition emits an entry via
``audit_service.write(operator, 'bolton.<action>', ...)``. See
``BOLTON_REFINEMENT_patch.md`` §5.2 for the schema.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - PyYAML is in requirements.txt
    yaml = None  # type: ignore

from webapp.backend.services import audit_service
from webapp.backend.services import bolton_facts_service
from webapp.backend.services.bolton_compatibility import (
    CompatibilityState,
    evaluate_compatibility,
)


# ──────────────────────────────────────────────────────────────────────
# Storage paths
# ──────────────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
JOBS_ROOT = _PROJECT_ROOT / "webapp" / "state" / "bolton" / "jobs"

# Default simulated duration (test hook can override via env var).
_SIMULATED_DURATION_SECONDS = float(os.environ.get("BOLTON_STUB_DURATION", "2.0"))


# ──────────────────────────────────────────────────────────────────────
# Enums + Job dataclass
# ──────────────────────────────────────────────────────────────────────

class JobAction(str, Enum):
    INSTALL = "install"
    UNINSTALL = "uninstall"
    PATCH = "patch"
    PATCH_REVERT = "patch_revert"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STUCK = "stuck"
    # Patch terminal failure: patch verify passed but exploit still works.
    AS_PATCHED_BUT_VULN = "as_patched_but_vuln"


_TERMINAL_STATUSES = {
    JobStatus.SUCCEEDED,
    JobStatus.FAILED,
    JobStatus.STUCK,
    JobStatus.AS_PATCHED_BUT_VULN,
}


@dataclass
class Job:
    id: str
    action: JobAction
    bolton_id: str
    lab: str
    host: str
    operator: str
    status: JobStatus = JobStatus.QUEUED
    log_path: Path = field(default_factory=lambda: Path("/dev/null"))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_summary: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def model_dump(self, mode: str = "python") -> dict[str, Any]:  # noqa: ARG002
        d = asdict(self)
        d["action"] = self.action.value
        d["status"] = self.status.value
        d["log_path"] = str(self.log_path)
        for k in ("created_at", "started_at", "finished_at"):
            v = d.get(k)
            if isinstance(v, datetime):
                d[k] = v.isoformat()
        return d


# ──────────────────────────────────────────────────────────────────────
# Persistence
# ──────────────────────────────────────────────────────────────────────

def _job_path(job_id: str) -> Path:
    return JOBS_ROOT / f"{job_id}.yaml"


def _log_path(job_id: str) -> Path:
    return JOBS_ROOT / f"{job_id}.log"


def _serialize_job(job: Job) -> str:
    payload = job.model_dump()
    if yaml is not None:
        return yaml.safe_dump(payload, sort_keys=True)
    return json.dumps(payload, sort_keys=True, indent=2)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    os.replace(tmp, path)


def _persist_job(job: Job) -> None:
    _atomic_write(_job_path(job.id), _serialize_job(job))


def _load_job_from_disk(path: Path) -> Job | None:
    try:
        text = path.read_text()
    except OSError:
        return None
    try:
        if yaml is not None:
            data = yaml.safe_load(text) or {}
        else:
            data = json.loads(text)
    except Exception:
        return None
    try:
        return Job(
            id=data["id"],
            action=JobAction(data["action"]),
            bolton_id=data["bolton_id"],
            lab=data["lab"],
            host=data["host"],
            operator=data["operator"],
            status=JobStatus(data["status"]),
            log_path=Path(data.get("log_path") or "/dev/null"),
            started_at=_parse_dt(data.get("started_at")),
            finished_at=_parse_dt(data.get("finished_at")),
            error_summary=data.get("error_summary"),
            created_at=_parse_dt(data.get("created_at")) or datetime.now(timezone.utc),
        )
    except (KeyError, ValueError, TypeError):
        return None


def _parse_dt(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    if not isinstance(v, str):
        return None
    try:
        dt = datetime.fromisoformat(v.rstrip("Z"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ──────────────────────────────────────────────────────────────────────
# Audit helpers
# ──────────────────────────────────────────────────────────────────────

def _audit_transition(job: Job, status_from: JobStatus, status_to: JobStatus) -> None:
    """Emit a ``bolton.<action>`` audit entry for one state transition.

    Used by ``dispatch_job`` for the initial QUEUED creation and by
    ``cancel_job``. The main run loop's ``_transition`` writes audit
    inline so that the audit log can never lag behind the in-memory
    state (important for test ``wait_for_job`` semantics).
    """
    audit_service.write(
        job.operator,
        f"bolton.{job.action.value}",
        target=job.bolton_id,
        project=job.lab,
        details={
            "job_id": job.id,
            "lab": job.lab,
            "host": job.host,
            "status_from": status_from.value,
            "status_to": status_to.value,
        },
    )


def _transition(job: Job, new_status: JobStatus, *, error: str | None = None) -> None:
    old = job.status
    now = datetime.now(timezone.utc)
    # Write the audit entry BEFORE flipping the in-memory status so that
    # observers polling for a terminal state (see wait_for_job in tests)
    # cannot see the new status before the audit log reflects it. The
    # audit log records the *transition*, not the prior state.
    audit_service.write(
        job.operator,
        f"bolton.{job.action.value}",
        target=job.bolton_id,
        project=job.lab,
        details={
            "job_id": job.id,
            "lab": job.lab,
            "host": job.host,
            "status_from": old.value,
            "status_to": new_status.value,
        },
    )
    if new_status is JobStatus.RUNNING and job.started_at is None:
        job.started_at = now
    if new_status in _TERMINAL_STATUSES:
        job.finished_at = now
    if error is not None:
        job.error_summary = error
    job.status = new_status
    _persist_job(job)


# ──────────────────────────────────────────────────────────────────────
# Stubbed execution
# ──────────────────────────────────────────────────────────────────────

def _write_log_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()}  {line}\n")


def _run_simulated_job(job: Job) -> None:
    """Phase 1 simulation: sleep + write a few log lines + transition.

    Test hook: any bolton_id ending in ``-fail`` transitions to FAILED.
    A bolton_id ending in ``-stuck`` transitions to STUCK. A bolton_id
    ending in ``-vuln`` transitions to AS_PATCHED_BUT_VULN (only for
    PATCH actions, falls back to SUCCEEDED otherwise).

    Phase 2 will replace this with a real ansible-playbook invocation.
    """
    log = _log_path(job.id)
    job.log_path = log
    _write_log_line(log, f"[STUB] dispatching {job.action.value} for {job.bolton_id}")
    _write_log_line(log, f"[STUB] target lab={job.lab} host={job.host} op={job.operator}")
    _transition(job, JobStatus.RUNNING)
    time.sleep(_SIMULATED_DURATION_SECONDS)

    bid = job.bolton_id.lower()
    if bid.endswith("-fail"):
        _write_log_line(log, "[STUB] simulated ansible exit code 2")
        _transition(
            job,
            JobStatus.FAILED,
            error="Simulated failure (bolton id ends with '-fail').",
        )
        # Invalidate facts even on failure — partial state may exist.
        _post_run_invalidate(job, success=False)
        return
    if bid.endswith("-stuck"):
        _write_log_line(log, "[STUB] simulated verify probe failure")
        _transition(
            job,
            JobStatus.STUCK,
            error="Verify probe failed (simulated). Agent intervention available.",
        )
        return
    if bid.endswith("-vuln") and job.action is JobAction.PATCH:
        _write_log_line(log, "[STUB] patch verified, exploit probe still succeeded")
        _transition(
            job,
            JobStatus.AS_PATCHED_BUT_VULN,
            error="exploit_probe_after_patch still succeeded — patch is broken.",
        )
        return

    _write_log_line(log, "[STUB] simulation completed")
    _transition(job, JobStatus.SUCCEEDED)
    _post_run_invalidate(job, success=True)


def _post_run_invalidate(job: Job, success: bool) -> None:
    """Invalidate cached host facts after a job ends.

    Phase 1 implementation drops only the target host. A future hook
    that knows the descriptor's ``side_effects.global`` can extend this
    to lab-wide invalidation.
    """
    try:
        bolton_facts_service.invalidate_facts(job.lab, job.host)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────
# In-memory registry (re-hydrated from disk on first access)
# ──────────────────────────────────────────────────────────────────────

_JOBS: dict[str, Job] = {}
_JOBS_LOCK = threading.RLock()
_REGISTRY_LOADED = False


def _ensure_registry_loaded() -> None:
    """Lazy-load every persisted job into memory.

    The dispatcher is in-process so the registry is authoritative; disk
    is purely durable backup. We re-hydrate once on first access so a
    process restart doesn't drop visibility of historical jobs.
    """
    global _REGISTRY_LOADED
    with _JOBS_LOCK:
        if _REGISTRY_LOADED:
            return
        if JOBS_ROOT.exists():
            for path in JOBS_ROOT.glob("*.yaml"):
                job = _load_job_from_disk(path)
                if job is not None and job.id not in _JOBS:
                    _JOBS[job.id] = job
        _REGISTRY_LOADED = True


def _new_job_id() -> str:
    return f"job_{uuid.uuid4().hex[:12]}"


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

def dispatch_job(
    action: JobAction,
    bolton_id: str,
    lab: str,
    host: str,
    operator: str,
    *,
    descriptor: Any = None,
    skip_compat_check: bool = False,
    run_inline: bool = False,
) -> Job:
    """Validate (if possible), persist, enqueue a job.

    Compatibility backstop:
      For ``install`` and ``patch`` actions, if a descriptor is supplied
      AND facts are cached for (lab, host), we re-evaluate compatibility
      and refuse if the current state is not ``INSTALLABLE``. This
      mirrors BOLTON_REFINEMENT_compatibility.md §4.1 install-time
      backstop. Uninstall/patch_revert skip the backstop because they
      operate on already-installed artifacts.

    The check is best-effort: when no descriptor or no facts exist, the
    job is dispatched and the underlying Ansible role / Phase 2 verify
    step is expected to surface any problem. Tests can force-skip via
    ``skip_compat_check=True``.
    """
    _ensure_registry_loaded()

    if not skip_compat_check and descriptor is not None and action in (
        JobAction.INSTALL,
        JobAction.PATCH,
    ):
        facts = bolton_facts_service.get_cached_facts(lab, host)
        if facts is not None:
            result = evaluate_compatibility(descriptor, facts)
            if (
                result.state is not CompatibilityState.INSTALLABLE
                and result.state is not CompatibilityState.ALREADY_INSTALLED
            ):
                raise CompatibilityRefusedError(
                    f"Refused {action.value} of {bolton_id} on {host}: "
                    f"{result.state.value} — {result.reason}",
                    state=result.state.name,
                )

    job = Job(
        id=_new_job_id(),
        action=action,
        bolton_id=bolton_id,
        lab=lab,
        host=host,
        operator=operator,
        status=JobStatus.QUEUED,
        log_path=Path("/dev/null"),
    )
    job.log_path = _log_path(job.id)
    with _JOBS_LOCK:
        _JOBS[job.id] = job
        _persist_job(job)
    # Audit the QUEUED creation explicitly.
    _audit_transition(job, JobStatus.QUEUED, JobStatus.QUEUED)

    # Kick off the simulated executor.
    if run_inline:
        _run_simulated_job(job)
    else:
        threading.Thread(target=_run_simulated_job, args=(job,), daemon=True).start()
    return job


def get_job(job_id: str) -> Job | None:
    _ensure_registry_loaded()
    with _JOBS_LOCK:
        return _JOBS.get(job_id)


def list_jobs(
    lab: str | None = None,
    host: str | None = None,
    status: JobStatus | None = None,
) -> list[Job]:
    _ensure_registry_loaded()
    with _JOBS_LOCK:
        jobs = list(_JOBS.values())
    out = []
    for j in jobs:
        if lab is not None and j.lab != lab:
            continue
        if host is not None and j.host != host:
            continue
        if status is not None and j.status != status:
            continue
        out.append(j)
    out.sort(key=lambda j: j.created_at, reverse=True)
    return out


def cancel_job(job_id: str, operator: str) -> Job | None:
    """Cancel a queued/running job (Phase 1: best-effort).

    The simulator can't be safely interrupted, so cancellation only
    succeeds when the job is still ``QUEUED``. In Phase 2 this will send
    a remote SIGTERM to the nohup'd ansible PID on the jumpbox.
    """
    _ensure_registry_loaded()
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return None
        if job.status is not JobStatus.QUEUED:
            return job
        old = job.status
        job.status = JobStatus.FAILED
        job.error_summary = f"Cancelled by {operator}"
        job.finished_at = datetime.now(timezone.utc)
        _persist_job(job)
    audit_service.write(
        operator,
        f"bolton.{job.action.value}",
        target=job.bolton_id,
        project=job.lab,
        details={
            "job_id": job.id,
            "lab": job.lab,
            "host": job.host,
            "status_from": old.value,
            "status_to": JobStatus.FAILED.value,
            "cancelled": True,
        },
    )
    return job


def wait_for_job(job_id: str, timeout: float = 10.0, poll: float = 0.05) -> Job | None:
    """Block until the job hits a terminal state. Test helper."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = get_job(job_id)
        if job is None:
            return None
        if job.status in _TERMINAL_STATUSES:
            return job
        time.sleep(poll)
    return get_job(job_id)


class CompatibilityRefusedError(Exception):
    """Raised by ``dispatch_job`` when the install-time backstop refuses."""

    def __init__(self, message: str, *, state: str | None = None):
        super().__init__(message)
        self.state = state


# Route layer (Agent D reconcile) catches the shorter alias.
CompatibilityRefused = CompatibilityRefusedError


# ──────────────────────────────────────────────────────────────────────
# Route-facing wrapper (Agent D reconcile)
# ──────────────────────────────────────────────────────────────────────

def dispatch(
    op: str,
    lab: str,
    host: str,
    vuln_id: str,
    role_vars: dict[str, Any] | None = None,
    run_probe: bool = False,
    confirm_no_detection: bool = False,
    actor: str | None = None,
) -> dict[str, Any]:
    """Route-facing entry point. Maps the string ``op`` to ``JobAction``,
    looks up the descriptor for the compat backstop, and returns the
    response shape the routes expect.

    Raises:
        KeyError: unknown ``op`` (mapped to 404 by the route)
        CompatibilityRefused: backstop refused (409)
    """
    try:
        action = JobAction(op.lower())
    except ValueError:
        raise KeyError(f"unknown op '{op}'") from None

    # Try to load the descriptor; skip backstop if unavailable.
    descriptor = None
    try:
        from webapp.backend.services import bolton_catalog_service
        descriptor = bolton_catalog_service.get_descriptor(vuln_id)
    except Exception:
        descriptor = None

    try:
        job = dispatch_job(
            action=action,
            bolton_id=vuln_id,
            lab=lab,
            host=host,
            operator=actor or "unknown",
            descriptor=descriptor,
        )
    except CompatibilityRefusedError as e:
        raise CompatibilityRefused(str(e), state=getattr(e, "state", None)) from e

    estimated = None
    if descriptor is not None:
        try:
            install = descriptor.install
            estimated = getattr(install, "estimated_time_seconds", None)
        except AttributeError:
            try:
                estimated = (descriptor or {}).get("install", {}).get(
                    "estimated_time_seconds"
                )
            except Exception:
                estimated = None

    return {
        "job_id": job.id,
        "estimated_time_seconds": estimated,
        "message": "queued",
        "run_probe": run_probe,
        "confirm_no_detection": confirm_no_detection,
        "role_vars": role_vars or {},
    }


# ──────────────────────────────────────────────────────────────────────
# Test helpers (NOT exported via public API doc — used by pytest fixtures)
# ──────────────────────────────────────────────────────────────────────

def _reset_registry_for_tests() -> None:
    """Drop in-memory state. Tests call this between cases."""
    global _REGISTRY_LOADED
    with _JOBS_LOCK:
        _JOBS.clear()
        _REGISTRY_LOADED = False


def _set_simulated_duration_for_tests(seconds: float) -> None:
    global _SIMULATED_DURATION_SECONDS
    _SIMULATED_DURATION_SECONDS = seconds
