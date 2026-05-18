"""
Terminal WebSocket Routes
Provides server shell and remote SSH terminal sessions over WebSocket.
"""

import os
import sys
import pty
import json
import signal
import select
import socket
import struct
import fcntl
import termios
import subprocess
import threading
from pathlib import Path

from flask import Blueprint, request
from flask_sock import Sock

from webapp.backend.services import audit_service, operator_service


def _audit_actor():
    """Resolve operator from the WebSocket upgrade request cookies.

    flask.g may not be reliably populated for WebSocket routes because
    before_request hooks behave inconsistently across sock implementations,
    so we re-resolve from the request cookie directly.
    """
    try:
        op = operator_service.resolve_from_request(request)
        return op.get("id") if op else "unknown"
    except Exception:
        return "unknown"


bp = Blueprint('terminal', __name__)
sock = Sock()


def _is_host_reachable(host, port=22, timeout=2):
    """Check if a host is directly reachable (e.g., via VPC peering on the server)."""
    try:
        conn = socket.create_connection((host, port), timeout=timeout)
        conn.close()
        return True
    except (ConnectionRefusedError, socket.timeout, OSError):
        return False

# Track active sessions for cleanup
_active_sessions = {}
_MAX_SESSIONS = 10


def _set_pty_size(fd, rows, cols):
    """Set PTY window size."""
    try:
        winsize = struct.pack('HHHH', rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
    except Exception:
        pass


def _pty_session(ws, cmd, env=None):
    """
    Run a command in a PTY and pipe it bidirectionally over WebSocket.
    Used for both local shell and SSH sessions.
    """
    master_fd, slave_fd = pty.openpty()

    # Merge environment
    proc_env = os.environ.copy()
    proc_env['TERM'] = 'xterm-256color'
    proc_env['COLORTERM'] = 'truecolor'
    if env:
        proc_env.update(env)

    proc = subprocess.Popen(
        cmd,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        preexec_fn=os.setsid,
        env=proc_env,
        close_fds=True,
    )
    os.close(slave_fd)

    session_id = id(ws)
    _active_sessions[session_id] = {'proc': proc, 'master_fd': master_fd}

    # Set default PTY size
    _set_pty_size(master_fd, 24, 80)

    # Thread: read from PTY → send to WebSocket
    ws_open = True

    def pty_reader():
        nonlocal ws_open
        try:
            while proc.poll() is None and ws_open:
                r, _, _ = select.select([master_fd], [], [], 0.1)
                if master_fd in r:
                    try:
                        data = os.read(master_fd, 16384)
                        if data:
                            ws.send(data)
                        else:
                            break
                    except OSError:
                        break
        except Exception:
            pass

    reader_thread = threading.Thread(target=pty_reader, daemon=True)
    reader_thread.start()

    # Main thread: read from WebSocket → write to PTY
    try:
        while proc.poll() is None:
            try:
                msg = ws.receive(timeout=0.5)
                if msg is None:
                    continue
                if isinstance(msg, str):
                    # Check for control messages (JSON)
                    if msg.startswith('{'):
                        try:
                            ctrl = json.loads(msg)
                            if ctrl.get('type') == 'close':
                                break  # Frontend requested close — exit loop, hit finally cleanup
                            if ctrl.get('type') == 'resize':
                                _set_pty_size(master_fd, ctrl.get('rows', 24), ctrl.get('cols', 80))
                                # Send SIGWINCH to the process group
                                os.killpg(os.getpgid(proc.pid), signal.SIGWINCH)
                                continue
                        except (json.JSONDecodeError, ProcessLookupError):
                            pass
                    os.write(master_fd, msg.encode('utf-8'))
                elif isinstance(msg, bytes):
                    os.write(master_fd, msg)
            except Exception:
                break
    except Exception:
        pass
    finally:
        ws_open = False
        # Clean up
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
        try:
            os.close(master_fd)
        except OSError:
            pass
        _active_sessions.pop(session_id, None)
        reader_thread.join(timeout=2)


@sock.route('/api/terminal/local')
def terminal_local(ws):
    """Server shell session — spawns bash on the dashboard server."""
    if len(_active_sessions) >= _MAX_SESSIONS:
        ws.send('\r\n\x1b[31mSession limit reached (max 5). Close a tab first.\x1b[0m\r\n')
        ws.close()
        return

    # Always use /bin/bash — the service user (dashboard) has /usr/sbin/nologin as $SHELL
    shell = '/bin/bash'
    home = os.environ.get('HOME', '/tmp')

    # Wait for initial resize message from client
    try:
        init_msg = ws.receive(timeout=5)
        if init_msg:
            try:
                ctrl = json.loads(init_msg)
                if ctrl.get('type') == 'init':
                    pass  # Initial handshake
            except (json.JSONDecodeError, TypeError):
                pass
    except Exception:
        pass

    audit_service.write(_audit_actor(), "terminal.start", details={"kind": "local"})

    _pty_session(ws, [shell, '-i'], env={
        'HOME': home,
    })


@sock.route('/api/terminal/ssh')
def terminal_ssh(ws):
    """SSH session to a remote instance, optionally via bastion ProxyJump."""
    if len(_active_sessions) >= _MAX_SESSIONS:
        ws.send('\r\n\x1b[31mSession limit reached (max 5). Close a tab first.\x1b[0m\r\n')
        ws.close()
        return

    # First message contains connection params
    try:
        init_msg = ws.receive(timeout=10)
        if not init_msg:
            ws.send('\r\n\x1b[31mNo connection parameters received.\x1b[0m\r\n')
            return
        params = json.loads(init_msg)
    except Exception as e:
        ws.send(f'\r\n\x1b[31mInvalid connection params: {e}\x1b[0m\r\n')
        return

    host = params.get('host')
    user = params.get('user', 'ubuntu')
    bastion = params.get('bastion')
    key_path = params.get('key_path', '')

    if not host:
        ws.send('\r\n\x1b[31mNo target host specified.\x1b[0m\r\n')
        return

    # Resolve SSH key path — server shared key only
    if not key_path:
        for candidate in [
            '/opt/redteam/.ssh/id_ed25519',
            '/opt/redteam/.ssh/id_rsa',
        ]:
            if os.path.exists(candidate):
                key_path = candidate
                break

    # Build SSH command
    cmd = ['ssh',
           '-o', 'StrictHostKeyChecking=accept-new',
           '-o', 'UserKnownHostsFile=/opt/redteam/.ssh/known_hosts',
           '-o', 'ServerAliveInterval=30',
           '-o', 'LogLevel=ERROR']

    using_jump = False
    if bastion and not _is_host_reachable(host):
        cmd += ['-J', f'ubuntu@{bastion}']
        using_jump = True
    elif bastion and _is_host_reachable(host):
        ws.send('\x1b[36mDirect route available — skipping bastion jump\x1b[0m\r\n')

    if key_path:
        cmd += ['-i', key_path]

    cmd.append(f'{user}@{host}')

    ws.send(f'\x1b[36mConnecting to {user}@{host}' +
            (f' via {bastion}' if using_jump else '') +
            '...\x1b[0m\r\n')

    audit_service.write(
        _audit_actor(),
        "terminal.start",
        target=f"{user}@{host}",
        details={"kind": "ssh", "via_bastion": using_jump},
    )

    _pty_session(ws, cmd)


def init_sock(app):
    """Initialize flask-sock with the Flask app."""
    sock.init_app(app)
