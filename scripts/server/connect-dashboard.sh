#!/usr/bin/env bash
# connect-dashboard.sh — open the Mission dashboard PRE-AUTHENTICATED.
#
# Flow (the "auto on SSH login" identity handoff):
#   1. SSH to the dashboard as your operator user and run `redteam-token`, which
#      mints a SINGLE-USE, short-TTL login code via the SO_PEERCRED socket. The
#      code is bound to YOUR ssh-authenticated Linux user — the kernel reports
#      your real uid to the server, so it can't be forged for anyone else. The
#      code (not a bearer token) is what travels in the URL, and it dies on first
#      use, so a leaked URL/log line is near-worthless.
#   2. Forward localhost:5000 -> dashboard:5000.
#   3. Open the browser at /login?c=<code>; the server redeems it once and sets
#      the HttpOnly, SameSite=Strict operator cookie, dropping you into the dashboard.
#
# Usage:  ./scripts/server/connect-dashboard.sh <operator>@<dashboard-eip>
#         (or set DASHBOARD=<operator>@<eip>; PORT overrides the local port)
set -euo pipefail

DASH="${1:-${DASHBOARD:-}}"
PORT="${PORT:-5000}"

if [ -z "$DASH" ]; then
    echo "usage: $(basename "$0") <operator>@<dashboard-eip>" >&2
    exit 1
fi

# Refuse to clobber a local port that's already in use (e.g. macOS AirPlay owns
# 5000) — otherwise the backgrounded forward fails silently and the page won't load.
if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "[!] Local port ${PORT} is already in use. Re-run with a free port, e.g.:" >&2
    echo "    PORT=5050 $(basename "$0") $DASH" >&2
    exit 1
fi

echo "[*] Minting your single-use login code on $DASH ..."
CODE="$(ssh "$DASH" redteam-token)" || {
    echo "[!] Could not mint a code. Are you provisioned as an operator on the" >&2
    echo "    dashboard, and is the service up? Try: ssh $DASH 'systemctl status dashboard'" >&2
    exit 1
}
if [ -z "$CODE" ]; then
    echo "[!] Empty code returned — not recognised as an operator on this host." >&2
    exit 1
fi

echo "[*] Forwarding localhost:${PORT} -> dashboard:5000 ..."
ssh -fN -L "${PORT}:localhost:5000" "$DASH"

URL="http://localhost:${PORT}/login?c=${CODE}"
echo "[*] Opening the signed login URL ..."
if command -v open >/dev/null 2>&1; then
    open "$URL"
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL"
else
    echo "    Open this URL in your browser:"
    echo "    $URL"
fi
echo "[*] Done. The tunnel runs in the background (kill it with: pkill -f '${PORT}:localhost:5000')."
