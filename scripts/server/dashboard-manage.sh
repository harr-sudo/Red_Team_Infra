#!/bin/bash
set -euo pipefail

# ============================================================================
# Dashboard Server Management Script
# Usage: ./dashboard-manage.sh {start|stop|restart|status|logs|upgrade}
# ============================================================================

SERVICE="dashboard"
REDTEAM_DIR="/opt/redteam"

case "${1:-help}" in
  start)
    echo "Starting dashboard..."
    sudo systemctl start "$SERVICE"
    echo "Dashboard started. Access via SSH tunnel + http://localhost:5000"
    ;;
  stop)
    echo "Stopping dashboard..."
    sudo systemctl stop "$SERVICE"
    echo "Dashboard stopped."
    ;;
  restart)
    echo "Restarting dashboard..."
    sudo systemctl restart "$SERVICE"
    echo "Dashboard restarted."
    ;;
  status)
    echo "=== Service Status ==="
    sudo systemctl status "$SERVICE" --no-pager || true
    echo ""
    echo "=== Disk Usage ==="
    df -h "$REDTEAM_DIR" 2>/dev/null || true
    echo ""
    echo "=== Active Terminal Sessions ==="
    ss -tnp | grep -c ":5000" || echo "0"
    ;;
  logs)
    echo "Streaming dashboard logs (Ctrl+C to stop)..."
    sudo journalctl -u "$SERVICE" -f
    ;;
  upgrade)
    echo "Upgrading dashboard..."
    echo "Note: Run rsync from the lead operator's laptop first:"
    echo "  rsync -avz --exclude=uploads/ --exclude=local-only/ --exclude=.git/ --exclude=venv/ --exclude=logs/ . user@server:/opt/redteam/"
    echo ""
    echo "Then run this command on the server to apply:"
    cd "$REDTEAM_DIR"
    source venv/bin/activate
    pip install -r requirements.txt
    sudo systemctl restart "$SERVICE"
    echo "Upgrade complete."
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|logs|upgrade}"
    exit 1
    ;;
esac
