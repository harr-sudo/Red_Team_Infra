#!/bin/bash
set -euo pipefail

# ============================================================================
# Dashboard Server Setup — Interactive Bootstrap
# Run this from your laptop to provision the centralized dashboard in AWS
#
# Usage:
#   ./setup-dashboard.sh              First-time provision / resume setup
#   ./setup-dashboard.sh --update-ip  Refresh dashboard_allowed_ips on an
#                                     already-provisioned dashboard (re-detects
#                                     your egress IP, lets you add entries, then
#                                     pushes the new allow-list with a targeted
#                                     terraform apply — no re-provisioning).
#   ./setup-dashboard.sh --help       Show this usage.
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"
CONFIGS_DIR="$PROJECT_ROOT/configs"
TFVARS_FILE="$CONFIGS_DIR/dashboard.tfvars"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# --- Flag parsing ---
UPDATE_IP_MODE=false
usage() {
    cat <<'USAGE'
Dashboard Server Setup — provision/manage the centralized dashboard in AWS.

Usage:
  ./setup-dashboard.sh              First-time provision / resume setup
  ./setup-dashboard.sh --update-ip  Refresh dashboard_allowed_ips on an
                                    already-provisioned dashboard: re-detects
                                    your egress IP, lets you add entries, then
                                    pushes the new allow-list with a targeted
                                    terraform apply (no re-provisioning).
  ./setup-dashboard.sh --help       Show this usage.
USAGE
}
for arg in "$@"; do
    case "$arg" in
        --update-ip) UPDATE_IP_MODE=true ;;
        -h|--help)   usage; exit 0 ;;
        *) error "Unknown argument: $arg (try --help)" ;;
    esac
done

# ----------------------------------------------------------------------------
# Shared helpers (used by both first-time setup and --update-ip mode)
# ----------------------------------------------------------------------------

