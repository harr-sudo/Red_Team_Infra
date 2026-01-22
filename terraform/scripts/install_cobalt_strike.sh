#!/bin/bash
# =============================================================================
# Cobalt Strike Installation Script (Legacy/C2-Only Mode)
# =============================================================================
# This script is used ONLY for standalone C2 infrastructure deployments
# (without GOAD lab). For GOAD deployments, use teamserver_init.sh instead.
#
# Variables passed via Terraform templatefile():
#   - cs_archive_s3_path: S3 path to Cobalt Strike archive
#   - cs_password: Team server password
#   - tools_repo_url: Git URL for tools repository (optional)
#   - tools_repo_branch: Branch to clone (optional)
#   - server_role: "c2_server" (legacy) - always treated as team server only
#   - hostname: OS hostname to set
# =============================================================================

set -e

# Variables from Terraform templatefile()
CS_ARCHIVE_S3_PATH="${cs_archive_s3_path}"
CS_PASSWORD="${cs_password}"
TOOLS_REPO_URL="${tools_repo_url}"
TOOLS_REPO_BRANCH="${tools_repo_branch}"
SERVER_ROLE="${server_role}"
HOSTNAME="${hostname}"

# Logging
LOG_FILE="/var/log/cs-install.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=============================================="
echo "Cobalt Strike Team Server Installation"
echo "Started: $(date)"
echo "Role: Team Server ONLY"
echo "=============================================="

# Set hostname
if [ -n "$HOSTNAME" ]; then
    hostnamectl set-hostname "$HOSTNAME"
    echo "127.0.0.1 $HOSTNAME" >> /etc/hosts
    echo "Hostname set to: $HOSTNAME"
fi

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

# Install required packages (minimal for team server)
apt-get install -y \
    openjdk-17-jdk \
    git \
    unzip \
    curl \
    wget \
    awscli \
    net-tools \
    htop \
    tmux \
    vim

echo "Dependencies installed successfully"

# =============================================================================
# 2. Create Directories
# =============================================================================
echo "[2/6] Creating directories..."

mkdir -p /opt/cobaltstrike/server
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

CS_EXTRACTED=false
LICENSE_STATUS="unknown"

if [ -n "$CS_ARCHIVE_S3_PATH" ] && [ "$CS_ARCHIVE_S3_PATH" != "" ]; then
    # Download from S3
    aws s3 cp "$CS_ARCHIVE_S3_PATH" /tmp/cs-archive
    
    if [ $? -eq 0 ] && [ -f /tmp/cs-archive ]; then
        echo "Downloaded Cobalt Strike archive"
        
        # Detect file type and extract accordingly
        FILE_TYPE=$(file /tmp/cs-archive)
        echo "Archive type: $FILE_TYPE"
        
        if echo "$FILE_TYPE" | grep -q "gzip compressed"; then
            echo "Extracting as gzip compressed tar..."
            tar -xzf /tmp/cs-archive -C /opt/cobaltstrike --strip-components=1 && CS_EXTRACTED=true
        elif echo "$FILE_TYPE" | grep -q "POSIX tar archive"; then
            echo "Extracting as plain tar..."
            tar -xf /tmp/cs-archive -C /opt/cobaltstrike --strip-components=1 && CS_EXTRACTED=true
        elif echo "$FILE_TYPE" | grep -q "Zip archive"; then
            echo "Extracting as zip..."
            unzip -o /tmp/cs-archive -d /opt/cobaltstrike && CS_EXTRACTED=true
        else
            echo "WARNING: Unknown archive type, trying multiple methods..."
            tar -xf /tmp/cs-archive -C /opt/cobaltstrike --strip-components=1 2>/dev/null && CS_EXTRACTED=true || \
            tar -xzf /tmp/cs-archive -C /opt/cobaltstrike --strip-components=1 2>/dev/null && CS_EXTRACTED=true || \
            echo "ERROR: Failed to extract archive"
        fi
        
        # Clean up
        rm -f /tmp/cs-archive
        
        if [ "$CS_EXTRACTED" = true ]; then
            echo "Cobalt Strike extracted successfully"
            
            # Extract TeamServerImage from JAR if not present (CS 4.6+ stores it in the JAR)
            if [ -f /opt/cobaltstrike/cobaltstrike.jar ] && [ ! -f /opt/cobaltstrike/server/TeamServerImage ]; then
                echo "Extracting TeamServerImage from JAR (CS 4.6+)..."
                cd /opt/cobaltstrike/server
                unzip -o ../cobaltstrike.jar TeamServerImage -d . 2>/dev/null || true
                chmod +x TeamServerImage 2>/dev/null || true
            fi
            
            # Set permissions
            chown -R ubuntu:ubuntu /opt/cobaltstrike
            chmod +x /opt/cobaltstrike/server/teamserver 2>/dev/null || true
            chmod +x /opt/cobaltstrike/update 2>/dev/null || true
            
            # Check if license activation is needed
            if [ -f /opt/cobaltstrike/server/TeamServerImage ]; then
                cd /opt/cobaltstrike/server
                if timeout 5 ./TeamServerImage --help 2>&1 | grep -q "Please run the 'update' program"; then
                    LICENSE_STATUS="needs_activation"
                    echo "LICENSE: Needs activation"
                else
                    LICENSE_STATUS="ready"
                    echo "LICENSE: Ready"
                fi
            fi
        fi
    else
        echo "WARNING: Failed to download Cobalt Strike from S3"
        echo "You will need to manually install Cobalt Strike"
    fi
else
    echo "No Cobalt Strike S3 path provided"
    echo "Skipping Cobalt Strike download - manual installation required"
