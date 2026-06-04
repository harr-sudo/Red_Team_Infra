"""Dashboard settings store + EIP resolver.

Persists operator-set dashboard settings (currently just the Dashboard
Server EIP override) at ~/.dashboard/dashboard_settings.json, mirroring
the idiom of operator_service.py — including honoring DASHBOARD_STATE_DIR
for test isolation (see task #54 / tests/README.md).

The "Dashboard Server EIP" is the public IP of the AWS-hosted Dashboard
Server, which is the sole SSH/RDP jump host. The frontend uses the
*effective* value to build connect commands (e.g.
``ssh -L 50050:<c2-ip>:50050 ubuntu@<eip>``) and exposes the override in
Settings so an operator can pin it when auto-detection is unavailable.

Resolution precedence for the detected value:
  1. DASHBOARD_PUBLIC_IP env var (set by setup-dashboard.sh on the server)
  2. terraform output ``dashboard_public_ip`` (default workspace)

The persisted *override* always wins over the detected value when set.
"""
import json
import os
import re
import threading
from pathlib import Path


def _resolve_dashboard_home() -> Path:
    """Honor DASHBOARD_STATE_DIR for test isolation; default to ~/.dashboard.

    Mirrors operator_service._resolve_dashboard_home so test runs that set
    DASHBOARD_STATE_DIR (e.g. /tmp/playwright-dashboard-state) never write
    to the live store at ~/.dashboard/dashboard_settings.json.
    """
    env = os.environ.get("DASHBOARD_STATE_DIR")
    if env:
        return Path(env)
    return Path.home() / ".dashboard"


def _store_path() -> Path:
    """Resolve the store path lazily so DASHBOARD_STATE_DIR set after import
    (as test harnesses do) is still honored."""
    return _resolve_dashboard_home() / "dashboard_settings.json"


# Repo root: services -> backend -> webapp -> <root>. Matches the idiom used
# by the route modules (Path(__file__).parent.parent.parent.parent).
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

_LOCK = threading.Lock()

DEFAULTS = {"dashboard_server_eip": ""}

# Empty string OR a dotted IPv4. Octet *range* (0-255) is not enforced — the
# regex matches the task contract; this is an operator-supplied hint, not a
# security boundary (trust is upstream: AWS IAM + SSH).
_IPV4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")

# The Dashboard Server EIP is a stable Elastic IP — once detected it does not
# change for the life of the deployment. Cache it module-globally so we don't
# shell out to terraform on every /api/settings request. ``None`` = not yet
# resolved; "" = resolved-but-empty (still cached, no repeat shell-out).
_detected_cache = None


def load() -> dict:
    """Return DEFAULTS merged with any persisted overrides on disk."""
    with _LOCK:
        data = dict(DEFAULTS)
        path = _store_path()
        if path.exists():
            try:
                stored = json.loads(path.read_text())
                if isinstance(stored, dict):
                    data.update({k: stored[k] for k in DEFAULTS if k in stored})
            except (json.JSONDecodeError, OSError):
                # Corrupt/unreadable store falls back to defaults rather than
                # taking down the settings endpoint.
                pass
        return data


def save(eip: str) -> dict:
    """Validate and persist the Dashboard Server EIP override.

    Args:
        eip: empty string (clears the override) or a dotted IPv4 string.

    Raises:
        ValueError: if ``eip`` is neither empty nor a dotted IPv4.

    Returns:
        The full settings dict as persisted.
    """
    if not isinstance(eip, str):
        raise ValueError("dashboard_server_eip must be a string")
    eip = eip.strip()
    if eip and not _IPV4_RE.match(eip):
        raise ValueError(f"Invalid IPv4 address: {eip!r}")
    with _LOCK:
        data = dict(DEFAULTS)
        data["dashboard_server_eip"] = eip
        path = _store_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))
        return data


def _detect_eip() -> str:
    """First non-empty of: DASHBOARD_PUBLIC_IP env, then terraform output.

    Never raises — terraform_service.output_raw returns "" on any failure
    (missing state, terraform not installed, etc.).
    """
    env_ip = os.environ.get("DASHBOARD_PUBLIC_IP", "")
    if env_ip:
        return env_ip
    try:
        from webapp.backend.services.terraform_service import get_terraform_service
        return get_terraform_service(_PROJECT_ROOT).output_raw("dashboard_public_ip")
    except Exception:
        # Defensive: output_raw itself shouldn't raise, but never let EIP
        # detection take down the settings endpoint.
        return ""


def resolve_eip() -> dict:
    """Resolve the Dashboard Server EIP from override + detected sources.

    Returns a dict:
        detected:  first non-empty of [DASHBOARD_PUBLIC_IP env, terraform out]
        override:  the persisted operator override (may be "")
        effective: override if set, else detected
        source:    "override" | "env" | "terraform" | "unset"
    """
    global _detected_cache
    # Re-check the env var each call (cheap, and lets a freshly-exported var be
    # picked up) while caching the comparatively expensive terraform shell-out.
    env_ip = os.environ.get("DASHBOARD_PUBLIC_IP", "")
    if _detected_cache is None:
        _detected_cache = _detect_eip()
    detected = env_ip or _detected_cache

    override = (load().get("dashboard_server_eip") or "").strip()
    effective = override or detected

    if override:
        source = "override"
    elif env_ip:
        source = "env"
    elif detected:
        source = "terraform"
    else:
        source = "unset"

    return {
        "detected": detected,
        "override": override,
        "effective": effective,
        "source": source,
    }
