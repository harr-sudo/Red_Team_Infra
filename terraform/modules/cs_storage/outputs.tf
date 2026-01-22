# CS Storage Module - Outputs
# =============================================================================
# Option C: Separate IAM Roles Per VPC
# - instance_profile_name_c2: For C2 VPC instances
# - instance_profile_name_goad: For GOAD VPC instances
# - instance_profile_name: Legacy/backwards compatible (single VPC mode)
# =============================================================================

# =============================================================================
# S3 Bucket Outputs
# =============================================================================

output "bucket_name" {
  description = "Name of the S3 bucket for CS files"
  value       = aws_s3_bucket.cs_files.id
}

output "bucket_arn" {
  description = "ARN of the S3 bucket"
  value       = aws_s3_bucket.cs_files.arn
}

output "bucket_domain_name" {
  description = "Domain name of the S3 bucket"
  value       = aws_s3_bucket.cs_files.bucket_domain_name
}

output "bucket_region" {
  description = "Region of the S3 bucket"
  value       = aws_s3_bucket.cs_files.region
}

# =============================================================================
# C2 VPC IAM Outputs (Option C - Separate Role)
# =============================================================================

output "iam_role_arn_c2" {
  description = "ARN of the IAM role for C2 VPC instances"
  value       = length(aws_iam_role.cs_download_c2) > 0 ? aws_iam_role.cs_download_c2[0].arn : null
}

output "iam_role_name_c2" {
  description = "Name of the IAM role for C2 VPC"
  value       = length(aws_iam_role.cs_download_c2) > 0 ? aws_iam_role.cs_download_c2[0].name : null
}

output "instance_profile_arn_c2" {
  description = "ARN of the instance profile for C2 VPC"
  value       = length(aws_iam_instance_profile.cs_download_c2) > 0 ? aws_iam_instance_profile.cs_download_c2[0].arn : null
}

output "instance_profile_name_c2" {
  description = "Name of the instance profile for C2 VPC (use this for C2 EC2 instances)"
  value       = length(aws_iam_instance_profile.cs_download_c2) > 0 ? aws_iam_instance_profile.cs_download_c2[0].name : null
}

# =============================================================================
# GOAD VPC IAM Outputs (Option C - Separate Role)
# =============================================================================

output "iam_role_arn_goad" {
  description = "ARN of the IAM role for GOAD VPC instances"
  value       = length(aws_iam_role.cs_download_goad) > 0 ? aws_iam_role.cs_download_goad[0].arn : null
}

output "iam_role_name_goad" {
  description = "Name of the IAM role for GOAD VPC"
  value       = length(aws_iam_role.cs_download_goad) > 0 ? aws_iam_role.cs_download_goad[0].name : null
}

output "instance_profile_arn_goad" {
  description = "ARN of the instance profile for GOAD VPC"
  value       = length(aws_iam_instance_profile.cs_download_goad) > 0 ? aws_iam_instance_profile.cs_download_goad[0].arn : null
}

output "instance_profile_name_goad" {
  description = "Name of the instance profile for GOAD VPC (use this for GOAD EC2 instances)"
  value       = length(aws_iam_instance_profile.cs_download_goad) > 0 ? aws_iam_instance_profile.cs_download_goad[0].name : null
}

# =============================================================================
# Legacy IAM Outputs (Backwards Compatibility - Single VPC Mode)
# =============================================================================

output "iam_role_arn" {
  description = "ARN of the IAM role (legacy single-VPC mode, or first available role)"
  value = coalesce(
    length(aws_iam_role.cs_download_legacy) > 0 ? aws_iam_role.cs_download_legacy[0].arn : null,
    length(aws_iam_role.cs_download_goad) > 0 ? aws_iam_role.cs_download_goad[0].arn : null,
    length(aws_iam_role.cs_download_c2) > 0 ? aws_iam_role.cs_download_c2[0].arn : null
  )
}

output "iam_role_name" {
  description = "Name of the IAM role (legacy single-VPC mode, or first available role)"
  value = coalesce(
    length(aws_iam_role.cs_download_legacy) > 0 ? aws_iam_role.cs_download_legacy[0].name : null,
    length(aws_iam_role.cs_download_goad) > 0 ? aws_iam_role.cs_download_goad[0].name : null,
    length(aws_iam_role.cs_download_c2) > 0 ? aws_iam_role.cs_download_c2[0].name : null
  )
}

output "instance_profile_arn" {
  description = "ARN of the instance profile (legacy single-VPC mode, or first available profile)"
  value = coalesce(
    length(aws_iam_instance_profile.cs_download_legacy) > 0 ? aws_iam_instance_profile.cs_download_legacy[0].arn : null,
    length(aws_iam_instance_profile.cs_download_goad) > 0 ? aws_iam_instance_profile.cs_download_goad[0].arn : null,
    length(aws_iam_instance_profile.cs_download_c2) > 0 ? aws_iam_instance_profile.cs_download_c2[0].arn : null
  )
}

