"""
Operator Identity
Local mode: returns laptop username via os.getlogin()
Server mode: traces the SSH tunnel back to the Linux user who owns it
"""

import os
import re
import subprocess
from flask import Blueprint, jsonify, request

bp = Blueprint('identity', __name__)


def get_operator():
    """Detect the current operator.

    Local mode: os.getlogin() returns the macOS/Linux username.
    Server mode: traces the TCP connection from Flask back through the
    SSH tunnel to determine which Linux user owns the forwarding sshd process.
    """
    # Try os.getlogin() first — works in local mode
    try:
        name = os.getlogin()
        if name and name not in ('root', 'dashboard'):
            return name
    except OSError:
        pass

    # Server mode: trace the request's source port to its SSH tunnel owner
    try:
        remote_port = request.environ.get('REMOTE_PORT')
        if remote_port:
            result = subprocess.run(
                ['ss', '-tnp', f'sport = :{remote_port}'],
                capture_output=True, text=True, timeout=2
            )
            match = re.search(r'pid=(\d+)', result.stdout)
            if match:
                pid = match.group(1)
                user = subprocess.run(
                    ['ps', '-o', 'user=', '-p', pid],
                    capture_output=True, text=True, timeout=2
                ).stdout.strip()
                if user and user not in ('root', 'dashboard', ''):
                    return user
    except Exception:
        pass

    return os.environ.get('USER', 'unknown')


@bp.route('/api/whoami', methods=['GET'])
def whoami():
    """Return the current operator identity."""
    return jsonify({"operator": get_operator()})
