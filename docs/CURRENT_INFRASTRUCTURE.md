# Current Infrastructure Configuration

This document describes what AWS infrastructure is currently **defined** in the configuration files. Note that the actual Terraform modules still need to be implemented.

## Current Status: **Template/Example Files Only**

The project currently contains **example/template files** that define the infrastructure architecture. The actual Terraform modules need to be implemented to deploy this infrastructure.

## Defined Infrastructure Components

Based on the configuration files, here's what will be deployed:

### 1. **VPC (Virtual Private Cloud)**
**Module**: `terraform/modules/vpc/`

**Configuration** (from `terraform.tfvars.example`):
- **CIDR Block**: `10.0.0.0/16` (65,536 IP addresses)
- **Availability Zones**: 2 zones (e.g., `us-east-1a`, `us-east-1b`)
- **Region**: `us-east-1` (configurable)

**Subnets**:
- **Public Subnets**: 
  - `10.0.1.0/24` (256 IPs) - Zone 1
  - `10.0.2.0/24` (256 IPs) - Zone 2
- **Private Subnets**:
  - `10.0.10.0/24` (256 IPs) - Zone 1
  - `10.0.11.0/24` (256 IPs) - Zone 2

**Expected Resources** (to be implemented):
- 1 VPC
- 2 Public Subnets
- 2 Private Subnets
- Internet Gateway (for public subnets)
- NAT Gateway (for private subnet outbound access) - *Optional*
- Route Tables (public and private)
- Security Groups

### 2. **EC2 Instances**
**Module**: `terraform/modules/ec2/`

**Configuration**:
- **Instance Type**: `t3.medium` (2 vCPU, 4 GB RAM)
- **AMI**: Latest Amazon Linux 2 (auto-selected)
- **Instance Count**: 2 instances
- **Placement**: Public subnets (for initial setup)
- **Key Pair**: `red-team-keypair` (must be created separately)

**Expected Resources** (to be implemented):
- 2 EC2 instances
- Elastic IPs (if configured)
- Security Group rules for SSH access

### 3. **Security Groups**
**Module**: `terraform/modules/security/` (referenced but not yet implemented)

**Configuration**:
- **SSH Access**: Enabled on port 22
- **Allowed CIDR**: `0.0.0.0/0` (should be restricted to your IP)
- **Inbound Rules**: SSH from allowed CIDR blocks
- **Outbound Rules**: All traffic (for initial setup)

**Expected Resources**:
- Security group for EC2 instances
- Rules for SSH access
- Rules for future services (C2, redirectors, etc.)

### 4. **Terraform Backend** (Optional but Recommended)
**Configuration**:
- **S3 Bucket**: `red-team-terraform-state` (for state storage)
- **DynamoDB Table**: `terraform-state-lock` (for state locking)
- **Region**: `us-east-1`
- **Encryption**: Enabled

**Note**: These need to be created manually before first deployment (see GETTING_STARTED.md)

### 5. **Networking Module**
**Module**: `terraform/modules/networking/` (directory exists, not yet implemented)

**Planned for Future**:
- Load Balancers (ALB/NLB)
- CloudFront distributions
- Route53 DNS configuration
- VPC endpoints

## Current Configuration Values

From `configs/terraform.tfvars.example`:

```hcl
# AWS Region
aws_region = "us-east-1"

# VPC Configuration
vpc_cidr = "10.0.0.0/16"
availability_zones = ["us-east-1a", "us-east-1b"]
public_subnet_cidrs = ["10.0.1.0/24", "10.0.2.0/24"]
private_subnet_cidrs = ["10.0.10.0/24", "10.0.11.0/24"]

# EC2 Configuration
instance_type = "t3.medium"
instance_count = 2
key_pair_name = "red-team-keypair"

# Security
allowed_cidr_blocks = ["0.0.0.0/0"]  # ⚠️ Should be restricted!
enable_ssh_access = true
ssh_port = 22
```

## What's NOT Yet Implemented

The following are **planned** but not yet implemented:

### Infrastructure Modules
- ❌ VPC module (`terraform/modules/vpc/`) - **Needs implementation**
- ❌ EC2 module (`terraform/modules/ec2/`) - **Needs implementation**
- ❌ Security module (`terraform/modules/security/`) - **Needs implementation**
- ❌ Networking module (`terraform/modules/networking/`) - **Needs implementation**

### Advanced Features
- ❌ NAT Gateway (for private subnet internet access)
- ❌ Auto Scaling Groups
- ❌ Load Balancers
- ❌ CloudFront distributions
- ❌ Route53 DNS
- ❌ SSL/TLS certificates (ACM)
- ❌ CloudWatch alarms and monitoring
- ❌ VPC Flow Logs
- ❌ IAM roles for EC2 instances

### Red Team Specific
- ❌ C2 server infrastructure
- ❌ Redirector setup
- ❌ Domain fronting configuration
- ❌ Phishing infrastructure
- ❌ Data exfiltration endpoints

## Estimated AWS Costs (Monthly)

Based on current configuration:

### Always-On Resources
- **2x t3.medium EC2 instances**: ~$60/month (24/7)
- **VPC**: Free
- **Internet Gateway**: Free
- **NAT Gateway** (if added): ~$32/month + data transfer
- **EBS Storage** (2x 8GB): ~$2/month
- **Elastic IPs** (if used): Free (if attached to instances)

### Optional Backend
- **S3 for Terraform state**: <$1/month
- **DynamoDB for state locking**: <$1/month

### Total Estimated Cost
- **Minimum**: ~$62/month (2 instances, basic VPC)
- **With NAT Gateway**: ~$95/month
- **With monitoring/logging**: +$10-20/month

**Note**: Costs vary by region and usage. Use AWS Calculator for accurate estimates.

## Next Steps to Make This Functional

1. **Implement VPC Module** (`terraform/modules/vpc/main.tf`)
   - Create VPC resource
   - Create public/private subnets
   - Create Internet Gateway
   - Create route tables
   - Create security groups

2. **Implement EC2 Module** (`terraform/modules/ec2/main.tf`)
   - Create EC2 instances
   - Attach security groups
   - Configure user data (optional)

3. **Create Main Terraform Files**
   - Copy `main.tf.example` to `main.tf`
   - Copy `variables.tf.example` to `variables.tf`
   - Create `outputs.tf`

4. **Test Deployment**
   - Run `terraform init`
   - Run `terraform plan`
   - Review changes
   - Run `terraform apply`

## Security Considerations

⚠️ **Current Configuration Issues**:

1. **SSH Access**: Currently set to `0.0.0.0/0` - **MUST be restricted** to your IP
2. **No IAM Roles**: EC2 instances don't have IAM roles configured
3. **No Encryption**: EBS volumes not explicitly encrypted
4. **No Monitoring**: CloudWatch alarms not configured
5. **No Logging**: VPC Flow Logs not enabled

**Recommendations**:
- Restrict SSH to your IP: `allowed_cidr_blocks = ["YOUR.IP.ADDRESS/32"]`
- Add IAM roles with least privilege
- Enable EBS encryption
- Set up CloudWatch monitoring
- Enable VPC Flow Logs

## Summary

**Current State**: 
- ✅ Configuration templates defined
- ✅ Architecture planned
- ❌ Terraform modules not implemented
- ❌ Cannot deploy yet

**To Deploy**:
1. Implement Terraform modules
2. Copy example files to actual files
3. Configure `terraform.tfvars`
4. Run deployment

The infrastructure is **designed** but not yet **implemented**. The next phase is to create the actual Terraform module code.