output "instance_profile_name" {
  description = "Name of the instance profile (legacy single-VPC mode, or first available profile)"
  value = coalesce(
    length(aws_iam_instance_profile.cs_download_legacy) > 0 ? aws_iam_instance_profile.cs_download_legacy[0].name : null,
    length(aws_iam_instance_profile.cs_download_goad) > 0 ? aws_iam_instance_profile.cs_download_goad[0].name : null,
    length(aws_iam_instance_profile.cs_download_c2) > 0 ? aws_iam_instance_profile.cs_download_c2[0].name : null
  )
}

# =============================================================================
# Upload Command
# =============================================================================

output "upload_command" {
  description = "Example command to upload CS archive to S3"
  value       = "aws s3 cp cobaltstrike.tar.gz s3://${aws_s3_bucket.cs_files.id}/cs/"
}

# =============================================================================
# SSH Key Exchange Outputs (Phase 5 - Secure Key Management)
# =============================================================================

output "key_exchange_bucket" {
  description = "S3 bucket name for SSH key exchange"
  value       = aws_s3_bucket.cs_files.id
}

output "key_exchange_prefix" {
  description = "S3 prefix for SSH public keys"
  value       = "keys/"
}

output "status_prefix" {
  description = "S3 prefix for bootstrap status files"
  value       = "status/"
}

output "key_exchange_info" {
  description = "Information for SSH key exchange configuration"
  value = {
    bucket_name   = aws_s3_bucket.cs_files.id
    bucket_region = aws_s3_bucket.cs_files.region
    key_prefix    = "keys/"
    status_prefix = "status/"

    # Example paths for bootstrap scripts
    jumpbox_key_path = "keys/{deployment_id}/jumpbox_internal.pub"

    # Security info
    encryption    = "AES256 (SSE-S3)"
    key_retention = "7 days (auto-deleted)"

    # IAM Roles (Option C - Separate per VPC)
    iam_roles = {
      c2_role_name   = length(aws_iam_role.cs_download_c2) > 0 ? aws_iam_role.cs_download_c2[0].name : null
      goad_role_name = length(aws_iam_role.cs_download_goad) > 0 ? aws_iam_role.cs_download_goad[0].name : null
    }

    # Permissions granted
    permissions = {
      jumpbox    = "PutObject to keys/, GetObject from keys/, status operations"
      teamserver = "GetObject from keys/, status operations"
      attackbox  = "GetObject from keys/, status operations"
    }

    # Security features
    security = {
      confused_deputy_protection = "ENABLED - SourceAccount + SourceVpc conditions"
      encryption_in_transit      = "REQUIRED - SecureTransport condition"
      encryption_at_rest         = "ENABLED - AES256 (SSE-S3)"
      public_access              = "BLOCKED - All public access blocked"
      vpc_isolation              = "ENABLED - Separate IAM roles per VPC"
    }
  }
}

# =============================================================================
# Security Summary Output
# =============================================================================

output "security_summary" {
  description = "Summary of security features implemented"
  value = {
    architecture = "Option C - Separate IAM Roles Per VPC"

    c2_vpc = {
      enabled          = length(aws_iam_role.cs_download_c2) > 0
      role_name        = length(aws_iam_role.cs_download_c2) > 0 ? aws_iam_role.cs_download_c2[0].name : "not created"
      instance_profile = length(aws_iam_instance_profile.cs_download_c2) > 0 ? aws_iam_instance_profile.cs_download_c2[0].name : "not created"
      vpc_restricted   = var.c2_vpc_id != ""
    }

    goad_vpc = {
      enabled          = length(aws_iam_role.cs_download_goad) > 0
      role_name        = length(aws_iam_role.cs_download_goad) > 0 ? aws_iam_role.cs_download_goad[0].name : "not created"
      instance_profile = length(aws_iam_instance_profile.cs_download_goad) > 0 ? aws_iam_instance_profile.cs_download_goad[0].name : "not created"
      vpc_restricted   = var.goad_vpc_id != ""
    }

    threats_mitigated = [
      "Confused Deputy Attack - BLOCKED by SourceAccount condition",
      "Cross-VPC Access - BLOCKED by SourceVpc condition per role",
      "Cross-Account Access - BLOCKED by SourceAccount condition",
      "Unencrypted Transfer - BLOCKED by SecureTransport condition",
      "Public Access - BLOCKED by S3 public access block"
    ]
  }
}
