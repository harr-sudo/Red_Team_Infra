"""Operator profile store + lookup + request resolution.

Profile data lives at ~/.dashboard/operators.json — a simple list of
{id, display, color, created}. Identity is AUTHENTICATED via the
`dashboard_operator` cookie, which carries an HMAC-signed token bound to the
operator's SSH-authenticated Linux user (see identity_token.py +
peercred_identity.py). resolve_from_request() verifies the signature and, in
production, trusts ONLY a valid signed token (a bare/self-asserted cookie
resolves to 'unknown'). Dev (no SO_PEERCRED socket) stays lenient for a single
local user.
"""
import json
import os
import pwd
import re
import threading
from datetime import datetime
from pathlib import Path


def _resolve_dashboard_home() -> Path:
    """Honor DASHBOARD_STATE_DIR for test isolation; default to ~/.dashboard.

    Set DASHBOARD_STATE_DIR (e.g. /tmp/playwright-dashboard-state) when
    starting Flask for Playwright / e2e runs so the live operator store
    at ~/.dashboard/operators.json is never written to. See task #54 and
    tests/browser/README.md.
    """
    env = os.environ.get("DASHBOARD_STATE_DIR")
    if env:
        return Path(env)
    return Path.home() / ".dashboard"


_STORE_PATH = _resolve_dashboard_home() / "operators.json"
_LOCK = threading.RLock()

DEFAULT_COLORS = ["#a31621", "#3b82f6", "#0d9488", "#7c3aed", "#ea580c", "#65a30d"]

# 6-hex-char color literal validator. The frontend swatch picker only emits
# values from DEFAULT_COLORS, but the PATCH endpoint accepts arbitrary input
# from any client so we validate strictly.
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# Canonical operator-id grammar, SHARED with identity_token (^[a-z_][a-z0-9_-]{0,31}$).
# A single normalizer used everywhere a Linux username becomes an operator id, so
# the auto-registered id, the stored id, and the id baked into a signed token are
# always identical. Without this, a perfectly valid Linux username (uppercase, a
# dot, or >32 chars) would register one way but fail the token grammar — minting
# an empty token and locking the operator out.
_CANON_STRIP_RE = re.compile(r"[^a-z0-9_-]+")


def canonical_id(name):
    """Map any Linux username (or user-supplied id) to a canonical operator id
    matching the identity-token grammar, or '' if nothing usable remains.
    Lowercases, replaces out-of-grammar runs with '-', ensures a valid leading
    char ([a-z_]), and caps length at 32. Idempotent."""
    s = (name or "").strip().lower()
    s = _CANON_STRIP_RE.sub("-", s).strip("-")
    if not s:
        return ""
    if not (s[0].isalpha() or s[0] == "_"):
        s = "op-" + s
    return s[:32]


def _ensure_store():
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _STORE_PATH.exists():
        # Seed with the SSH user as the default operator
        try:
            user = pwd.getpwuid(os.getuid()).pw_name
        except Exception:
            user = "operator"
        seed = {
            "operators": [{
                "id": user,
                "display": user.capitalize(),
                "color": DEFAULT_COLORS[0],
                "created": datetime.utcnow().isoformat() + "Z",
            }],
            "default": user,
        }
        _STORE_PATH.write_text(json.dumps(seed, indent=2))


def load():
    with _LOCK:
        _ensure_store()
        return json.loads(_STORE_PATH.read_text())


def save(data):
    with _LOCK:
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STORE_PATH.write_text(json.dumps(data, indent=2))


def list_operators():
    return load()["operators"]


def get(op_id):
    return next((o for o in list_operators() if o["id"] == op_id), None)


def add(op_id, display, color):
    """Add a new operator. Returns the created entry.

    The id is normalized via canonical_id() so it always matches the identity-
    token grammar — the same normalization the SO_PEERCRED minter applies, so an
    auto-registered operator and its token id never diverge."""
    op_id = canonical_id(op_id)
    if not op_id:
        raise ValueError("operator id must contain at least one [a-z0-9_-] character")
    with _LOCK:
        data = load()
        if any(o["id"] == op_id for o in data["operators"]):
            raise ValueError(f"operator '{op_id}' already exists")
        if len(data["operators"]) >= 32:
            raise ValueError("too many operators (max 32)")
        entry = {
            "id": op_id,
            "display": display or op_id.capitalize(),
            "color": color or DEFAULT_COLORS[len(data["operators"]) % len(DEFAULT_COLORS)],
            "created": datetime.utcnow().isoformat() + "Z",
        }
        data["operators"].append(entry)
        save(data)
        return entry


def update(op_id, *, display=None, color=None):
    """Rename and/or recolor an existing operator. Returns the updated entry.

    Only ``display`` and ``color`` are mutable — the ``id`` is the audit-log
    join key and must never change. Pass ``None`` for fields you don't want
    to touch; an empty/whitespace ``display`` is also treated as no-op
    (callers shouldn't blank out display names).

    Raises ValueError for unknown id or invalid color literal.
    """
    if color is not None:
        if not isinstance(color, str) or not _COLOR_RE.match(color):
            raise ValueError("color must be a 6-hex-char '#RRGGBB' literal")
    with _LOCK:
        data = load()
        entry = next((o for o in data["operators"] if o["id"] == op_id), None)
        if entry is None:
            raise ValueError(f"operator '{op_id}' not found")
        if display is not None:
            d = str(display).strip()
            if d:
                entry["display"] = d
        if color is not None:
            entry["color"] = color
        save(data)
        return entry


