# Getting Started Guide

This guide will walk you through setting up and deploying the Red Team Infrastructure from scratch. Follow these steps in order.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Initial Setup](#initial-setup)
3. [AWS Configuration](#aws-configuration)
4. [Project Configuration](#project-configuration)
5. [First Deployment](#first-deployment)
6. [Verification](#verification)
7. [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Software

Before starting, ensure you have the following installed on your local machine:

#### 1. AWS CLI
```bash
# Check if installed
aws --version

# Install (macOS)
brew install awscli

# Install (Linux)
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Install (Windows)
# Download from: https://aws.amazon.com/cli/
```

#### 2. Terraform
```bash
# Check if installed
terraform --version

# Install (macOS)
brew install terraform

# Install (Linux)
wget https://releases.hashicorp.com/terraform/1.6.0/terraform_1.6.0_linux_amd64.zip
unzip terraform_1.6.0_linux_amd64.zip
sudo mv terraform /usr/local/bin/

# Install (Windows)
# Download from: https://www.terraform.io/downloads
```

#### 3. Ansible
```bash
# Check if installed
ansible --version

# Install (macOS)
brew install ansible

# Install (Linux)
sudo apt-get update
sudo apt-get install ansible

# Install (Windows)
pip install ansible
```

#### 4. Python 3
```bash
# Check if installed
python3 --version

# Install (macOS)
brew install python3

# Install (Linux)
sudo apt-get install python3 python3-pip
```

#### 5. jq (JSON processor)
```bash
# Check if installed
jq --version

# Install (macOS)
brew install jq

# Install (Linux)
sudo apt-get install jq

# Install (Windows)
# Download from: https://stedolan.github.io/jq/download/
```

#### 6. Git
```bash
# Check if installed
git --version

# Install (macOS)
# Usually pre-installed, or: brew install git

# Install (Linux)
sudo apt-get install git
```

### Required Accounts

1. **AWS Account** with appropriate permissions
   - Ability to create VPCs, EC2 instances, IAM roles
   - Billing enabled
   - Access to AWS Console

2. **Domain Registrations** ⚠️ **REQUIRED PREREQUISITE**
   - **Primary domain** for C2 infrastructure
   - **2-3 backup domains** for redundancy and OpSec
   - See [Domain Requirements Guide](./DOMAIN_REQUIREMENTS.md) for details
   - **Estimated Cost**: $30-60/year for 2-3 domains

3. **GitHub Account** (optional, for version control)
   - For private repository hosting
   - For collaboration

## Initial Setup

### Step 0: Register Domains (REQUIRED PREREQUISITE) ⚠️

**Before proceeding with infrastructure setup, you MUST register domains:**

1. **Register Primary Domain**
   - Choose a legitimate-sounding domain name
   - Enable privacy protection
   - Set up auto-renewal
   - Document registrar and credentials

2. **Register Backup Domains** (2-3 minimum)
   - Use different registrars if possible
   - Different TLDs recommended (.com, .net, .org)
   - Enable privacy protection on all

3. **Set Up DNS Management**
   - Create Route53 hosted zones (if using Route53)
   - Update nameservers at registrar
   - Verify DNS propagation

**Time Required**: 1-2 hours  
**Cost**: $30-60/year for 2-3 domains

**📖 See [Domain Requirements Guide](./DOMAIN_REQUIREMENTS.md) for complete details**

### Step 1: Clone or Download the Project

If using Git:
```bash
git clone <repository-url>
cd Red_Team_Infra
```

If downloading manually:
```bash
# Extract the project to your desired location
cd Red_Team_Infra
```

### Step 2: Install Python Dependencies

```bash
# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Verify Prerequisites

Run this command to check all prerequisites:
```bash
# Check AWS CLI
aws --version || echo "ERROR: AWS CLI not installed"

# Check Terraform
terraform --version || echo "ERROR: Terraform not installed"

# Check Ansible
ansible --version || echo "ERROR: Ansible not installed"

# Check Python
python3 --version || echo "ERROR: Python 3 not installed"

# Check jq
jq --version || echo "ERROR: jq not installed"
```

All commands should return version information. If any fail, install the missing tool before proceeding.

## AWS Configuration

### Step 1: Configure AWS Credentials

You have two options:

#### Option A: AWS CLI Configuration (Recommended for Development)
```bash
aws configure
```

You'll be prompted for:
- **AWS Access Key ID**: Your AWS access key
- **AWS Secret Access Key**: Your AWS secret key
- **Default region**: e.g., `us-east-1`
- **Default output format**: `json`

#### Option B: Environment Variables
```bash
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"
```

### Step 2: Verify AWS Access

```bash
# Test your credentials
aws sts get-caller-identity
```

You should see output like:
```json
{
    "UserId": "AIDA...",
    "Account": "123456789012",
    "Arn": "arn:aws:iam::123456789012:user/your-username"
}
```

### Step 3: Create S3 Bucket for Terraform State (Optional but Recommended)

```bash
# Set your bucket name (must be globally unique)
BUCKET_NAME="red-team-terraform-state-$(date +%s)"

# Create bucket
aws s3 mb s3://$BUCKET_NAME --region us-east-1

# Enable versioning
aws s3api put-bucket-versioning \
    --bucket $BUCKET_NAME \
    --versioning-configuration Status=Enabled

# Enable encryption
aws s3api put-bucket-encryption \
    --bucket $BUCKET_NAME \
    --server-side-encryption-configuration '{
        "Rules": [{
            "ApplyServerSideEncryptionByDefault": {
                "SSEAlgorithm": "AES256"
            }
        }]
    }'

echo "Bucket created: $BUCKET_NAME"
echo "Add this to your terraform.tfvars: terraform_backend_bucket = \"$BUCKET_NAME\""
```

### Step 4: Create DynamoDB Table for State Locking (Optional but Recommended)

```bash
# Create DynamoDB table for state locking
aws dynamodb create-table \
    --table-name terraform-state-lock \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5 \
    --region us-east-1

echo "DynamoDB table created for state locking"
```

### Step 5: Create EC2 Key Pair

```bash
# Generate a new key pair
KEY_NAME="red-team-keypair"
aws ec2 create-key-pair \
    --key-name $KEY_NAME \
    --query 'KeyMaterial' \
    --output text > ~/.ssh/$KEY_NAME.pem

# Set proper permissions
chmod 400 ~/.ssh/$KEY_NAME.pem

echo "Key pair created: $KEY_NAME"
echo "Private key saved to: ~/.ssh/$KEY_NAME.pem"
```

**Important**: Save the key pair name - you'll need it in the configuration file.

## Project Configuration

### Step 1: Copy Configuration Template

```bash
cd Red_Team_Infra
cp configs/terraform.tfvars.example configs/terraform.tfvars
```

### Step 2: Edit Configuration File

Open `configs/terraform.tfvars` in your preferred editor and update the following:

**⚠️ IMPORTANT**: You must have registered your domains before configuring this section!

```hcl
# Required: AWS Configuration
aws_region = "us-east-1"  # Change to your preferred region
aws_profile = "default"   # Or your AWS profile name

# Required: Project Configuration
project_name = "red-team-infra"  # Your project name
environment = "dev"              # dev, staging, or prod

# Required: VPC Configuration
vpc_cidr = "10.0.0.0/16"  # CIDR block for your VPC
availability_zones = ["us-east-1a", "us-east-1b"]  # Adjust for your region

# Required: Subnet Configuration
public_subnet_cidrs = ["10.0.1.0/24", "10.0.2.0/24"]
private_subnet_cidrs = ["10.0.10.0/24", "10.0.11.0/24"]

# Required: EC2 Configuration
instance_type = "t3.medium"  # Instance size
key_pair_name = "red-team-keypair"  # The key pair you created
instance_count = 2  # Number of instances

# Required: Security Configuration
allowed_cidr_blocks = ["YOUR.IP.ADDRESS.HERE/32"]  # Your public IP for SSH access
enable_ssh_access = true
ssh_port = 22

# Optional: Terraform Backend (if you created S3 bucket)
terraform_backend_bucket = "red-team-terraform-state-1234567890"
terraform_backend_region = "us-east-1"
terraform_backend_key = "terraform.tfstate"

# Domain Configuration (REQUIRED - see DOMAIN_REQUIREMENTS.md)
primary_domain_name = "your-domain.com"  # Your registered primary domain
primary_domain_hosted_zone_id = ""  # Route53 hosted zone ID (if using Route53)

# Backup Domains (REQUIRED - minimum 2-3)
backup_domains = [
  {
    domain_name = "backup-domain-1.com"
    hosted_zone_id = ""
  },
  {
    domain_name = "backup-domain-2.net"
    hosted_zone_id = ""
  }
]

# Subdomain Configuration
c2_subdomain = "c2"
www_subdomain = "www"
cdn_subdomain = "cdn"
```

### Step 3: Find Your Public IP Address

```bash
# Get your public IP
curl ifconfig.me
# or
curl ipinfo.io/ip
```

Add this IP to `allowed_cidr_blocks` in the format: `"YOUR.IP.ADDRESS/32"`

### Step 4: Configure Ansible Inventory (After First Deployment)

The Ansible inventory will be generated automatically after the first Terraform deployment. However, you can create a template:

```bash
cp ansible/inventory/hosts.yml.example ansible/inventory/hosts.yml
```

You'll update this with actual IP addresses after the first deployment.

## First Deployment

### Step 1: Review the Deployment Script

Before running, review what the deployment script will do:

```bash
cat scripts/deployment/deploy.sh
```

### Step 2: Run the Deployment

```bash
# Make script executable (if needed)
chmod +x scripts/deployment/deploy.sh

# Run deployment
./scripts/deployment/deploy.sh
```

The script will:
1. ✅ Check all prerequisites
2. ✅ Verify AWS credentials
3. ✅ Validate configuration files
4. ✅ Initialize Terraform
5. ✅ Plan infrastructure changes
6. ⚠️ Ask for confirmation
7. ✅ Deploy infrastructure
8. ✅ Wait for instances to be ready
9. ✅ Configure instances with Ansible

### Step 3: Monitor the Deployment

The script will output progress information. Watch for:
- ✅ Green `[INFO]` messages for successful steps
- ⚠️ Yellow `[WARN]` messages for warnings
- ❌ Red `[ERROR]` messages for failures

### Step 4: Save Output Information

After successful deployment, the script creates `terraform-outputs.json` with connection information. Save this file securely.

```bash
# View outputs
cat terraform-outputs.json | jq
```

## Verification

### Step 1: Check Infrastructure Health

```bash
# Run health check script
chmod +x scripts/utilities/health-check.sh
./scripts/utilities/health-check.sh
```

### Step 2: Verify EC2 Instances

```bash
# List instances
aws ec2 describe-instances \
    --filters "Name=tag:Project,Values=RedTeamInfra" \
    --query 'Reservations[*].Instances[*].[InstanceId,State.Name,PublicIpAddress,Tags[?Key==`Name`].Value|[0]]' \
    --output table
```

### Step 3: Test SSH Connection

```bash
# Get instance IP from outputs
INSTANCE_IP=$(jq -r '.instance_public_ips.value[0]' terraform-outputs.json)

# Test SSH connection
ssh -i ~/.ssh/red-team-keypair.pem ec2-user@$INSTANCE_IP "echo 'SSH connection successful'"
```

### Step 4: Verify Ansible Configuration

```bash
# Test Ansible connectivity
cd ansible
ansible all -i inventory/hosts.yml -m ping
```

## Next Steps

After successful deployment:

1. **Review Infrastructure**: Check AWS Console to verify all resources
2. **Configure C2**: Run C2 setup scripts (when implemented)
3. **Set Up Monitoring**: Configure CloudWatch alarms
4. **Document Changes**: Update any custom configurations
5. **Backup Configurations**: Run backup script

```bash
# Backup configurations
chmod +x scripts/utilities/backup.sh
./scripts/utilities/backup.sh
```

## Troubleshooting

### Common Issues

#### Issue: "AWS credentials not configured"
**Solution**: Run `aws configure` and verify with `aws sts get-caller-identity`

#### Issue: "Terraform not initialized"
**Solution**: Run `cd terraform && terraform init`

#### Issue: "Permission denied" when running scripts
**Solution**: Run `chmod +x scripts/**/*.sh`

#### Issue: "Key pair not found"
**Solution**: Create key pair in AWS Console or via CLI (see AWS Configuration section)

#### Issue: "Instance not accessible via SSH"
**Solution**: 
- Check security group allows SSH from your IP
- Verify key pair name matches configuration
- Check instance is in "running" state

#### Issue: "Ansible connection failed"
**Solution**:
- Verify SSH key permissions: `chmod 400 ~/.ssh/red-team-keypair.pem`
- Check Ansible inventory has correct IP addresses
- Verify security groups allow SSH

### Getting Help

1. Check logs in `terraform/` directory
2. Review Terraform state: `terraform show`
3. Check AWS CloudWatch Logs
4. Review Ansible logs: `ansible-playbook -v` for verbose output

### Cleanup and Start Over

If you need to start over:

```bash
# Destroy infrastructure
./scripts/deployment/destroy.sh

# Remove local state (if needed)
rm -rf terraform/.terraform terraform/terraform.tfstate*

# Re-run deployment
./scripts/deployment/deploy.sh
```

## Additional Resources

- [Architecture Guide](./architecture.md) - Detailed architecture documentation
- [Deployment Guide](./deployment-guide.md) - Advanced deployment scenarios
- [Scripting Guide](./scripting-guide.md) - Understanding the automation scripts
- [Operational Procedures](./operational-procedures.md) - Day-to-day operations

## Security Reminders

⚠️ **Important Security Notes**:

1. **Never commit secrets**: The `.gitignore` file excludes sensitive files
2. **Rotate credentials**: Regularly rotate AWS access keys
3. **Limit access**: Only grant necessary permissions
4. **Monitor usage**: Regularly review CloudTrail logs
5. **Secure backups**: Encrypt backup files containing sensitive data

