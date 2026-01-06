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
    
    # Update Ansible inventory from Terraform output
    log_info "Updating Ansible inventory..."
    # TODO: Generate inventory from Terraform outputs
    
    # Run Ansible playbooks
    cd "${ANSIBLE_DIR}"
    
    log_info "Running base setup playbook..."
    ansible-playbook playbooks/base-setup.yml
    
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
}

# Run main function
main "$@"

