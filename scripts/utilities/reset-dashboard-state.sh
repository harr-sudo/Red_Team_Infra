#!/usr/bin/env bash
# reset-dashboard-state.sh — wipe the live dashboard state files.
#
# Use this if a previous test run (Playwright, manual, or otherwise)
# polluted ~/.dashboard/ with stray operators / audit lines / presence
# YAML. Task #54 introduced DASHBOARD_STATE_DIR to prevent future
# pollution; this script is the cleanup for residue from before that
# fix.
#
# Safe to run anytime: re-seeds on next Flask request.
set -euo pipefail

DASHBOARD_DIR="${HOME}/.dashboard"
PRESENCE_DIR="$(cd "$(dirname "$0")"/../.. && pwd)/webapp/state/presence"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Resetting dashboard state:${NC}"
for target in \
    "${DASHBOARD_DIR}/operators.json" \
    "${DASHBOARD_DIR}/audit.log" \
    "${DASHBOARD_DIR}/presence" \
    "${PRESENCE_DIR}"
do
    if [ -e "${target}" ]; then
        rm -rf "${target}"
        echo -e "  ${GREEN}removed${NC} ${target}"
    else
        echo "  skipped ${target} (not present)"
    fi
done

echo -e "${GREEN}done.${NC} Flask will re-seed on next request."
