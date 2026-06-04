"""Bolt-on install dispatcher.

Owns the install / uninstall / patch / patch_revert job lifecycle. Jobs
are persisted as YAML under ``webapp/state/bolton/jobs/`` and run on a
background thread.

Execution model
---------------
The dispatcher generates a playbook from the descriptor's ``steps`` block
and shells out to ``ansible-playbook`` (real execution path,
``_run_ansible_job``). The playbook is written to ``/tmp`` per-job and
includes each step's ``ansible_role`` invocation or ``script`` exec. On
exit the verify probe runs as a final play; success/failure drives the
terminal job status.

The simulation path (``_run_simulated_job``) is preserved as a fallback
for environments where ``ansible-playbook`` is not on PATH (e.g. CI
runners) or when ``BOLTON_SIMULATE_ANSIBLE=1`` is exported. Tests rely on
this path; production operators never see it once Ansible is installed
on the dashboard host.

Operator configuration
----------------------
- ``ansible-playbook`` must be on the dashboard host's PATH (it already
  is for GOAD provisioning — see ``ansible/playbooks/``).
- Inventory location: ``ansible/inventory/<lab>/hosts`` (per-lab YAML or
  INI). If the file is absent, the service falls back to writing a
  minimal in-memory inventory from cached ``HostFacts``.
- Environment variables:

    BOLTON_SIMULATE_ANSIBLE=1   force the simulation path (CI safety)
    BOLTON_ANSIBLE_BIN=...      override ``ansible-playbook`` path
    BOLTON_ANSIBLE_TIMEOUT_X=3  multiplier on descriptor estimated_time;
                                hard kill threshold. Default = 3.
    BOLTON_ROLES_SEARCH_PATH    colon-separated role search paths.
                                Default: <project>/ansible/roles +
                                <project>/tools/goad/ansible/roles so
                                descriptors can opt into upstream GOAD
                                vuln roles via ``import_role: name: vulns/<n>``
                                (see docs/internal/BOLTON_ANSIBLE_AUDIT.md).

State machine
-------------
::

    QUEUED ─▶ RUNNING ─▶ SUCCEEDED                (happy path)
                   │
                   ├─▶ FAILED                      (Ansible exit != 0 OR
                   │                                hard timeout SIGTERM)
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
import shutil
import signal
import subprocess
import tempfile
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
# Real Ansible execution
# ──────────────────────────────────────────────────────────────────────

_PROJECT_ANSIBLE_ROOT = _PROJECT_ROOT / "ansible"
_PROJECT_BOLTON_ROLES = _PROJECT_ANSIBLE_ROOT / "roles"
# Upstream GOAD vuln roles ship as a submodule under tools/goad/. They live
# at tools/goad/ansible/roles/vulns/<name>/. Including the parent directory
# (tools/goad/ansible/roles) in the Ansible roles search path lets a
# descriptor write ``import_role: name: vulns/enable_llmnr`` and resolve it
# without per-descriptor path gymnastics. The audit doc
# (docs/internal/BOLTON_ANSIBLE_AUDIT.md) explains why no descriptor uses
# this today and what the prerequisites are before any of them can.
_UPSTREAM_GOAD_ROLES = _PROJECT_ROOT / "tools" / "goad" / "ansible" / "roles"

# Minimum hard-timeout floor (seconds). Avoids a 5-second descriptor
# being killed before Ansible even finishes booting. Tests may patch
# this to a smaller value to exercise the timeout codepath quickly.
_HARD_TIMEOUT_FLOOR_SECONDS = 30

# Running subprocess.Popen handles, keyed by job_id. Populated by
# ``_run_ansible_job`` and consulted by ``cancel_job`` to deliver SIGTERM.
_RUNNING_PROCS: dict[str, subprocess.Popen[str]] = {}
_RUNNING_PROCS_LOCK = threading.Lock()


def _write_log_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()}  {line}\n")


def _fail(job: Job, message: str) -> None:
    """Helper: write the message to the job log + flip status to FAILED."""
    log = _log_path(job.id)
    job.log_path = log
    _write_log_line(log, f"[ERROR] {message}")
    _transition(job, JobStatus.FAILED, error=message)


def _ansible_bin() -> str | None:
    """Resolve the ansible-playbook binary, honouring BOLTON_ANSIBLE_BIN."""
    override = os.environ.get("BOLTON_ANSIBLE_BIN")
    if override:
        return override if Path(override).exists() else None
    return shutil.which("ansible-playbook")


def _should_simulate() -> bool:
    """Choose between simulation and real ansible-playbook.

    Returns True when:
      - BOLTON_SIMULATE_ANSIBLE=1 (explicit operator/test opt-in), or
      - ansible-playbook is not on PATH (CI / dev environment safety).
    """
    if os.environ.get("BOLTON_SIMULATE_ANSIBLE") == "1":
        return True
    return _ansible_bin() is None


def _load_descriptor(bolton_id: str) -> Any:
    """Best-effort descriptor lookup. Returns ``None`` on any failure."""
    try:
        from webapp.backend.services import bolton_catalog_service
        return bolton_catalog_service.get_descriptor(bolton_id)
    except Exception:
        return None


def _step_to_task(step: Any) -> dict[str, Any]:
    """Translate one descriptor step (AnsibleStep or ScriptStep, or a dict
    representation thereof) into a single Ansible task dict."""
    # Normalize to dict form (descriptor may give us Pydantic models).
    if hasattr(step, "model_dump"):
        sd = step.model_dump()
    elif isinstance(step, dict):
        sd = dict(step)
    else:
        sd = {}

    name = sd.get("description") or sd.get("ansible_role") or sd.get("script") or "step"

    if "ansible_role" in sd and sd.get("ansible_role"):
        # Generic Ansible module invocation: the descriptor's "ansible_role"
        # field is the module FQCN (e.g. community.windows.win_domain_user),
        # and "role_vars" become the module args. For project-local roles
        # (e.g. bolton_kerberoastable_svc) we use the include_role form so
        # operators can author full roles under ansible/roles/.
        role = sd["ansible_role"]
        role_vars = sd.get("role_vars") or {}

        if "." not in role:
            # Local role under ansible/roles/ — use include_role.
            return {
                "name": name,
                "include_role": {"name": role},
                "vars": role_vars,
            }
        return {
            "name": name,
            role: role_vars,
        }

    if "script" in sd and sd.get("script"):
        # Inline script / path-to-script. Engine hint maps to module.
        engine = (sd.get("engine") or "bash").lower()
        body = sd["script"]
        if engine == "powershell":
            return {"name": name, "ansible.windows.win_shell": body}
        # Default: POSIX shell on the target.
        return {"name": name, "ansible.builtin.shell": body}

    return {"name": name, "ansible.builtin.debug": {"msg": f"empty step: {sd!r}"}}


def _generate_playbook(job: Job, block: Any) -> Path:
    """Write a YAML playbook to ``/tmp/bolton-playbook-<job_id>.yml``.

    Each step is translated into one task. Project-local roles are picked
    up via the default Ansible roles search path; the generated playbook
    also adds ``ansible/roles/`` explicitly via ``roles_path`` in the
    accompanying ``ansible.cfg`` env (set by the caller).
    """
    if yaml is None:
        raise RuntimeError("PyYAML is required to generate bolt-on playbooks")

    steps = list(getattr(block, "steps", None) or [])
    tasks = [_step_to_task(s) for s in steps]

    play = {
        "name": f"bolton {job.action.value} {job.bolton_id}",
        "hosts": job.host,
        "gather_facts": False,
        "any_errors_fatal": True,
        "tasks": tasks,
    }
    playbook_path = Path(tempfile.gettempdir()) / f"bolton-playbook-{job.id}.yml"
    playbook_path.write_text(yaml.safe_dump([play], sort_keys=False))
    return playbook_path


def _inventory_path(lab: str, host: str) -> Path:
    """Return a usable inventory path for the lab.

    Resolution order:
      1. ``ansible/inventory/<lab>/hosts`` (operator-managed)
      2. ``ansible/inventory/<lab>.yml``
      3. Dynamically-generated minimal inventory under
         ``/tmp/bolton-inventory-<lab>.yml`` derived from
         ``bolton_facts_service.get_cached_facts``.
    """
    candidates = [
        _PROJECT_ANSIBLE_ROOT / "inventory" / lab / "hosts",
        _PROJECT_ANSIBLE_ROOT / "inventory" / f"{lab}.yml",
        _PROJECT_ANSIBLE_ROOT / "inventory" / lab / "hosts.yml",
    ]
    for c in candidates:
        if c.exists():
            return c
    # Fallback: synthesize from cached facts.
    return _generate_dynamic_inventory(lab, host)


def _generate_dynamic_inventory(lab: str, host: str) -> Path:
    """Build a minimal inventory file from cached facts for `host`.

    Used when the operator hasn't pre-staged ``ansible/inventory/<lab>/``.
    The generated inventory groups the host by OS family so Windows hosts
    get the ``ansible_connection: winrm`` defaults.
    """
    if yaml is None:
        raise RuntimeError("PyYAML is required for dynamic inventory")

    os_family = "linux"
    try:
        from webapp.backend.services import bolton_facts_service
        facts = bolton_facts_service.get_cached_facts(lab, host)
        if facts is not None:
            os_family = facts.os_family or "linux"
    except Exception:
        pass

    if os_family == "windows":
        group_vars = {
            "ansible_connection": "winrm",
            "ansible_winrm_transport": "kerberos",
            "ansible_port": 5985,
        }
    else:
        group_vars = {
            "ansible_connection": "ssh",
            "ansible_user": "ubuntu",
        }

    inv = {
        "all": {
            "children": {
                f"{os_family}_hosts": {
                    "hosts": {host: {}},
                    "vars": group_vars,
                }
            }
        }
    }
    path = Path(tempfile.gettempdir()) / f"bolton-inventory-{lab}-{job_safe_id(host)}.yml"
    path.write_text(yaml.safe_dump(inv, sort_keys=False))
    return path


def job_safe_id(s: str) -> str:
    """Sanitise a string for use in a tmpfile name."""
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in s)


def _run_verify_probe(job: Job, block: Any) -> bool:
    """Execute the verify probe attached to the descriptor block.

    Returns True on success (matching expectations), False otherwise.
    The probe is wrapped in a tiny ad-hoc playbook so it inherits the
    same inventory + connection settings as the install steps.
    """
    verify = getattr(block, "verify", None)
    if verify is None:
        # No probe defined — treat as a pass (descriptor's choice).
        _write_log_line(job.log_path, "[verify] no probe declared; skipping")
        return True

    probe = getattr(verify, "probe", None) or ""
    timeout = int(getattr(verify, "timeout_seconds", 60) or 60)
    expected_rc = getattr(verify, "expect_exit_code", 0)
    expect_contains = getattr(verify, "expect_stdout_contains", None)

    if not probe.strip():
        return True

    if _should_simulate():
        # No ansible binary — emit a friendly log line and pass-through.
        _write_log_line(job.log_path, "[verify] simulated probe (no ansible-playbook on PATH)")
        return True

    # Decide shell module from the descriptor's OS family hint (re-use
    # facts). PowerShell scripts get win_shell; everything else gets shell.
    os_family = "linux"
    try:
        from webapp.backend.services import bolton_facts_service
        facts = bolton_facts_service.get_cached_facts(job.lab, job.host)
        if facts is not None:
            os_family = facts.os_family or "linux"
    except Exception:
        pass
    shell_mod = "ansible.windows.win_shell" if os_family == "windows" else "ansible.builtin.shell"

    play = [{
        "name": f"bolton verify {job.bolton_id}",
        "hosts": job.host,
        "gather_facts": False,
        "tasks": [
            {
                "name": "verify probe",
                shell_mod: probe,
                "register": "probe_result",
                "ignore_errors": True,
            },
        ],
    }]
    probe_pb = Path(tempfile.gettempdir()) / f"bolton-probe-{job.id}.yml"
    probe_pb.write_text(yaml.safe_dump(play, sort_keys=False))

    cmd = [
        _ansible_bin() or "ansible-playbook",
        str(probe_pb),
        "-i", str(_inventory_path(job.lab, job.host)),
        "--limit", job.host,
    ]
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 30,
        )
    except subprocess.TimeoutExpired:
        _write_log_line(job.log_path, f"[verify] probe timed out after {timeout}s")
        return False
    finally:
        try:
            probe_pb.unlink()
        except OSError:
            pass

    out = (completed.stdout or "") + (completed.stderr or "")
    _write_log_line(job.log_path, f"[verify] rc={completed.returncode}")
    if completed.returncode != 0:
        return False
    if expected_rc is not None and completed.returncode != expected_rc:
        return False
    if expect_contains and expect_contains not in out:
        return False
    return True


def _run_ansible_job(job: Job) -> None:
    """Execute the descriptor's steps via real ansible-playbook.

    Captures stdout/stderr to the job's log file; transitions the job
    status based on exit code, hard timeout, and the verify probe.
    """
    log = _log_path(job.id)
    job.log_path = log
    log.parent.mkdir(parents=True, exist_ok=True)
    _transition(job, JobStatus.RUNNING)

    descriptor = _load_descriptor(job.bolton_id)
    if descriptor is None:
        _fail(job, f"descriptor not found for bolton_id={job.bolton_id}")
        return

    block_name = {
        JobAction.INSTALL.value: "install",
        JobAction.UNINSTALL.value: "uninstall",
        JobAction.PATCH.value: "patch",
        JobAction.PATCH_REVERT.value: "patch_revert",
    }[job.action.value]
    block = getattr(descriptor, block_name, None)
    if block is None:
        _fail(job, f"descriptor has no {block_name} block")
        return

    try:
        playbook_path = _generate_playbook(job, block)
    except Exception as exc:
        _fail(job, f"failed to generate playbook: {exc!r}")
        return

    inventory = _inventory_path(job.lab, job.host)
    bin_path = _ansible_bin() or "ansible-playbook"

    cmd = [
        bin_path,
        str(playbook_path),
        "-i", str(inventory),
        "--limit", job.host,
        "-e", f"target_host={job.host}",
        "-e", f"bolton_op={job.action.value}",
        "-e", f"lab_name={job.lab}",
        "-e", f"bolton_id={job.bolton_id}",
    ]

    # Hard timeout: estimated_time × multiplier (default 3).
    estimated = int(getattr(block, "estimated_time_seconds", 60) or 60)
    multiplier = float(os.environ.get("BOLTON_ANSIBLE_TIMEOUT_X", "3") or 3)
    hard_timeout = max(int(estimated * multiplier), _HARD_TIMEOUT_FLOOR_SECONDS)

    env = os.environ.copy()
    # Make project-local + upstream GOAD vuln roles discoverable.
    # BOLTON_ROLES_SEARCH_PATH override (colon-separated) lets operators
    # point at a different roles checkout; default is project-local
    # ansible/roles + tools/goad/ansible/roles. We always prepend the
    # resolved path to any inherited ANSIBLE_ROLES_PATH so collections
    # installed at the system level still work.
    default_search = f"{_PROJECT_BOLTON_ROLES}:{_UPSTREAM_GOAD_ROLES}"
    configured_search = os.environ.get("BOLTON_ROLES_SEARCH_PATH") or default_search
    existing_roles_path = env.get("ANSIBLE_ROLES_PATH", "")
    env["ANSIBLE_ROLES_PATH"] = (
        f"{configured_search}:{existing_roles_path}".rstrip(":")
    )

    with open(log, "a") as logf:
        logf.write(
            f"[{datetime.now(timezone.utc).isoformat()}] Executing: {' '.join(cmd)}\n"
        )
        logf.write(f"[{datetime.now(timezone.utc).isoformat()}] hard_timeout={hard_timeout}s\n")
        logf.flush()
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
            )
        except FileNotFoundError as exc:
            _fail(job, f"ansible-playbook not found: {exc}")
            return

        with _RUNNING_PROCS_LOCK:
            _RUNNING_PROCS[job.id] = proc

        # Watchdog: enforce hard_timeout regardless of stdout cadence. The
        # main thread's stdout iteration can block on a silent subprocess,
        # so we use a daemon timer to deliver SIGTERM then SIGKILL.
        timed_out = {"flag": False}

        def _watchdog_kill() -> None:
            timed_out["flag"] = True
            try:
                proc.terminate()
            except OSError:
                pass

        watchdog = threading.Timer(hard_timeout, _watchdog_kill)
        watchdog.daemon = True
        watchdog.start()

        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                logf.write(line)
                logf.flush()
            rc = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except OSError:
                pass
            rc = proc.wait()
        finally:
            watchdog.cancel()
            with _RUNNING_PROCS_LOCK:
                _RUNNING_PROCS.pop(job.id, None)
            try:
                playbook_path.unlink()
            except OSError:
                pass

        if timed_out["flag"]:
            logf.write(
                f"[{datetime.now(timezone.utc).isoformat()}] HARD TIMEOUT "
                f"({hard_timeout}s) — subprocess SIGTERMed\n"
            )
            logf.flush()

    if rc != 0:
        msg = (
            f"hard timeout ({hard_timeout}s) — subprocess killed"
            if timed_out["flag"]
            else f"ansible exited with code {rc}"
        )
        _transition(job, JobStatus.FAILED, error=msg)
        _post_run_invalidate(job, success=False)
        return

    # Verify probe — install/uninstall/patch_revert -> STUCK on probe fail.
    # PATCH treats probe-failure as AS_PATCHED_BUT_VULN to surface the
    # exploit-still-works case to the operator distinctly.
    try:
        probe_ok = _run_verify_probe(job, block)
    except Exception as exc:
        _fail(job, f"verify probe crashed: {exc!r}")
        _post_run_invalidate(job, success=False)
        return

    if not probe_ok:
        if job.action is JobAction.PATCH:
            _transition(
                job,
                JobStatus.AS_PATCHED_BUT_VULN,
                error="patch applied but exploit probe still succeeded.",
            )
        else:
            _transition(
                job,
                JobStatus.STUCK,
                error="verify probe failed.",
            )
        _post_run_invalidate(job, success=False)
        return

    _transition(job, JobStatus.SUCCEEDED)
    _post_run_invalidate(job, success=True)


def _run_job(job: Job) -> None:
    """Top-level job runner. Dispatches to real or simulated execution
    based on environment + ansible availability."""
    if _should_simulate():
        _run_simulated_job(job)
    else:
        _run_ansible_job(job)


# ──────────────────────────────────────────────────────────────────────
# Simulated execution (CI / no-ansible fallback)
# ──────────────────────────────────────────────────────────────────────


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

    # Kick off the executor — real Ansible by default, simulation when
    # BOLTON_SIMULATE_ANSIBLE=1 or ansible-playbook isn't on PATH.
    if run_inline:
        _run_job(job)
    else:
        threading.Thread(target=_run_job, args=(job,), daemon=True).start()
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
    """Cancel a queued or running job.

    QUEUED jobs are flipped to FAILED with a 'cancelled' audit marker.
    RUNNING jobs that have a live ``ansible-playbook`` subprocess get a
    SIGTERM; the runner loop observes the rc and writes the terminal
    transition. Simulated runs (no subprocess) cannot be interrupted —
    they finish naturally and the cancellation is recorded as a
    best-effort attempt.
    """
    _ensure_registry_loaded()
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return None
        if job.status is JobStatus.QUEUED:
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
        if job.status is JobStatus.RUNNING:
            # Real-Ansible path: SIGTERM the subprocess if we have one.
            proc = None
            with _RUNNING_PROCS_LOCK:
                proc = _RUNNING_PROCS.get(job.id)
            if proc is not None and proc.poll() is None:
                try:
                    proc.send_signal(signal.SIGTERM)
                except OSError:
                    pass
                _write_log_line(
                    job.log_path,
                    f"[cancel] SIGTERM sent by {operator}",
                )
                audit_service.write(
                    operator,
                    f"bolton.{job.action.value}",
                    target=job.bolton_id,
                    project=job.lab,
                    details={
                        "job_id": job.id,
                        "lab": job.lab,
                        "host": job.host,
                        "status_from": JobStatus.RUNNING.value,
                        "status_to": JobStatus.RUNNING.value,
                        "cancelled": True,
                    },
                )
            return job
        return job


def retry_with_modifications(
    job_id: str,
    modifications: dict[str, Any] | None,
    operator: str = "agent",
) -> Job:
    """Re-dispatch a stuck job with modified role_vars (agent retry path).

    The agent loop (``bolton_agent_service``) produces an
    ``AgentProposal`` whose ``retry_inputs`` describes which descriptor
    inputs to override. The operator approves, the route calls this
    function, and we re-queue the job. Compatibility backstop is
    skipped because the original dispatch already passed it.

    Phase 3a contract: ``modifications`` is a dict of input name → value
    pairs. The Phase 2 install runner will pass them as Ansible
    role_vars (descriptor input overrides) when the playbook is
    re-generated. Until that's wired, modifications travel through the
    audit log as breadcrumbs so a retry can always be traced back to
    the agent proposal that suggested it.

    Args:
        job_id: the stuck job to retry.
        modifications: dict of descriptor inputs to override.
        operator: who approved the retry (audit attribution).

    Returns:
        The newly-created Job (status QUEUED).

    Raises:
        KeyError: unknown job id.
        ValueError: job is not in STUCK state.
    """
    _ensure_registry_loaded()
    with _JOBS_LOCK:
        original = _JOBS.get(job_id)
    if original is None:
        raise KeyError(f"job '{job_id}' not found")
    if original.status is not JobStatus.STUCK:
        raise ValueError(
            f"job '{job_id}' is in state '{original.status.value}', "
            f"not 'stuck' — cannot retry"
        )

    # Look up the descriptor for the new dispatch.
    descriptor = None
    try:
        from webapp.backend.services import bolton_catalog_service
        descriptor = bolton_catalog_service.get_descriptor(original.bolton_id)
    except Exception:
        descriptor = None

    new_job = dispatch_job(
        action=original.action,
        bolton_id=original.bolton_id,
        lab=original.lab,
        host=original.host,
        operator=operator,
        descriptor=descriptor,
        skip_compat_check=True,  # original passed; we're re-trying.
    )

    audit_service.write(
        operator,
        "bolton.agent.retry",
        target=new_job.id,
        project=new_job.lab,
        details={
            "previous_job_id": job_id,
            "bolton_id": new_job.bolton_id,
            "host": new_job.host,
            "modifications": modifications or {},
        },
    )
    return new_job


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
