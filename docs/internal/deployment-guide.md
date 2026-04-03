# Deployment Guide

This guide provides detailed information about deploying the Red Team Infrastructure, including advanced scenarios and troubleshooting.

## Table of Contents

1. [Quick Deployment](#quick-deployment)
2. [Step-by-Step Deployment](#step-by-step-deployment)
3. [Environment-Specific Deployments](#environment-specific-deployments)
4. [Advanced Scenarios](#advanced-scenarios)
5. [Updating Infrastructure](#updating-infrastructure)
6. [Troubleshooting](#troubleshooting)

## Quick Deployment

For experienced users, here's the quickest path to deployment:

```bash
# 1. Configure AWS
aws configure

# 2. Copy and edit configuration
cp configs/terraform.tfvars.example configs/terraform.tfvars
# Edit terraform.tfvars with your values

# 3. Deploy
./scripts/deployment/deploy.sh
```

## Step-by-Step Deployment

### Phase 1: Pre-Deployment Checks

#### 1.1 Verify Prerequisites

```bash
# Run prerequisite check
./scripts/deployment/deploy.sh
# The script will check prerequisites automatically
```

Manual verification:
```bash
# Check all tools
aws --version
terraform --version
ansible --version
python3 --version
jq --version
```

#### 1.2 Verify AWS Access

```bash
# Test AWS credentials
aws sts get-caller-identity

# Test permissions (optional)
aws ec2 describe-regions
aws ec2 describe-availability-zones --region us-east-1
```

#### 1.3 Review Configuration

```bash
# Review your configuration
cat configs/terraform.tfvars

# Validate configuration format
cd terraform
terraform init
terraform validate -var-file=../configs/terraform.tfvars
```

### Phase 2: Infrastructure Deployment

#### 2.1 Initialize Terraform

```bash
cd terraform

# Initialize Terraform
terraform init

# If using S3 backend, verify backend configuration
terraform init -backend-config=../configs/terraform.tfvars
```

#### 2.2 Review Deployment Plan

```bash
# Create and review plan
terraform plan -var-file=../configs/terraform.tfvars -out=tfplan

# Review what will be created
terraform show tfplan
```

#### 2.3 Deploy Infrastructure

```bash
# Apply the plan
terraform apply tfplan

# Or use the deployment script (recommended)
cd ..
./scripts/deployment/deploy.sh
```

#### 2.4 Save Outputs

```bash
# Save Terraform outputs
terraform output -json > ../terraform-outputs.json

# View outputs
cat ../terraform-outputs.json | jq
```

### Phase 3: Instance Configuration

#### 3.1 Wait for Instances

```bash
# Get instance IDs from outputs
INSTANCE_IDS=$(jq -r '.instance_ids.value[]' terraform-outputs.json)

# Wait for instances to be ready
for instance_id in $INSTANCE_IDS; do
    echo "Waiting for instance $instance_id..."
    aws ec2 wait instance-status-ok --instance-ids $instance_id
done
```

#### 3.2 Update Ansible Inventory

```bash
# Generate inventory from Terraform outputs
cd ansible

# Create inventory file
cat > inventory/hosts.yml <<EOF
all:
  children:
    all_servers:
      hosts:
EOF

# Add instances to inventory
jq -r '.instance_public_ips.value[]' ../terraform-outputs.json | \
  awk '{print "        server" NR ":"; print "          ansible_host: " $1; print "          ansible_user: ec2-user"}' >> inventory/hosts.yml

# Add common variables
cat >> inventory/hosts.yml <<EOF
  vars:
    ansible_ssh_private_key_file: ~/.ssh/red-team-keypair.pem
    ansible_ssh_common_args: '-o StrictHostKeyChecking=no'
EOF
```

#### 3.3 Run Ansible Playbooks

```bash
# Test connectivity
ansible all -i inventory/hosts.yml -m ping

# Run base setup
ansible-playbook -i inventory/hosts.yml playbooks/base-setup.yml

# Run additional playbooks as needed
# ansible-playbook -i inventory/hosts.yml playbooks/c2-setup.yml
```

### Phase 4: Verification

#### 4.1 Infrastructure Health Check

```bash
# Run health check script
./scripts/utilities/health-check.sh
```

#### 4.2 Manual Verification

```bash
# Check EC2 instances
aws ec2 describe-instances \
    --filters "Name=tag:Project,Values=RedTeamInfra" \
    --query 'Reservations[*].Instances[*].[InstanceId,State.Name,PublicIpAddress]' \
    --output table

# Check VPC
aws ec2 describe-vpcs \
    --filters "Name=tag:Project,Values=RedTeamInfra" \
    --query 'Vpcs[*].[VpcId,CidrBlock,State]' \
    --output table

# Check Security Groups
aws ec2 describe-security-groups \
    --filters "Name=tag:Project,Values=RedTeamInfra" \
    --query 'SecurityGroups[*].[GroupId,GroupName,Description]' \
    --output table
```

#### 4.3 Test Connectivity

```bash
# Get instance IP
INSTANCE_IP=$(jq -r '.instance_public_ips.value[0]' terraform-outputs.json)

# Test SSH
ssh -i ~/.ssh/red-team-keypair.pem ec2-user@$INSTANCE_IP "hostname"

# Test HTTP (if web server configured)
curl -I http://$INSTANCE_IP
```

## Environment-Specific Deployments

### Development Environment

```bash
# Use dev configuration
cp configs/terraform.tfvars.example configs/terraform.tfvars.dev

# Edit for dev environment
# environment = "dev"
# instance_count = 1
# instance_type = "t3.small"

# Deploy with specific config
cd terraform
terraform workspace select dev
terraform apply -var-file=../configs/terraform.tfvars.dev
```

### Staging Environment

```bash
# Similar process for staging
cp configs/terraform.tfvars.example configs/terraform.tfvars.staging
# Edit configuration
terraform workspace select staging
terraform apply -var-file=../configs/terraform.tfvars.staging
```

### Production Environment

```bash
# Production deployment
cp configs/terraform.tfvars.example configs/terraform.tfvars.prod
# Edit configuration with production values
terraform workspace select prod
terraform plan -var-file=../configs/terraform.tfvars.prod
# Review plan carefully
terraform apply -var-file=../configs/terraform.tfvars.prod
```

## Advanced Scenarios

### Multi-Region Deployment

```bash
# Deploy to multiple regions
for region in us-east-1 us-west-2 eu-west-1; do
    export AWS_DEFAULT_REGION=$region
    terraform workspace new $region
    terraform apply -var-file=../configs/terraform.tfvars
done
```

### Custom AMI Deployment

```bash
# Use custom AMI
# In terraform.tfvars:
# ami_id = "ami-0123456789abcdef0"

# Or use Packer-built AMI
# Build AMI with Packer first, then use AMI ID
```

### High Availability Deployment

```bash
# Deploy across multiple availability zones
# In terraform.tfvars:
# availability_zones = ["us-east-1a", "us-east-1b", "us-east-1c"]
# instance_count = 3

# Use load balancer for distribution
```

## Updating Infrastructure

### Minor Updates (Configuration Changes)

```bash
# Update configuration file
# Edit configs/terraform.tfvars

# Plan changes
cd terraform
terraform plan -var-file=../configs/terraform.tfvars

# Apply changes
terraform apply -var-file=../configs/terraform.tfvars
```

### Major Updates (Infrastructure Changes)

```bash
# Review changes carefully
terraform plan -var-file=../configs/terraform.tfvars -detailed-exitcode

# If exit code is 2, there are changes
# Review the plan output

# Apply with confirmation
terraform apply -var-file=../configs/terraform.tfvars
```

### Updating Ansible Configuration

```bash
# Update playbooks
cd ansible

# Test playbook syntax
ansible-playbook --syntax-check playbooks/base-setup.yml

# Run playbook with check mode first
ansible-playbook -i inventory/hosts.yml playbooks/base-setup.yml --check

# Apply changes
ansible-playbook -i inventory/hosts.yml playbooks/base-setup.yml
```

## Troubleshooting

### Common Deployment Issues

#### Issue: Terraform State Lock

```bash
# If state is locked, check DynamoDB table
aws dynamodb get-item \
    --table-name terraform-state-lock \
    --key '{"LockID":{"S":"..."}}'

# Force unlock (use with caution)
terraform force-unlock <LOCK_ID>
```

#### Issue: Instance Not Accessible

```bash
# Check instance status
aws ec2 describe-instance-status --instance-ids <INSTANCE_ID>

# Check security group rules
aws ec2 describe-security-groups --group-ids <SG_ID>

# Check route tables
aws ec2 describe-route-tables --filters "Name=vpc-id,Values=<VPC_ID>"
```

#### Issue: Ansible Connection Failed

```bash
# Test SSH manually
ssh -i ~/.ssh/red-team-keypair.pem ec2-user@<INSTANCE_IP>

# Check Ansible inventory
ansible-inventory -i inventory/hosts.yml --list

# Test with verbose output
ansible all -i inventory/hosts.yml -m ping -vvv
```

### Recovery Procedures

#### Recover from Failed Deployment

```bash
# Check Terraform state
terraform show

# Identify failed resources
terraform state list

# Remove failed resource from state (if needed)
terraform state rm <resource_address>

# Re-run deployment
terraform apply -var-file=../configs/terraform.tfvars
```

#### Rollback Deployment

```bash
# If using Git, revert to previous version
git log  # Find previous commit
git checkout <previous_commit_hash> terraform/

# Re-apply previous configuration
terraform apply -var-file=../configs/terraform.tfvars
```

## Best Practices

1. **Always review plans** before applying
2. **Use workspaces** for environment separation
3. **Backup state files** regularly
4. **Test in dev** before production
5. **Monitor costs** during deployment
6. **Document custom changes**
7. **Use version control** for all changes

## Next Steps

After successful deployment:

1. Configure C2 infrastructure (see C2 setup guides)
2. Set up monitoring and alerting
3. Configure backup procedures
4. Document operational procedures
5. Train team members

