#!/bin/bash

# Start Red Team Infrastructure Web Application

set -euo pipefail

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Starting Red Team Infrastructure Web Application${NC}"
echo "=========================================="

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "$PROJECT_ROOT/venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv "$PROJECT_ROOT/venv"
fi

# Activate virtual environment
source "$PROJECT_ROOT/venv/bin/activate"

# Verify pip works (venv breaks if the project directory was moved/renamed)
if ! pip --version &> /dev/null; then
    echo -e "${YELLOW}Virtual environment appears broken (common after moving/renaming the project directory).${NC}"
    echo -e "${YELLOW}Recreating virtual environment...${NC}"
    deactivate 2>/dev/null || true
    rm -rf "$PROJECT_ROOT/venv"
    python3 -m venv "$PROJECT_ROOT/venv"
    source "$PROJECT_ROOT/venv/bin/activate"
fi

# Install/update dependencies
echo -e "${YELLOW}Installing dependencies...${NC}"
pip install -q --upgrade pip
pip install -q -r "$PROJECT_ROOT/requirements.txt"

# Start the application
echo -e "${GREEN}Starting web server...${NC}"
echo "Access the application at: http://127.0.0.1:5000"
echo "Press Ctrl+C to stop"
echo "=========================================="

cd "$PROJECT_ROOT"
python3 webapp/backend/app.py

