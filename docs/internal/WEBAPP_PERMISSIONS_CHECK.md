# Web Application - AWS Permissions Check Feature

## Overview

The web application now includes a **permissions checker** that validates whether your AWS account has all the required permissions to deploy the Red Team Infrastructure.

## Feature Location

**Health Tab** → **AWS Permissions** section

## What It Checks

The permissions checker validates permissions across four categories:

### 1. EC2 Permissions
- `ec2:CreateVpc` - Create VPC
- `ec2:CreateSubnet` - Create subnets
- `ec2:CreateInternetGateway` - Create Internet Gateway
- `ec2:CreateRouteTable` - Create route tables
- `ec2:CreateRoute` - Create routes
- `ec2:CreateSecurityGroup` - Create security groups
- `ec2:RunInstances` - Launch EC2 instances
- `ec2:AllocateAddress` - Allocate Elastic IPs
- `ec2:AssociateAddress` - Associate Elastic IPs
- `ec2:Describe*` - Read EC2 resources
- And more...

### 2. IAM Permissions
- `iam:GetRole` - Read IAM roles
- `iam:GetInstanceProfile` - Read instance profiles
- `iam:PassRole` - Pass roles to EC2 instances (if using instance profiles)

### 3. S3 Permissions (if using Terraform backend)
- `s3:CreateBucket` - Create S3 buckets
- `s3:PutObject` - Store Terraform state
- `s3:GetObject` - Retrieve Terraform state
- `s3:ListBucket` - List buckets

### 4. CloudWatch Permissions (if using monitoring)
- `cloudwatch:PutMetricData` - Send metrics
- `logs:CreateLogGroup` - Create log groups
- `logs:PutLogEvents` - Write logs

## How It Works

### Method 1: Policy Simulation (Preferred)

If your AWS account has `iam:SimulatePrincipalPolicy` permission:

1. Gets your AWS identity (ARN)
2. Simulates all required permissions
3. Returns accurate results for each permission
4. Shows exactly which permissions are missing

**Status**: ✅ **Accurate** - Uses AWS IAM policy simulation

### Method 2: Simple Check (Fallback)

If policy simulation is not available:

1. Tests read-only operations (safe to test)
2. Notes write operations as "cannot safely test"
3. Provides best-effort results

**Status**: ⚠️ **Best Effort** - Cannot test write permissions safely

## Using the Feature

### In Web Application

1. Start the web application:
   ```bash
   ./webapp/start.sh
   ```

2. Navigate to **Health** tab

3. Scroll to **AWS Permissions** section

4. Click **Check Required Permissions**

5. Review the results:
   - ✅ **Green**: All permissions available
   - ⚠️ **Yellow**: Some permissions may be missing
   - ❌ **Red**: Missing required permissions

### API Endpoint

You can also check permissions via API:

```bash
curl http://127.0.0.1:5000/api/health/permissions
```

**Response Example:**
```json
{
  "success": true,
  "method": "policy_simulation",
  "overall_status": "complete",
  "missing_permissions": [],
  "available_permissions": [
    "ec2:CreateVpc",
    "ec2:CreateSubnet",
    ...
  ],
  "permissions": {
    "ec2:CreateVpc": {
      "allowed": true,
      "decision": "allowed"
    },
    ...
  },
  "categories": {
    "EC2": {
      "status": "complete",
      "required": true
    },
    ...
  }
}
```

## Understanding Results

### Overall Status

- **complete**: ✅ All required permissions are available
- **partial**: ⚠️ Some permissions may be missing
- **missing**: ❌ Required permissions are missing
- **unknown**: Cannot determine (using fallback method)

### Category Status

Each category (EC2, IAM, S3, CloudWatch) shows:
- **complete**: All permissions available
- **partial**: Some permissions available
- **missing**: No permissions available

### Missing Permissions List

If permissions are missing, the checker shows:
- Exact permission names (e.g., `ec2:CreateVpc`)
- Which category they belong to
- Total count of missing permissions

## What to Do If Permissions Are Missing

### Option 1: Request Additional Permissions

Contact your AWS administrator to add the missing permissions to your IAM user/role.

### Option 2: Use a Different AWS Account

If you have access to another AWS account with full permissions, configure that account:

```bash
aws configure --profile red-team
# Enter credentials for account with full permissions
```

Then in `terraform.tfvars`:
```hcl
aws_profile = "red-team"
```

### Option 3: Create IAM Policy

Create an IAM policy with required permissions and attach it to your user:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:*",
                "iam:GetRole",
                "iam:GetInstanceProfile",
                "iam:PassRole",
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

## Limitations

### Write Permissions

The simple check method cannot safely test write permissions (like `ec2:CreateVpc`) because:
- Testing would actually create resources
- Could incur costs
- Could cause conflicts

These are marked as "cannot safely test" in the results.

### Policy Simulation

Policy simulation requires:
- `iam:SimulatePrincipalPolicy` permission
- IAM access to your account

If not available, the checker falls back to simple checks.

### Best Practices

1. **Run before deployment**: Check permissions before attempting deployment
2. **Use policy simulation**: Ensure you have `iam:SimulatePrincipalPolicy` for accurate results
3. **Review missing permissions**: Address missing permissions before deployment
4. **Test in non-production**: Test permissions in a non-production account first

## Integration with Deployment

The permissions checker is **informational only**. It doesn't block deployment, but:

1. **Recommended**: Check permissions before deploying
2. **Warning**: If permissions are missing, deployment will fail
3. **Action**: Fix missing permissions before deploying

## Troubleshooting

### "Policy simulation not available"

**Cause**: Your AWS account doesn't have `iam:SimulatePrincipalPolicy` permission.

**Solution**: 
- Request this permission from your AWS administrator
- Or use the fallback simple check method

### "Cannot get caller identity"

**Cause**: AWS credentials not configured.

**Solution**: 
```bash
aws configure
```

### "Access Denied" errors

**Cause**: Missing required permissions.

**Solution**: 
- Review missing permissions list
- Request additional permissions
- Or use different AWS account

## Summary

✅ **New Feature**: AWS Permissions Checker  
✅ **Location**: Health Tab → AWS Permissions  
✅ **Purpose**: Validate required permissions before deployment  
✅ **Methods**: Policy simulation (accurate) or simple check (fallback)  
✅ **Status**: Shows overall and per-category permission status  

**Use this feature before deploying to ensure your AWS account has all required permissions!**

