# Quick Reference Guide

Quick commands and checklists for common tasks.

## Prerequisites Checklist

```bash
# Verify all tools installed
aws --version && \
terraform --version && \
ansible --version && \
python3 --version && \
jq --version && \
git --version
```

## Initial Setup

```bash
# 1. Configure AWS
aws configure

# 2. Verify AWS access
aws sts get-caller-identity

# 3. Create key pair
aws ec2 create-key-pair --key-name red-team-keypair \
    --query 'KeyMaterial' --output text > ~/.ssh/red-team-keypair.pem
chmod 400 ~/.ssh/red-team-keypair.pem

# 4. Copy configuration
cp configs/terraform.tfvars.example configs/terraform.tfvars
# Edit terraform.tfvars with your values

# 5. Install Python dependencies
pip install -r requirements.txt
```

## Local Mode Commands

```bash
# Dashboard server (first-time setup)
./scripts/server/setup-dashboard.sh
# Then SSH tunnel: ssh -L 5000:localhost:5000 <user>@<dashboard-ip>

# Full deployment
./scripts/deployment/deploy.sh

# Health check
./scripts/utilities/health-check.sh

# Destroy infrastructure
./scripts/deployment/destroy.sh
```

## Server Mode Commands

```bash
# Connect to dashboard (from operator laptop)
ssh -L 5000:localhost:5000 harris@<dashboard-ip>

# Setup script (first time on the server)
./scripts/server/setup-dashboard.sh

# Server management (on the server)
./scripts/server/dashboard-manage.sh start|stop|restart|status|logs

# Push code updates to server
./scripts/server/setup-dashboard.sh  # select Resume
```

## Manual Terraform Commands

```bash
cd terraform

# Initialize
terraform init

# Plan
terraform plan -var-file=../configs/terraform.tfvars

# Apply
terraform apply -var-file=../configs/terraform.tfvars

# Destroy
terraform destroy -var-file=../configs/terraform.tfvars

# Show outputs
terraform output
terraform output -json > ../terraform-outputs.json
```

## Ansible Commands

```bash
cd ansible

# Test connectivity
ansible all -i inventory/hosts.yml -m ping

# Run playbook
ansible-playbook -i inventory/hosts.yml playbooks/base-setup.yml

# Run with tags
ansible-playbook -i inventory/hosts.yml playbooks/base-setup.yml --tags "security"

# Dry run (check mode)
ansible-playbook -i inventory/hosts.yml playbooks/base-setup.yml --check
```

## AWS CLI Commands

```bash
# List instances
aws ec2 describe-instances \
    --filters "Name=tag:Project,Values=RedTeamInfra" \
    --query 'Reservations[*].Instances[*].[InstanceId,State.Name,PublicIpAddress]' \
    --output table

# Get instance status
aws ec2 describe-instance-status --instance-ids <INSTANCE_ID>

# Wait for instance
aws ec2 wait instance-status-ok --instance-ids <INSTANCE_ID>

# List security groups
aws ec2 describe-security-groups \
    --filters "Name=tag:Project,Values=RedTeamInfra" \
    --output table
```

## SSH Commands

```bash
# Get instance IP from outputs
INSTANCE_IP=$(jq -r '.instance_public_ips.value[0]' terraform-outputs.json)

# SSH to instance
ssh -i ~/.ssh/red-team-keypair.pem ec2-user@$INSTANCE_IP

# Run command remotely
ssh -i ~/.ssh/red-team-keypair.pem ec2-user@$INSTANCE_IP "command"
```

## GitHub Commands

```bash
# Check GitHub auth
gh auth status

# Login to GitHub
gh auth login

# Create repository
gh repo create Red_Team_Infra --private --source=. --remote=origin --push

# Initial commit and push
git add .
git commit -m "Initial commit"
git push -u origin main
```

## Troubleshooting Commands

```bash
# Check Terraform state
cd terraform && terraform show

# List Terraform resources
terraform state list

# Validate Terraform config
terraform validate

# Check Ansible syntax
ansible-playbook --syntax-check playbooks/base-setup.yml

# Verbose Ansible output
ansible-playbook -i inventory/hosts.yml playbooks/base-setup.yml -vvv
```

## File Locations

```
terraform-outputs.json    # Infrastructure connection info
configs/terraform.tfvars  # Main configuration (DO NOT COMMIT)
~/.ssh/red-team-keypair.pem  # SSH private key
terraform/.terraform/     # Terraform cache
terraform/terraform.tfstate  # Terraform state (if local)
```

## Important Notes

- ⚠️ Never commit `terraform.tfvars` (contains secrets)
- ⚠️ Never commit `.pem` or `.key` files
- ✅ Always review `terraform plan` before applying
- ✅ Backup `terraform-outputs.json` securely
- ✅ Use private GitHub repositories
- ✅ Rotate credentials regularly

