#!/bin/bash

# Generate Ansible Inventory from Terraform Outputs
# This script creates an Ansible inventory file from Terraform outputs

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Paths
TERRAFORM_DIR="${PROJECT_ROOT}/terraform"
ANSIBLE_INVENTORY="${PROJECT_ROOT}/ansible/inventory/hosts.yml"
TERRAFORM_OUTPUTS="${PROJECT_ROOT}/terraform-outputs.json"

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Check if Terraform outputs exist
if [ ! -f "${TERRAFORM_OUTPUTS}" ]; then
    log_warn "Terraform outputs file not found. Generating from Terraform state..."
    cd "${TERRAFORM_DIR}"
    terraform output -json > "${TERRAFORM_OUTPUTS}" 2>/dev/null || {
        log_warn "Could not generate outputs. Please run 'terraform output -json > ${TERRAFORM_OUTPUTS}' manually"
        exit 1
    }
fi

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    log_warn "jq not found. Please install jq to generate inventory."
    exit 1
fi

log_info "Generating Ansible inventory from Terraform outputs..."

# Read Terraform outputs
ANSIBLE_INVENTORY_DIR="$(dirname "${ANSIBLE_INVENTORY}")"
mkdir -p "${ANSIBLE_INVENTORY_DIR}"

# Generate inventory
cat > "${ANSIBLE_INVENTORY}" << 'EOF'
---
# Ansible Inventory - Auto-generated from Terraform outputs
# DO NOT EDIT MANUALLY - Regenerate using scripts/utilities/generate-inventory.sh

all:
  children:
    c2_team_servers:
      hosts:
EOF

# Add C2 servers - Use unified output that works for all deployment modes
# This handles: single (1 server), redundancy (2+ servers), phases (3 servers)
# The unified c2_servers output works for all modes

# Try unified output first (preferred - works for all modes)
C2_SERVERS_COUNT=$(jq -r '.c2_servers.value | length' "${TERRAFORM_OUTPUTS}" 2>/dev/null || echo "0")

if [ "$C2_SERVERS_COUNT" != "0" ] && [ "$C2_SERVERS_COUNT" != "null" ] && [ -n "$C2_SERVERS_COUNT" ]; then
    # Use unified c2_servers output (works for all modes: single, redundancy, phases)
    log_info "Using unified c2_servers output (supports all deployment modes)"
    
    jq -r '.c2_servers.value | to_entries[] | "\(.key)|\(.value.private_ip)|\(.value.phase // "generic")"' "${TERRAFORM_OUTPUTS}" 2>/dev/null | while IFS='|' read -r server_name ip phase; do
        if [ -n "$ip" ] && [ "$ip" != "null" ] && [ "$ip" != "" ]; then
            # Determine hostname based on phase
            if [ "$phase" != "generic" ] && [ "$phase" != "null" ] && [ -n "$phase" ]; then
                hostname="c2-${phase}-server"
            else
                # Use server name or generate sequential name
                if [[ "$server_name" =~ ^server- ]]; then
                    hostname="c2-${server_name}"
                else
                    hostname="c2-${server_name}"
                fi
            fi
            
            cat >> "${ANSIBLE_INVENTORY}" << EOF
        ${hostname}:
          ansible_host: ${ip}
          ansible_user: ec2-user
          ansible_ssh_private_key_file: ~/.ssh/red-team-keypair.pem
          phase: ${phase}
          server_name: ${server_name}
EOF
        fi
    done
else
    # Fallback: Try mode-specific outputs (for backwards compatibility)
    log_info "Unified output not available, using mode-specific outputs"
    
    # Add C2 team servers (single/redundancy mode)
    C2_SERVERS=$(jq -r '.c2_team_server_private_ips.value[]?' "${TERRAFORM_OUTPUTS}" 2>/dev/null || echo "")
    if [ -n "$C2_SERVERS" ] && [ "$C2_SERVERS" != "null" ]; then
        SERVER_NUM=1
        echo "$C2_SERVERS" | while read -r ip; do
            if [ -n "$ip" ] && [ "$ip" != "null" ] && [ "$ip" != "" ]; then
                cat >> "${ANSIBLE_INVENTORY}" << EOF
        c2-server-${SERVER_NUM}:
          ansible_host: ${ip}
          ansible_user: ec2-user
          ansible_ssh_private_key_file: ~/.ssh/red-team-keypair.pem
          phase: generic
EOF
                SERVER_NUM=$((SERVER_NUM + 1))
            fi
        done
    fi
    
    # Add C2 phase servers (phases mode)
    C2_PHASES=$(jq -r '.c2_phase_server_private_ips.value | to_entries[]? | "\(.key):\(.value)"' "${TERRAFORM_OUTPUTS}" 2>/dev/null || echo "")
    if [ -n "$C2_PHASES" ] && [ "$C2_PHASES" != "null" ]; then
        echo "$C2_PHASES" | while IFS=':' read -r phase ip; do
            if [ -n "$ip" ] && [ "$ip" != "null" ] && [ "$ip" != "" ]; then
                cat >> "${ANSIBLE_INVENTORY}" << EOF
        c2-${phase}-server:
          ansible_host: ${ip}
          ansible_user: ec2-user
          ansible_ssh_private_key_file: ~/.ssh/red-team-keypair.pem
          phase: ${phase}
EOF
            fi
        done
    fi
fi

# Add proxy/redirectors
cat >> "${ANSIBLE_INVENTORY}" << 'EOF'
    
    proxy_redirectors:
      hosts:
EOF

PROXY_IPS=$(jq -r '.proxy_redirector_public_ips.value[]?' "${TERRAFORM_OUTPUTS}" 2>/dev/null || echo "")
if [ -n "$PROXY_IPS" ]; then
    PROXY_NUM=1
    echo "$PROXY_IPS" | while read -r ip; do
        if [ -n "$ip" ] && [ "$ip" != "null" ]; then
            cat >> "${ANSIBLE_INVENTORY}" << EOF
        proxy-${PROXY_NUM}:
          ansible_host: ${ip}
          ansible_user: ec2-user
          ansible_ssh_private_key_file: ~/.ssh/red-team-keypair.pem
EOF
            PROXY_NUM=$((PROXY_NUM + 1))
        fi
    done
fi

# Add common variables
cat >> "${ANSIBLE_INVENTORY}" << 'EOF'

  vars:
    ansible_ssh_common_args: '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'
    ansible_python_interpreter: /usr/bin/python3
EOF

log_info "Inventory generated: ${ANSIBLE_INVENTORY}"
log_info "You can now use: ansible all -i ${ANSIBLE_INVENTORY} -m ping"