def remove(op_id, current_id=None):
    """Remove an operator.

    2026-05-22 — Added ``current_id`` guard to close a UX/backend mismatch:
    the dashboard UI disables the Delete button for the currently-active
    operator, but a direct ``DELETE /api/operators/<id>`` previously
    succeeded against the current operator, leaving the ``dashboard_operator``
    cookie pointing at a now-orphaned id (resolved via fallback to
    ``default``). Callers in the route layer pass ``g.operator['id']`` as
    ``current_id`` so the backend enforces what the UI claims.

    Raises ``ValueError`` for:
      - not_found     — no operator with that id
      - last_operator — would empty the registry
      - current_operator — would orphan the request's cookie
    """
    with _LOCK:
        data = load()
        if current_id is not None and op_id == current_id:
            raise ValueError(
                "cannot remove the currently-active operator — "
                "switch to another operator first"
            )
        before = len(data["operators"])
        data["operators"] = [o for o in data["operators"] if o["id"] != op_id]
        if len(data["operators"]) == before:
            raise ValueError(f"operator '{op_id}' not found")
        if len(data["operators"]) == 0:
            raise ValueError("cannot remove the last operator")
        if data.get("default") == op_id:
            data["default"] = data["operators"][0]["id"]
        save(data)


def get_default():
    data = load()
    default_id = data.get("default")
    if default_id:
        return default_id
    ops = data.get("operators") or []
    return ops[0]["id"] if ops else None


def get_last_active(op_id):
    """Return the ISO timestamp of the most recent audit-log action by
    ``op_id``, or None if the operator has never acted.

    Imported lazily to avoid a circular dependency: audit_service is a peer
    module that does not import operator_service, but the Flask app wires
    both into the same package and we'd rather not invert that.
    """
    from webapp.backend.services import audit_service
    rows = audit_service.read_recent(limit=500, op_filter=op_id)
    return rows[0]["ts"] if rows else None


def get_last_active_map():
    """Bulk variant — single audit-log scan returning a map of
    ``{op_id: {"last_active": iso_or_None, "action_count": int}}`` for every
    known operator. O(N audit entries) once, vs O(N operators * N entries)
    if callers loop over get_last_active().

    Unknown operators (entries in audit log whose id no longer exists in the
    operator store) are silently ignored — they don't get a slot in the map.
    """
    from webapp.backend.services import audit_service
    ids = {o["id"] for o in list_operators()}
    out = {oid: {"last_active": None, "action_count": 0} for oid in ids}
    # 500 is the same cap used by the activity feed; sufficient for typical
    # ops history and bounded so a runaway audit log doesn't tank this call.
    for entry in audit_service.read_recent(limit=500):
        op = entry.get("op")
        if op not in out:
            continue
        slot = out[op]
        slot["action_count"] += 1
        # read_recent is most-recent-first, so the first hit IS last_active.
        if slot["last_active"] is None:
            slot["last_active"] = entry.get("ts")
    return out


def _unknown():
    return {"id": "unknown", "display": "Unknown", "color": "#666666", "created": None}


def is_dev_mode():
    """Dev (laptop) vs prod (AWS Dashboard Server). In prod the dashboard runs on
    Linux where SO_PEERCRED is available and the socket minter authenticates
    operators by their SSH-bound uid, so we accept ONLY signed identity tokens.
    In dev there is no peercred socket, so we stay lenient (single local user)
    rather than locking the operator out. `DASHBOARD_DEV=1` forces dev."""
    if os.environ.get("DASHBOARD_DEV") == "1":
        return True
    try:
        import socket as _s
        return not hasattr(_s, "SO_PEERCRED")
    except Exception:
        # Fail SAFE, not open: if we can't tell, assume PRODUCTION (strict — accept
        # only signed tokens). Never grant dev leniency (bare-cookie acceptance) on
        # an error.
        return False


def resolve_from_request(request):
    """Resolve the operator from the `dashboard_operator` cookie.

    SECURE path (always): the cookie holds an HMAC-signed identity token minted
    by the SO_PEERCRED socket (bound to the operator's SSH-authenticated Linux
    user). We verify it and trust ONLY a valid signature.

    In dev (no peercred socket) we additionally accept a bare op-id cookie and
    fall back to the default local operator, so a laptop instance still works.
    In prod an unverifiable cookie yields 'unknown' — never a trusted identity
    from a self-asserted value. Returns a dict, never None."""
    # Lazy import avoids a circular import (identity_token imports this module).
    from webapp.backend.services import identity_token

    cookie = request.cookies.get("dashboard_operator")
    if cookie:
        op_id = identity_token.verify(cookie)
        if op_id:
            op = get(op_id)
            if op:
                return op
        # Dev-only leniency: accept a legacy/bare op-id cookie.
        if is_dev_mode():
            op = get(cookie)
            if op:
                return op

    if is_dev_mode():
        default_id = get_default()
        if default_id:
            op = get(default_id)
            if op:
                return op
    return _unknown()
