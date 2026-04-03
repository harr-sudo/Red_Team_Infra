#!/bin/bash
# Bastion Host Bootstrap Script
# Lightweight Linux SSH relay — no tools, no heavy packages
set -euo pipefail

LOG_FILE="/var/log/bastion-setup.log"
exec > >(tee -a "$LOG_FILE") 2>&1

# Setup Status Tracking (for Host Setup Checker dashboard feature)
SETUP_STATUS_FILE="/opt/setup-status.json"
SETUP_ROLE="bastion"
SETUP_TOTAL=5
SETUP_STARTED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SETUP_STEP_START=$(date +%s)
CURRENT_STEP=0
CURRENT_STEP_NAME=""

write_step_status() {
    local step_num=$1 step_name=$2 step_status=$3 message="$${4:-}"
    local now=$(date +%s)
    local duration=$((now - SETUP_STEP_START))
    SETUP_STEP_START=$now
    CURRENT_STEP=$step_num
    CURRENT_STEP_NAME=$step_name

    if [ ! -f "$SETUP_STATUS_FILE" ] || [ "$step_num" -eq 1 ]; then
        echo "{\"host\":\"$(hostname)\",\"role\":\"$SETUP_ROLE\",\"total_steps\":$SETUP_TOTAL,\"completed\":0,\"failed\":0,\"warnings\":0,\"status\":\"running\",\"steps\":[],\"started_at\":\"$SETUP_STARTED_AT\",\"finished_at\":null}" > "$SETUP_STATUS_FILE"
    fi

    local escaped_msg=$(echo "$message" | sed 's/"/\\"/g' | tr '\n' ' ')
    local new_step="{\"step\":$step_num,\"name\":\"$step_name\",\"status\":\"$step_status\",\"duration_s\":$duration,\"message\":\"$escaped_msg\"}"

    python3 -c "
import json, sys
with open('$SETUP_STATUS_FILE') as f:
    data = json.load(f)
step = json.loads('$new_step')
data['steps'].append(step)
data['completed'] = sum(1 for s in data['steps'] if s['status'] in ('ok','warning'))
data['failed'] = sum(1 for s in data['steps'] if s['status'] == 'failed')
data['warnings'] = sum(1 for s in data['steps'] if s['status'] == 'warning')
if data['failed'] > 0:
    data['status'] = 'partial'
elif data['completed'] == data['total_steps']:
    data['status'] = 'complete'
data['finished_at'] = '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
with open('$SETUP_STATUS_FILE', 'w') as f:
    json.dump(data, f, indent=2)
" 2>/dev/null || echo "WARNING: Failed to write setup status for step $step_num"
}

trap 'write_step_status $CURRENT_STEP "$CURRENT_STEP_NAME" "failed" "Script exited unexpectedly"' ERR

echo "=== Bastion Setup Starting ==="

# Set hostname
hostnamectl set-hostname "${hostname}"
echo "127.0.0.1 ${hostname}" >> /etc/hosts
write_step_status 1 "Hostname" "ok"

# System update
apt-get update -y
apt-get upgrade -y
write_step_status 2 "System Updates" "ok"

# Install minimal utilities (SSH relay host only)
apt-get install -y curl wget jq htop tmux unzip net-tools
write_step_status 3 "Utilities" "ok"

# Install SSM agent (for remote management without SSH key hopping)
snap install amazon-ssm-agent --classic 2>/dev/null || true
systemctl enable snap.amazon-ssm-agent.amazon-ssm-agent.service 2>/dev/null || true
systemctl start snap.amazon-ssm-agent.amazon-ssm-agent.service 2>/dev/null || true
write_step_status 4 "SSM Agent" "ok"

# Harden SSH
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak
cat >> /etc/ssh/sshd_config << 'SSHEOF'

# Bastion SSH hardening
PermitRootLogin no
PasswordAuthentication no
MaxAuthTries 3
MaxSessions 10
ClientAliveInterval 300
ClientAliveCountMax 2
AllowAgentForwarding yes
AllowTcpForwarding yes
X11Forwarding no
SSHEOF
systemctl restart sshd
write_step_status 5 "SSH Hardening" "ok"

echo "=== Bastion Setup Complete — SSH relay host ready ==="
