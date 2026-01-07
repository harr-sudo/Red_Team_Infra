#!/bin/bash

# Create Tools Repository Structure
# This script creates the initial structure for the tools repository
# Run this after creating the GitHub repository

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Creating tools repository structure...${NC}"

# Check if we're in a git repository
if [ ! -d ".git" ]; then
    echo -e "${YELLOW}Warning: Not in a git repository. Make sure you've cloned the tools repository first.${NC}"
    echo "Example: git clone git@github.com:YOUR-ORG/red-team-tools.git"
    exit 1
fi

# Create directory structure
echo "Creating directories..."
mkdir -p tools/{c2,post-exploitation,network,utilities,custom}
mkdir -p docs/{installation,usage}

# Create main README
cat > README.md << 'EOF'
# Red Team Tools Repository

Private repository for red team tools and utilities.

## Structure

- `tools/c2/` - C2 frameworks and tools
- `tools/post-exploitation/` - Post-exploitation tools
- `tools/network/` - Network analysis tools
- `tools/utilities/` - Utility scripts
- `tools/custom/` - Custom tools and scripts
- `docs/` - Tool documentation

## Access

Tools are automatically deployed to the jump box at:
- **Windows**: `C:\Tools\`
- **WSL2**: `/opt/tools/`

Access via RDP or SSH to the jump box.

## Adding Tools

1. Add tools to appropriate directory
2. Include README.md in tool directory with:
   - Tool description
   - Installation instructions
   - Usage examples
3. Commit and push changes
4. Tools will be updated on jump box on next deployment

## Security

- **Private repository only**
- Access restricted to authorized team members
- Do not commit sensitive data or credentials
- Scan all tools before adding
EOF

# Create .gitignore
cat > .gitignore << 'EOF'
# Binaries and executables
*.exe
*.dll
*.so
*.dylib
*.bin

# Archives (unless they're tool distributions)
*.zip
*.tar.gz
*.tar
*.rar
*.7z

# Sensitive files
*.key
*.pem
*.p12
*.pfx
*.secret
*.env
*.config
credentials.*
secrets.*

# OS files
.DS_Store
Thumbs.db
*.swp
*.swo
*~

# IDE
.vscode/
.idea/
*.iml

# Temporary files
*.tmp
*.log
*.cache
EOF

# Create README files for each directory
cat > tools/c2/README.md << 'EOF'
# C2 Frameworks

Place C2 framework tools here.

## Examples
- Cobalt Strike
- Empire
- Covenant
- Sliver
EOF

cat > tools/post-exploitation/README.md << 'EOF'
# Post-Exploitation Tools

Place post-exploitation tools here.

## Examples
- Mimikatz
- BloodHound
- PowerView
- Rubeus
EOF

cat > tools/network/README.md << 'EOF'
# Network Tools

Place network analysis and tools here.

## Examples
- Nmap
- Wireshark
- tcpdump
- Network scanners
EOF

cat > tools/utilities/README.md << 'EOF'
# Utility Scripts

Place utility scripts here.

## Examples
- Persistence scripts
- Privilege escalation scripts
- Data exfiltration scripts
EOF

cat > tools/custom/README.md << 'EOF'
# Custom Tools

Place custom tools and scripts here.

## Examples
- Custom payloads
- Team-specific tools
- One-off scripts
EOF

echo -e "${GREEN}Repository structure created!${NC}"
echo ""
echo "Next steps:"
echo "1. Review the structure: ls -la"
echo "2. Add initial commit:"
echo "   git add ."
echo "   git commit -m 'Initial repository structure'"
echo "3. Push to GitHub:"
echo "   git push -u origin main"
echo ""
echo "See docs/TOOLS_REPOSITORY_SETUP.md for complete setup instructions."

