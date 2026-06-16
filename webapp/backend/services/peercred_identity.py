"""
SO_PEERCRED identity minter
===========================
A tiny local unix-socket service that authenticates an operator by the KERNEL-
reported uid of the connecting process (SO_PEERCRED) — which is unforgeable. An
operator's SSH session (running as their key-authenticated Linux user) connects
to the socket; we map uid -> Linux username -> operator id and return a signed
identity token (identity_token.mint). That token becomes the dashboard cookie.

This is the trust anchor: the operator cannot lie about their uid to the kernel,
so the minted token is bound to the SSH key that authenticated them. No root and
no fragile ss/proc tracing required — the socket reads the peer's real uid.

Linux-only (SO_PEERCRED). The socket server simply does not start elsewhere; the
pure uid->token logic (`mint_for_uid`) is unit-testable on any OS.
"""

import logging
import os
import socket
import struct
import threading

from webapp.backend.services import operator_service
from webapp.backend.services import identity_token

log = logging.getLogger(__name__)

# Linux uid convention: regular login users start at 1000; anything below is a
# system account. Combined with an explicit denylist for the service/system users
# that share the box.
_MIN_OPERATOR_UID = 1000
_SYSTEM_DENY = {"root", "dashboard", "nobody", "daemon", "sshd", "sync", "bin", "sys"}

_DEFAULT_COLORS = ["#a31621", "#1b4965", "#2a7f62", "#8a5a00", "#5b3a8a", "#7a4a52"]


def uid_to_operator(uid):
    """Resolve a kernel-reported uid to a registered operator id, auto-registering
    a first-seen login user. Returns None for system/service accounts."""
    import pwd
    try:
        name = pwd.getpwuid(uid).pw_name
    except Exception:
        return None
    if not name or name in _SYSTEM_DENY:
        return None
    if uid < _MIN_OPERATOR_UID:
        return None
    # Normalize the Linux username to the canonical operator id ONCE, and use it
    # for both registration and the returned value, so the id we hand back is the
    # same one stored in the roster AND accepted by the token grammar — a username
    # like "Alice" or "dev.svc" can never auto-register one way then fail to mint.
    op_id = operator_service.canonical_id(name)
    if not op_id:
        return None
    # Register first-seen operators so the roster + colours exist. Never fatal.
    try:
        if not operator_service.get(op_id):
            n = len(operator_service.list_operators())
            operator_service.add(op_id, name.capitalize(),
                                 _DEFAULT_COLORS[n % len(_DEFAULT_COLORS)])
    except Exception:
        pass
    return op_id


def mint_for_uid(uid):
    """uid -> single-use login handoff CODE, or None if the uid isn't an operator.
    The code (not the 12h token) is what the operator carries to /login, so the
    bearer token never appears in a URL. Pure/testable: inject any uid on any OS."""
    op_id = uid_to_operator(uid)
    if not op_id:
        return None
    try:
        return identity_token.issue_handoff(op_id)
    except ValueError:
        return None  # username didn't match the operator-id grammar


def _peer_uid(conn):
    """Read the connecting process's real uid via SO_PEERCRED (Linux)."""
    creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                            struct.calcsize("3i"))
    _pid, uid, _gid = struct.unpack("3i", creds)
    return uid


def _handle(conn):
    try:
        uid = _peer_uid(conn)
        token = mint_for_uid(uid) or ""
        conn.sendall(token.encode("utf-8"))
    except Exception as e:
        log.warning("peercred mint failed: %s", e)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _serve(socket_path, group):
    try:
        if os.path.exists(socket_path):
            os.unlink(socket_path)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(socket_path)
        srv.listen(16)
        # Make the socket reachable by operator users (group `redteam`), not world.
        try:
            os.chmod(socket_path, 0o660)
            if group:
                import grp
                os.chown(socket_path, -1, grp.getgrnam(group).gr_gid)
        except Exception as e:
            log.warning("could not set socket perms/group: %s", e)
        log.info("peercred identity socket listening at %s", socket_path)
        while True:
            conn, _ = srv.accept()
            _handle(conn)
    except Exception as e:
        log.warning("peercred socket server stopped: %s", e)


def start(socket_path=None, group="redteam"):
    """Start the SO_PEERCRED socket server in a daemon thread (Linux only).
    Returns True if started. No-op (returns False) where SO_PEERCRED is absent
    (e.g. macOS dev) — there the cookie is set via the dev login path instead."""
    if not hasattr(socket, "SO_PEERCRED"):
        log.info("SO_PEERCRED unavailable — peercred minter not started (dev OS)")
        return False
    if socket_path is None:
        # RuntimeDirectory=redteam -> /run/redteam on the dashboard; fall back to
        # the dashboard state dir for non-systemd contexts.
        runtime = os.environ.get("RUNTIME_DIRECTORY") or "/run/redteam"
        try:
            os.makedirs(runtime, exist_ok=True)
            socket_path = os.path.join(runtime, "identity.sock")
        except Exception:
            from webapp.backend.services.operator_service import _resolve_dashboard_home
            socket_path = str(_resolve_dashboard_home() / "identity.sock")
    threading.Thread(target=_serve, args=(socket_path, group), daemon=True).start()
    return True
