#!/bin/bash

# Create and Populate Tools Repository
# This script creates the initial structure for the red team tools repository
# and clones all tool repos. Run this after creating the GitHub repository.
#
# Usage: ./create-tools-repo.sh [--skip-clone]
#   --skip-clone    Only create structure, skip cloning tool repos

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SKIP_CLONE=false
if [[ "${1:-}" == "--skip-clone" ]]; then
    SKIP_CLONE=true
fi

echo -e "${GREEN}Creating tools repository structure...${NC}"

# Check if we're in a git repository
if [ ! -d ".git" ]; then
    echo -e "${YELLOW}Warning: Not in a git repository. Make sure you've cloned the tools repository first.${NC}"
    echo "Example: git clone git@github.com:YOUR-ORG/red-team-tools.git"
    exit 1
fi

# Check prerequisites
if ! command -v git &> /dev/null; then
    echo -e "${RED}Error: git is not installed${NC}"
    exit 1
fi

# Create docs directory
echo "Creating directories..."
mkdir -p docs

# ============================================================================
# Tool Repository Definitions
# Format: "directory_name|git_url"
# ============================================================================

# --- AD Enumeration & Exploitation ---
AD_TOOLS=(
    "ADSearch|https://github.com/tomcarver16/ADSearch.git"
    "BloodHound|https://github.com/SpecterOps/BloodHound.git"
    "Certify|https://github.com/GhostPack/Certify.git"
    "ForgeCert|https://github.com/GhostPack/ForgeCert.git"
    "Rubeus|https://github.com/GhostPack/Rubeus.git"
    "Whisker|https://github.com/eladshamir/Whisker.git"
    "SharpADWS|https://github.com/wh0amitz/SharpADWS.git"
    "StandIn|https://github.com/FuzzySecurity/StandIn.git"
    "PowerUpSQL|https://github.com/NetSPI/PowerUpSQL.git"
    "SQLRecon|https://github.com/skahwah/SQLRecon.git"
    "DRSAT|https://github.com/CCob/DRSAT.git"
)

# --- Post-Exploitation & Situational Awareness ---
POSTEX_TOOLS=(
    "mimikatz|https://github.com/gentilkiwi/mimikatz.git"
    "Seatbelt|https://github.com/GhostPack/Seatbelt.git"
    "SharpDPAPI|https://github.com/GhostPack/SharpDPAPI.git"
    "SharpUp|https://github.com/GhostPack/SharpUp.git"
    "SharpView|https://github.com/tevora-threat/SharpView.git"
    "SharpWMI|https://github.com/GhostPack/SharpWMI.git"
    "PowerSploit|https://github.com/PowerShellMafia/PowerSploit.git"
    "SweetPotato|https://github.com/CCob/SweetPotato.git"
    "SharpSystemTriggers|https://github.com/cube0x0/SharpSystemTriggers.git"
    "SCShell|https://github.com/Mr-Un1k0d3r/SCShell.git"
)

# --- Cobalt Strike BOFs & Kits ---
CS_TOOLS=(
    "CS-Remote-OPs-BOF|https://github.com/trustedsec/CS-Remote-OPs-BOF.git"
    "CS-Situational-Awareness-BOF|https://github.com/trustedsec/CS-Situational-Awareness-BOF.git"
    "Kerbeus-BOF|https://github.com/RalfHacker/Kerbeus-BOF.git"
    "SQL-BOF|https://github.com/Tw1sm/SQL-BOF.git"
    "Crystal-Kit|https://github.com/rasta-mouse/Crystal-Kit.git"
    "sleepmask-vs|https://github.com/Cobalt-Strike/sleepmask-vs.git"
)

# --- Evasion & Payload Generation ---
EVASION_TOOLS=(
    "Invoke-Obfuscation|https://github.com/danielbohannon/Invoke-Obfuscation.git"
    "GadgetToJScript|https://github.com/med0x2e/GadgetToJScript.git"
    "PackMyPayload|https://github.com/mgeeky/PackMyPayload.git"
    "DLL-Template|https://github.com/FuzzySecurity/DLL-Template.git"
    "ThreatCheck|https://github.com/rasta-mouse/ThreatCheck.git"
    "ysoserial.net|https://github.com/pwntester/ysoserial.net.git"
    "WDACTools|https://github.com/mattifestation/WDACTools.git"
)

