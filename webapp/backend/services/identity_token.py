"""
Operator Identity Token (HMAC)
==============================
Short-lived, HMAC-signed tokens that carry a VERIFIED operator id. A token is
only ever minted by the server after it has authenticated the operator's real
identity via SO_PEERCRED on a local unix socket (see peercred_identity.py) — so
the token is cryptographically bound to the SSH-authenticated Linux user, and
tamper-evident. The token becomes the `dashboard_operator` cookie value; every
request re-verifies it. This replaces the old self-asserted, unsigned cookie.

Token format (all printable, cookie-safe):
    <op_id>.<exp_unix>.<base64url(hmac_sha256(secret, "<op_id>.<exp_unix>"))>

The server secret is a 32-byte random value persisted (0600) under the dashboard
state dir. It is generated once on first use; rotating it invalidates all tokens
(operators simply re-login).
"""

import base64
import hashlib
import hmac
import os
import re
import secrets
import threading
import time

# Operator ids are Linux usernames; constrain to prevent delimiter confusion or
# odd values ever entering a token (defense-in-depth — verify() is safe anyway).
_OP_ID_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")

from webapp.backend.services.operator_service import _resolve_dashboard_home

# Default token lifetime: a working day. Operators re-login next session.
TTL_DEFAULT = 12 * 3600

_SECRET_CACHE = None
_SECRET_LOCK = threading.Lock()


def _secret_path():
    return _resolve_dashboard_home() / ".operator_secret"


def _secret() -> bytes:
    """Load (or generate, 0600) the server HMAC secret. Cached per process."""
    global _SECRET_CACHE
    with _SECRET_LOCK:
        if _SECRET_CACHE is not None:
            return _SECRET_CACHE
        path = _secret_path()
        try:
            if path.exists():
                data = path.read_bytes()
                if len(data) >= 32:
                    _SECRET_CACHE = data
                    return _SECRET_CACHE
            # Generate a fresh 32-byte secret, written atomically with 0600.
            secret = os.urandom(32)
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(fd, secret)
            finally:
                os.close(fd)
            # Best-effort tighten in case of a permissive umask on pre-existing file.
            try:
                os.chmod(str(path), 0o600)
            except OSError:
                pass
            _SECRET_CACHE = secret
            return _SECRET_CACHE
        except Exception:
            # Last-resort ephemeral secret (process-local). Tokens still work
            # within this process; a restart invalidates them (operators re-login).
            if _SECRET_CACHE is None:
                _SECRET_CACHE = os.urandom(32)
            return _SECRET_CACHE


def _sign(payload: str) -> str:
    digest = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def mint(op_id: str, ttl: int = TTL_DEFAULT, *, now: int = None) -> str:
    """Mint a signed token for an already-authenticated operator id.

    `now` is injectable for tests. op_id must not contain '.' (operator ids are
    Linux usernames: [a-z0-9_-]); callers upstream validate this."""
    if not op_id or not _OP_ID_RE.match(op_id):
        raise ValueError(f"invalid operator id for token: {op_id!r}")
    if now is None:
        now = int(time.time())
    exp = now + int(ttl)
    payload = f"{op_id}.{exp}"
    return f"{payload}.{_sign(payload)}"


def verify(token: str, *, now: int = None):
    """Return the op_id if the token is well-formed, untampered and unexpired;
    otherwise None. Constant-time signature comparison."""
    if not token or not isinstance(token, str):
        return None
    if now is None:
        now = int(time.time())
    try:
        op_id, exp_s, sig = token.rsplit(".", 2)
        if not op_id or not exp_s or not sig:
            return None
        exp = int(exp_s)
        payload = f"{op_id}.{exp_s}"
        expected = _sign(payload)
        # constant-time compare on the base64 strings
        if not hmac.compare_digest(expected, sig):
            return None
        if exp < now:
            return None
        return op_id
    except Exception:
        return None


# ── One-time login handoff codes ─────────────────────────────────────────────
# The 12h bearer token must NOT travel in a URL (browser history / access logs /
# SSH scrollback). Instead the SO_PEERCRED socket hands the operator a single-use,
# short-TTL CODE; /login redeems it exactly once for the real cookie token. A
# leaked code is near-worthless: it dies on first redemption or after HANDOFF_TTL.
HANDOFF_TTL = 300  # seconds — generous enough to forward a port and open a tab
_HANDOFF = {}      # code -> {"op": op_id, "exp": int, "used": bool}
_HANDOFF_LOCK = threading.Lock()


def issue_handoff(op_id: str, *, now: int = None, ttl: int = HANDOFF_TTL) -> str:
    """Issue a single-use handoff code for an already-authenticated operator id.
    The CODE (not the token) is what travels in the /login URL."""
    if not op_id or not _OP_ID_RE.match(op_id):
        raise ValueError(f"invalid operator id for handoff: {op_id!r}")
    if now is None:
        now = int(time.time())
    code = secrets.token_urlsafe(32)
    with _HANDOFF_LOCK:
        # opportunistic prune of expired codes while we hold the lock
        for c in [c for c, v in _HANDOFF.items() if v["exp"] < now]:
            _HANDOFF.pop(c, None)
        _HANDOFF[code] = {"op": op_id, "exp": now + int(ttl), "used": False}
    return code


def redeem_handoff(code: str, *, now: int = None):
    """Redeem a handoff code EXACTLY ONCE → op_id, else None (unknown / reused /
    expired). The code is consumed on the first valid redemption."""
    if not code or not isinstance(code, str):
        return None
    if now is None:
        now = int(time.time())
    with _HANDOFF_LOCK:
        rec = _HANDOFF.get(code)
        if not rec:
            return None
        if rec["used"] or rec["exp"] < now:
            _HANDOFF.pop(code, None)
            return None
        rec["used"] = True
        return rec["op"]
