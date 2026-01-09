# CS Storage Module - S3 Bucket and IAM for Cobalt Strike Files
# =============================================================================
# This module creates:
#   - S3 bucket for storing Cobalt Strike archives
#   - IAM role and instance profile for EC2 to download from S3
#   - Bucket encryption and lifecycle policies
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
}

# =============================================================================
# S3 Bucket for Cobalt Strike Files
# =============================================================================

resource "aws_s3_bucket" "cs_files" {
  bucket = "${local.sanitized_name}-cs-files-${random_id.bucket_suffix.hex}"

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

# Server-side encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "cs_files" {
  bucket = aws_s3_bucket.cs_files.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
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

  rule {
    id     = "delete-old-files"
    status = "Enabled"

    filter {
      prefix = "" # Apply to all objects
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
# IAM Role for EC2 to Access S3
# =============================================================================

# Trust policy - allow EC2 to assume this role
data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

# IAM Role
resource "aws_iam_role" "cs_download" {
  name = "${local.sanitized_name}-${var.environment}-cs-download-role"

  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json

  tags = merge(var.tags, {
    Name    = "${var.project_name}-cs-download-role"
    Purpose = "AllowEC2ToDownloadCS"
  })
}

# Policy document - allow GetObject from CS bucket
data "aws_iam_policy_document" "cs_download" {
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
  }

  # Allow CloudWatch logs (useful for debugging)
  statement {
    sid    = "AllowCloudWatchLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams"
    ]

    resources = ["arn:aws:logs:*:*:*"]
  }
}

# Attach policy to role
resource "aws_iam_role_policy" "cs_download" {
  name   = "${local.sanitized_name}-cs-download-policy"
  role   = aws_iam_role.cs_download.id
  policy = data.aws_iam_policy_document.cs_download.json
}

# Instance profile (required for EC2)
resource "aws_iam_instance_profile" "cs_download" {
  name = "${local.sanitized_name}-${var.environment}-cs-download-profile"
  role = aws_iam_role.cs_download.name

  tags = merge(var.tags, {
    Name = "${var.project_name}-cs-download-profile"
  })
}