# --- Detection & Research ---
RESEARCH_TOOLS=(
    "protections-artifacts|https://github.com/elastic/protections-artifacts.git"
)

# Combine all tool arrays
ALL_TOOLS=(
    "${AD_TOOLS[@]}"
    "${POSTEX_TOOLS[@]}"
    "${CS_TOOLS[@]}"
    "${EVASION_TOOLS[@]}"
    "${RESEARCH_TOOLS[@]}"
)

# ============================================================================
# Clone Function
# ============================================================================

clone_tool() {
    local name="$1"
    local url="$2"

    if [ -d "$name" ]; then
        echo -e "  ${YELLOW}[SKIP]${NC} $name (already exists)"
        return 0
    fi

    echo -e "  ${BLUE}[CLONE]${NC} $name"
    if git clone --depth 1 "$url" "$name" 2>/dev/null; then
        echo -e "  ${GREEN}[OK]${NC} $name"
        return 0
    else
        echo -e "  ${RED}[FAIL]${NC} $name — $url"
        return 1
    fi
}

# ============================================================================
# Clone Tool Repositories
# ============================================================================

if [ "$SKIP_CLONE" = false ]; then
    echo ""
    echo -e "${GREEN}Cloning tool repositories (shallow clone)...${NC}"
    echo ""

    CLONE_SUCCESS=0
    CLONE_FAIL=0
    CLONE_SKIP=0

    for entry in "${ALL_TOOLS[@]}"; do
        name="${entry%%|*}"
        url="${entry##*|}"
        if [ -d "$name" ]; then
            CLONE_SKIP=$((CLONE_SKIP + 1))
            echo -e "  ${YELLOW}[SKIP]${NC} $name (already exists)"
        elif clone_tool "$name" "$url"; then
            CLONE_SUCCESS=$((CLONE_SUCCESS + 1))
        else
            CLONE_FAIL=$((CLONE_FAIL + 1))
        fi
    done

    echo ""
    echo -e "${GREEN}Clone summary: ${CLONE_SUCCESS} cloned, ${CLONE_SKIP} skipped, ${CLONE_FAIL} failed${NC}"
fi

# ============================================================================
# Manual Tools (not public git repos — must be added manually)
# ============================================================================

echo ""
echo -e "${YELLOW}The following tools must be added manually:${NC}"
echo ""
echo "  cobaltstrike/        — Licensed software. Upload your Cobalt Strike archive."
echo "  driver-bofs/         — Private repository. Clone manually if you have access."
echo "  ghidra/              — Download release from https://github.com/NationalSecurityAgency/ghidra/releases"
echo "  hashcat/             — Download release from https://github.com/hashcat/hashcat/releases"
echo "  HeidiSQL/            — Download from https://www.heidisql.com/download.php"
echo "  SysinternalsSuite/   — Download from https://learn.microsoft.com/en-us/sysinternals/downloads/"
echo "  dotPeek64.exe        — Download from https://www.jetbrains.com/decompiler/download/"
echo "  Invoke-DCOM.ps1      — Download from https://github.com/rvrsh3ll/Misc-Powershell-Scripts"
echo ""

# Create placeholder directories for manual tools
for dir in cobaltstrike driver-bofs ghidra hashcat HeidiSQL SysinternalsSuite; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        echo "Place $dir files here." > "$dir/.gitkeep"
    fi
done

# ============================================================================
# README
# ============================================================================

cat > README.md << 'READMEEOF'
# Red Team Tools Repository

Private repository containing red team tools for attack box deployment.

## Deployment

