#!/bin/bash

# Red Team Infrastructure Destruction Script
# This script safely tears down the infrastructure

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Configuration
TERRAFORM_DIR="${PROJECT_ROOT}/terraform"
CONFIG_DIR="${PROJECT_ROOT}/configs"

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

confirm_destruction() {
    log_warn "============================================"
    log_warn "WARNING: This will destroy all infrastructure!"
    log_warn "============================================"
    echo ""
    read -p "Type 'DESTROY' to confirm: " confirm
    
    if [ "$confirm" != "DESTROY" ]; then
        log_info "Destruction cancelled"
        exit 0
    fi
}

destroy_infrastructure() {
    log_info "Destroying infrastructure with Terraform..."
    
    cd "${TERRAFORM_DIR}"
    
    # Check if Terraform is initialized
    if [ ! -d ".terraform" ]; then
        log_error "Terraform not initialized. Run deploy.sh first."
        exit 1
    fi
    
    # Plan destruction
    log_info "Creating destruction plan..."
    terraform plan -destroy -out=destroy-plan -var-file="${CONFIG_DIR}/terraform.tfvars"
    
    # Apply destruction
    log_info "Destroying infrastructure..."
    terraform apply destroy-plan
    
    # Clean up
    rm -f destroy-plan tfplan
    rm -f "${PROJECT_ROOT}/terraform-outputs.json"
    
    log_info "Infrastructure destroyed!"
}

main() {
    log_info "Starting Infrastructure Destruction"
    log_info "===================================="
    
    confirm_destruction
    destroy_infrastructure
    
    log_info "===================================="
    log_info "Destruction completed!"
}

# Run main function
main "$@"

