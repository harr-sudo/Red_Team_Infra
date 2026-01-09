#!/bin/bash
# =============================================================================
# GOAD Jumpbox Initialization Script (Minimal SSH Gateway)
# =============================================================================
# This script sets up a minimal, hardened SSH gateway (bastion host)
# The jumpbox is ONLY for SSH access - all tools are on the Attack Box
#
# Security: This jumpbox stores the INTERNAL private key for accessing
#           Team Server and Attack Box in the private subnet.
# =============================================================================

set -e

USERNAME="${username}"
ATTACKBOX_IP="${attackbox_ip}"
TEAMSERVER_IP="${teamserver_ip}"
INSTALL_CS="${install_cs}"
INTERNAL_KEY="${internal_key}"

# Logging
LOG_FILE="/var/log/jumpbox-init.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=============================================="
echo "GOAD Jumpbox (SSH Gateway) Initialization"
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
# 2. Install Minimal Required Packages
# =============================================================================
echo "[2/5] Installing minimal packages..."
apt-get install -y \
    curl \
    wget \
    net-tools \
    htop \
    tmux \
    vim \
    jq \
    nc

# =============================================================================
# 3. Harden SSH Configuration
# =============================================================================
echo "[3/5] Hardening SSH configuration..."

# Backup original config
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak

# Apply hardened settings
cat >> /etc/ssh/sshd_config << 'EOF'

# Hardened SSH Settings for Bastion Host
PermitRootLogin no
MaxAuthTries 3
MaxSessions 10
ClientAliveInterval 300
ClientAliveCountMax 2
AllowAgentForwarding yes
AllowTcpForwarding yes
X11Forwarding no
EOF

# Restart SSH
systemctl restart sshd

# =============================================================================
# 4. Install Internal SSH Key (for accessing Team Server)
# =============================================================================
echo "[4/5] Setting up internal SSH key..."

if [ "$INSTALL_CS" = "true" ] && [ -n "$INTERNAL_KEY" ]; then
    # Create SSH directory for ubuntu user
    mkdir -p /home/ubuntu/.ssh
    chmod 700 /home/ubuntu/.ssh
    
    # Save the internal private key
    echo "$INTERNAL_KEY" > /home/ubuntu/.ssh/internal_key
    chmod 600 /home/ubuntu/.ssh/internal_key
    chown ubuntu:ubuntu /home/ubuntu/.ssh/internal_key
    
    # Create SSH config for easy access to internal hosts
    cat > /home/ubuntu/.ssh/config << SSHCONFIG
# Internal SSH Configuration
# This key is for accessing hosts in the PRIVATE subnet only

Host teamserver ts
    HostName $TEAMSERVER_IP
    User ubuntu
    IdentityFile ~/.ssh/internal_key
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null

Host attackbox ab
    HostName $ATTACKBOX_IP
    User ubuntu
    IdentityFile ~/.ssh/internal_key
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null

# Wildcard for any 192.168.56.x host
Host 192.168.56.*
    User ubuntu
    IdentityFile ~/.ssh/internal_key
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
SSHCONFIG
    chmod 600 /home/ubuntu/.ssh/config
    chown ubuntu:ubuntu /home/ubuntu/.ssh/config
    
    echo "Internal SSH key and config installed"
    echo "  - ssh teamserver (or ssh ts) → Team Server"
    echo "  - ssh attackbox (or ssh ab) → Attack Box"
fi

# =============================================================================
# 5. Create Helper Scripts and Connection Info
# =============================================================================
echo "[5/5] Creating helper scripts..."

# Create directory for scripts
mkdir -p /opt/jumpbox

# Create comprehensive README on the jumpbox
cat > /home/ubuntu/README.txt << 'README'
================================================================================
                    JUMPBOX (SSH GATEWAY) - QUICK START GUIDE
================================================================================

ROLE: Minimal SSH Gateway / Bastion Host

This is a MINIMAL jumpbox. Do NOT install tools here!
All offensive tools are on the Attack Box.

================================================================================
                              SSH KEY INFORMATION
================================================================================

This jumpbox has TWO types of keys:

1. EXTERNAL KEY (authorized_keys):
   - Used by YOUR LOCAL MACHINE to SSH into this jumpbox
   - You downloaded this key from the web app to ~/.ssh/

2. INTERNAL KEY (~/.ssh/internal_key):
   - Used to SSH FROM THIS JUMPBOX to the Team Server
   - Pre-installed and configured

IMPORTANT SECURITY NOTE:
  - External key can ONLY access this Jumpbox
  - Internal key can ONLY access Team Server (not your machine!)
  - Compromise of one key doesn't compromise the other

================================================================================
                            QUICK COMMANDS
================================================================================

From this Jumpbox, connect to internal hosts:

  ssh teamserver      (or: ssh ts)   → CS Team Server
  ssh attackbox       (or: ssh ab)   → Attack Box (if Linux)
  ssh 192.168.56.10                  → Windows DC01

Show connection info:
  /opt/jumpbox/show-connections.sh

Check network connectivity:
  /opt/jumpbox/check-network.sh

================================================================================
                              RDP TO WINDOWS VMs
================================================================================

To RDP to Windows AD VMs, create an SSH tunnel from YOUR LOCAL MACHINE:

  # On your local machine (not here!):
  ssh -i ~/.ssh/<jumpbox-key>.pem -L 3389:192.168.56.10:3389 ubuntu@<JUMPBOX_IP>
  
  # Then RDP to:
  localhost:3389