fi

# =============================================================================
# 4. Clone Tools Repository (Optional)
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

if [ -f /opt/cobaltstrike/server/teamserver ]; then
    # Create systemd service file
    cat > /etc/systemd/system/teamserver.service << EOF
[Unit]
Description=Cobalt Strike Team Server
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/cobaltstrike/server
ExecStart=/opt/cobaltstrike/server/teamserver 0.0.0.0 $CS_PASSWORD
Restart=on-failure
RestartSec=10
StandardOutput=append:/opt/logs/teamserver.log
StandardError=append:/opt/logs/teamserver-error.log

[Install]
WantedBy=multi-user.target
EOF

    # Reload systemd and enable service
    systemctl daemon-reload
    systemctl enable teamserver
    
    # Only start if we have a password AND license is ready
    if [ -n "$CS_PASSWORD" ] && [ "$CS_PASSWORD" != "" ] && [ "$LICENSE_STATUS" = "ready" ]; then
        echo "Starting team server..."
        systemctl start teamserver
        echo "Team server service created and started"
        echo "Team server running on port 50050"
    else
        echo "Team server service created but NOT started"
        if [ "$LICENSE_STATUS" = "needs_activation" ]; then
            echo "REASON: License activation required"
            echo "Run: cd /opt/cobaltstrike && sudo ./update"
        elif [ -z "$CS_PASSWORD" ]; then
            echo "REASON: No password configured"
        fi
    fi
else
    echo "Skipping team server service creation - teamserver script not found"
fi

# =============================================================================
# 6. Create Helper Scripts and README
# =============================================================================
echo "[6/6] Creating helper scripts..."

# README with license activation instructions
cat > /home/ubuntu/README.txt << 'READMEEOF'
================================================================================
                    COBALT STRIKE TEAM SERVER
================================================================================

IMPORTANT: LICENSE ACTIVATION REQUIRED
--------------------------------------
Before the team server can run, you must activate your Cobalt Strike license:

    cd /opt/cobaltstrike
    sudo ./update

Enter your license key when prompted. This downloads the licensed binaries.

AFTER LICENSE ACTIVATION
------------------------
Start the team server:

    sudo systemctl start teamserver

Or manually:

    cd /opt/cobaltstrike/server
    sudo ./teamserver 0.0.0.0 <YOUR_PASSWORD>

USEFUL COMMANDS
---------------
Check status:     /opt/cobaltstrike/check-status.sh
Restart:          sudo systemctl restart teamserver
View logs:        tail -f /opt/logs/teamserver.log
Stop:             sudo systemctl stop teamserver

CONNECTION INFO
---------------
Team Server Port: 50050
Connect your CS Client to: <THIS_SERVER_IP>:50050

================================================================================
READMEEOF
chown ubuntu:ubuntu /home/ubuntu/README.txt

# Script to check team server status
cat > /opt/cobaltstrike/check-status.sh << 'EOF'
#!/bin/bash
echo "=== Cobalt Strike Team Server Status ==="
echo ""

# Check license status
if [ -f /opt/cobaltstrike/server/TeamServerImage ]; then
    cd /opt/cobaltstrike/server
    if timeout 3 ./TeamServerImage --help 2>&1 | grep -q "Please run the 'update' program"; then
        echo "LICENSE: ❌ NOT ACTIVATED"
        echo "         Run: cd /opt/cobaltstrike && sudo ./update"
        echo ""
    else
        echo "LICENSE: ✅ Activated"
        echo ""
    fi
else
    echo "LICENSE: ⚠️  TeamServerImage not found"
    echo ""
fi

echo "=== Service Status ==="
systemctl status teamserver --no-pager 2>/dev/null || echo "Service not running"
echo ""

echo "=== Listening Ports ==="
netstat -tlnp 2>/dev/null | grep -E '(50050|443|80)' || echo "Not listening on expected ports"
echo ""

echo "=== Recent Logs ==="
tail -20 /opt/logs/teamserver.log 2>/dev/null || echo "No logs yet"
EOF
chmod +x /opt/cobaltstrike/check-status.sh

# Script to activate license
cat > /opt/cobaltstrike/activate-license.sh << 'EOF'
#!/bin/bash
echo "=== Cobalt Strike License Activation ==="
echo ""
echo "This will run the Cobalt Strike update program."
echo "You will need your license key."
echo ""
cd /opt/cobaltstrike
sudo ./update
echo ""
echo "If activation was successful, start the team server with:"
echo "    sudo systemctl start teamserver"
EOF
chmod +x /opt/cobaltstrike/activate-license.sh

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
echo "Installation Complete!"
echo "Finished: $(date)"
echo "=============================================="
echo ""
if [ "$LICENSE_STATUS" = "needs_activation" ]; then
    echo "⚠️  NEXT STEP: Activate your Cobalt Strike license"
    echo "    cd /opt/cobaltstrike && sudo ./update"
    echo ""
fi
echo "=== Cobalt Strike ==="
echo "  Check status:  /opt/cobaltstrike/check-status.sh"
echo "  Activate:      /opt/cobaltstrike/activate-license.sh"
echo "  Restart:       /opt/cobaltstrike/restart-teamserver.sh"
echo "  View logs:     /opt/cobaltstrike/view-logs.sh"
echo "  Team server:   Port 50050"
echo ""
echo "=== Tools ==="
echo "  Tools repo:    /opt/tools"
echo ""

# Create completion marker
touch /opt/cobaltstrike/.install-complete
echo "LICENSE_STATUS=$LICENSE_STATUS" > /opt/cobaltstrike/bootstrap-status
