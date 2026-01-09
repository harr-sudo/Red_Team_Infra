#!/bin/bash
# =============================================================================
# Team Server Initialization Script (Cobalt Strike ONLY)
# =============================================================================
# This script sets up a MINIMAL Cobalt Strike Team Server
# NO other tools - just Java + CS teamserver daemon
# =============================================================================

set -e

# Variables from Terraform templatefile()
CS_ARCHIVE_S3_PATH="${cs_archive_s3_path}"
CS_PASSWORD="${cs_password}"

# Logging
LOG_FILE="/var/log/teamserver-init.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=============================================="
echo "Cobalt Strike Team Server Initialization"
echo "Started: $(date)"
echo "This is a MINIMAL server - CS teamserver ONLY"
echo "=============================================="

# Wait for cloud-init to complete
while [ ! -f /var/lib/cloud/instance/boot-finished ]; do
    echo "Waiting for cloud-init to complete..."
    sleep 5
done

# =============================================================================
# 1. System Updates and Minimal Dependencies
# =============================================================================
echo "[1/5] Installing minimal dependencies..."

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y

# Install ONLY what's needed for Cobalt Strike
apt-get install -y \
    openjdk-11-jdk \
    awscli \
    net-tools \
    curl \
    wget \
    unzip

echo "Dependencies installed"

# =============================================================================
# 2. Create Directories
# =============================================================================
echo "[2/5] Creating directories..."

mkdir -p /opt/cobaltstrike
mkdir -p /opt/logs

chown -R ubuntu:ubuntu /opt/cobaltstrike
chown -R ubuntu:ubuntu /opt/logs

echo "Directories created"

# =============================================================================
# 3. Download and Extract Cobalt Strike
# =============================================================================
echo "[3/5] Downloading Cobalt Strike from S3..."

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
# 4. Create Systemd Service for Team Server
# =============================================================================
echo "[4/5] Creating systemd service..."

if [ -n "$CS_PASSWORD" ] && [ "$CS_PASSWORD" != "" ] && [ -f /opt/cobaltstrike/teamserver ]; then
    # Create systemd service file
    cat > /etc/systemd/system/teamserver.service << EOF
[Unit]
Description=Cobalt Strike Team Server
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/cobaltstrike
ExecStart=/opt/cobaltstrike/teamserver 0.0.0.0 $CS_PASSWORD
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
    
    # Start the service
    systemctl start teamserver
    
    echo "Team server service created and started"
    echo "Team server running on port 50050"
else
    echo "Skipping team server service creation"
    echo "Either password not set or teamserver binary not found"
fi

# =============================================================================
# 5. Create Helper Scripts and README
# =============================================================================
echo "[5/5] Creating helper scripts..."

# Create comprehensive README
cat > /home/ubuntu/README.txt << 'README'
================================================================================
                    TEAM SERVER - QUICK START GUIDE
================================================================================

ROLE: Cobalt Strike Team Server ONLY

This is a MINIMAL server. It runs ONLY the CS teamserver daemon.
NO offensive tools are installed here - use the Attack Box for tools.

================================================================================
                              SSH KEY INFORMATION
================================================================================

This server uses the INTERNAL SSH key for access.

Who can access this server:
  ✅ Jumpbox (has internal key at ~/.ssh/internal_key)
  ✅ Attack Box WSL (has internal key at ~/.ssh/teamserver_key)
  ❌ Your local machine (external key doesn't work here!)

IMPORTANT SECURITY NOTE:
  - This server has NO outbound SSH keys
  - It cannot initiate connections to other hosts
  - Compromise here is contained - no lateral movement possible

================================================================================
                              TEAM SERVER STATUS
================================================================================

Check if team server is running:
  /opt/cobaltstrike/check-status.sh

Restart team server:
  /opt/cobaltstrike/restart-teamserver.sh

View live logs:
  /opt/cobaltstrike/view-logs.sh

Check listening ports:
  netstat -tlnp | grep -E '(50050|443|80)'

================================================================================
                              CONNECTING CS CLIENT
================================================================================

FROM ATTACK BOX (Windows):
  1. RDP to Attack Box
  2. Run CS Client: java -jar C:\Tools\cobaltstrike\cobaltstrike.jar
  3. Connect to: 192.168.56.40:50050

FROM YOUR LOCAL MACHINE:
  1. Create SSH tunnel through Jumpbox:
     ssh -i ~/.ssh/<jumpbox-key>.pem -L 50050:192.168.56.40:50050 ubuntu@<JUMPBOX_IP>
  2. Run your local CS Client
  3. Connect to: localhost:50050

FROM ATTACK BOX WSL:
  ssh teamserver   # Pre-configured alias

================================================================================
                              NETWORK ACCESS
================================================================================

This Team Server:
  - Private IP: 192.168.56.40
  - CS Port: 50050
  - NO public IP (private subnet only)

Can reach:
  - GOAD AD VMs (192.168.56.10-25) for beacons
  - Outbound internet (via NAT) for staged payloads

Cannot reach:
  - Jumpbox (no SSH key)
  - Your local machine (no route)

================================================================================
                              TROUBLESHOOTING
================================================================================

Team server not starting?
  - Check logs: cat /opt/logs/teamserver.log
  - Check Java: java -version
  - Check files: ls -la /opt/cobaltstrike/

Port 50050 not listening?
  - Restart: sudo systemctl restart teamserver
  - Check: sudo systemctl status teamserver

Can't connect from CS Client?
  - Verify SSH tunnel is active
  - Check password is correct
  - Verify firewall allows 50050

================================================================================
Created by Red Team Infrastructure Deployment Tool
================================================================================
README

chown ubuntu:ubuntu /home/ubuntu/README.txt
chmod 644 /home/ubuntu/README.txt

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
# Complete
# =============================================================================
echo ""
echo "=============================================="
echo "Team Server Installation Complete!"
echo "Finished: $(date)"
echo "=============================================="
echo ""
echo "This server runs ONLY the Cobalt Strike Team Server"
echo "No other tools are installed here."
echo ""
echo "=== Commands ==="
echo "  Check status:  /opt/cobaltstrike/check-status.sh"
echo "  Restart:       /opt/cobaltstrike/restart-teamserver.sh"
echo "  View logs:     /opt/cobaltstrike/view-logs.sh"
echo ""
echo "=== Connection ==="
echo "  Team Server Port: 50050"
echo "  Connect via SSH tunnel from your local machine:"
echo "    ssh -L 50050:192.168.56.40:50050 ubuntu@<JUMPBOX_IP>"
echo ""

# Create completion marker
touch /opt/cobaltstrike/.install-complete

