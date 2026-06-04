# C2 Team Server Module Variables
# =============================================================================

# =============================================================================
# Instance Configuration
# =============================================================================

variable "c2_server_count" {
  description = "Number of C2 team server instances to create"
  type        = number
  default     = 2
}

variable "instance_type" {
  description = "EC2 instance type for C2 team servers"
  type        = string
  default     = "t3.medium"
}

variable "ami_id" {
  description = "AMI ID for C2 team servers"
  type        = string
}

variable "key_pair_name" {
  description = "Name of the AWS key pair for SSH access"
  type        = string
}

variable "root_volume_size" {
  description = "Size of root volume in GB"
  type        = number
  default     = 20
}

# =============================================================================
# Network Configuration
# =============================================================================

variable "private_subnet_ids" {
  description = "List of private subnet IDs for C2 server placement"
  type        = list(string)
}

variable "security_group_id" {
  description = "Security group ID for C2 team servers"
  type        = string
}

variable "private_ips" {
  description = "List of static private IPs for C2 servers (empty list = DHCP)"
  type        = list(string)
  default     = []
}

# =============================================================================
# Project Configuration
# =============================================================================

variable "project_name" {
  description = "Name of the project (used for resource naming)"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "phase" {
  description = "Engagement phase name (staging, post-ex, long-haul). Leave empty for generic/redundancy mode"
  type        = string
  default     = ""
}

# =============================================================================
# Monitoring and IAM
# =============================================================================

variable "enable_detailed_monitoring" {
  description = "Enable detailed CloudWatch monitoring"
  type        = bool
  default     = false
}

variable "enable_elastic_ips" {
  description = "Enable Elastic IPs for C2 servers (typically not needed in private subnets)"
  type        = bool
  default     = false
}

variable "iam_instance_profile_name" {
  description = "IAM instance profile name for C2 servers (for S3 access)"
  type        = string
  default     = ""
}

# =============================================================================
# Cobalt Strike Configuration
# =============================================================================

variable "cobalt_strike_s3_path" {
  description = "S3 path to Cobalt Strike archive (e.g., s3://bucket/cobaltstrike.tar.gz)"
  type        = string
  default     = ""
}

variable "cs_teamserver_password" {
  description = "Password for Cobalt Strike team server"
  type        = string
  default     = ""
  sensitive   = true
}

# =============================================================================
# Custom User Data (overrides centralized CS script)
# =============================================================================

variable "user_data" {
  description = "Custom user data script. If provided, overrides the centralized CS installation script."
  type        = string
  default     = ""
}

# =============================================================================
# Domain / Listener Configuration (for CS Listener Guide generation)
# =============================================================================

variable "primary_domain" {
  description = "Primary domain name for C2 operations (e.g., example.com)"
  type        = string
  default     = ""
}

variable "c2_subdomain" {
  description = "C2 subdomain prefix (e.g., api → api.example.com)"
  type        = string
  default     = "api"
}

variable "malleable_profile" {
  description = "Malleable C2 profile name configured on redirectors"
  type        = string
  default     = "default"
}

variable "custom_profile_content" {
  description = "Base64-encoded custom Malleable C2 profile content (only used when malleable_profile = 'custom')"
  type        = string
  default     = ""
  sensitive   = true
}

variable "cs_license_secret_name" {
  description = "Secrets Manager secret name containing CS license key (empty = manual activation)"
  type        = string
  default     = ""
}

# =============================================================================
# S3 Bootstrap Configuration (bypasses 16KB EC2 user_data limit)
# =============================================================================

variable "enable_s3_bootstrap" {
  description = "Upload user_data script to S3 and bootstrap from there (bypasses 16KB limit)"
  type        = bool
  default     = false
}

variable "deployment_bucket" {
  description = "S3 bucket name for uploading bootstrap scripts"
  type        = string
  default     = ""
}

variable "deployment_id" {
  description = "Unique deployment identifier (used as S3 key prefix)"
  type        = string
  default     = ""
}

variable "aws_region" {
  description = "AWS region for S3 operations"
  type        = string
  default     = "eu-central-1"
}

# =============================================================================
# Tags
# =============================================================================

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "enable_rest_api" {
  description = "Enable Cobalt Strike REST API (--experimental-db + csrestapi service)"
  type        = bool
  default     = false
}
