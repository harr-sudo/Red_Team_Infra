# AWS Authentication Guide

This document explains how the Red Team Infrastructure deployment connects to your AWS account.

## Overview

The deployment uses the **AWS credential chain** to authenticate with AWS. This means Terraform and AWS CLI automatically look for credentials in a specific order until they find valid ones.

The framework supports two deployment modes with different authentication models:

- **Server Mode** — IAM instance role on the dashboard EC2 server (recommended)
- **Local Mode** — AWS credentials configured on your laptop

---

## Server Mode Authentication

When the dashboard runs on a centralized EC2 server (t3.medium in its own VPC at 10.100.0.0/16), authentication is handled by an **IAM instance role** attached to the server.

### How It Works

```
┌─────────────────────────────────────────┐
│  Dashboard Server (EC2)                 │
│  IAM Instance Role auto-attached        │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│  AWS Credential Chain (automatic)       │
│  → IAM Role credentials (auto-rotating) │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│  AWS API (Terraform, AWS CLI, etc.)     │
└─────────────────────────────────────────┘
```

### Key Benefits

- **No credentials on disk** — The instance role provides temporary credentials that rotate automatically. There are no access keys stored in `~/.aws/credentials` or environment variables.
- **Operators don't need AWS CLI configured locally** — The server handles all AWS API calls. Operators only need SSH access to the dashboard server.
- **Terraform runs ON the server** — `terraform plan` and `terraform apply` execute on the EC2 instance using the instance role. No credentials leave the server.
- **More secure than local mode** — Eliminates the risk of long-lived access keys on operator laptops, which can be lost, stolen, or accidentally committed to Git.
- **Automatic rotation** — IAM instance role credentials are rotated by AWS automatically (typically every ~6 hours). No manual key rotation needed.

### What Operators Need

Operators connecting to the dashboard server only need:

1. **SSH access** to the dashboard server (key-based authentication)
2. A browser to open `http://localhost:5000` after tunneling in

They do **not** need:
- AWS CLI installed locally
- AWS access keys or secret keys
- `~/.aws/credentials` or `~/.aws/config` files
- Any AWS IAM user account (unless they need direct AWS Console access)

### Verification (On the Server)

```bash
# SSH into the dashboard server
ssh harris@<dashboard-server-ip>

# Verify the instance role is working
aws sts get-caller-identity
# Should show the instance role ARN, not an IAM user
```

---

## Local Mode Authentication

> **Note:** This section applies when running the dashboard from your laptop. If you are using Server Mode, see the section above.

## How It Works

### Authentication Flow

```
┌─────────────────────────────────────────┐
│  Deployment Script / Terraform          │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│  AWS Credential Chain (automatic)       │
│  1. Environment Variables               │
│  2. AWS Credentials File (~/.aws/)      │
│  3. IAM Role (if on EC2)                │
│  4. AWS SSO (if configured)               │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│  AWS API (creates resources)            │
└─────────────────────────────────────────┘
```

### Terraform Provider

The Terraform AWS provider automatically uses credentials from the credential chain:

```hcl
provider "aws" {
  region = var.aws_region
  # No explicit credentials needed - uses credential chain
}
```

Terraform will automatically:
1. Check environment variables
2. Check `~/.aws/credentials` file
3. Check `~/.aws/config` file (for profiles)
4. Use IAM roles if running on EC2
5. Use AWS SSO if configured

## Configuration Methods

### Method 1: AWS CLI Configuration (Recommended)

This is the **easiest and most common** method:

```bash
aws configure
```

You'll be prompted for:
- **AWS Access Key ID**: Your AWS access key
- **AWS Secret Access Key**: Your AWS secret key
- **Default region**: e.g., `us-east-1`
- **Default output format**: `json`

This creates:
- `~/.aws/credentials` - Contains your access keys
- `~/.aws/config` - Contains region and output format

