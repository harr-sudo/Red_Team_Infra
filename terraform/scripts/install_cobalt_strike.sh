#!/bin/bash
# =============================================================================
# Centralized Cobalt Strike Installation Script
# =============================================================================
# Used by:
#   - C2 Team Servers (all modes)
#   - GOAD Jumpbox (GOAD-only mode)
#
# Variables passed via Terraform templatefile():
#   - cs_archive_s3_path: S3 path to Cobalt Strike archive
#   - cs_password: Team server password
#   - tools_repo_url: Git URL for tools repository
#   - tools_repo_branch: Branch to clone
#   - server_role: "c2_server" or "jumpbox"
# =============================================================================

set -e

# Variables from Terraform templatefile()
CS_ARCHIVE_S3_PATH="${cs_archive_s3_path}"
CS_PASSWORD="${cs_password}"
TOOLS_REPO_URL="${tools_repo_url}"
TOOLS_REPO_BRANCH="${tools_repo_branch}"
SERVER_ROLE="${server_role}"

# Logging
LOG_FILE="/var/log/cs-install.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=============================================="
echo "Cobalt Strike Installation Script"
echo "Started: $(date)"
echo "Role: $SERVER_ROLE"
echo "=============================================="

# =============================================================================
# 1. System Updates and Dependencies
# =============================================================================
echo "[1/6] Installing dependencies..."

# Wait for cloud-init to complete
while [ ! -f /var/lib/cloud/instance/boot-finished ]; do
    echo "Waiting for cloud-init to complete..."
    sleep 5
done

# Update system
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y

# Install required packages
apt-get install -y \
    openjdk-11-jdk \
    git \
    unzip \
    curl \
    wget \
    awscli \
    net-tools \
    htop \
    tmux \
    vim \
    jq

echo "Dependencies installed successfully"

# =============================================================================
# 2. Create Directories
# =============================================================================
echo "[2/6] Creating directories..."

mkdir -p /opt/cobaltstrike
mkdir -p /opt/tools
mkdir -p /opt/logs

# Set ownership
chown -R ubuntu:ubuntu /opt/cobaltstrike
chown -R ubuntu:ubuntu /opt/tools
chown -R ubuntu:ubuntu /opt/logs

echo "Directories created"

# =============================================================================
# 3. Download and Extract Cobalt Strike
# =============================================================================
echo "[3/6] Downloading Cobalt Strike from S3..."

if [ -n "$CS_ARCHIVE_S3_PATH" ] && [ "$CS_ARCHIVE_S3_PATH" != "" ]; then
    # Download from S3
    aws s3 cp "$CS_ARCHIVE_S3_PATH" /tmp/cobaltstrike.tar.gz
    
    if [ $? -eq 0 ]; then
        echo "Downloaded Cobalt Strike archive"
        
        # Extract
        tar -xzf /tmp/cobaltstrike.tar.gz -C /opt/cobaltstrike --strip-components=1
        
        # Clean up
        rm -f /tmp/cobaltstrike.tar.gz
        
        # Set permissions
        chown -R ubuntu:ubuntu /opt/cobaltstrike
        chmod +x /opt/cobaltstrike/teamserver 2>/dev/null || true
        chmod +x /opt/cobaltstrike/cobaltstrike 2>/dev/null || true
        
        echo "Cobalt Strike extracted successfully"
    else
        echo "WARNING: Failed to download Cobalt Strike from S3"
        echo "You will need to manually install Cobalt Strike"
    fi
else
    echo "No Cobalt Strike S3 path provided"
    echo "Skipping Cobalt Strike download - manual installation required"
fi

# =============================================================================
# 4. Clone Tools Repository
# =============================================================================
echo "[4/6] Cloning tools repository..."

if [ -n "$TOOLS_REPO_URL" ] && [ "$TOOLS_REPO_URL" != "" ]; then
    cd /opt/tools
    
    # Clone the repository
    if git clone --branch "$TOOLS_REPO_BRANCH" "$TOOLS_REPO_URL" . 2>/dev/null; then
        echo "Tools repository cloned successfully"
        chown -R ubuntu:ubuntu /opt/tools
    else
        echo "WARNING: Failed to clone tools repository"
        echo "URL: $TOOLS_REPO_URL"
        echo "Branch: $TOOLS_REPO_BRANCH"
    fi
else
    echo "No tools repository URL provided, skipping"
fi

# =============================================================================
# 5. Create Systemd Service for Team Server
# =============================================================================
echo "[5/6] Creating systemd service..."

if [ -n "$CS_PASSWORD" ] && [ "$CS_PASSWORD" != "" ] && [ -f /opt/cobaltstrike/teamserver ]; then
    cat > /etc/systemd/system/teamserver.service << 'SERVICEEOF'
[Unit]
Description=Cobalt Strike Team Server
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/cobaltstrike
ExecStart=/opt/cobaltstrike/teamserver 0.0.0.0 ${cs_password}
Restart=on-failure
RestartSec=10
StandardOutput=append:/opt/logs/teamserver.log
StandardError=append:/opt/logs/teamserver-error.log

[Install]
WantedBy=multi-user.target
SERVICEEOF

    # Reload systemd and enable service
    systemctl daemon-reload
    systemctl enable teamserver
    
    # Start the service
    systemctl start teamserver
    
    echo "Team server service created and started"
    echo "Team server running on port 50050"
else
    echo "Skipping team server service creation"
    echo "Either password not set or teamserver binary not found"
fi

# =============================================================================
# 6. Create Helper Scripts
# =============================================================================
echo "[6/6] Creating helper scripts..."

# Script to check team server status
cat > /opt/cobaltstrike/check-status.sh << 'EOF'
#!/bin/bash
echo "=== Team Server Status ==="
systemctl status teamserver --no-pager
echo ""
echo "=== Listening Ports ==="
netstat -tlnp | grep -E '(50050|443|80)'
echo ""
echo "=== Recent Logs ==="
tail -20 /opt/logs/teamserver.log 2>/dev/null || echo "No logs yet"
EOF
chmod +x /opt/cobaltstrike/check-status.sh

# Script to restart team server
cat > /opt/cobaltstrike/restart-teamserver.sh << 'EOF'
#!/bin/bash
echo "Restarting team server..."
sudo systemctl restart teamserver
sleep 3
sudo systemctl status teamserver --no-pager
EOF
chmod +x /opt/cobaltstrike/restart-teamserver.sh

# Script to view logs
cat > /opt/cobaltstrike/view-logs.sh << 'EOF'
#!/bin/bash
tail -f /opt/logs/teamserver.log
EOF
chmod +x /opt/cobaltstrike/view-logs.sh

chown -R ubuntu:ubuntu /opt/cobaltstrike

# =============================================================================
# Installation Complete
# =============================================================================
echo ""
echo "=============================================="
echo "Cobalt Strike Installation Complete!"
echo "Finished: $(date)"
echo "=============================================="
echo ""
echo "Useful commands:"
echo "  Check status:  /opt/cobaltstrike/check-status.sh"
echo "  Restart:       /opt/cobaltstrike/restart-teamserver.sh"
echo "  View logs:     /opt/cobaltstrike/view-logs.sh"
echo ""
echo "Team server port: 50050"
echo "Tools directory:  /opt/tools"
echo ""

# Create completion marker
touch /opt/cobaltstrike/.install-complete

