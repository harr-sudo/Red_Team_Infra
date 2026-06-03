# Attack Box User Data Fix - S3 Bootstrap Pattern

> **Updated**: February 2026 — Reflects standalone attack box module (`terraform/modules/attack_box/`)

## Problem

The `attack_box_init.ps1` script exceeds AWS EC2's **16,384 byte** (16KB) limit for user_data. Passing it directly as user_data causes Terraform to fail with:

```
Error: expected length of user_data to be in the range (0 - 16384)
```

## Solution: S3 Bootstrap Pattern

Instead of passing the large script directly as user_data, the standalone module:

1. **Uploads the full script to S3** during Terraform deployment (`aws_s3_object`)
2. **Uses a small bootstrap script** (~3KB) as user_data that downloads and executes the full script
3. **Leverages existing IAM permissions** that already allow S3 access

## Implementation in Standalone Module

### File Structure

```
terraform/modules/attack_box/
├── main.tf                              # S3 upload + instance definition
└── scripts/
    ├── attack_box_init.ps1              # Full init script (uploaded to S3)
    └── attack_box_bootstrap.ps1         # Lightweight bootstrap (EC2 user_data)
```

### 1. S3 Upload (`main.tf`)

```hcl
resource "aws_s3_object" "attack_box_init_script" {
  count   = local.use_s3_bootstrap ? 1 : 0  # true when deployment_bucket != ""
  bucket  = var.deployment_bucket
  key     = "${var.deployment_id}/scripts/attack_box_init.ps1"
  content = templatefile("${path.module}/scripts/attack_box_init.ps1", {
    c2_server_ip       = var.c2_server_ip
    c2_server_port     = var.c2_server_port
    admin_password     = local.admin_password
    # ... all template variables
  })
}
```

### 2. Bootstrap Script (`attack_box_bootstrap.ps1`)

The lightweight bootstrap (< 16KB) runs as EC2 user_data:
- Downloads `attack_box_init.ps1` from S3 using AWS CLI (pre-installed on Windows Server 2022)
- Retries up to 5 times with 10-second delays
- Executes the full init script
- Logs to `C:\Users\Administrator\Desktop\Deployment-Logs-Scripts\bootstrap.log`

### 3. Instance Definition (`main.tf`)

```hcl
resource "aws_instance" "attack_box" {
  user_data = local.use_s3_bootstrap ? templatefile("${path.module}/scripts/attack_box_bootstrap.ps1", {
    deployment_bucket = var.deployment_bucket
    deployment_id     = var.deployment_id
    aws_region        = var.aws_region
  }) : null

  # Prevent instance recreation when init script changes
  lifecycle {
    ignore_changes = [user_data]
  }

  depends_on = [aws_s3_object.attack_box_init_script]
}
```

### 4. IAM Permissions (No Changes Required)

The attack box uses existing IAM instance profiles from the `cs_storage` module:
- **C2/Combined mode**: C2 instance profile with `s3:GetObject` (VPC-restricted)
- **GOAD mode**: GOAD instance profile with `s3:GetObject` + `s3:PutObject` (VPC-restricted, needs PutObject for key exchange)

## How It Works

### Deployment Flow:
1. **Terraform uploads** the full `attack_box_init.ps1` to S3 (templated with all variables)
2. **EC2 instance launches** with the small bootstrap script as user_data
3. **Bootstrap script runs** and downloads the full script from S3
4. **Full init script executes** all 8 phases of configuration

### Error Handling:
- Bootstrap retries download up to 5 times with 10-second delays
- Comprehensive logging to `C:\Users\Administrator\Desktop\Deployment-Logs-Scripts\bootstrap.log`
- Creates error marker file if bootstrap fails
- Main init script logs to `attackbox-init.log`

### Lifecycle Protection:
- `ignore_changes = [user_data]` prevents instance recreation when scripts are updated
- Use `terraform taint 'module.attack_box[0].aws_instance.attack_box'` to force rebuild

## Benefits

- **Bypasses EC2 user_data size limit** — Can use scripts of any size
- **No IAM changes required** — Uses existing S3 permissions
- **Maintains all functionality** — Full init script runs identically
- **Better debugging** — Separate logs for bootstrap vs. main init
- **Works across all 12 deployment types** — Same pattern in C2 VPC and GOAD VPC

## Verification

```bash
# Bootstrap script size (well under 16KB limit)
$ wc -c terraform/modules/attack_box/scripts/attack_box_bootstrap.ps1
# ~3KB — 19% of limit

# Full init script (would exceed limit if used directly)
$ wc -c terraform/modules/attack_box/scripts/attack_box_init.ps1
# ~15KB+ after template rendering
```

## Migration Note

This pattern was originally implemented in the GOAD module (`modules/goad/attackbox_scripts.tf`). Those files have been removed and the pattern now lives in the standalone module. The approach is identical — only the file locations changed.

See [Attack Box Architecture](./architectures/attackbox.md) for full documentation.
