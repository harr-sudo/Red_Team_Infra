#!/bin/bash

# Setup SSH Keys - Automated Key Distribution
# This script generates SSH keys on jump box and distributes them to all instances via Ansible

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Paths
ANSIBLE_DIR="${PROJECT_ROOT}/ansible"
ANSIBLE_INVENTORY="${ANSIBLE_DIR}/inventory/hosts.yml"
SSH_KEY_NAME="red-team-jumpbox-key"
SSH_KEY_PATH="${HOME}/.ssh/${SSH_KEY_NAME}"

# AWS Key pair (for initial connection if needed)
KEY_PAIR_NAME="${KEY_PAIR_NAME:-red-team-keypair}"
KEY_PAIR_PATH="${KEY_PAIR_PATH:-${HOME}/.ssh/${KEY_PAIR_NAME}.pem}"

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    local missing=()
    
    command -v ansible >/dev/null 2>&1 || missing+=("ansible")
    command -v jq >/dev/null 2>&1 || missing+=("jq")
    command -v ssh-keygen >/dev/null 2>&1 || missing+=("ssh-keygen")
    
    if [ ${#missing[@]} -ne 0 ]; then
        log_error "Missing required tools: ${missing[*]}"
        exit 1
    fi
    
    # Check if inventory exists
    if [ ! -f "${ANSIBLE_INVENTORY}" ]; then
        log_warn "Ansible inventory not found. Generating..."
        "${SCRIPT_DIR}/generate-inventory.sh"
    fi
    
    log_info "All prerequisites met!"
}

# Generate SSH key on jump box
generate_ssh_key() {
    log_info "Generating SSH key pair..."
    
    # Create .ssh directory if it doesn't exist
    mkdir -p "${HOME}/.ssh"
    chmod 700 "${HOME}/.ssh"
    
    # Check if key already exists
    if [ -f "${SSH_KEY_PATH}" ]; then
        log_warn "SSH key already exists: ${SSH_KEY_PATH}"
        read -p "Do you want to generate a new key? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Using existing key: ${SSH_KEY_PATH}"
            return 0
        fi
        # Backup existing key
        mv "${SSH_KEY_PATH}" "${SSH_KEY_PATH}.backup.$(date +%s)"
        mv "${SSH_KEY_PATH}.pub" "${SSH_KEY_PATH}.pub.backup.$(date +%s)" 2>/dev/null || true
    fi
    
    # Generate new key
    ssh-keygen -t rsa -b 4096 -f "${SSH_KEY_PATH}" -N "" -C "red-team-jumpbox@$(hostname)"
    chmod 600 "${SSH_KEY_PATH}"
    chmod 644 "${SSH_KEY_PATH}.pub"
    
    log_info "SSH key generated: ${SSH_KEY_PATH}"
    log_info "Public key: ${SSH_KEY_PATH}.pub"
}

# Distribute keys via Ansible
distribute_keys() {
    log_info "Distributing SSH keys to all instances via Ansible..."
    
    # Check if we can connect to instances first
    log_info "Testing connectivity to instances..."
    if ! ansible all -i "${ANSIBLE_INVENTORY}" -m ping >/dev/null 2>&1; then
        log_warn "Cannot connect to all instances. This is expected if keys haven't been distributed yet."
        log_info "Proceeding with key distribution..."
    fi
    
    # Run Ansible playbook
    cd "${ANSIBLE_DIR}"
    
    # Check if we need to use the AWS key pair for initial connection
    # First, try with the generated key (may fail if not distributed yet)
    # Then fall back to AWS key pair if needed
    
    log_info "Running Ansible playbook to distribute keys..."
    
    # Use AWS key pair for initial connection (instances have AWS key pair by default)
    # Then distribute the new jump box key
    
    # Get AWS key pair path (try common locations)
    AWS_KEY_PATH=""
    if [ -n "${KEY_PAIR_PATH:-}" ] && [ -f "${KEY_PAIR_PATH}" ]; then
        AWS_KEY_PATH="${KEY_PAIR_PATH}"
    elif [ -f "${HOME}/.ssh/${KEY_PAIR_NAME}.pem" ]; then
        AWS_KEY_PATH="${HOME}/.ssh/${KEY_PAIR_NAME}.pem"
    elif [ -f "${HOME}/.ssh/red-team-keypair.pem" ]; then
        AWS_KEY_PATH="${HOME}/.ssh/red-team-keypair.pem"
    else
        log_warn "AWS key pair not found in common locations."
        log_info "Instances should have AWS key pair configured. Trying without explicit key..."
        AWS_KEY_PATH=""
    fi
    
    # Build ansible-playbook command
    ANSIBLE_CMD="ansible-playbook -i ${ANSIBLE_INVENTORY} playbooks/distribute-ssh-keys.yml"
    ANSIBLE_CMD="${ANSIBLE_CMD} -e ssh_public_key_file=${SSH_KEY_PATH}.pub"
    
    # Add AWS key pair if found (for initial connection)
    if [ -n "${AWS_KEY_PATH}" ] && [ -f "${AWS_KEY_PATH}" ]; then
        ANSIBLE_CMD="${ANSIBLE_CMD} -e ansible_ssh_private_key_file=${AWS_KEY_PATH}"
        log_info "Using AWS key pair (${AWS_KEY_PATH}) for initial connection"
    fi
    
    ANSIBLE_CMD="${ANSIBLE_CMD} -v"
    
    # Run the playbook
    eval "${ANSIBLE_CMD}"
    
    if [ $? -eq 0 ]; then
        log_info "Keys distributed successfully!"
    else
        log_error "Failed to distribute keys. Check Ansible output above."
        log_info "You may need to:"
        log_info "  1. Ensure AWS key pair is accessible"
        log_info "  2. Check security groups allow SSH from jump box"
        log_info "  3. Verify instances are running"
        exit 1
    fi
    
    if [ $? -eq 0 ]; then
        log_info "SSH keys successfully distributed to all instances!"
    else
        log_error "Failed to distribute SSH keys. Check Ansible output above."
        exit 1
    fi
}

# Test SSH access
test_ssh_access() {
    log_info "Testing SSH access to instances..."
    
    local failed=0
    
    # Test C2 servers
    if ansible c2_team_servers -i "${ANSIBLE_INVENTORY}" -m ping >/dev/null 2>&1; then
        log_info "✅ C2 team servers: Accessible"
    else
        log_warn "⚠️  C2 team servers: Some may not be accessible"
        failed=1
    fi
    
    # Test proxy/redirectors
    if ansible proxy_redirectors -i "${ANSIBLE_INVENTORY}" -m ping >/dev/null 2>&1; then
        log_info "✅ Proxy/redirectors: Accessible"
    else
        log_warn "⚠️  Proxy/redirectors: Some may not be accessible"
        failed=1
    fi
    
    if [ $failed -eq 0 ]; then
        log_info "All instances are accessible via SSH!"
    else
        log_warn "Some instances may not be accessible. Check connectivity manually."
    fi
}

# Main execution
main() {
    log_info "=== SSH Key Setup and Distribution ==="
    echo
    
    check_prerequisites
    echo
    
    generate_ssh_key
    echo
    
    distribute_keys
    echo
    
    test_ssh_access
    echo
    
    log_info "=== Setup Complete ==="
    log_info "You can now SSH to instances using:"
    log_info "  ssh -i ${SSH_KEY_PATH} ec2-user@<instance-ip>"
    log_info ""
    log_info "Or use Ansible:"
    log_info "  ansible all -i ${ANSIBLE_INVENTORY} -m ping"
}

# Run main function
main

