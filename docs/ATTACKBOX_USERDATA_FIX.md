# Attack Box User Data Fix - S3 Download Pattern

## Problem
The `attackbox_init.ps1` script was **49,197 bytes** (48KB), exceeding AWS EC2's **16,384 byte** (16KB) limit for user_data. This caused Terraform operations (including destroy) to fail with:

```
Error: expected length of user_data to be in the range (0 - 16384)
```

## Solution: S3 Download Pattern

Instead of passing the large script directly as user_data, we now:

1. **Upload the full script to S3** during Terraform deployment
2. **Use a small bootstrap script** (3KB) as user_data that downloads and executes the full script
3. **Leverage existing IAM permissions** that already allow S3 access

## Changes Made

### 1. New File: `terraform/modules/goad/attackbox_scripts.tf`
- Creates an S3 object resource for the attackbox init script
- Templates the script with all necessary variables
- Uploads to: `s3://{deployment_bucket}/{deployment_id}/scripts/attackbox_init.ps1`

### 2. New File: `terraform/modules/goad/scripts/attackbox_bootstrap.ps1`
- Lightweight bootstrap script (3,110 bytes - well under 16KB limit)
- Downloads the full init script from S3
- Includes retry logic and comprehensive error logging
- Uses AWS CLI (pre-installed on Windows Server 2022)

### 3. Modified: `terraform/modules/goad/attackbox.tf`
- Changed `user_data` to use the bootstrap script instead of the full init script
- Added dependency on `aws_s3_object.attackbox_init_script` to ensure script is uploaded before instance starts
- Reduced user_data variables to only what bootstrap needs

### 4. IAM Permissions (No Changes Required)
- Existing GOAD instance profile already has the necessary permissions:
  - `s3:GetObject` - Download the script
  - `s3:GetObjectVersion` - Version support
  - `s3:ListBucket` - Bucket access
- Policy defined in `terraform/modules/cs_storage/main.tf` lines 471-502

## How It Works

### Deployment Flow:
1. **Terraform uploads** the full `attackbox_init.ps1` to S3 (templated with variables)
2. **EC2 instance launches** with the small bootstrap script as user_data
3. **Bootstrap script runs** and downloads the full script from S3
4. **Full init script executes** with all 1,102 lines of configuration

### Error Handling:
- Bootstrap retries download up to 5 times with 10-second delays
- Comprehensive logging to `C:\Users\Administrator\Desktop\Deployment-Logs-Scripts\bootstrap.log`
- Creates error marker file if bootstrap fails
- Main init script logs to `attackbox-init.log` as before

## Benefits

✅ **Bypasses EC2 user_data size limit** - Can now use scripts of any size
✅ **No IAM changes required** - Uses existing S3 permissions
✅ **Maintains all functionality** - Full init script runs identically
✅ **Better debugging** - Separate logs for bootstrap vs. main init
✅ **Scalable pattern** - Can be applied to other large scripts if needed

## Files Structure

```
terraform/modules/goad/
├── attackbox.tf                      # Modified: uses bootstrap script
├── attackbox_scripts.tf              # New: S3 upload resource
└── scripts/
    ├── attackbox_init.ps1            # Original: now uploaded to S3
    └── attackbox_bootstrap.ps1       # New: lightweight download script
```

## Verification

```bash
# Original script size (too large)
$ wc -c attackbox_init.ps1
49197 attackbox_init.ps1  # ❌ 3x over limit

# Bootstrap script size (well under limit)
$ wc -c attackbox_bootstrap.ps1
3110 attackbox_bootstrap.ps1  # ✅ Only 19% of limit
```

## Next Steps

The infrastructure can now be destroyed or deployed without the user_data size error. The fix is transparent to users - the attack box will configure itself identically to before.