**Example `~/.aws/credentials`:**
```ini
[default]
aws_access_key_id = AKIAIOSFODNN7EXAMPLE
aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

**Example `~/.aws/config`:**
```ini
[default]
region = us-east-1
output = json
```

### Method 2: Environment Variables

Set these in your shell session:

```bash
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"
```

**For permanent setup**, add to `~/.bashrc` or `~/.zshrc`:
```bash
echo 'export AWS_ACCESS_KEY_ID="your-access-key"' >> ~/.bashrc
echo 'export AWS_SECRET_ACCESS_KEY="your-secret-key"' >> ~/.bashrc
echo 'export AWS_DEFAULT_REGION="us-east-1"' >> ~/.bashrc
source ~/.bashrc
```

### Method 3: AWS Profiles

Use different credentials for different projects:

```bash
aws configure --profile red-team
```

Then specify the profile in `terraform.tfvars`:
```hcl
aws_profile = "red-team"
```

Or use environment variable:
```bash
export AWS_PROFILE=red-team
```

### Method 4: IAM Roles (EC2 Instances)

If running Terraform from an EC2 instance, you can use IAM roles:

1. Create an IAM role with necessary permissions
2. Attach the role to the EC2 instance
3. Terraform will automatically use the role's credentials

**No configuration needed** - it's automatic!

### Method 5: AWS SSO (Single Sign-On)

For organizations using AWS SSO:

```bash
aws configure sso
```

Follow the prompts to configure SSO access.

## Verification

### Check Your Credentials

The deployment script automatically checks credentials:

```bash
./scripts/deployment/deploy.sh
# Will check: aws sts get-caller-identity
```

**Manual check:**
```bash
aws sts get-caller-identity
```

**Expected output:**
```json
{
    "UserId": "AIDAEXAMPLE123",
    "Account": "123456789012",
    "Arn": "arn:aws:iam::123456789012:user/your-username"
}
```

### Using the Web Application

The web application also checks AWS connectivity:

1. Go to **Health** tab
2. Click **Check AWS**
3. View your AWS account and user information

## How Deployment Uses Credentials

### Step-by-Step Process

1. **Deployment Script Starts**
   ```bash
   ./scripts/deployment/deploy.sh
   ```

2. **Checks AWS Credentials**
   ```bash
   aws sts get-caller-identity
   ```
   - Verifies credentials are configured
   - Displays AWS account and user

3. **Terraform Initializes**
   ```bash
   terraform init
   ```
   - Terraform provider automatically uses credentials from chain

4. **Terraform Applies**
   ```bash
   terraform apply
   ```
   - Uses same credentials to create AWS resources
   - All API calls authenticated automatically

### What Happens Behind the Scenes

When Terraform runs, it:
1. Reads credentials from the credential chain
2. Makes API calls to AWS (EC2, VPC, IAM, etc.)
3. Creates/modifies/deletes resources in your AWS account
4. Stores state locally (or in S3 if configured)

**Example API calls:**
- `CreateVpc` - Creates your VPC
- `RunInstances` - Creates EC2 instances
- `CreateSecurityGroup` - Creates security groups
- `AllocateAddress` - Creates Elastic IPs

All authenticated using your credentials!

## Security Best Practices

### ✅ Do's

1. **Use IAM Users with Least Privilege**
   - Create dedicated IAM user for Terraform
   - Grant only necessary permissions
   - Use separate users for different environments

2. **Rotate Credentials Regularly**
   - Rotate access keys every 90 days
   - Use AWS IAM Access Analyzer to find unused keys

3. **Use IAM Roles When Possible**
   - Prefer IAM roles over access keys
   - Use roles for EC2 instances
   - Use roles for CI/CD pipelines

4. **Protect Credential Files**
   ```bash
   chmod 600 ~/.aws/credentials
   chmod 600 ~/.aws/config
   ```

5. **Use AWS SSO for Organizations**
   - Centralized credential management
   - Automatic credential rotation
   - Better audit trail

### ❌ Don'ts

1. **Don't Commit Credentials to Git**
   - Never commit `~/.aws/credentials`
   - Never commit `terraform.tfvars` with secrets
   - Use `.gitignore` to exclude sensitive files

2. **Don't Share Credentials**
   - Each user should have their own credentials
   - Use IAM roles for shared access

3. **Don't Use Root Account Credentials**
   - Always use IAM users or roles
   - Root account should only be for billing

4. **Don't Hardcode Credentials**
   - Never put credentials in code
   - Use environment variables or credential files

## Required AWS Permissions

Your AWS credentials need permissions to:

### EC2
- `ec2:CreateVpc`
- `ec2:CreateSubnet`
- `ec2:RunInstances`
- `ec2:CreateSecurityGroup`
- `ec2:AllocateAddress`
- `ec2:AssociateAddress`
- `ec2:Describe*` (for reading resources)

### VPC
- `ec2:CreateInternetGateway`
- `ec2:CreateRouteTable`
- `ec2:CreateRoute`
- `ec2:CreateNatGateway`

### IAM (if using instance profiles)
- `iam:CreateRole`
- `iam:AttachRolePolicy`
- `iam:CreateInstanceProfile`
- `iam:AddRoleToInstanceProfile`

### S3 (if using Terraform backend)
- `s3:CreateBucket`
- `s3:PutObject`
- `s3:GetObject`
- `s3:ListBucket`

### CloudWatch (if using monitoring)
- `cloudwatch:PutMetricData`
- `logs:CreateLogGroup`
- `logs:PutLogEvents`

### Example IAM Policy

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:*",
                "iam:CreateRole",
                "iam:AttachRolePolicy",
                "iam:CreateInstanceProfile",
                "iam:AddRoleToInstanceProfile",
                "s3:*",
                "cloudwatch:*",
                "logs:*"
            ],
            "Resource": "*"
        }
    ]
}
```

