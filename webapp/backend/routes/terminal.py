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
    # Demo mode marker — frontend tags every demo instance button so we
    # can short-circuit the real SSH path even though the host/IP looks
    # plausible (10.99.50.x test_lab range etc).
    is_demo = bool(params.get('is_demo')) or str(params.get('project', '')).strip().lower() == 'demo'

    if not host:
        ws.send('\r\n\x1b[31mNo target host specified.\x1b[0m\r\n')
        return

    # ── Demo bypass ──────────────────────────────────────────────────
    # Don't shell out to ssh — spawn a LOCAL bash with a fake login
    # banner so the operator gets a working PTY labelled as the demo
    # target. The session is fully local; nothing leaves the dashboard.
    if is_demo:
        from webapp.backend.services import demo_data_service
        demo_data_service.seed_demo_audit_entries()
        audit_service.write(
            _audit_actor(),
            "terminal.start",
            target=f"{user}@{host}",
            details={"kind": "ssh", "is_demo": True, "demo_host": host},
        )
        # Build a fake-MOTD bash shim. We use bash --rcfile to inject
        # a custom prompt + login banner without persisting anything.
        # The PS1 shows {user}@{host_label} so it visually matches the
        # real remote shell the operator would see.
        from datetime import datetime as _dt
        login_ts = _dt.now().strftime("%a %b %d %H:%M:%S %Y")
        host_label = (host.split('.')[0] if host else 'demo')[:32]
        # Single-quote the dynamic bits so they survive the rcfile heredoc.
        rcfile_body = (
            "if [ -f /etc/bash.bashrc ]; then . /etc/bash.bashrc; fi\n"
            "if [ -f \"$HOME/.bashrc\" ]; then . \"$HOME/.bashrc\"; fi\n"
            "clear 2>/dev/null || true\n"
            "printf 'Welcome to Ubuntu 22.04 LTS (GNU/Linux 5.15.0-aws x86_64) [DEMO]\\n'\n"
            "printf '\\n'\n"
            "printf '  * Documentation:  https://help.ubuntu.com\\n'\n"
            "printf '  * Management:     https://landscape.canonical.com\\n'\n"
            "printf '  * Support:        https://ubuntu.com/advantage\\n'\n"
            "printf '\\n'\n"
            f"printf 'Last login: {login_ts} from 203.0.113.10\\n'\n"
            "printf '\\n'\n"
            "printf '\\033[33m[demo] this is a LOCAL shell labelled as the demo target.\\033[0m\\n'\n"
            "printf '\\033[33m[demo] no remote SSH is performed — operations are synthetic.\\033[0m\\n'\n"
            "printf '\\n'\n"
            f"export PS1='\\[\\e[32m\\]{user}@{host_label}\\[\\e[0m\\]:\\[\\e[34m\\]\\w\\[\\e[0m\\]$ '\n"
            "export DEMO_SSH_TARGET='" + f"{user}@{host}" + "'\n"
        )
        import tempfile
        rc = tempfile.NamedTemporaryFile(
            mode='w', suffix='.demoshrc', delete=False, prefix='demo-ssh-'
        )
        rc.write(rcfile_body)
        rc.flush()
        rc.close()
        ws.send(f'\x1b[36m[demo] Connecting to {user}@{host} (local PTY, synthetic)...\x1b[0m\r\n')
        _pty_session(ws, ['/bin/bash', '--rcfile', rc.name, '-i'], env={
            'HOME': os.environ.get('HOME', '/tmp'),
            'DEMO_MODE': '1',
        })
        try:
            os.unlink(rc.name)
        except OSError:
            pass
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