Tools are automatically cloned to the attack box during infrastructure provisioning:
- **Windows**: `C:\Tools\`
- **WSL2**: `/opt/tools/`

## Tool Inventory

### AD Enumeration & Exploitation
| Tool | Description |
|------|-------------|
| ADSearch | C# LDAP query tool |
| BloodHound | AD attack path mapping (Community Edition) |
| Certify | AD CS enumeration and abuse |
| ForgeCert | Certificate forgery via stolen CA keys |
| Rubeus | Kerberos interaction and abuse |
| Whisker | Shadow Credentials (msDS-KeyCredentialLink) |
| SharpADWS | AD recon via ADWS protocol (bypasses LDAP monitoring) |
| StandIn | .NET AD post-exploitation toolkit |
| PowerUpSQL | SQL Server discovery and exploitation |
| SQLRecon | C# MS-SQL offensive toolkit |
| DRSAT | Disconnected RSAT for non-domain-joined machines |

### Post-Exploitation & Situational Awareness
| Tool | Description |
|------|-------------|
| mimikatz | Credential extraction |
| Seatbelt | Host situational awareness |
| SharpDPAPI | DPAPI secret extraction |
| SharpUp | Privilege escalation checks |
| SharpView | C# port of PowerView |
| SharpWMI | WMI interaction |
| PowerSploit | PowerShell post-exploitation framework |
| SweetPotato | Potato privilege escalation (service → SYSTEM) |
| SharpSystemTriggers | Remote authentication coercion (PetitPotam, PrintSpooler) |
| SCShell | Fileless lateral movement via service config |

### Cobalt Strike BOFs & Kits
| Tool | Description |
|------|-------------|
| CS-Remote-OPs-BOF | TrustedSec remote operations BOFs |
| CS-Situational-Awareness-BOF | TrustedSec situational awareness BOFs |
| Kerbeus-BOF | Kerberos BOF (C implementation of Rubeus) |
| SQL-BOF | MS-SQL BOFs |
| Crystal-Kit | CS evasion kit (Sleepmask/BeaconGate replacements) |
| sleepmask-vs | CS Sleepmask BOF Visual Studio template |
| cobaltstrike | Licensed CS archive (manual) |

### Evasion & Payload Generation
| Tool | Description |
|------|-------------|
| Invoke-Obfuscation | PowerShell obfuscation framework |
| GadgetToJScript | .NET deserialization gadgets for JS/VBS/VBA |
| PackMyPayload | Payload packaging (ISO, VHD, ZIP, CAB) |
| DLL-Template | C++ DLL skeleton template |
| ThreatCheck | AV/AMSI signature identification |
| ysoserial.net | .NET deserialization payload generator |
| WDACTools | WDAC policy building and auditing |

### Detection & Research
| Tool | Description |
|------|-------------|
| protections-artifacts | Elastic detection rules and YARA signatures |

### Utilities & Reversing (Manual Download)
| Tool | Description |
|------|-------------|
| ghidra | NSA reverse engineering framework |
| hashcat | GPU password cracking |
| HeidiSQL | Database management client |
| SysinternalsSuite | Microsoft Sysinternals tools |
| dotPeek64.exe | JetBrains .NET decompiler |
| Invoke-DCOM.ps1 | DCOM lateral movement script |
| driver-bofs | Driver BOFs (private repo) |

## Adding Tools

1. Clone or download the tool into this repository root
2. Commit and push
3. Tools sync to the attack box on next deployment

## Security

- **Private repository only** — do not make public
- Access restricted to authorized team members
- Do not commit credentials or operational data
READMEEOF

# ============================================================================
# .gitignore
# ============================================================================

cat > .gitignore << 'IGNOREEOF'
# Sensitive files
*.key
*.pem
*.p12
*.pfx
*.secret
*.env
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

# Build artifacts
bin/
obj/
*.o
IGNOREEOF

# ============================================================================
# Done
# ============================================================================

echo -e "${GREEN}Repository structure created!${NC}"
echo ""
echo "Next steps:"
echo "1. Add manual tools (ghidra, hashcat, HeidiSQL, SysinternalsSuite, etc.)"
echo "2. Review the structure: ls -la"
echo "3. Commit:"
echo "   git add ."
echo "   git commit -m 'Populate tools repository'"
echo "4. Push to GitHub:"
echo "   git push -u origin main"
echo ""
echo "See docs/TOOLS_REPOSITORY_SETUP.md for complete setup instructions."
