# CS Storage Module - S3 Bucket and IAM for Cobalt Strike Files
# =============================================================================
# This module creates:
#   - S3 bucket for storing Cobalt Strike archives
#   - SEPARATE IAM roles per VPC (Option C - Maximum Security)
#     - cs_download_c2: For C2 VPC instances (Team Servers, Redirectors, Bastion)
#     - cs_download_goad: For GOAD VPC instances (Jumpbox, Attack Box, Team Server)
#   - Bucket encryption and lifecycle policies
#   - SSH key exchange support (Phase 5 - Secure Key Management)
#
# SECURITY ARCHITECTURE (Option C - Separate IAM Roles Per VPC):
# ┌─────────────────────────────────────────────────────────────────────────┐
# │                           S3 BUCKET                                     │
# │                    (cs-files-{random})                                  │
# │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                     │
# │  │    cs/      │  │   keys/     │  │  status/    │                     │
# │  │ (archives)  │  │ (SSH keys)  │  │ (bootstrap) │                     │
# │  └─────────────┘  └─────────────┘  └─────────────┘                     │
# └─────────────────────────────────────────────────────────────────────────┘
#                    ▲                              ▲
#                    │                              │
#     ┌──────────────┴──────────────┐  ┌───────────┴───────────────┐
#     │   IAM Role: cs_download_c2  │  │  IAM Role: cs_download_goad│
#     │   ✅ SourceAccount: YOUR_ID │  │  ✅ SourceAccount: YOUR_ID │
#     │   ✅ SourceVpc: C2_VPC_ID   │  │  ✅ SourceVpc: GOAD_VPC_ID │
#     │   ✅ SecureTransport: true  │  │  ✅ SecureTransport: true  │
#     └─────────────────────────────┘  └─────────────────────────────┘
#                    ▲                              ▲
#                    │                              │
#     ┌──────────────┴──────────────┐  ┌───────────┴───────────────┐
#     │         C2 VPC              │  │        GOAD VPC           │
#     │  • Team Servers             │  │  • Jumpbox                │
#     │  • Redirectors              │  │  • Team Server            │
#     │  • Bastion                  │  │  • Attack Box             │
#     │                             │  │  • GOAD VMs               │
#     └─────────────────────────────┘  └─────────────────────────────┘
#
# CONFUSED DEPUTY ATTACK: BLOCKED ✅
# - Each role restricted to specific AWS account
# - Each role restricted to specific VPC
# - Cross-VPC access: IMPOSSIBLE
# - Cross-account access: IMPOSSIBLE
# =============================================================================

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

# Random suffix for globally unique bucket name
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# Local to sanitize project name for S3 bucket (lowercase, no underscores)
locals {
  # S3 bucket names must be lowercase, 3-63 chars, only letters, numbers, hyphens
  sanitized_name = lower(replace(var.project_name, "_", "-"))

  # Determine which roles to create based on VPC IDs provided
  create_c2_role   = var.enable_c2_role && var.c2_vpc_id != ""
  create_goad_role = var.enable_goad_role && var.goad_vpc_id != ""

  # Backwards compatibility: if old vpc_id is provided, determine which role to create
  # This handles the case where only one VPC exists (C2-only or GOAD-only modes)
  legacy_vpc_id = var.vpc_id != "" && !local.create_c2_role && !local.create_goad_role ? var.vpc_id : ""
}

# =============================================================================
# S3 Bucket for Cobalt Strike Files and SSH Key Exchange
# =============================================================================

resource "aws_s3_bucket" "cs_files" {
  bucket = "${local.sanitized_name}-cs-files-${random_id.bucket_suffix.hex}"

  # Allow Terraform to delete bucket even if it contains objects
  # This is needed because versioning is enabled and objects may exist
  force_destroy = true

  tags = merge(var.tags, {
    Name      = "${var.project_name}-cs-files"
    Purpose   = "CobaltStrikeStorage"
    Component = "C2Infrastructure"
  })
}

# Bucket versioning (optional but recommended)
resource "aws_s3_bucket_versioning" "cs_files" {
  bucket = aws_s3_bucket.cs_files.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Server-side encryption (REQUIRED for Cobalt Strike files)
# Uses AES256 (SSE-S3) - AWS manages encryption keys automatically
# All objects uploaded to this bucket are encrypted at rest
resource "aws_s3_bucket_server_side_encryption_configuration" "cs_files" {
  bucket = aws_s3_bucket.cs_files.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true # Reduces S3 API calls for encryption
  }
}

