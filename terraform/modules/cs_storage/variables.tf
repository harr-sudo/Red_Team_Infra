# CS Storage Module - Variables
# =============================================================================

variable "project_name" {
  description = "Name of the project (used for resource naming)"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# =============================================================================
# Security Enhancement Variables - Multi-VPC Support (Option C)
# =============================================================================

variable "aws_region" {
  description = "AWS region for CloudWatch logs restriction"
  type        = string
  default     = ""
}

# C2 VPC Configuration (for C2-only and Combined modes)
variable "c2_vpc_id" {
  description = "VPC ID for C2 infrastructure (for IAM policy conditions)"
  type        = string
  default     = ""
}

variable "enable_c2_role" {
  description = "Whether to create IAM role for C2 VPC instances"
  type        = bool
  default     = false
}

# GOAD VPC Configuration (for GOAD-only and Combined modes)
variable "goad_vpc_id" {
  description = "VPC ID for GOAD infrastructure (for IAM policy conditions)"
  type        = string
  default     = ""
}

variable "enable_goad_role" {
  description = "Whether to create IAM role for GOAD VPC instances"
  type        = bool
  default     = false
}

# =============================================================================
# Deprecated - For backwards compatibility
# =============================================================================

variable "vpc_id" {
  description = "DEPRECATED: Use c2_vpc_id or goad_vpc_id instead. Single VPC ID for restricting S3 access"
  type        = string
  default     = ""
}

variable "allowed_instance_arns" {
  description = "List of EC2 instance ARNs allowed to access S3 (security enhancement)"
  type        = list(string)
  default     = []
}
