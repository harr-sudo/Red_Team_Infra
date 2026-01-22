#!/bin/bash
# Team Server Init - Cobalt Strike ONLY with Secure Key Management
set -e

CS_ARCHIVE_S3_PATH="${cs_archive_s3_path}"
CS_PASSWORD="${cs_password}"
DEPLOYMENT_BUCKET="${deployment_bucket}"
DEPLOYMENT_ID="${deployment_id}"
AWS_REGION="${aws_region}"
HOSTNAME="${hostname}"

LOG_FILE="/var/log/teamserver-init.log"
exec > >(tee -a "$LOG_FILE") 2>&1
echo "=== Team Server Init Started: $(date) ==="

# Set hostname
if [ -n "$HOSTNAME" ]; then
    hostnamectl set-hostname "$HOSTNAME"
    echo "127.0.0.1 $HOSTNAME" >> /etc/hosts
    echo "Hostname set to: $HOSTNAME"
fi

# Note: We don't wait for boot-finished here because this script IS part of cloud-init
# The boot-finished file is created AFTER user-data scripts complete

# Install dependencies
export DEBIAN_FRONTEND=noninteractive
apt-get update -y && apt-get upgrade -y
apt-get install -y openjdk-17-jdk awscli net-tools curl wget unzip

# Create directories
mkdir -p /opt/cobaltstrike/server /opt/logs /home/ubuntu/.ssh
chown -R ubuntu:ubuntu /opt/cobaltstrike /opt/logs
chmod 700 /home/ubuntu/.ssh
chown ubuntu:ubuntu /home/ubuntu/.ssh

# Download jumpbox public key from S3
if [ -n "$DEPLOYMENT_BUCKET" ]; then
    S3_KEY="s3://$DEPLOYMENT_BUCKET/keys/$DEPLOYMENT_ID/jumpbox_internal.pub"
    echo "Downloading jumpbox public key from S3..."
    for i in $(seq 1 60); do
        if aws s3 cp "$S3_KEY" /tmp/jumpbox.pub --region "$AWS_REGION" 2>/dev/null; then
            if ssh-keygen -l -f /tmp/jumpbox.pub >/dev/null 2>&1; then
                cat /tmp/jumpbox.pub >> /home/ubuntu/.ssh/authorized_keys
                chmod 600 /home/ubuntu/.ssh/authorized_keys
                chown ubuntu:ubuntu /home/ubuntu/.ssh/authorized_keys
                rm -f /tmp/jumpbox.pub
                echo "KEY_CONFIGURED" > /opt/cobaltstrike/bootstrap-status
                echo "Jumpbox public key configured"
                break
            fi
        fi
        echo "Waiting for jumpbox key... ($i/60)"
        sleep 10
    done
    
    # Download attack box public key from S3 (allow SSH from attack box)
    S3_ATTACKBOX_KEY="s3://$DEPLOYMENT_BUCKET/keys/$DEPLOYMENT_ID/attackbox_internal.pub"
    echo "Downloading attack box public key from S3..."
    for i in $(seq 1 60); do
        if aws s3 cp "$S3_ATTACKBOX_KEY" /tmp/attackbox.pub --region "$AWS_REGION" 2>/dev/null; then
            if ssh-keygen -l -f /tmp/attackbox.pub >/dev/null 2>&1; then
                cat /tmp/attackbox.pub >> /home/ubuntu/.ssh/authorized_keys
                chmod 600 /home/ubuntu/.ssh/authorized_keys
                chown ubuntu:ubuntu /home/ubuntu/.ssh/authorized_keys
                rm -f /tmp/attackbox.pub
                echo "ATTACKBOX_KEY_CONFIGURED" >> /opt/cobaltstrike/bootstrap-status
                echo "Attack box public key configured"
                break
            fi
        fi
        echo "Waiting for attack box key... ($i/60)"
        sleep 10
    done
    
    # Download attack box WSL public key from S3 (allow SSH from WSL on attack box)
    S3_WSL_KEY="s3://$DEPLOYMENT_BUCKET/keys/$DEPLOYMENT_ID/wsl_attackbox_internal.pub"
    echo "Downloading attack box WSL public key from S3..."
    for i in $(seq 1 60); do
        if aws s3 cp "$S3_WSL_KEY" /tmp/wsl_attackbox.pub --region "$AWS_REGION" 2>/dev/null; then
            if ssh-keygen -l -f /tmp/wsl_attackbox.pub >/dev/null 2>&1; then
                cat /tmp/wsl_attackbox.pub >> /home/ubuntu/.ssh/authorized_keys
                chmod 600 /home/ubuntu/.ssh/authorized_keys
                chown ubuntu:ubuntu /home/ubuntu/.ssh/authorized_keys
                rm -f /tmp/wsl_attackbox.pub
                echo "WSL_KEY_CONFIGURED" >> /opt/cobaltstrike/bootstrap-status
                echo "Attack box WSL public key configured"
                break
            fi
        fi
        echo "Waiting for attack box WSL key... ($i/60)"
        sleep 10
    done
