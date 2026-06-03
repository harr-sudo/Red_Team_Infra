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

## Primary Path: Dashboard Server

The AWS-hosted Dashboard Server is the production control plane and sole SSH/RDP jump. Provision it once from your laptop, then do all deploying/managing from the dashboard UI.

```bash
# 1. Provision the AWS Dashboard Server (run once, from your laptop)
./scripts/server/setup-dashboard.sh

# 2. Tunnel in and open the UI
ssh -L 5000:localhost:5000 ubuntu@<dashboard-eip>
# Then open http://localhost:5000 — deploy / destroy / manage from here

# Push code updates to the server later
./scripts/server/setup-dashboard.sh   # select Resume
```

### Dashboard Server lifecycle (run ON the server)

```bash
./scripts/server/dashboard-manage.sh start|stop|restart|status|logs|upgrade
```

## Advanced: CLI Deploy (dev-only)

> The CLI path runs Terraform from your laptop and is for development/testing. Production deploys run through the Dashboard Server above.

```bash
# Full deployment
./scripts/deployment/deploy.sh

# Health check
./scripts/utilities/health-check.sh

# Destroy infrastructure
./scripts/deployment/destroy.sh
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

Instances live in private subnets — reach them **through the Dashboard Server** (the sole SSH jump). There is no per-deployment bastion.

```bash
# Open the dashboard UI (primary)
ssh -L 5000:localhost:5000 ubuntu@<dashboard-eip>
# Then use the in-browser Terminal tab for SSH to any instance — no manual hops.

# Manual SSH to a private instance via the Dashboard Server (ProxyJump)
ssh -J ubuntu@<dashboard-eip> ec2-user@<instance-private-ip>

# Tunnel CS client to the team server through the Dashboard Server
ssh -L 50050:<c2-private-ip>:50050 ubuntu@<dashboard-eip>
# then connect Cobalt Strike to localhost:50050
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

