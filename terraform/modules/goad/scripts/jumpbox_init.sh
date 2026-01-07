#!/bin/bash
# =============================================================================
# GOAD Jumpbox Initialization Script (Without Cobalt Strike)
# =============================================================================
# This script sets up the jumpbox for GOAD lab management
# For GOAD-only mode with CS, use install_cobalt_strike.sh instead
# =============================================================================

set -e

USERNAME="${username}"

# Logging
LOG_FILE="/var/log/jumpbox-init.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=============================================="
echo "GOAD Jumpbox Initialization"
echo "Started: $(date)"
echo "=============================================="

# Wait for cloud-init
while [ ! -f /var/lib/cloud/instance/boot-finished ]; do
    echo "Waiting for cloud-init..."
    sleep 5
done

# =============================================================================
# 1. System Updates
# =============================================================================
echo "[1/5] Updating system..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y

# =============================================================================
# 2. Install Required Packages
# =============================================================================
echo "[2/5] Installing packages..."
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    ansible \
    git \
    curl \
    wget \
    unzip \
    sshpass \
    net-tools \
    htop \
    tmux \
    vim \
    jq \
    nmap \
    dnsutils \
    ldap-utils \
    krb5-user \
    smbclient

# =============================================================================
# 3. Configure User
# =============================================================================
echo "[3/5] Configuring user..."

# Rename ubuntu user if different username specified
if [ "$USERNAME" != "ubuntu" ] && [ "$USERNAME" != "" ]; then
    if id "ubuntu" &>/dev/null; then
        usermod -l "$USERNAME" ubuntu
        usermod -d "/home/$USERNAME" -m "$USERNAME"
        sed -i "s/ubuntu/$USERNAME/" /etc/sudoers.d/90-cloud-init-users 2>/dev/null || true
        echo "User renamed to: $USERNAME"
    fi
fi

# =============================================================================
# 4. Install Python Tools
# =============================================================================
echo "[4/5] Installing Python tools..."

pip3 install --upgrade pip
pip3 install \
    impacket \
    bloodhound \
    ldap3 \
    pycryptodome \
    pyasn1 \
    certipy-ad \
    coercer

# =============================================================================
# 5. Create Helper Scripts
# =============================================================================
echo "[5/5] Creating helper scripts..."

# Create GOAD directory
mkdir -p /opt/goad
mkdir -p /opt/tools

# Script to check lab status
cat > /opt/goad/check-lab.sh << 'EOF'
#!/bin/bash
echo "=== GOAD Lab Status ==="
echo ""
echo "Checking connectivity to lab VMs..."
for ip in 10 11 12 20 21 22 23; do
    ping -c 1 -W 1 192.168.56.$ip > /dev/null 2>&1 && echo "192.168.56.$ip: UP" || echo "192.168.56.$ip: DOWN"
done
echo ""
echo "=== DNS Resolution ==="
nslookup sevenkingdoms.local 192.168.56.10 2>/dev/null || echo "DNS not configured yet"
EOF
chmod +x /opt/goad/check-lab.sh

# Script to run Ansible provisioning
cat > /opt/goad/provision.sh << 'EOF'
#!/bin/bash
echo "=== GOAD Ansible Provisioning ==="
echo "This will configure Active Directory on the lab VMs"
echo "This process takes 30-60 minutes"
echo ""
echo "To run: cd /opt/goad && ansible-playbook -i inventory main.yml"
EOF
chmod +x /opt/goad/provision.sh

# =============================================================================
# Complete
# =============================================================================
echo ""
echo "=============================================="
echo "GOAD Jumpbox Initialization Complete!"
echo "Finished: $(date)"
echo "=============================================="
echo ""
echo "Useful directories:"
echo "  /opt/goad   - GOAD management scripts"
echo "  /opt/tools  - Red team tools"
echo ""
echo "Check lab status: /opt/goad/check-lab.sh"
echo ""

touch /opt/goad/.init-complete

