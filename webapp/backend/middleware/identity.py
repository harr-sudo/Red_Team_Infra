"""
Operator Identity
Traces the SSH tunnel back to the Linux user who owns it.
"""

import logging
import os
import re
import subprocess
from flask import Blueprint, jsonify, request

bp = Blueprint('identity', __name__)
log = logging.getLogger(__name__)


def get_operator():
    """Detect the current operator by tracing the SSH tunnel back to
    the Linux user who owns the forwarding sshd process."""
    # Trace the request's source port to its SSH tunnel owner.
    # Method 1: ss -tnp (may need root to see PIDs of other users' processes)
    # Method 2: scan /proc for sshd processes with port forwarding
    try:
        remote_port = request.environ.get('REMOTE_PORT')
        if remote_port:
            # Try ss first (works if dashboard user can see socket PIDs)
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

            # Fallback: find sshd processes and their owners
            # Each operator's SSH tunnel creates an sshd child process owned by their Linux user
            result = subprocess.run(
                ['ps', '-eo', 'user,pid,args'],
                capture_output=True, text=True, timeout=2
            )
            for line in result.stdout.splitlines():
                parts = line.split(None, 2)
                if len(parts) >= 3 and 'sshd' in parts[2] and parts[0] not in ('root', 'dashboard', 'USER', ''):
                    return parts[0]  # Return the first non-root sshd user
    except Exception:
        pass

    # Final fallback: check who has active SSH sessions via 'who'
    try:
        result = subprocess.run(['who'], capture_output=True, text=True, timeout=2)
        for line in result.stdout.splitlines():
            user = line.split()[0] if line.strip() else ''
            if user and user not in ('root', 'dashboard'):
                return user
    except Exception:
        pass

    fallback = os.environ.get('USER', 'unknown')
    log.warning("Could not trace SSH tunnel — falling back to $USER='%s'", fallback)
    return fallback


@bp.route('/api/whoami', methods=['GET'])
def whoami():
    """Return the current operator identity."""
    return jsonify({"operator": get_operator()})
