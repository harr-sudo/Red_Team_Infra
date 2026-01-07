#!/bin/bash

# Red Team Infrastructure Deployment Script
# This script orchestrates the deployment of the entire infrastructure

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
ANSIBLE_DIR="${PROJECT_ROOT}/ansible"
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

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    local missing_tools=()
    
    command -v aws >/dev/null 2>&1 || missing_tools+=("aws-cli")
    command -v terraform >/dev/null 2>&1 || missing_tools+=("terraform")
    command -v ansible >/dev/null 2>&1 || missing_tools+=("ansible")
    command -v jq >/dev/null 2>&1 || missing_tools+=("jq")
    
    if [ ${#missing_tools[@]} -ne 0 ]; then
        log_error "Missing required tools: ${missing_tools[*]}"
        log_error "Please install the missing tools and try again."
        exit 1
    fi
    
    log_info "All prerequisites met!"
}

check_aws_credentials() {
    log_info "Checking AWS credentials..."
    
    if ! aws sts get-caller-identity >/dev/null 2>&1; then
        log_error "AWS credentials not configured or invalid"
        log_error "Run 'aws configure' to set up your credentials"
        exit 1
    fi
    
    local aws_account=$(aws sts get-caller-identity --query Account --output text)
    local aws_user=$(aws sts get-caller-identity --query Arn --output text)
    log_info "AWS Account: ${aws_account}"
    log_info "AWS User: ${aws_user}"
}

check_terraform_config() {
    log_info "Checking Terraform configuration..."
    
    if [ ! -f "${CONFIG_DIR}/terraform.tfvars" ]; then
        log_error "terraform.tfvars not found in ${CONFIG_DIR}"
        log_error "Please copy terraform.tfvars.example and configure it"
        exit 1
    fi
    
    log_info "Terraform configuration found"
}

deploy_infrastructure() {
    log_info "Deploying infrastructure with Terraform..."
    
    cd "${TERRAFORM_DIR}"
    
    # Initialize Terraform
    log_info "Initializing Terraform..."
    terraform init
    
    # Validate configuration
    log_info "Validating Terraform configuration..."
    terraform validate
    
    # Plan deployment
    log_info "Creating Terraform plan..."
    terraform plan -out=tfplan -var-file="${CONFIG_DIR}/terraform.tfvars"
    
    # Ask for confirmation
    read -p "Do you want to apply these changes? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        log_warn "Deployment cancelled by user"
        exit 0
    fi
    
    # Apply changes
    log_info "Applying Terraform changes..."
    terraform apply tfplan
    
    # Get outputs
    log_info "Gathering infrastructure outputs..."
    terraform output -json > "${PROJECT_ROOT}/terraform-outputs.json"
    
    log_info "Infrastructure deployment completed!"
}

wait_for_instances() {
    log_info "Waiting for EC2 instances to be ready..."
    
    # Extract instance IDs from Terraform output
    local instance_ids=$(jq -r '.instance_ids.value[]' "${PROJECT_ROOT}/terraform-outputs.json" 2>/dev/null || echo "")
    
    if [ -z "$instance_ids" ]; then
        log_warn "No instance IDs found in Terraform output"
        return
    fi
    
    log_info "Waiting for instances: $instance_ids"
    
    aws ec2 wait instance-status-ok --instance-ids $instance_ids
    
    log_info "All instances are ready!"
}

configure_instances() {
    log_info "Configuring instances with Ansible..."
    
    # Generate Ansible inventory from Terraform outputs
    log_info "Generating Ansible inventory from Terraform outputs..."
    if [ -f "${PROJECT_ROOT}/scripts/utilities/generate-inventory.sh" ]; then
        bash "${PROJECT_ROOT}/scripts/utilities/generate-inventory.sh"
    else
        log_warn "Inventory generation script not found. Skipping..."
    fi
    
    # Run Ansible playbooks
    cd "${ANSIBLE_DIR}"
    
    # Check if base setup playbook exists
    if [ -f "playbooks/base-setup.yml" ]; then
        log_info "Running base setup playbook..."
        ansible-playbook -i inventory/hosts.yml playbooks/base-setup.yml || log_warn "Base setup playbook failed or not configured"
    fi
    
    # Deploy tools repository to jump box (if configured)
    if [ -f "playbooks/deploy-tools-repo.yml" ]; then
        # Check if tools repo URL is configured
        local tools_repo_url=$(grep -E "^tools_repo_url\s*=" "${CONFIG_DIR}/terraform.tfvars" 2>/dev/null | sed 's/.*=\s*"\(.*\)".*/\1/' | sed 's/.*=\s*\(.*\)/\1/' | head -1)
        
        if [ -n "$tools_repo_url" ] && [ "$tools_repo_url" != '""' ] && [ "$tools_repo_url" != "" ]; then
            log_info "Deploying tools repository to jump box..."
            
            # Extract tools repo configuration from terraform.tfvars
            local tools_repo_branch=$(grep -E "^tools_repo_branch\s*=" "${CONFIG_DIR}/terraform.tfvars" 2>/dev/null | sed 's/.*=\s*"\(.*\)".*/\1/' | sed 's/.*=\s*\(.*\)/\1/' | head -1 || echo "main")
            local tools_repo_ssh_key=$(grep -E "^tools_repo_ssh_key\s*=" "${CONFIG_DIR}/terraform.tfvars" 2>/dev/null | sed 's/.*=\s*"\(.*\)".*/\1/' | sed 's/.*=\s*\(.*\)/\1/' | head -1 || echo "")
            local tools_repo_https_token=$(grep -E "^tools_repo_https_token\s*=" "${CONFIG_DIR}/terraform.tfvars" 2>/dev/null | sed 's/.*=\s*"\(.*\)".*/\1/' | sed 's/.*=\s*\(.*\)/\1/' | head -1 || echo "")
            
            # Export environment variables for Ansible
            export TOOLS_REPO_URL="$tools_repo_url"
            export TOOLS_REPO_BRANCH="${tools_repo_branch:-main}"
            [ -n "$tools_repo_ssh_key" ] && export TOOLS_REPO_SSH_KEY="$tools_repo_ssh_key"
            [ -n "$tools_repo_https_token" ] && export TOOLS_REPO_HTTPS_TOKEN="$tools_repo_https_token"
            
            ansible-playbook -i inventory/hosts.yml playbooks/deploy-tools-repo.yml || log_warn "Tools repository deployment failed or not configured"
        else
            log_info "Tools repository URL not configured. Skipping tools deployment."
        fi
    fi
    
    log_info "Configuration completed!"
}

main() {
    log_info "Starting Red Team Infrastructure Deployment"
    log_info "============================================"
    
    check_prerequisites
    check_aws_credentials
    check_terraform_config
    deploy_infrastructure
    wait_for_instances
    configure_instances
    
    log_info "============================================"
    log_info "Deployment completed successfully!"
    log_info "Check terraform-outputs.json for connection information"
    log_info ""
    
    # Prompt for SSH key distribution
    if [ -f "${PROJECT_ROOT}/scripts/utilities/setup-ssh-keys.sh" ]; then
        log_info "Next step: Distribute SSH keys to all instances"
        log_info "Run: ${PROJECT_ROOT}/scripts/utilities/setup-ssh-keys.sh"
        log_info ""
        read -p "Do you want to distribute SSH keys now? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "Distributing SSH keys..."
            bash "${PROJECT_ROOT}/scripts/utilities/setup-ssh-keys.sh"
        else
            log_info "You can distribute SSH keys later by running:"
            log_info "  ./scripts/utilities/setup-ssh-keys.sh"
        fi
    fi
}

# Run main function
main "$@"