fi

# Download and extract Cobalt Strike
CS_EXTRACTED=false
if [ -n "$CS_ARCHIVE_S3_PATH" ]; then
    echo "Downloading Cobalt Strike from S3..."
    aws s3 cp "$CS_ARCHIVE_S3_PATH" /tmp/cs-archive
    
    if [ -f /tmp/cs-archive ]; then
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
            echo "WARNING: Unknown archive type, trying tar -xf..."
            tar -xf /tmp/cs-archive -C /opt/cobaltstrike --strip-components=1 && CS_EXTRACTED=true || \
            tar -xzf /tmp/cs-archive -C /opt/cobaltstrike --strip-components=1 && CS_EXTRACTED=true || \
            echo "ERROR: Failed to extract archive"
        fi
        
        rm -f /tmp/cs-archive
    fi
fi

# Post-extraction setup for Cobalt Strike 4.6+
if [ "$CS_EXTRACTED" = true ]; then
    echo "Cobalt Strike extracted successfully"
    
    # Extract TeamServerImage from JAR if not present (CS 4.6+ stores it in the JAR)
    if [ -f /opt/cobaltstrike/cobaltstrike.jar ] && [ ! -f /opt/cobaltstrike/server/TeamServerImage ]; then
        echo "Extracting TeamServerImage from JAR (CS 4.6+)..."
        cd /opt/cobaltstrike/server
        unzip -o ../cobaltstrike.jar TeamServerImage -d . 2>/dev/null || true
        chmod +x TeamServerImage 2>/dev/null || true
    fi
    
    # Make scripts executable
    chmod +x /opt/cobaltstrike/server/teamserver 2>/dev/null || true
    chmod +x /opt/cobaltstrike/update 2>/dev/null || true
    
    # Set ownership
    chown -R ubuntu:ubuntu /opt/cobaltstrike
    
    # Check if license activation is needed
    LICENSE_STATUS="unknown"
    if [ -f /opt/cobaltstrike/server/TeamServerImage ]; then
        # Try a quick test to see if licensed
        cd /opt/cobaltstrike/server
        timeout 5 ./TeamServerImage --help 2>&1 | grep -q "Please run the 'update' program" && LICENSE_STATUS="needs_activation" || LICENSE_STATUS="ready"
    fi
    echo "LICENSE_STATUS=$LICENSE_STATUS" >> /opt/cobaltstrike/bootstrap-status
fi

# Create systemd service (will only work after license activation)
if [ -f /opt/cobaltstrike/server/teamserver ]; then
    cat > /etc/systemd/system/teamserver.service << EOF
[Unit]
Description=Cobalt Strike Team Server
After=network.target

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
    systemctl daemon-reload
    systemctl enable teamserver
    
    # Only start if we have a password and license appears ready
    if [ -n "$CS_PASSWORD" ] && [ "$LICENSE_STATUS" = "ready" ]; then
        echo "Starting team server..."
        systemctl start teamserver
    else
        echo "Team server service created but NOT started - license activation required"
    fi
fi

# README with clear instructions
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
Team Server IP:   192.168.56.40
Team Server Port: 50050

From your LOCAL machine, create an SSH tunnel:
    ssh -L 50050:192.168.56.40:50050 ubuntu@<JUMPBOX_PUBLIC_IP>

Then connect your CS Client to: localhost:50050

================================================================================
READMEEOF
chown ubuntu:ubuntu /home/ubuntu/README.txt

# Helper scripts
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

# Check service status
echo "=== Service Status ==="
systemctl status teamserver --no-pager 2>/dev/null || echo "Service not running"
echo ""

# Check if listening
echo "=== Port 50050 ==="
netstat -tlnp 2>/dev/null | grep 50050 || echo "Not listening on port 50050"
EOF
chmod +x /opt/cobaltstrike/check-status.sh

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

chown -R ubuntu:ubuntu /opt/cobaltstrike

touch /opt/cobaltstrike/.install-complete
echo "=== Team Server Init Complete: $(date) ==="
echo ""
echo "NEXT STEP: Activate your Cobalt Strike license"
echo "    ssh teamserver"
echo "    cd /opt/cobaltstrike && sudo ./update"
