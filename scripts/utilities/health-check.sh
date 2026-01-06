#!/bin/bash

# Health Check Script
# Checks the health and status of deployed infrastructure

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

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

check_terraform_outputs() {
    log_info "Checking Terraform outputs..."
    
    if [ ! -f "${PROJECT_ROOT}/terraform-outputs.json" ]; then
        log_error "Terraform outputs not found. Has infrastructure been deployed?"
        return 1
    fi
    
    log_info "Terraform outputs found"
    return 0
}

check_aws_connectivity() {
    log_info "Checking AWS connectivity..."
    
    if aws sts get-caller-identity >/dev/null 2>&1; then
        local account=$(aws sts get-caller-identity --query Account --output text)
        log_info "Connected to AWS Account: ${account}"
        return 0
    else
        log_error "Cannot connect to AWS"
        return 1
    fi
}

check_ec2_instances() {
    log_info "Checking EC2 instances..."
    
    # TODO: Extract instance IDs from Terraform outputs and check status
    local instances=$(aws ec2 describe-instances \
        --filters "Name=tag:Project,Values=RedTeamInfra" \
        --query 'Reservations[*].Instances[*].[InstanceId,State.Name,PublicIpAddress]' \
        --output text 2>/dev/null || echo "")
    
    if [ -z "$instances" ]; then
        log_warn "No instances found"
        return 1
    fi
    
    echo "$instances" | while read -r instance_id state ip; do
        if [ "$state" == "running" ]; then
            log_info "Instance ${instance_id}: ${state} (${ip})"
        else
            log_warn "Instance ${instance_id}: ${state}"
        fi
    done
    
    return 0
}

main() {
    log_info "Running Health Check"
    log_info "==================="
    
    check_aws_connectivity || exit 1
    check_terraform_outputs || exit 1
    check_ec2_instances
    
    log_info "==================="
    log_info "Health check completed"
}

main "$@"

