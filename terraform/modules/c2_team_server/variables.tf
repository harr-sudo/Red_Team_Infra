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

variable "tools_repo_url" {
  description = "Git repository URL for red team tools"
  type        = string
  default     = ""
}

variable "tools_repo_branch" {
  description = "Git branch to clone for tools repository"
  type        = string
  default     = "main"
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
# Tags
# =============================================================================

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