================================================================================
                              NETWORK ACCESS
================================================================================

From this Jumpbox, you can reach:

  Team Server:     192.168.56.40 (SSH: ssh teamserver)
  Attack Box:      192.168.56.50 (SSH: ssh attackbox)
  GOAD AD VMs:     192.168.56.10-25 (DC01, DC02, Servers)
  Internet:        Yes (public subnet)

================================================================================
                              SECURITY NOTES
================================================================================

1. This jumpbox has MINIMAL software installed
2. Do NOT store sensitive data here
3. Do NOT install offensive tools here (use Attack Box)
4. SSH sessions are logged in /var/log/auth.log
5. The internal_key file is chmod 600 (only ubuntu user can read)

================================================================================
                              TROUBLESHOOTING
================================================================================

Can't SSH to Team Server?
  - Check key: ls -la ~/.ssh/internal_key
  - Test connection: ssh -v teamserver
  - Check Team Server is up: ping 192.168.56.40

Can't reach Windows VMs?
  - Check network: /opt/jumpbox/check-network.sh
  - VMs may still be booting (wait 5-10 mins)

================================================================================
Created by Red Team Infrastructure Deployment Tool
================================================================================
README

chown ubuntu:ubuntu /home/ubuntu/README.txt
chmod 644 /home/ubuntu/README.txt

# Create connection info script
cat > /opt/jumpbox/show-connections.sh << 'SCRIPT'
#!/bin/bash
echo "=============================================="
echo "GOAD Lab Connection Information"
echo "=============================================="
echo ""
echo "=== This Jumpbox ==="
echo "  Role: SSH Gateway (Bastion Host)"
echo "  IP:   $(hostname -I | awk '{print $1}')"
echo ""
SCRIPT

# Add internal hosts info if CS is installed
if [ "$INSTALL_CS" = "true" ] && [ -n "$TEAMSERVER_IP" ]; then
    cat >> /opt/jumpbox/show-connections.sh << SCRIPT
echo "=== Team Server (CS Only) ==="
echo "  IP:   $TEAMSERVER_IP"
echo "  SSH:  ssh teamserver  (or: ssh ts)"
echo "  CS:   Port 50050"
echo ""
echo "=== Attack Box (Windows) ==="
echo "  IP:   $ATTACKBOX_IP"
echo "  RDP:  Via SSH tunnel from your local machine"
echo ""
echo "=== Quick Commands (from this jumpbox) ==="
echo "  ssh teamserver    - Connect to Team Server"
echo "  ssh attackbox     - Connect to Attack Box (if Linux)"
echo ""
SCRIPT
fi

cat >> /opt/jumpbox/show-connections.sh << 'SCRIPT'
echo "=== Windows AD VMs (Private Network) ==="
echo "  DC01:  192.168.56.10 (Domain Controller)"
echo "  DC02:  192.168.56.11 (if deployed)"
echo "  SRV01: 192.168.56.20 (if deployed)"
echo ""
echo "  RDP via SSH tunnel (from your local machine):"
echo "    ssh -L 3389:192.168.56.10:3389 ubuntu@<JUMPBOX_PUBLIC_IP>"
echo "    Then RDP to localhost:3389"
echo ""
echo "=============================================="
SCRIPT
chmod +x /opt/jumpbox/show-connections.sh

# Create quick status check script
cat > /opt/jumpbox/check-network.sh << 'EOF'
#!/bin/bash
echo "=== Network Connectivity Check ==="
echo ""
echo "Checking internal hosts..."
for ip in 10 11 12 20 21 22 23 40 50; do
    if ping -c 1 -W 1 192.168.56.$ip > /dev/null 2>&1; then
        echo "192.168.56.$ip: ✅ UP"
    else
        echo "192.168.56.$ip: ❌ DOWN"
    fi
done
echo ""
echo "Checking WinRM (5985)..."
for ip in 10 11 12 20 21 22 23; do
    if nc -z -w 2 192.168.56.$ip 5985 2>/dev/null; then
        echo "192.168.56.$ip:5985: ✅ OPEN"
    fi
done
echo ""
echo "Checking Team Server (50050)..."
if nc -z -w 2 192.168.56.40 50050 2>/dev/null; then
    echo "192.168.56.40:50050: ✅ OPEN (Team Server)"
fi
EOF
chmod +x /opt/jumpbox/check-network.sh

# Set ownership
chown -R ubuntu:ubuntu /opt/jumpbox

# =============================================================================
# Complete
# =============================================================================
echo ""
echo "=============================================="
echo "Jumpbox (SSH Gateway) Initialization Complete!"
echo "Finished: $(date)"
echo "=============================================="
echo ""
echo "This is a MINIMAL SSH gateway. Do NOT install tools here."
echo ""
echo "Useful commands:"
echo "  Show connections:  /opt/jumpbox/show-connections.sh"
echo "  Check network:     /opt/jumpbox/check-network.sh"
echo ""

if [ "$INSTALL_CS" = "true" ] && [ -n "$TEAMSERVER_IP" ]; then
    echo "=== Internal Access (from this jumpbox) ==="
    echo "  ssh teamserver    - Connect to CS Team Server"
    echo "  ssh attackbox     - Connect to Attack Box"
    echo ""
fi

touch /opt/jumpbox/.init-complete

