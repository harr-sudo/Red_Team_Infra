#!/bin/bash
# GOAD Jumpbox Init - Minimal SSH Gateway with Secure Key Management
set -e

USERNAME="${username}"
ATTACKBOX_IP="${attackbox_ip}"
TEAMSERVER_IP="${teamserver_ip}"
INSTALL_CS="${install_cs}"
DEPLOYMENT_BUCKET="${deployment_bucket}"
DEPLOYMENT_ID="${deployment_id}"
AWS_REGION="${aws_region}"
HOSTNAME="${hostname}"

LOG_FILE="/var/log/jumpbox-init.log"
exec > >(tee -a "$LOG_FILE") 2>&1
echo "=== Jumpbox Init Started: $(date) ==="

# Set hostname
if [ -n "$HOSTNAME" ]; then
    hostnamectl set-hostname "$HOSTNAME"
    echo "127.0.0.1 $HOSTNAME" >> /etc/hosts
    echo "Hostname set to: $HOSTNAME"
fi

# Note: We don't wait for boot-finished here because this script IS part of cloud-init
# The boot-finished file is created AFTER user-data scripts complete

# System setup
export DEBIAN_FRONTEND=noninteractive
apt-get update -y && apt-get upgrade -y
apt-get install -y curl wget net-tools htop tmux vim jq netcat-openbsd awscli git python3-pip sshpass

# =============================================================================
# Install Ansible + pywinrm for GOAD AD provisioning
# =============================================================================
echo "=== Installing Ansible for GOAD provisioning ==="
pip3 install ansible-core==2.12.6 pywinrm

# Clone GOAD repository for Ansible playbooks
echo "=== Cloning GOAD repository ==="
git clone https://github.com/Orange-Cyberdefense/GOAD.git /home/ubuntu/GOAD
chown -R ubuntu:ubuntu /home/ubuntu/GOAD

# Install Ansible Galaxy requirements
cd /home/ubuntu/GOAD/ansible
sudo -u ubuntu ansible-galaxy install -r requirements.yml
cd /home/ubuntu

echo "=== Ansible + GOAD setup complete ==="

# Harden SSH
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak
cat >> /etc/ssh/sshd_config << 'EOF'
PermitRootLogin no
MaxAuthTries 3
MaxSessions 10
ClientAliveInterval 300
ClientAliveCountMax 2
AllowAgentForwarding yes
AllowTcpForwarding yes
X11Forwarding no
EOF
systemctl restart sshd

# Setup directories
mkdir -p /home/ubuntu/.ssh /opt/jumpbox
chmod 700 /home/ubuntu/.ssh

if [ "$INSTALL_CS" = "true" ]; then
    # Generate internal SSH key ON THIS HOST
    ssh-keygen -t ed25519 -f /home/ubuntu/.ssh/jumpbox_internal_key -N "" -C "jumpbox-$(hostname)"
    chmod 600 /home/ubuntu/.ssh/jumpbox_internal_key
    chmod 644 /home/ubuntu/.ssh/jumpbox_internal_key.pub
    chown ubuntu:ubuntu /home/ubuntu/.ssh/jumpbox_internal_key*
    
    # Upload public key to S3
    if [ -n "$DEPLOYMENT_BUCKET" ]; then
        S3_KEY="s3://$DEPLOYMENT_BUCKET/keys/$DEPLOYMENT_ID/jumpbox_internal.pub"
        for i in 1 2 3 4 5; do
            if aws s3 cp /home/ubuntu/.ssh/jumpbox_internal_key.pub "$S3_KEY" --region "$AWS_REGION"; then
                echo "KEY_UPLOAD_SUCCESS" > /opt/jumpbox/bootstrap-status
                aws s3 cp - "s3://$DEPLOYMENT_BUCKET/status/$DEPLOYMENT_ID/jumpbox-ready" --region "$AWS_REGION" <<< "ready" || true
                break
            fi
            sleep $((i * 5))
        done
    fi
    
    # SSH config for internal hosts
    cat > /home/ubuntu/.ssh/config << SSHCONFIG
Host teamserver ts
    HostName $TEAMSERVER_IP
    User ubuntu
    IdentityFile ~/.ssh/jumpbox_internal_key
    StrictHostKeyChecking accept-new

Host attackbox ab
    HostName $ATTACKBOX_IP
    User Administrator
    IdentityFile ~/.ssh/jumpbox_internal_key
    StrictHostKeyChecking accept-new

Host 192.168.56.*
    User ubuntu
    IdentityFile ~/.ssh/jumpbox_internal_key
    StrictHostKeyChecking accept-new
SSHCONFIG
    chmod 600 /home/ubuntu/.ssh/config
    chown ubuntu:ubuntu /home/ubuntu/.ssh/config
fi

# README
cat > /home/ubuntu/README.txt << 'EOF'
JUMPBOX - SSH Gateway
=====================
Commands: ssh teamserver | ssh attackbox | ssh 192.168.56.10
Scripts:  /opt/jumpbox/check-key-status.sh | check-network.sh
RDP:      ssh -L 3389:192.168.56.10:3389 ubuntu@<JUMPBOX_IP> (from local)
Key:      Internal key generated on this host, public key shared via S3
EOF
chown ubuntu:ubuntu /home/ubuntu/README.txt

# Helper scripts
cat > /opt/jumpbox/check-key-status.sh << 'EOF'
#!/bin/bash
echo "=== Key Status ==="
[ -f ~/.ssh/jumpbox_internal_key ] && echo "✅ Private key OK" || echo "❌ No private key"
[ -f ~/.ssh/jumpbox_internal_key.pub ] && echo "✅ Public key OK" || echo "❌ No public key"
[ -f /opt/jumpbox/bootstrap-status ] && cat /opt/jumpbox/bootstrap-status
EOF

cat > /opt/jumpbox/check-network.sh << 'EOF'
#!/bin/bash
echo "=== Network Check ==="
for ip in 10 11 40 50; do
    ping -c1 -W1 192.168.56.$ip >/dev/null 2>&1 && echo "192.168.56.$ip: UP" || echo "192.168.56.$ip: DOWN"
done
EOF

chmod +x /opt/jumpbox/*.sh
chown -R ubuntu:ubuntu /opt/jumpbox

touch /opt/jumpbox/.init-complete
echo "=== Jumpbox Init Complete: $(date) ==="