# Detect egress IP from two independent sources and cross-check. Sets globals:
#   DETECTED_IP        — primary detected IPv4 (may be empty if both fail)
#   DETECTED_IP_ALT    — secondary source value (may be empty)
# Prints a WARNING when the two disagree (rotating/load-balanced egress).
# NOTE: every fetch is guarded with `|| echo ""` so a failed curl never trips
# `set -e`, and --max-time keeps a dead source from hanging the script.
detect_egress_ip() {
    DETECTED_IP=$(curl -4 -s --max-time 5 https://api.ipify.org 2>/dev/null || echo "")
    DETECTED_IP_ALT=$(curl -4 -s --max-time 5 https://ifconfig.me/ip 2>/dev/null || echo "")
    # Fallback third source only if one of the first two came back empty.
    if [ -z "$DETECTED_IP" ] || [ -z "$DETECTED_IP_ALT" ]; then
        local third
        third=$(curl -4 -s --max-time 5 https://icanhazip.com 2>/dev/null || echo "")
        third=$(echo "$third" | tr -d '[:space:]')
        [ -z "$DETECTED_IP" ] && DETECTED_IP="$third"
        [ -z "$DETECTED_IP_ALT" ] && DETECTED_IP_ALT="$third"
    fi
    # Strip any stray whitespace/newlines the providers may return.
    DETECTED_IP=$(echo "$DETECTED_IP" | tr -d '[:space:]')
    DETECTED_IP_ALT=$(echo "$DETECTED_IP_ALT" | tr -d '[:space:]')

    if [ -n "$DETECTED_IP" ] && [ -n "$DETECTED_IP_ALT" ] && [ "$DETECTED_IP" != "$DETECTED_IP_ALT" ]; then
        warn "Egress IP differs between sources ($DETECTED_IP vs $DETECTED_IP_ALT)."
        warn "Your egress looks load-balanced/rotating (VPN or iCloud Private Relay)."
        warn "The detected value may NOT be stable — see the guidance below."
    fi
}

# Print OPSEC guidance about /32 vs rotating egress. Called after detection.
print_ip_guidance() {
    echo ""
    info  "About the allow-list (dashboard_allowed_ips):"
    echo  "  - A single /32 is locked tight (good OPSEC) and is the recommended choice"
    echo  "    when you have a STABLE egress IP."
    echo  "  - iCloud Private Relay, mobile/cellular networks, and rotating-egress VPNs"
    echo  "    CHANGE your public IP and WILL lock you out of the dashboard."
    echo  "  - For stable access use a fixed egress: turn iCloud Private Relay OFF for"
    echo  "    this network, or use a static-IP VPN."
    echo  "  - Do NOT paste an entire relay/VPN provider range — that defeats the"
    echo  "    purpose of the allow-list. Add only the specific IPs/CIDRs you trust."
    echo  "  - You can add several entries (home + VPN + office), and refresh later"
    echo  "    any time with:  ./scripts/server/setup-dashboard.sh --update-ip"
    echo ""
}

# Validate a single allow-list entry as a bare IPv4 or IPv4/CIDR.
# Returns 0 if valid, 1 otherwise. Does NOT exit (caller decides).
valid_ip_or_cidr() {
    echo "$1" | grep -qE '^([0-9]{1,3}\.){3}[0-9]{1,3}(/([0-9]|[12][0-9]|3[0-2]))?$'
}

# Normalize an entry: append /32 to a bare IP, pass CIDRs through unchanged.
normalize_entry() {
    case "$1" in
        */*) echo "$1" ;;
        *)   echo "$1/32" ;;
    esac
}

# Interactively collect allow-list entries into the global ALLOWED_ENTRIES array.
# Accepts a comma-separated list at the first prompt (pre-filled with the
# detected IP) and then loops "add another". Each entry is validated and
# normalized. Resets ALLOWED_ENTRIES on entry so it is safe to call repeatedly.
collect_allowed_entries() {
    ALLOWED_ENTRIES=()
    local default_first="$1"   # pre-fill value (detected IP), may be empty
    local raw entry norm

    read -rp "Allowed IP(s)/CIDR(s) — comma-separated [${default_first}]: " raw
    raw="${raw:-$default_first}"
    [ -n "$raw" ] || error "No IP/CIDR provided and none detected. Enter at least one."

    # Split the (possibly comma-separated) first answer.
    local IFS=','
    for entry in $raw; do
        entry=$(echo "$entry" | tr -d '[:space:]')
        [ -z "$entry" ] && continue
        if valid_ip_or_cidr "$entry"; then
            norm=$(normalize_entry "$entry")
            ALLOWED_ENTRIES+=("$norm")
            success "Added: $norm"
        else
            warn "Skipping invalid entry: '$entry' (expected IPv4 or IPv4/CIDR)"
        fi
    done
    unset IFS

    # Loop to add more individual entries.
    while true; do
        read -rp "Add another IP/CIDR? (blank to finish): " entry
        entry=$(echo "$entry" | tr -d '[:space:]')
        [ -z "$entry" ] && break
        if valid_ip_or_cidr "$entry"; then
            norm=$(normalize_entry "$entry")
            ALLOWED_ENTRIES+=("$norm")
            success "Added: $norm"
        else
            warn "Invalid entry: '$entry' (expected IPv4 or IPv4/CIDR). Try again."
        fi
    done

    [ "${#ALLOWED_ENTRIES[@]}" -gt 0 ] || error "No valid IP/CIDR entries collected."
}

# Auto-detect an SSH public key into SSH_KEY_PATH (empty if none found).
detect_ssh_key() {
    SSH_KEY_PATH=""
    local candidate
    for candidate in \
        ~/.ssh/id_ed25519.pub \
        ~/.ssh/id_rsa.pub \
        ~/.ssh/id_ecdsa.pub \
        /mnt/c/Users/${USER:-}/.ssh/id_ed25519.pub \
        /mnt/c/Users/${USER:-}/.ssh/id_rsa.pub \
        "${USERPROFILE:-}/.ssh/id_ed25519.pub" \
        "${USERPROFILE:-}/.ssh/id_rsa.pub"; do
        if [ -n "$candidate" ] && [ -f "$candidate" ] 2>/dev/null; then
            SSH_KEY_PATH="$candidate"
            break
        fi
    done
}

# Generate an ed25519 keypair if none exists, then set SSH_KEY_PATH to the
# resulting .pub. Never overwrites an existing ~/.ssh/id_ed25519 — if one is
# already there it is reused. $1 = operator name (for the key comment).
generate_ssh_key() {
    local op_name="${1:-redteam-dashboard}"
    local target="$HOME/.ssh/id_ed25519"
    mkdir -p "$HOME/.ssh"
    chmod 700 "$HOME/.ssh" 2>/dev/null || true
    if [ -f "$target" ]; then
        warn "$target already exists — reusing it (not overwriting)."
    else
        info "Generating ed25519 keypair at $target ..."
        ssh-keygen -t ed25519 -f "$target" -N "" -C "redteam-dashboard-$op_name"
        success "SSH keypair generated."
    fi
    SSH_KEY_PATH="$target.pub"
}

echo ""
echo "============================================"
echo "  Red Team Dashboard — Server Setup"
echo "============================================"
echo ""

# --- Prerequisites ---
info "Checking prerequisites..."

command -v aws >/dev/null 2>&1 || error "AWS CLI not found. Install: https://aws.amazon.com/cli/"
command -v terraform >/dev/null 2>&1 || error "Terraform not found. Install: https://terraform.io"
command -v ssh >/dev/null 2>&1 || error "SSH client not found."
command -v rsync >/dev/null 2>&1 || error "rsync not found."

# Verify AWS credentials
info "Verifying AWS credentials..."
AWS_IDENTITY=$(aws sts get-caller-identity 2>/dev/null) || error "AWS credentials not configured. Run: aws configure"
AWS_ACCOUNT=$(echo "$AWS_IDENTITY" | jq -r '.Account')
success "AWS account: $AWS_ACCOUNT"

# ============================================================================
# --update-ip MODE — refresh the allow-list on an already-provisioned dashboard
# ============================================================================
if [ "$UPDATE_IP_MODE" = true ]; then
    echo ""
    info "Update-IP mode: refreshing dashboard_allowed_ips (no re-provisioning)."

    # Guard: only run when a dashboard already exists.
    cd "$TERRAFORM_DIR"
    UPD_DASHBOARD_IP=$(terraform output -raw dashboard_public_ip 2>/dev/null || echo "")
    [ -n "$UPD_DASHBOARD_IP" ] || error "No provisioned dashboard found (terraform output dashboard_public_ip is empty). Run without --update-ip to provision first."
    [ -f "$TFVARS_FILE" ] || error "Existing config not found: $TFVARS_FILE. Cannot update allow-list without it."
    success "Found dashboard: $UPD_DASHBOARD_IP"

    # Re-detect the current egress IP from two sources and cross-check.
    info "Detecting current egress IP..."
    detect_egress_ip
    if [ -n "$DETECTED_IP" ]; then
        success "Detected egress IP: $DETECTED_IP"
    else
        warn "Could not auto-detect your egress IP — you'll need to enter it manually."
    fi
    print_ip_guidance

    # Collect the new entry list (pre-filled with the freshly detected IP).
    collect_allowed_entries "$DETECTED_IP"

    # Join entries into a single comma-separated token for awk. We pass ONE line
    # to awk (no embedded newlines) because BSD/macOS awk rejects multi-line -v
    # values; awk reconstructs the multi-line block itself.
    ENTRIES_JOINED=""
    for e in "${ALLOWED_ENTRIES[@]}"; do
        ENTRIES_JOINED="${ENTRIES_JOINED:+$ENTRIES_JOINED,}$e"
    done

    echo ""
    info "New allow-list:"
    echo "  dashboard_allowed_ips = ["
    for e in "${ALLOWED_ENTRIES[@]}"; do echo "    \"$e\","; done
    echo "  ]"
    echo ""
    read -rp "Rewrite $TFVARS_FILE with this allow-list and apply? (yes/no): " UPD_CONFIRM
    [ "$UPD_CONFIRM" = "yes" ] || { warn "Aborted — no changes made."; exit 0; }

    # Rewrite ONLY the dashboard_allowed_ips array in-place, preserving
    # operator_ssh_public_keys and every other setting in the file. awk copies
    # everything, drops the old array lines (single- or multi-line), and emits a
    # freshly formatted block at the array's original position. Portable across
    # GNU and BSD awk (entries arrive as one comma-separated -v token).
    UPD_TMP=$(mktemp)
    awk -v entries="$ENTRIES_JOINED" '
        BEGIN {
            in_arr = 0; done = 0
            n = split(entries, arr, ",")
        }
        function print_block(   i) {
            print "dashboard_allowed_ips = ["
            for (i = 1; i <= n; i++) {
                if (arr[i] != "") print "  \"" arr[i] "\","
            }
            print "]"
        }
        # Detect start of the array (line beginning with the key).
        (!done && $0 ~ /^[[:space:]]*dashboard_allowed_ips[[:space:]]*=[[:space:]]*\[/) {
            print_block()
            in_arr = 1
            # If the opening line also closes the array on the same line, were done.
            if ($0 ~ /\]/) { in_arr = 0; done = 1 }
            next
        }
        in_arr {
            # Inside the old multi-line array — drop lines until the closing ].
            if ($0 ~ /\]/) { in_arr = 0; done = 1 }
            next
        }
        { print }
    ' "$TFVARS_FILE" > "$UPD_TMP"

    # Safety: confirm the awk actually wrote the new block before clobbering.
    if ! grep -q '^dashboard_allowed_ips = \[' "$UPD_TMP"; then
        rm -f "$UPD_TMP"
        error "Failed to rewrite allow-list in $TFVARS_FILE (key not found). File left unchanged."
    fi
    mv "$UPD_TMP" "$TFVARS_FILE"
    success "Updated allow-list in $TFVARS_FILE"

    # Find an existing deployment tfvars to satisfy root variables on apply.
    UPD_EXISTING_TFVARS=""
    for candidate in "$CONFIGS_DIR/terraform.tfvars" "$CONFIGS_DIR"/*.tfvars; do
        if [ -f "$candidate" ] && [ "$candidate" != "$TFVARS_FILE" ]; then
            UPD_EXISTING_TFVARS="$candidate"
            break
        fi
    done

    echo ""
    info "Pushing new allow-list with a targeted terraform apply..."
    terraform init >/dev/null
    UPD_APPLY_CMD="terraform apply -target=module.dashboard_server -var-file=$TFVARS_FILE"
    if [ -n "$UPD_EXISTING_TFVARS" ]; then
        info "Using existing config: $UPD_EXISTING_TFVARS"
        UPD_APPLY_CMD="terraform apply -target=module.dashboard_server -var-file=$UPD_EXISTING_TFVARS -var-file=$TFVARS_FILE"
    fi
    eval "$UPD_APPLY_CMD"

    echo ""
    success "Allow-list updated. Dashboard reachable at: $UPD_DASHBOARD_IP"
    info "If you still can't connect, confirm your current egress matches an entry above."
    exit 0
fi

# --- Check if dashboard already exists (resume mode) ---
cd "$TERRAFORM_DIR"
EXISTING_DASHBOARD_IP=$(terraform output -raw dashboard_public_ip 2>/dev/null || echo "")
if [ -n "$EXISTING_DASHBOARD_IP" ] && [ "$EXISTING_DASHBOARD_IP" != "" ]; then
    echo ""
    success "Dashboard server already provisioned: $EXISTING_DASHBOARD_IP"
    read -rp "Resume setup (rsync code + start service)? (yes/no): " RESUME
    if [ "$RESUME" = "yes" ]; then
        DASHBOARD_IP="$EXISTING_DASHBOARD_IP"
        INSTANCE_ID=$(terraform output -raw dashboard_instance_id 2>/dev/null || echo "")

        # Read operator name from the dashboard.tfvars (matches the Linux user on the server)
        OPERATOR_NAME=""
        if [ -f "$TFVARS_FILE" ]; then
            OPERATOR_NAME=$(grep 'operator_ssh_public_keys' -A5 "$TFVARS_FILE" | grep '"[a-z]' | head -1 | sed 's/.*"\([a-z][a-z0-9_-]*\)".*/\1/')
        fi
        if [ -z "$OPERATOR_NAME" ]; then
            OPERATOR_NAME=$(whoami | tr '[:upper:]' '[:lower:]')
        fi

        # Still need an SSH key for rsync/SSH. Auto-detect; if none, offer to generate.
        detect_ssh_key
        if [ -z "$SSH_KEY_PATH" ]; then
            warn "No SSH key auto-detected for resume."
            read -rp "No SSH key found — generate an ed25519 key now? (yes/no): " GEN_KEY
            if [ "$GEN_KEY" = "yes" ]; then
                generate_ssh_key "$OPERATOR_NAME"
            else
                read -rp "Path to your SSH public key: " SSH_KEY_PATH
                [ -f "$SSH_KEY_PATH" ] || error "SSH public key not found: $SSH_KEY_PATH"
            fi
        fi
        # Validate the key format (same check as the fresh path).
        if ! grep -qE '^ssh-(ed25519|rsa|ecdsa-sha2-nistp[0-9]+) [A-Za-z0-9+/=]+' "$SSH_KEY_PATH" 2>/dev/null; then
            error "Invalid SSH public key format in $SSH_KEY_PATH"
        fi
        SSH_KEY_PRIVATE="${SSH_KEY_PATH%.pub}"

        AWS_REGION=$(aws configure get region 2>/dev/null || echo "eu-central-1")

        info "Using SSH key: $SSH_KEY_PATH"
        info "Using operator: $OPERATOR_NAME"
        echo ""
        info "Copying codebase to server..."
        rsync -rltz --progress --no-perms --no-owner --no-group \
            --exclude='uploads/' \
            --exclude='uploads_client/' \
            --exclude='uploads_tools/' \
            --exclude='local-only/' \
            --exclude='.git/' \
            --exclude='venv/' \
            --exclude='logs/' \
            --exclude='terraform.tfstate*' \
            --exclude='*.tfplan' \
            --exclude='.terraform/' \
            --exclude='.DS_Store' \
            --exclude='.claude/' \
            --exclude='.obsidian/' \
            --exclude='.c2lint_cache/' \
            --exclude='.mcp.json' \
            --exclude='*.rtf' \
            --exclude='__pycache__/' \
            --exclude='*.pyc' \
            --exclude='Research/' \
            --exclude='goad_workspace/' \
            --exclude='ssh_keys/' \
            --exclude='tools/goad/' \
            --exclude='configs/*.tfvars' \
            --exclude='configs/ssh/' \
            --exclude='*.png' \
            --exclude='c2-adhoc-architecture.png' \
            --exclude='domain_categorization_results.csv' \
            --exclude='SpeakView*' \
            --exclude='PLAN.md' \
            -e "ssh -i $SSH_KEY_PRIVATE -o StrictHostKeyChecking=accept-new" \
            "$PROJECT_ROOT/" \
            "$OPERATOR_NAME@$DASHBOARD_IP:/opt/redteam/" || true
        # rsync exit code 23 = partial transfer (some files skipped) — acceptable

        success "Codebase synced"

        # Step 1: Set up venv and install deps (as operator — owns the files via group)
        info "Installing Python dependencies on server..."
        ssh -i "$SSH_KEY_PRIVATE" -o StrictHostKeyChecking=accept-new "$OPERATOR_NAME@$DASHBOARD_IP" bash -e <<'REMOTE_PIP'
cd /opt/redteam

# Ensure server SSH keypair exists
if [ ! -f /opt/redteam/.ssh/id_ed25519 ]; then
    mkdir -p /opt/redteam/.ssh
    ssh-keygen -t ed25519 -f /opt/redteam/.ssh/id_ed25519 -N "" -C "dashboard-server"
    chown dashboard:redteam /opt/redteam/.ssh/id_ed25519 /opt/redteam/.ssh/id_ed25519.pub 2>/dev/null || true
    chmod 600 /opt/redteam/.ssh/id_ed25519
    echo "Server SSH keypair generated"
fi

# Update terraform.tfvars with server's key
SERVER_PUB_KEY=$(cat /opt/redteam/.ssh/id_ed25519.pub)
if grep -q "^user_public_key" /opt/redteam/configs/terraform.tfvars 2>/dev/null; then
    sed -i "s|^user_public_key = .*|user_public_key = \"$SERVER_PUB_KEY\"|" /opt/redteam/configs/terraform.tfvars
fi

# Remove stale venv if it exists with wrong ownership
if [ -d venv ] && [ ! -w venv ]; then
    echo "Removing stale venv with wrong permissions..."
    rm -rf venv 2>/dev/null || true
fi

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "Dependencies installed OK"
REMOTE_PIP

        # Step 2: Terraform init (as operator — no sudo needed, uses operator's AWS creds via instance role)
        info "Initializing Terraform on server..."
        ssh -i "$SSH_KEY_PRIVATE" -o StrictHostKeyChecking=accept-new "$OPERATOR_NAME@$DASHBOARD_IP" bash -e <<'REMOTE_TF'
cd /opt/redteam/terraform
terraform init -backend-config=/opt/redteam/backend.hcl || echo "Terraform init completed (may show warnings)"
REMOTE_TF

        # Step 3: Create systemd service (needs root — use EC2 Instance Connect via ubuntu)
        info "Creating systemd service..."
        aws ec2-instance-connect send-ssh-public-key \
            --instance-id "$INSTANCE_ID" \
            --instance-os-user ubuntu \
            --ssh-public-key "file://$SSH_KEY_PATH" \
            --region "$AWS_REGION" > /dev/null 2>&1

        ssh -i "$SSH_KEY_PRIVATE" -o StrictHostKeyChecking=accept-new "ubuntu@$DASHBOARD_IP" bash <<'REMOTE_SVC'
# Create systemd service if it doesn't exist (or update it)
sudo tee /etc/systemd/system/dashboard.service > /dev/null <<'SERVICE'
[Unit]
Description=Red Team Dashboard
After=network.target

[Service]
Type=simple
User=dashboard
Group=redteam
WorkingDirectory=/opt/redteam
ExecStart=/opt/redteam/venv/bin/python3 webapp/backend/app.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/redteam
PrivateTmp=true

[Install]
WantedBy=multi-user.target
SERVICE

sudo hostnamectl set-hostname redteam-dashboard 2>/dev/null || true
sudo systemctl daemon-reload
sudo systemctl enable dashboard
sudo systemctl restart dashboard
echo "Dashboard service started"
REMOTE_SVC

        success "Dashboard service started"
        echo ""
        echo "============================================"
        echo "  Dashboard Server Ready!"
        echo "============================================"
        echo ""
        echo "  IP:       $DASHBOARD_IP"
        echo "  Connect:  ssh -L 5000:localhost:5000 $OPERATOR_NAME@$DASHBOARD_IP"
        echo "  Open:     http://localhost:5000"
        echo ""
        echo "  Configure + deploy in the browser. Full walkthrough: docs/GETTING_STARTED.md"
        echo ""
        echo "============================================"
        exit 0
    fi
fi
cd "$PROJECT_ROOT"

# --- Auto-detect values ---

# SSH key — check common locations across macOS, Linux, Windows (WSL/Git Bash)
detect_ssh_key

# Public IP — detected from two sources and cross-checked (rotating-egress aware)
detect_egress_ip

# AWS region
DETECTED_REGION=$(aws configure get region 2>/dev/null || echo "eu-central-1")

# Operator name
DETECTED_USER=$(whoami)

# --- Prompt for values ---
echo ""
info "Configure your dashboard server:"
echo ""

# SSH key
if [ -n "$SSH_KEY_PATH" ]; then
    success "Auto-detected SSH key: $SSH_KEY_PATH"
fi
read -rp "SSH public key path (press Enter to use detected) [$SSH_KEY_PATH]: " INPUT_KEY
SSH_KEY_PATH="${INPUT_KEY:-$SSH_KEY_PATH}"

# If still no key (none detected and operator supplied none), offer to generate.
if [ -z "$SSH_KEY_PATH" ] || [ ! -f "$SSH_KEY_PATH" ]; then
    if [ -n "$SSH_KEY_PATH" ]; then
        warn "SSH public key not found: $SSH_KEY_PATH"
    fi
    read -rp "No SSH key found — generate an ed25519 key now? (yes/no): " GEN_KEY
    if [ "$GEN_KEY" = "yes" ]; then
        # OPERATOR_NAME isn't set yet at this point; use the detected user
        # (lowercased) for the key comment.
        generate_ssh_key "$(echo "$DETECTED_USER" | tr '[:upper:]' '[:lower:]')"
    else
        error "SSH public key required. Provide a path or re-run and choose to generate one."
    fi
fi
SSH_KEY_CONTENT=$(cat "$SSH_KEY_PATH")

# Validate SSH key format
if ! echo "$SSH_KEY_CONTENT" | grep -qE '^ssh-(ed25519|rsa|ecdsa-sha2-nistp[0-9]+) [A-Za-z0-9+/=]+'; then
    error "Invalid SSH public key format in $SSH_KEY_PATH"
fi
success "SSH key: $SSH_KEY_PATH"

# Operator name
while true; do
    read -rp "Your operator name [$DETECTED_USER]: " INPUT_USER
    OPERATOR_NAME="${INPUT_USER:-$DETECTED_USER}"
    # Auto-lowercase
    OPERATOR_NAME=$(echo "$OPERATOR_NAME" | tr '[:upper:]' '[:lower:]')
    if echo "$OPERATOR_NAME" | grep -qE '^[a-z][a-z0-9_-]{0,31}$'; then
        break
    fi
    warn "Invalid name '$OPERATOR_NAME'. Must be lowercase, start with letter, 1-32 chars, only a-z 0-9 _ -. Try again."
done

# Public IP — allow-list (supports multiple entries: home + VPN + office)
if [ -n "$DETECTED_IP" ]; then
    success "Detected egress IP: $DETECTED_IP"
else
    warn "Could not auto-detect your egress IP — enter it manually below."
fi
print_ip_guidance
collect_allowed_entries "$DETECTED_IP"

# Region
read -rp "AWS region [$DETECTED_REGION]: " INPUT_REGION
AWS_REGION="${INPUT_REGION:-$DETECTED_REGION}"

# Second operator (optional)
echo ""
read -rp "Second operator SSH public key (paste full key, or press Enter to skip): " OP2_KEY
OP2_NAME=""
OP2_IP=""
if [ -n "$OP2_KEY" ]; then
    # Validate second operator's key
    if ! echo "$OP2_KEY" | grep -qE '^ssh-(ed25519|rsa|ecdsa-sha2-nistp[0-9]+) [A-Za-z0-9+/=]+'; then
        error "Invalid SSH public key format for second operator"
    fi
    while true; do
        read -rp "Second operator name: " OP2_NAME
        OP2_NAME=$(echo "$OP2_NAME" | tr '[:upper:]' '[:lower:]')
        if echo "$OP2_NAME" | grep -qE '^[a-z][a-z0-9_-]{0,31}$'; then break; fi
        warn "Invalid name. Must be lowercase, start with letter, 1-32 chars. Try again."
    done
    while true; do
        read -rp "Second operator IP/CIDR: " OP2_IP
        OP2_IP=$(echo "$OP2_IP" | tr -d '[:space:]')
        if [ -z "$OP2_IP" ]; then
            warn "IP is required. Try again."
            continue
        fi
        if valid_ip_or_cidr "$OP2_IP"; then break; fi
        warn "Invalid entry '$OP2_IP' (expected IPv4 or IPv4/CIDR). Try again."
    done
    # Fold the second operator's IP into the allow-list entries.
    ALLOWED_ENTRIES+=("$(normalize_entry "$OP2_IP")")
fi

# --- Generate tfvars ---
echo ""
info "Generating $TFVARS_FILE..."

# Build the dashboard_allowed_ips array body from all collected entries
# (operator's one-or-many + any second-operator IP), de-duplicated, preserving
# order of first appearance. The trailing newline is stripped HERE (not inside
# the heredoc) because ANSI-C $'\n' quoting is not honored inside heredoc text,
# which would otherwise leave a stray blank line before the closing bracket.
ALLOWED_IPS_LINES=""
declare -a _SEEN=()
for e in "${ALLOWED_ENTRIES[@]}"; do
    _dup=false
    for s in "${_SEEN[@]:-}"; do
        [ "$s" = "$e" ] && { _dup=true; break; }
    done
    [ "$_dup" = true ] && continue
    _SEEN+=("$e")
    ALLOWED_IPS_LINES+="  \"$e\","$'\n'
done
ALLOWED_IPS_BLOCK="${ALLOWED_IPS_LINES%$'\n'}"

mkdir -p "$CONFIGS_DIR"
cat > "$TFVARS_FILE" <<EOF
# Dashboard Server Configuration
# Generated by setup-dashboard.sh on $(date)

enable_dashboard_server = true
aws_region              = "$AWS_REGION"

dashboard_allowed_ips = [
$ALLOWED_IPS_BLOCK
]

operator_ssh_public_keys = {
  "$OPERATOR_NAME" = "$SSH_KEY_CONTENT"
$([ -n "$OP2_KEY" ] && echo "  \"$OP2_NAME\" = \"$OP2_KEY\"")
}
EOF

success "Generated: $TFVARS_FILE"

# --- Find existing deployment tfvars (provides root variables like project_name, environment) ---
EXISTING_TFVARS=""
for candidate in "$CONFIGS_DIR/terraform.tfvars" "$CONFIGS_DIR"/*.tfvars; do
    if [ -f "$candidate" ] && [ "$candidate" != "$TFVARS_FILE" ]; then
        EXISTING_TFVARS="$candidate"
        break
    fi
done

# --- Terraform ---
echo ""
info "Initializing Terraform..."
cd "$TERRAFORM_DIR"
terraform init

info "Planning dashboard server..."
PLAN_CMD="terraform plan -var-file=$TFVARS_FILE -target=module.dashboard_server -out=dashboard.tfplan"
if [ -n "$EXISTING_TFVARS" ]; then
    info "Using existing config: $EXISTING_TFVARS"
    PLAN_CMD="terraform plan -var-file=$EXISTING_TFVARS -var-file=$TFVARS_FILE -target=module.dashboard_server -out=dashboard.tfplan"
fi
eval "$PLAN_CMD"

echo ""
read -rp "Apply this plan? (yes/no): " CONFIRM
[ "$CONFIRM" = "yes" ] || { warn "Aborted."; exit 0; }

info "Applying..."
terraform apply dashboard.tfplan
rm -f dashboard.tfplan

# Get the dashboard IP
DASHBOARD_IP=$(terraform output -raw dashboard_public_ip 2>/dev/null || echo "")
[ -n "$DASHBOARD_IP" ] || error "Could not determine dashboard IP from Terraform output"

success "Dashboard server provisioned: $DASHBOARD_IP"

# --- Wait for instance ---
echo ""
info "Waiting for instance to be ready (this may take 2-3 minutes)..."
INSTANCE_ID=$(terraform output -raw dashboard_instance_id 2>/dev/null || echo "")
if [ -n "$INSTANCE_ID" ]; then
    aws ec2 wait instance-status-ok --instance-ids "$INSTANCE_ID" --region "$AWS_REGION" 2>/dev/null || true
fi
# Extra wait for user_data to complete
sleep 30

# --- Rsync codebase ---
# Note: --no-perms/--no-owner/--no-group preserve the server's setgid ownership
# model (dashboard:redteam, mode 2775) that user_data.sh established on /opt/redteam.
# configs/*.tfvars are intentionally NOT excluded here so the freshly generated
# dashboard.tfvars (and terraform.tfvars, if present) reach the server on first provision.
echo ""
info "Copying codebase to server..."
SSH_KEY_PRIVATE="${SSH_KEY_PATH%.pub}"
rsync -rltz --progress --no-perms --no-owner --no-group \
    --exclude='uploads/' \
    --exclude='uploads_client/' \
    --exclude='uploads_tools/' \
    --exclude='local-only/' \
    --exclude='.git/' \
    --exclude='venv/' \
    --exclude='logs/' \
    --exclude='terraform.tfstate*' \
    --exclude='*.tfplan' \
    --exclude='.terraform/' \
    --exclude='.DS_Store' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    -e "ssh -i $SSH_KEY_PRIVATE -o StrictHostKeyChecking=accept-new" \
    "$PROJECT_ROOT/" \
    "$OPERATOR_NAME@$DASHBOARD_IP:/opt/redteam/" || true
# rsync exit code 23 = partial transfer (some files skipped) — acceptable

success "Codebase synced"

# --- Remote setup ---
info "Setting up dashboard on server..."
ssh -i "$SSH_KEY_PRIVATE" -o StrictHostKeyChecking=accept-new "$OPERATOR_NAME@$DASHBOARD_IP" bash <<'REMOTE'
set -euo pipefail
cd /opt/redteam

# Generate server SSH keypair (used for SSH to all deployed instances)
if [ ! -f /opt/redteam/.ssh/id_ed25519 ]; then
    mkdir -p /opt/redteam/.ssh
    ssh-keygen -t ed25519 -f /opt/redteam/.ssh/id_ed25519 -N "" -C "dashboard-server"
    # Make readable by dashboard service user
    chown dashboard:redteam /opt/redteam/.ssh/id_ed25519 /opt/redteam/.ssh/id_ed25519.pub
    chmod 600 /opt/redteam/.ssh/id_ed25519
    chmod 644 /opt/redteam/.ssh/id_ed25519.pub
    echo "Server SSH keypair generated"
fi

# Update terraform.tfvars to use the server's key for new deployments
SERVER_PUB_KEY=$(cat /opt/redteam/.ssh/id_ed25519.pub)
if grep -q "^user_public_key" /opt/redteam/configs/terraform.tfvars 2>/dev/null; then
    sed -i "s|^user_public_key = .*|user_public_key = \"$SERVER_PUB_KEY\"|" /opt/redteam/configs/terraform.tfvars
else
    echo "user_public_key = \"$SERVER_PUB_KEY\"" >> /opt/redteam/configs/terraform.tfvars
fi
echo "terraform.tfvars updated with server SSH key"

# Add dashboard peering variables if not already set
if ! grep -q "^dashboard_vpc_id" /opt/redteam/configs/terraform.tfvars 2>/dev/null; then
    # Read from backend.hcl or terraform outputs
    DASH_VPC=$(cd /opt/redteam/terraform && terraform output -raw dashboard_vpc_id 2>/dev/null || echo "")
    DASH_CIDR=$(cd /opt/redteam/terraform && terraform output -raw dashboard_vpc_cidr 2>/dev/null || echo "")
    DASH_SG=$(cd /opt/redteam/terraform && terraform output -raw dashboard_sg_id 2>/dev/null || echo "")
    if [ -n "$DASH_VPC" ]; then
        cat >> /opt/redteam/configs/terraform.tfvars <<PEERING
dashboard_vpc_id   = "$DASH_VPC"
dashboard_vpc_cidr = "$DASH_CIDR"
dashboard_sg_id    = "$DASH_SG"
PEERING
        echo "Dashboard peering variables added to terraform.tfvars"
    fi
fi

# Create venv and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Initialize Terraform with S3 backend
cd terraform
terraform init -backend-config=/opt/redteam/backend.hcl || true

# Create systemd service
sudo tee /etc/systemd/system/dashboard.service > /dev/null <<'SERVICE'
[Unit]
Description=Red Team Dashboard
After=network.target

[Service]
Type=simple
User=dashboard
Group=redteam
WorkingDirectory=/opt/redteam
ExecStart=/opt/redteam/venv/bin/python3 webapp/backend/app.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

# Hardening
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/redteam
PrivateTmp=true

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable dashboard
sudo systemctl start dashboard
REMOTE

success "Dashboard service started"

# --- Done ---
echo ""
echo "============================================"
echo "  Dashboard Server Ready!"
echo "============================================"
echo ""
echo "  IP:       $DASHBOARD_IP"
echo "  Connect:  ssh -L 5000:localhost:5000 $OPERATOR_NAME@$DASHBOARD_IP"
echo "  Open:     http://localhost:5000"
echo ""
echo "  Next steps (all in the browser at http://localhost:5000):"
echo "  1. Configure a deployment, then satisfy its prerequisites:"
echo "       - Register a domain         (docs/DOMAIN_REQUIREMENTS.md)"
echo "       - Upload Cobalt Strike      (docs/COBALT_STRIKE_DEPLOYMENT.md)"
echo "  2. Deploy and watch the streaming logs."
echo ""
echo "  Full walkthrough: docs/GETTING_STARTED.md"
echo ""
if [ -n "$OP2_NAME" ]; then
echo "  Second operator connects:"
echo "     ssh -L 5000:localhost:5000 $OP2_NAME@$DASHBOARD_IP"
echo ""
fi
echo "============================================"
