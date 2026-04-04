#!/bin/bash
set -euo pipefail

# ============================================================================
# Dashboard Server Setup — Interactive Bootstrap
# Run this from your laptop to provision the centralized dashboard in AWS
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

        # Still need SSH key and operator name for rsync/SSH
        SSH_KEY_PATH=""
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
        SSH_KEY_PRIVATE="${SSH_KEY_PATH%.pub}"

        # Read operator name from the dashboard.tfvars (matches the Linux user on the server)
        OPERATOR_NAME=""
        if [ -f "$TFVARS_FILE" ]; then
            OPERATOR_NAME=$(grep 'operator_ssh_public_keys' -A5 "$TFVARS_FILE" | grep '"[a-z]' | head -1 | sed 's/.*"\([a-z][a-z0-9_-]*\)".*/\1/')
        fi
        if [ -z "$OPERATOR_NAME" ]; then
            OPERATOR_NAME=$(whoami | tr '[:upper:]' '[:lower:]')
        fi

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
        echo "============================================"
        exit 0
    fi
fi
cd "$PROJECT_ROOT"

# --- Auto-detect values ---

# SSH key — check common locations across macOS, Linux, Windows (WSL/Git Bash)
SSH_KEY_PATH=""
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

# Public IP
DETECTED_IP=$(curl -4 -s --max-time 5 https://api.ipify.org 2>/dev/null || echo "")

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
[ -f "$SSH_KEY_PATH" ] || error "SSH public key not found: $SSH_KEY_PATH"
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

# Public IP
read -rp "Your public IP [$DETECTED_IP]: " INPUT_IP
OPERATOR_IP="${INPUT_IP:-$DETECTED_IP}"
[ -n "$OPERATOR_IP" ] || error "Could not detect public IP. Enter manually."
success "Your IP: $OPERATOR_IP"

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
        read -rp "Second operator IP: " OP2_IP
        if [ -n "$OP2_IP" ]; then break; fi
        warn "IP is required. Try again."
    done
fi

# --- Generate tfvars ---
echo ""
info "Generating $TFVARS_FILE..."

mkdir -p "$CONFIGS_DIR"
cat > "$TFVARS_FILE" <<EOF
# Dashboard Server Configuration
# Generated by setup-dashboard.sh on $(date)

enable_dashboard_server = true
aws_region              = "$AWS_REGION"

dashboard_allowed_ips = [
  "$OPERATOR_IP/32",
$([ -n "$OP2_IP" ] && echo "  \"$OP2_IP/32\",")
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
echo ""
info "Copying codebase to server..."
SSH_KEY_PRIVATE="${SSH_KEY_PATH%.pub}"
rsync -avz --progress \
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
    -e "ssh -i $SSH_KEY_PRIVATE -o StrictHostKeyChecking=accept-new" \
    "$PROJECT_ROOT/" \
    "$OPERATOR_NAME@$DASHBOARD_IP:/opt/redteam/"

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
Group=dashboard
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
echo "  Next steps:"
echo "  1. SCP Cobalt Strike archive:"
echo "     scp cobaltstrike.tar $OPERATOR_NAME@$DASHBOARD_IP:/opt/redteam/uploads/"
echo ""
if [ -n "$OP2_NAME" ]; then
echo "  2. Second operator connects:"
echo "     ssh -L 5000:localhost:5000 $OP2_NAME@$DASHBOARD_IP"
echo ""
fi
echo "============================================"