**Note**: For production, use more restrictive policies with specific resource ARNs.

## Troubleshooting

### Issue: "AWS credentials not configured"

**Symptoms:**
```
Error: No valid credential sources found
```

**Solutions:**
1. Run `aws configure`
2. Check environment variables: `echo $AWS_ACCESS_KEY_ID`
3. Verify credentials file: `cat ~/.aws/credentials`
4. Test credentials: `aws sts get-caller-identity`

### Issue: "Access Denied"

**Symptoms:**
```
Error: AccessDenied: User is not authorized to perform: ec2:RunInstances
```

**Solutions:**
1. Check IAM permissions
2. Verify user has necessary policies attached
3. Check if resource limits are reached
4. Verify region permissions

### Issue: "Invalid credentials"

**Symptoms:**
```
Error: InvalidClientTokenId: The security token included in the request is invalid
```

**Solutions:**
1. Verify access key ID is correct
2. Check if secret key is correct
3. Verify credentials haven't been rotated
4. Check if account is suspended

### Issue: "Region not available"

**Symptoms:**
```
Error: Could not find region
```

**Solutions:**
1. Verify region name is correct
2. Check if region is enabled in your account
3. Verify `aws_region` in `terraform.tfvars`

## Testing Your Setup

### Quick Test

```bash
# 1. Check credentials
aws sts get-caller-identity

# 2. Check region access
aws ec2 describe-regions

# 3. Check permissions (list EC2 instances)
aws ec2 describe-instances

# 4. Test Terraform
cd terraform
terraform init
terraform validate
```

### Using Web Application

1. Connect to dashboard: `ssh -L 5000:localhost:5000 <operator>@<dashboard-ip>`
2. Go to **Health** tab
3. Click **Check AWS**
4. Verify account and user information

## Summary

- ✅ **Credentials are automatic** - Terraform uses AWS credential chain
- ✅ **No hardcoding needed** - Credentials come from environment or files
- ✅ **Multiple methods** - CLI config, environment variables, profiles, roles
- ✅ **Secure by default** - Credentials never in code
- ✅ **Easy to verify** - Use `aws sts get-caller-identity`

**Most common setup:**
```bash
aws configure
# Enter your access key, secret key, and region
# Done! Terraform will use these automatically
```

## Additional Resources

- [AWS CLI Configuration](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html)
- [Terraform AWS Provider Authentication](https://registry.terraform.io/providers/hashicorp/aws/latest/docs#authentication)
- [AWS IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)

