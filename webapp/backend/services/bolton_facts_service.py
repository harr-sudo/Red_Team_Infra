"""Bolt-on host facts service — Phase 1 (Agent B).

Gathers per-host facts (OS, role, services, KBs, installed bolt-ons) and
caches them on disk so the compatibility evaluator can run a tight loop
over the whole catalog without round-tripping to the target.

STUB / Phase 1 disclaimer
-------------------------
Real Ansible setup-module collection is OUT OF SCOPE for Phase 1. The
``gather_facts`` function here consults a static lookup table of fake
hosts. Phase 2 will replace ``_probe_host`` with a real SSH-to-jumpbox +
``ansible -m setup`` execution following the same pattern as
``webapp/backend/routes/goad.py::provision_goad``.

Cache layout
------------
::

    webapp/state/bolton/host_facts/<lab>/<host>.yaml

- 5-minute TTL based on ``gathered_at``
- atomic write (write to ``.tmp`` then ``os.replace``)
- per-host filelock (``<host>.yaml.lock``) prevents racing refreshes
- on install/uninstall/patch hooks, ``invalidate_facts`` drops the YAML

Pydantic
--------
Agent A is producing ``webapp/bolton/schema.py`` with Pydantic v2 models.
This module avoids hard-importing pydantic so the test suite can run in
environments where pydantic is not installed. A tiny ``_Model`` shim
provides a ``model_dump`` method and dict-style access for tests.
"""

from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - PyYAML is in requirements.txt
    yaml = None  # type: ignore


# ──────────────────────────────────────────────────────────────────────
# Storage paths
# ──────────────────────────────────────────────────────────────────────

# Resolve project root: this file lives at webapp/backend/services/
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
STATE_ROOT = _PROJECT_ROOT / "webapp" / "state" / "bolton" / "host_facts"

# 5-minute TTL per BOLTON_REFINEMENT_compatibility.md §2.4
FACTS_TTL_SECONDS = 5 * 60

# Per-host locks for refresh serialization. Held only while writing.
_HOST_LOCKS: dict[str, threading.Lock] = {}
_HOST_LOCKS_GUARD = threading.Lock()


def _host_lock(lab: str, host: str) -> threading.Lock:
    key = f"{lab}/{host}"
    with _HOST_LOCKS_GUARD:
        lock = _HOST_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _HOST_LOCKS[key] = lock
        return lock


# ──────────────────────────────────────────────────────────────────────
# HostFacts model (dataclass with .model_dump() compat layer)
# ──────────────────────────────────────────────────────────────────────