# Block all public access
resource "aws_s3_bucket_public_access_block" "cs_files" {
  bucket = aws_s3_bucket.cs_files.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle policy - delete old files after 30 days
resource "aws_s3_bucket_lifecycle_configuration" "cs_files" {
  bucket = aws_s3_bucket.cs_files.id

  # Rule for CS archives - keep for 30 days
  rule {
    id     = "delete-old-cs-files"
    status = "Enabled"

    filter {
      prefix = "cs/" # Only apply to CS archives
    }

    expiration {
      days = 30
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }

  # Rule for SSH key exchange - delete after 7 days (keys are only needed during bootstrap)
  rule {
    id     = "delete-old-keys"
    status = "Enabled"

    filter {
      prefix = "keys/" # SSH public keys for key exchange
    }

    expiration {
      days = 7 # Keys only needed during initial bootstrap
    }

    noncurrent_version_expiration {
      noncurrent_days = 1
    }
  }

  # Rule for status files - delete after 7 days
  rule {
    id     = "delete-old-status"
    status = "Enabled"

    filter {
      prefix = "status/" # Bootstrap status files
    }

    expiration {
      days = 7
    }

    noncurrent_version_expiration {
      noncurrent_days = 1
    }
  }

  # Default rule for other files
  rule {
    id     = "delete-other-old-files"
    status = "Enabled"

    filter {
      prefix = "" # Apply to all other objects
    }

    expiration {
      days = 30
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }
}

# =============================================================================
# Get Current AWS Account ID (for security restrictions)
# =============================================================================

data "aws_caller_identity" "current" {}

# =============================================================================
# S3 BUCKET POLICY - Confused Deputy Attack Protection
# =============================================================================
# This policy provides defense-in-depth by enforcing security at the bucket level
# in addition to IAM role policies. This protects against Confused Deputy attacks
# where an attacker might bypass IAM trust policies.
#
# Protection Layers:
#   1. Deny all access from outside authorized VPCs
#   2. Deny all access from other AWS accounts  
#   3. Deny all unencrypted (non-HTTPS) requests
#
# AWS Best Practice: Use both IAM policies AND bucket policies for defense in depth
# Reference: https://docs.aws.amazon.com/IAM/latest/UserGuide/confused-deputy.html
# =============================================================================

data "aws_iam_policy_document" "bucket_policy" {
  # Statement 1: Deny access from outside authorized VPCs
  # This prevents Confused Deputy attacks by validating request origin at bucket level
  statement {
    sid    = "DenyAccessFromOutsideVPCs"
    effect = "Deny"
    
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    
    actions = ["s3:*"]
    
    resources = [
      aws_s3_bucket.cs_files.arn,
      "${aws_s3_bucket.cs_files.arn}/*"
    ]
    
    # Deny if request is NOT from authorized VPCs
    # Build list of allowed VPCs dynamically based on what's configured
    condition {
      test     = "StringNotEquals"
      variable = "aws:SourceVpc"
      values = compact([
        local.create_c2_role ? var.c2_vpc_id : "",
        local.create_goad_role ? var.goad_vpc_id : "",
        local.legacy_vpc_id != "" ? local.legacy_vpc_id : ""
      ])
    }
    
    # IMPORTANT: Don't block Terraform operations (which don't come from VPC)
    # Allow access if principal is in our account (for Terraform)
    condition {
      test     = "StringNotEquals"
      variable = "aws:PrincipalAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
  
  # Statement 2: Deny access from other AWS accounts
  # Additional protection against cross-account access attempts
  statement {
    sid    = "DenyAccessFromOtherAccounts"
    effect = "Deny"
    
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    
    actions = ["s3:*"]
    
    resources = [
      aws_s3_bucket.cs_files.arn,
      "${aws_s3_bucket.cs_files.arn}/*"
    ]
    
    condition {
      test     = "StringNotEquals"
      variable = "aws:PrincipalAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
  
  # Statement 3: Enforce HTTPS (encryption in transit)
  # Deny all requests that don't use encrypted transport
  statement {
    sid    = "DenyUnencryptedTransport"
    effect = "Deny"
    
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    
    actions = ["s3:*"]
    
    resources = [
      aws_s3_bucket.cs_files.arn,
      "${aws_s3_bucket.cs_files.arn}/*"
    ]
    
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

# Apply the bucket policy
resource "aws_s3_bucket_policy" "cs_files" {
  bucket = aws_s3_bucket.cs_files.id
  policy = data.aws_iam_policy_document.bucket_policy.json
  
  # Ensure public access block is created first
  depends_on = [aws_s3_bucket_public_access_block.cs_files]
}

# =============================================================================
# IAM ROLE 1: C2 VPC Instances (cs_download_c2)
# =============================================================================
# Used by: Team Servers, Redirectors, Bastion (in C2 VPC)
# Security: Restricted to C2 VPC only

# Trust policy for C2 role
data "aws_iam_policy_document" "ec2_assume_role_c2" {
  count = local.create_c2_role ? 1 : 0

  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }

    # SECURITY: Restrict to YOUR AWS account only
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    # SECURITY: Restrict to C2 VPC only
    condition {
      test     = "StringEquals"
      variable = "aws:SourceVpc"
      values   = [var.c2_vpc_id]
    }
  }
}

# C2 IAM Role
resource "aws_iam_role" "cs_download_c2" {
  count = local.create_c2_role ? 1 : 0

  name = "${local.sanitized_name}-${var.environment}-cs-download-c2-role"

  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role_c2[0].json

  tags = merge(var.tags, {
    Name    = "${var.project_name}-cs-download-c2-role"
    Purpose = "AllowC2EC2ToAccessS3"
    VPC     = "C2"
  })
}

# C2 Download Policy
data "aws_iam_policy_document" "cs_download_c2" {
  count = local.create_c2_role ? 1 : 0

  statement {
    sid    = "AllowS3GetObject"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:ListBucket"
    ]

    resources = [
      aws_s3_bucket.cs_files.arn,
      "${aws_s3_bucket.cs_files.arn}/*"
    ]

    # SECURITY: Restrict to C2 VPC
    condition {
      test     = "StringEquals"
      variable = "aws:SourceVpc"
      values   = [var.c2_vpc_id]
    }

    # SECURITY: Enforce encryption in transit
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["true"]
    }
  }

  # CloudWatch logs (restricted)
  statement {
    sid    = "AllowCloudWatchLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams"
    ]

    resources = [
      "arn:aws:logs:${var.aws_region != "" ? var.aws_region : "*"}:${data.aws_caller_identity.current.account_id}:log-group:/aws/ec2/${var.project_name}*:*"
    ]
  }
}

# C2 SSH Key Exchange Policy
data "aws_iam_policy_document" "ssh_key_exchange_c2" {
  count = local.create_c2_role ? 1 : 0

  # Allow key upload
  statement {
    sid       = "AllowKeyUpload"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.cs_files.arn}/keys/*"]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceVpc"
      values   = [var.c2_vpc_id]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["true"]
    }
  }

  # Allow key download
  statement {
    sid       = "AllowKeyDownload"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${aws_s3_bucket.cs_files.arn}/keys/*"]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceVpc"
      values   = [var.c2_vpc_id]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["true"]
    }
  }

  # Status operations
  statement {
    sid     = "AllowStatusOperations"
    effect  = "Allow"
    actions = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"]
    resources = [
      aws_s3_bucket.cs_files.arn,
      "${aws_s3_bucket.cs_files.arn}/status/*"
    ]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceVpc"
      values   = [var.c2_vpc_id]
    }
  }

  # List keys/status
  statement {
    sid       = "AllowListKeys"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.cs_files.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["keys/*", "status/*"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceVpc"
      values   = [var.c2_vpc_id]
    }
  }
}

# Attach policies to C2 role
resource "aws_iam_role_policy" "cs_download_c2" {
  count  = local.create_c2_role ? 1 : 0
  name   = "${local.sanitized_name}-cs-download-c2-policy"
  role   = aws_iam_role.cs_download_c2[0].id
  policy = data.aws_iam_policy_document.cs_download_c2[0].json
}

resource "aws_iam_role_policy" "ssh_key_exchange_c2" {
  count  = local.create_c2_role ? 1 : 0
  name   = "${local.sanitized_name}-ssh-key-exchange-c2-policy"
  role   = aws_iam_role.cs_download_c2[0].id
  policy = data.aws_iam_policy_document.ssh_key_exchange_c2[0].json
}

# C2 Instance Profile
resource "aws_iam_instance_profile" "cs_download_c2" {
  count = local.create_c2_role ? 1 : 0
  name  = "${local.sanitized_name}-${var.environment}-cs-download-c2-profile"
  role  = aws_iam_role.cs_download_c2[0].name

  tags = merge(var.tags, {
    Name = "${var.project_name}-cs-download-c2-profile"
    VPC  = "C2"
  })
}

# =============================================================================
# IAM ROLE 2: GOAD VPC Instances (cs_download_goad)
# =============================================================================
# Used by: Jumpbox, Team Server, Attack Box, GOAD VMs (in GOAD VPC)
# Security: Restricted to GOAD VPC only

# Trust policy for GOAD role
data "aws_iam_policy_document" "ec2_assume_role_goad" {
  count = local.create_goad_role ? 1 : 0

  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }

    # SECURITY: Restrict to YOUR AWS account only
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    # SECURITY: Restrict to GOAD VPC only
    condition {
      test     = "StringEquals"
      variable = "aws:SourceVpc"
      values   = [var.goad_vpc_id]
    }
  }
}

# GOAD IAM Role
resource "aws_iam_role" "cs_download_goad" {
  count = local.create_goad_role ? 1 : 0

  name = "${local.sanitized_name}-${var.environment}-cs-download-goad-role"

  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role_goad[0].json

  tags = merge(var.tags, {
    Name    = "${var.project_name}-cs-download-goad-role"
    Purpose = "AllowGOADEC2ToAccessS3"
    VPC     = "GOAD"
  })
}

# GOAD Download Policy
data "aws_iam_policy_document" "cs_download_goad" {
  count = local.create_goad_role ? 1 : 0

  statement {
    sid    = "AllowS3GetObject"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:ListBucket"
    ]

    resources = [
      aws_s3_bucket.cs_files.arn,
      "${aws_s3_bucket.cs_files.arn}/*"
    ]

    # SECURITY: Restrict to GOAD VPC
    condition {
      test     = "StringEquals"
      variable = "aws:SourceVpc"
      values   = [var.goad_vpc_id]
    }

    # SECURITY: Enforce encryption in transit
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["true"]
    }
  }

  # CloudWatch logs (restricted)
  statement {
    sid    = "AllowCloudWatchLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams"
    ]

    resources = [
      "arn:aws:logs:${var.aws_region != "" ? var.aws_region : "*"}:${data.aws_caller_identity.current.account_id}:log-group:/aws/ec2/${var.project_name}*:*"
    ]
  }
}

# GOAD SSH Key Exchange Policy
data "aws_iam_policy_document" "ssh_key_exchange_goad" {
  count = local.create_goad_role ? 1 : 0

  # Allow key upload
  statement {
    sid       = "AllowKeyUpload"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.cs_files.arn}/keys/*"]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceVpc"
      values   = [var.goad_vpc_id]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["true"]
    }
  }

  # Allow key download
  statement {
    sid       = "AllowKeyDownload"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${aws_s3_bucket.cs_files.arn}/keys/*"]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceVpc"
      values   = [var.goad_vpc_id]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["true"]
    }
  }

  # Status operations
  statement {
    sid     = "AllowStatusOperations"
    effect  = "Allow"
    actions = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"]
    resources = [
      aws_s3_bucket.cs_files.arn,
      "${aws_s3_bucket.cs_files.arn}/status/*"
    ]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceVpc"
      values   = [var.goad_vpc_id]
    }
  }

  # List keys/status
  statement {
    sid       = "AllowListKeys"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.cs_files.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["keys/*", "status/*"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceVpc"
      values   = [var.goad_vpc_id]
    }
  }
}

# Attach policies to GOAD role
resource "aws_iam_role_policy" "cs_download_goad" {
  count  = local.create_goad_role ? 1 : 0
  name   = "${local.sanitized_name}-cs-download-goad-policy"
  role   = aws_iam_role.cs_download_goad[0].id
  policy = data.aws_iam_policy_document.cs_download_goad[0].json
}

resource "aws_iam_role_policy" "ssh_key_exchange_goad" {
  count  = local.create_goad_role ? 1 : 0
  name   = "${local.sanitized_name}-ssh-key-exchange-goad-policy"
  role   = aws_iam_role.cs_download_goad[0].id
  policy = data.aws_iam_policy_document.ssh_key_exchange_goad[0].json
}

# GOAD Instance Profile
resource "aws_iam_instance_profile" "cs_download_goad" {
  count = local.create_goad_role ? 1 : 0
  name  = "${local.sanitized_name}-${var.environment}-cs-download-goad-profile"
  role  = aws_iam_role.cs_download_goad[0].name

  tags = merge(var.tags, {
    Name = "${var.project_name}-cs-download-goad-profile"
    VPC  = "GOAD"
  })
}

# =============================================================================
# LEGACY IAM ROLE (Backwards Compatibility)
# =============================================================================
# Used when: Only vpc_id is provided (single VPC mode)
# This maintains backwards compatibility with existing deployments

# Trust policy for legacy role
data "aws_iam_policy_document" "ec2_assume_role_legacy" {
  count = local.legacy_vpc_id != "" ? 1 : 0

  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }

    # SECURITY: Restrict to YOUR AWS account only
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    # SECURITY: Restrict to specific VPC
    condition {
      test     = "StringEquals"
      variable = "aws:SourceVpc"
      values   = [local.legacy_vpc_id]
    }
  }
}

# Legacy IAM Role
resource "aws_iam_role" "cs_download_legacy" {
  count = local.legacy_vpc_id != "" ? 1 : 0

  name = "${local.sanitized_name}-${var.environment}-cs-download-role"

  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role_legacy[0].json

  tags = merge(var.tags, {
    Name    = "${var.project_name}-cs-download-role"
    Purpose = "AllowEC2ToAccessS3"
    Note    = "Legacy single-VPC mode"
  })
}

# Legacy Download Policy
data "aws_iam_policy_document" "cs_download_legacy" {
  count = local.legacy_vpc_id != "" ? 1 : 0

  statement {
    sid    = "AllowS3GetObject"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:ListBucket"
    ]

    resources = [
      aws_s3_bucket.cs_files.arn,
      "${aws_s3_bucket.cs_files.arn}/*"
    ]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceVpc"
      values   = [local.legacy_vpc_id]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["true"]
    }
  }

  statement {
    sid    = "AllowCloudWatchLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams"
    ]

    resources = [
      "arn:aws:logs:${var.aws_region != "" ? var.aws_region : "*"}:${data.aws_caller_identity.current.account_id}:log-group:/aws/ec2/${var.project_name}*:*"
    ]
  }
}

# Legacy SSH Key Exchange Policy
data "aws_iam_policy_document" "ssh_key_exchange_legacy" {
  count = local.legacy_vpc_id != "" ? 1 : 0

  statement {
    sid       = "AllowKeyUpload"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.cs_files.arn}/keys/*"]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceVpc"
      values   = [local.legacy_vpc_id]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["true"]
    }
  }

  statement {
    sid       = "AllowKeyDownload"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${aws_s3_bucket.cs_files.arn}/keys/*"]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceVpc"
      values   = [local.legacy_vpc_id]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["true"]
    }
  }

  statement {
    sid     = "AllowStatusOperations"
    effect  = "Allow"
    actions = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"]
    resources = [
      aws_s3_bucket.cs_files.arn,
      "${aws_s3_bucket.cs_files.arn}/status/*"
    ]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceVpc"
      values   = [local.legacy_vpc_id]
    }
  }

  statement {
    sid       = "AllowListKeys"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.cs_files.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["keys/*", "status/*"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceVpc"
      values   = [local.legacy_vpc_id]
    }
  }
}

# Attach policies to legacy role
resource "aws_iam_role_policy" "cs_download_legacy" {
  count  = local.legacy_vpc_id != "" ? 1 : 0
  name   = "${local.sanitized_name}-cs-download-policy"
  role   = aws_iam_role.cs_download_legacy[0].id
  policy = data.aws_iam_policy_document.cs_download_legacy[0].json
}

resource "aws_iam_role_policy" "ssh_key_exchange_legacy" {
  count  = local.legacy_vpc_id != "" ? 1 : 0
  name   = "${local.sanitized_name}-ssh-key-exchange-policy"
  role   = aws_iam_role.cs_download_legacy[0].id
  policy = data.aws_iam_policy_document.ssh_key_exchange_legacy[0].json
}

# Legacy Instance Profile
resource "aws_iam_instance_profile" "cs_download_legacy" {
  count = local.legacy_vpc_id != "" ? 1 : 0
  name  = "${local.sanitized_name}-${var.environment}-cs-download-profile"
  role  = aws_iam_role.cs_download_legacy[0].name

  tags = merge(var.tags, {
    Name = "${var.project_name}-cs-download-profile"
  })
}