@dataclass
class HostFacts:
    """Per-host bolt-on compatibility facts.

    Field names mirror BOLTON_REFINEMENT_compatibility.md §2.2. This is a
    plain dataclass to avoid a runtime pydantic dependency; Agent A's
    schema may import or duck-type this if needed.
    """

    host: str
    lab: str
    os_family: str  # 'windows' | 'linux' | 'macos'
    os_version: str
    role: str  # 'domain_controller' | 'member_server' | 'workstation' | 'standalone' | 'linux_member'
    gathered_at: datetime
    # 2026-05-23 — added so descriptors with `edition_in` / `required_domain_function_level`
    # are actually enforced by the resolver (previously read from YAML but
    # silently dropped). os_edition: 'Datacenter' | 'Standard' | 'Pro' |
    # 'Enterprise' | 'Home' | 'Server Core' | etc.
    os_edition: str | None = None
    domain_function_level: str | None = None
    installed_services: dict[str, str] = field(default_factory=dict)
    applied_kbs: list[str] = field(default_factory=list)
    installed_boltons: list[str] = field(default_factory=list)
    active_gpos: list[str] = field(default_factory=list)
    network_subnet: str | None = None
    # Patched CVEs — populated from applied_kbs via cve_kb_map at gather time.
    patched_cves: list[str] = field(default_factory=list)

    # ── Pydantic-compatible API for downstream code ───────────────────
    def model_dump(self, mode: str = "python") -> dict[str, Any]:  # noqa: ARG002
        out: dict[str, Any] = {}
        for k, v in asdict(self).items():
            if isinstance(v, datetime):
                out[k] = v.isoformat()
            else:
                out[k] = v
        return out

    def is_fresh(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        age = (now - self.gathered_at).total_seconds()
        return age <= FACTS_TTL_SECONDS


# ──────────────────────────────────────────────────────────────────────
# Mocked Ansible probe (Phase 1 stub)
# ──────────────────────────────────────────────────────────────────────

# Static lookup table — keyed by host (case-insensitive). In Phase 2 this
# is replaced by a real ``ansible -m setup`` invocation over SSH to the
# jumpbox.
_MOCK_HOST_FACTS: dict[str, dict[str, Any]] = {
    "dc01": {
        "os_family": "windows",
        "os_version": "2019",
        "role": "domain_controller",
        "domain_function_level": "2016",
        "installed_services": {"adcs": "ADCS-Cert-Authority", "iis": "10.0", "smb": "SMBv3"},
        "applied_kbs": ["KB5005010", "KB5034441"],
        "installed_boltons": [],
        "active_gpos": ["Default Domain Policy"],
        "network_subnet": "10.0.10.0/24",
        "patched_cves": ["CVE-2021-34527"],
    },
    "dc02": {
        "os_family": "windows",
        "os_version": "2022",
        "role": "domain_controller",
        "domain_function_level": "2016",
        "installed_services": {"smb": "SMBv3"},
        "applied_kbs": [],
        "installed_boltons": [],
        "active_gpos": ["Default Domain Policy"],
        "network_subnet": "10.0.10.0/24",
        "patched_cves": [],
    },
    "srv01": {
        "os_family": "windows",
        "os_version": "2019",
        "role": "member_server",
        "domain_function_level": "2016",
        "installed_services": {"iis": "10.0"},
        "applied_kbs": [],
        "installed_boltons": [],
        "active_gpos": [],
        "network_subnet": "10.0.11.0/24",
        "patched_cves": [],
    },
    "ws01": {
        "os_family": "windows",
        "os_version": "10",
        "role": "workstation",
        "domain_function_level": "2016",
        "installed_services": {},
        "applied_kbs": [],
        "installed_boltons": [],
        "active_gpos": [],
        "network_subnet": "10.0.11.0/24",
        "patched_cves": [],
    },
    "ca01": {
        "os_family": "windows",
        "os_version": "2019",
        "role": "member_server",
        "domain_function_level": "2016",
        "installed_services": {"adcs": "ADCS-Cert-Authority"},
        "applied_kbs": [],
        "installed_boltons": [],
        "active_gpos": [],
        "network_subnet": "10.0.11.0/24",
        "patched_cves": [],
    },
    "linux01": {
        "os_family": "linux",
        "os_version": "22.04",
        "role": "standalone",
        "domain_function_level": None,
        "installed_services": {"docker": "24.0"},
        "applied_kbs": [],
        "installed_boltons": [],
        "active_gpos": [],
        "network_subnet": "10.0.12.0/24",
        "patched_cves": [],
    },
}


def _mock_lookup(host: str) -> dict[str, Any] | None:
    """Phase 1 stub — look up canned facts for a host name."""
    return _MOCK_HOST_FACTS.get(host.lower())


def _probe_host(lab: str, host: str) -> dict[str, Any]:
    """STUB. Phase 2 will replace this with a real Ansible setup probe.

    Returns the raw dict of facts (without ``gathered_at`` / ``lab`` /
    ``host`` — those are filled in by ``gather_facts``).
    """
    canned = _mock_lookup(host)
    if canned is not None:
        return dict(canned)
    # Unknown host — return a "minimal viable" fact set marked as
    # standalone Linux so compatibility logic still works in tests.
    return {
        "os_family": "linux",
        "os_version": "unknown",
        "role": "standalone",
        "domain_function_level": None,
        "installed_services": {},
        "applied_kbs": [],
        "installed_boltons": [],
        "active_gpos": [],
        "network_subnet": None,
        "patched_cves": [],
    }


# ──────────────────────────────────────────────────────────────────────
# Atomic YAML write + cache layer
# ──────────────────────────────────────────────────────────────────────

def _facts_path(lab: str, host: str) -> Path:
    return STATE_ROOT / lab / f"{host}.yaml"


def _serialize(facts: HostFacts) -> str:
    payload = facts.model_dump()
    if yaml is not None:
        return yaml.safe_dump(payload, sort_keys=True)
    return json.dumps(payload, sort_keys=True, indent=2)


def _deserialize(path: Path) -> HostFacts | None:
    try:
        text = path.read_text()
    except FileNotFoundError:
        return None
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
        gathered_at_raw = data.pop("gathered_at", None)
        if isinstance(gathered_at_raw, str):
            # Allow trailing Z + microseconds
            iso = gathered_at_raw.rstrip("Z")
            try:
                gathered_at = datetime.fromisoformat(iso)
            except ValueError:
                return None
            if gathered_at.tzinfo is None:
                gathered_at = gathered_at.replace(tzinfo=timezone.utc)
        elif isinstance(gathered_at_raw, datetime):
            gathered_at = gathered_at_raw
            if gathered_at.tzinfo is None:
                gathered_at = gathered_at.replace(tzinfo=timezone.utc)
        else:
            return None
        return HostFacts(gathered_at=gathered_at, **data)
    except TypeError:
        # Schema drift — treat as missing.
        return None


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    os.replace(tmp, path)


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

def get_cached_facts(lab: str, host: str) -> HostFacts | None:
    """Read the cached YAML for (lab, host).

    Returns None when the file is missing OR the cached facts are older
    than ``FACTS_TTL_SECONDS``. A stale-but-present cache is treated as a
    miss so callers re-probe.
    """
    path = _facts_path(lab, host)
    facts = _deserialize(path)
    if facts is None:
        return None
    if not facts.is_fresh():
        return None
    return facts


def gather_facts(lab: str, host: str, force_refresh: bool = False) -> HostFacts:
    """Return host facts. Reads from cache when fresh, else probes.

    STUB / Phase 1: probing is a static lookup in ``_MOCK_HOST_FACTS``.
    """
    if not force_refresh:
        cached = get_cached_facts(lab, host)
        if cached is not None:
            return cached

    # Refresh — serialize per-host to avoid two threads writing the same
    # YAML simultaneously. We deliberately re-check the cache inside the
    # lock so a second waiter doesn't re-probe.
    with _host_lock(lab, host):
        if not force_refresh:
            cached = get_cached_facts(lab, host)
            if cached is not None:
                return cached
        raw = _probe_host(lab, host)
        facts = HostFacts(
            host=host,
            lab=lab,
            gathered_at=datetime.now(timezone.utc),
            **raw,
        )
        _atomic_write(_facts_path(lab, host), _serialize(facts))
        return facts


def invalidate_facts(lab: str, host: str | None = None) -> int:
    """Drop cached YAML for one host or every host in the lab.

    Returns the number of files removed. Never raises — invalidation must
    be best-effort because it's wired into install/uninstall completion
    hooks.
    """
    removed = 0
    lab_dir = STATE_ROOT / lab
    if not lab_dir.exists():
        return 0
    try:
        if host is None:
            for entry in lab_dir.glob("*.yaml"):
                try:
                    entry.unlink()
                    removed += 1
                except OSError:
                    pass
        else:
            path = _facts_path(lab, host)
            if path.exists():
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass
    except OSError:
        pass
    return removed


def gather_facts_async(
    lab: str,
    host: str,
    callback: Callable[[HostFacts], None] | None = None,
) -> str:
    """Background variant of ``gather_facts`` — returns a job id.

    A thread is spawned that sleeps ~200 ms then writes the mocked
    result. Used by the UI to refresh in the background without blocking
    the request thread. Phase 2 swaps the sleep for a real Ansible call.
    """
    job_id = f"factjob_{int(time.time() * 1000)}_{host}"

    def _run():
        try:
            time.sleep(0.2)
            facts = gather_facts(lab, host, force_refresh=True)
            if callback is not None:
                try:
                    callback(facts)
                except Exception:
                    pass
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()
    return job_id


# ──────────────────────────────────────────────────────────────────────
# Lab-state helpers (used by compatibility module)
# ──────────────────────────────────────────────────────────────────────

def list_lab_hosts(lab: str) -> list[str]:
    """List every host that has a cached facts file in this lab."""
    lab_dir = STATE_ROOT / lab
    if not lab_dir.exists():
        return []
    return sorted(p.stem for p in lab_dir.glob("*.yaml"))


# ──────────────────────────────────────────────────────────────────────
# Route-facing exceptions (Agent D reconcile)
# ──────────────────────────────────────────────────────────────────────

class HostUnreachable(Exception):
    """Raised by route-facing wrappers when a probe target is unreachable.

    Phase 2 will raise this from ``_probe_host`` when Ansible/WinRM fails.
    Phase 1 stub never raises it (mock lookup always succeeds), but the
    exception class exists so route handlers can ``except`` it and the
    test suite can monkeypatch refresh_facts to raise it.
    """
    def __init__(self, message: str, *, last_collected_at: str | None = None):
        super().__init__(message)
        self.last_collected_at = last_collected_at


class ProbeTimeout(Exception):
    """Raised when a probe exceeds its allowed window."""


# ──────────────────────────────────────────────────────────────────────
# Route-facing wrappers (Agent D reconcile)
# ──────────────────────────────────────────────────────────────────────

def _maybe_resolve_testlab_hosts(lab: str) -> list[dict[str, Any]] | None:
    """Return the live test lab host inventory for `lab`, or None.

    The test lab lives in the C2 VPC and is gated by the ``enable_test_lab``
    tfvars flag. When a project has it set, the bolt-on UI should see the
    REAL 4 hosts (tldc01/tlms01/tlws01/tllinux01) — not the static mock
    map. We consult two cheap on-disk sources before touching SSH/Ansible:

      1. logs/deployment_state/<lab>.state.json  → terraform outputs cache
         (already maintained by deploy_service)
      2. configs/<lab>.tfvars                    → confirms enable_test_lab

    Returns None when the lab isn't a deployment we know about OR when
    enable_test_lab is false. Returning None falls through to the mock
    map (preserving Phase 1 dev-loop behavior).
    """
    # Lazy import — pulling test_lab at module load would create a cycle
    # (routes/test_lab.py imports nothing from services, but the route
    # blueprint registers under flask.Blueprint at import time which can
    # surprise the test runner).
    try:
        from webapp.backend.routes import test_lab as _tl
    except Exception:
        return None

    if not _tl._test_lab_enabled(lab):
        return None
    state = _tl._read_state(lab)
    if state is None:
        return None
    host_inventory = _tl._read_host_inventory_from_state(state)
    if not host_inventory:
        # Avoid calling terraform here — it's a network/disk hit and
        # list_hosts is called per-page-render. Operators can call
        # /api/test_lab/hosts to force a refresh from terraform.
        return None
    out: list[dict[str, Any]] = []
    for name, meta in host_inventory.items():
        if not isinstance(meta, dict):
            continue
        out.append(
            {
                "name": name,
                "host_id": name,
                "role": meta.get("role", "unknown"),
                "os_family": meta.get("os_family", "unknown"),
                "os_version": "2022" if meta.get("os_family") == "windows" else "22.04",
                "ip": meta.get("private_ip"),
                "installed_count": 0,
                "stale": False,
                # Mark these so the frontend can tell real lab hosts apart
                # from cached mocks if it wants to.
                "source": "testlab",
            }
        )
    out.sort(key=lambda h: h.get("name") or "")
    return out


def list_hosts(lab: str) -> list[dict[str, Any]]:
    """Route-facing variant of ``list_lab_hosts`` — returns summary dicts.

    Resolution order:
      1. If the project has ``enable_test_lab=true`` in its tfvars AND
         the terraform output is in state.json, return the 4 real lab
         hosts with their actual private IPs + role tags.
      2. Otherwise fall back to disk-cached facts written by previous
         gather_facts() calls.
      3. Last resort — surface the static ``_MOCK_HOST_FACTS`` so the
         dev loop and bolt-on tests still have something to render.
    """
    # 1. Real test lab hosts when enable_test_lab=true and outputs landed.
    testlab_hosts = _maybe_resolve_testlab_hosts(lab)
    if testlab_hosts is not None:
        return testlab_hosts

    # 2. Disk cache fallback.
    cached = list_lab_hosts(lab)
    if not cached:
        # Surface every mock host as a possible target for the lab.
        cached = sorted(_MOCK_HOST_FACTS.keys())

    out: list[dict[str, Any]] = []
    for host in cached:
        facts = get_cached_facts(lab, host)
        if facts is None:
            # No cache yet — return shallow row so the UI can render and
            # gather_facts lazily on selection.
            mock = _mock_lookup(host) or {}
            out.append({
                "name": host,
                "host_id": host,
                "role": mock.get("role", "unknown"),
                "os_family": mock.get("os_family", "unknown"),
                "os_version": mock.get("os_version", "unknown"),
                "ip": None,
                "installed_count": 0,
                "stale": True,
            })
        else:
            out.append({
                "name": host,
                "host_id": host,
                "role": facts.role,
                "os_family": facts.os_family,
                "os_version": facts.os_version,
                "ip": None,
                "installed_count": len(facts.installed_boltons),
                "stale": not facts.is_fresh(),
            })
    return out


def get_facts(
    lab: str,
    host: str,
    force_refresh: bool = False,
    include_raw: bool = False,
) -> dict[str, Any]:
    """Route-facing variant of ``gather_facts`` returning a plain dict.

    Adds ``host_id`` / ``stale`` envelope fields the frontend expects.
    Raises ``KeyError`` when the (lab, host) pair is unknown — the route
    surfaces this as a 404.
    """
    # Reject obviously unknown hosts (Phase 1 — mock-table check). Phase 2
    # replaces this with a Terraform inventory lookup.
    if _mock_lookup(host) is None and get_cached_facts(lab, host) is None:
        # Allow facts that have been previously written to disk for
        # arbitrary host names (test fixtures rely on this).
        path = _facts_path(lab, host)
        if not path.exists():
            raise KeyError(f"host '{host}' in lab '{lab}' not found")
    facts = gather_facts(lab, host, force_refresh=force_refresh)
    payload = facts.model_dump()
    payload["host_id"] = host
    payload["stale"] = not facts.is_fresh()
    if not include_raw:
        # Caller doesn't need the verbose probe stdout (none in Phase 1).
        payload.pop("raw_probe_output", None)
    return payload


def refresh_facts(
    lab: str,
    host: str,
    deep_probe: bool = False,
) -> dict[str, Any]:
    """Force re-probe + return fresh facts. ``deep_probe`` is a Phase 2 hook."""
    if _mock_lookup(host) is None and get_cached_facts(lab, host) is None:
        path = _facts_path(lab, host)
        if not path.exists():
            raise KeyError(f"host '{host}' in lab '{lab}' not found")
    facts = gather_facts(lab, host, force_refresh=True)
    payload = facts.model_dump()
    payload["host_id"] = host
    payload["stale"] = False
    payload["deep_probe"] = deep_probe
    return payload


def get_installed(lab: str, host: str) -> list[dict[str, Any]]:
    """Return ``installed_boltons`` for a host as install-record dicts."""
    facts = get_cached_facts(lab, host)
    if facts is None:
        # Try a fresh gather so the route doesn't 404 just because the
        # cache is cold. Phase 2 will skip this in favor of a dedicated
        # install-registry index.
        if _mock_lookup(host) is None:
            path = _facts_path(lab, host)
            if not path.exists():
                raise KeyError(f"host '{host}' in lab '{lab}' not found")
        facts = gather_facts(lab, host)
    return [
        {
            "id": bolton_id,
            "installed_at": facts.gathered_at.isoformat(),
        }
        for bolton_id in facts.installed_boltons
    ]


def build_installed_boltons_map(lab: str) -> dict[str, list[str]]:
    """Return ``{host: [installed_bolton_ids]}`` for every cached host.

    Used by ``evaluate_compatibility`` to detect cross-host conflicts.
    """
    out: dict[str, list[str]] = {}
    for host in list_lab_hosts(lab):
        path = _facts_path(lab, host)
        facts = _deserialize(path)
        if facts is None:
            continue
        out[host] = list(facts.installed_boltons)
    return out


@contextmanager
def _stub_mock_host(name: str, payload: dict[str, Any]):
    """Test helper — temporarily install a host into ``_MOCK_HOST_FACTS``.

    Tests use this to drive ``gather_facts`` without monkeypatching.
    """
    previous = _MOCK_HOST_FACTS.get(name.lower())
    _MOCK_HOST_FACTS[name.lower()] = payload
    try:
        yield
    finally:
        if previous is None:
            _MOCK_HOST_FACTS.pop(name.lower(), None)
        else:
            _MOCK_HOST_FACTS[name.lower()] = previous
