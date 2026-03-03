# Attack Box Module - Variables
# =============================================================================
# Standalone Windows attack workstation for all deployment types
# =============================================================================

# -----------------------------------------------------------------------------
# Required
# -----------------------------------------------------------------------------

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment (e.g., production, staging)"
  type        = string
  default     = "production"
}

variable "subnet_id" {
  description = "Subnet ID for attack box placement (private subnet recommended)"
  type        = string
}

variable "security_group_id" {
  description = "Security group ID for attack box"
  type        = string
}

# -----------------------------------------------------------------------------
# Instance Configuration
# -----------------------------------------------------------------------------

variable "instance_type" {
  description = "EC2 instance type (Windows needs 8GB+ RAM)"
  type        = string
  default     = "t2.large"
}

variable "ami_id" {
  description = "Custom AMI ID (leave empty for latest Windows Server 2022)"
  type        = string
  default     = ""
}

variable "root_volume_size" {
  description = "Root volume size in GB"
  type        = number
  default     = 100
}

variable "key_pair_name" {
  description = "EC2 key pair name for Windows password retrieval"
  type        = string
  default     = ""
}

variable "enable_detailed_monitoring" {
  description = "Enable detailed CloudWatch monitoring"
  type        = bool
  default     = false
}

variable "private_ip" {
  description = "Static private IP address (leave empty for DHCP)"
  type        = string
  default     = ""
}

# -----------------------------------------------------------------------------
# Authentication
# -----------------------------------------------------------------------------

variable "admin_password" {
  description = "Windows Administrator password (empty = auto-generate 30-char)"
  type        = string
  default     = ""
  sensitive   = true
}

# -----------------------------------------------------------------------------
# C2 Server Connection
# -----------------------------------------------------------------------------

variable "c2_server_ip" {
  description = "Primary C2 team server private IP (for CS client config)"
  type        = string
  default     = ""
}

variable "c2_server_port" {
  description = "C2 team server port"
  type        = number
  default     = 50050
}

# -----------------------------------------------------------------------------
# S3 / Deployment
# -----------------------------------------------------------------------------

variable "deployment_bucket" {
  description = "S3 bucket name for deployment artifacts (scripts, CS files)"
  type        = string
  default     = ""
}

variable "deployment_id" {
  description = "Unique deployment ID for S3 path prefixes"
  type        = string
  default     = ""
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "eu-central-1"
}

variable "iam_instance_profile_name" {
  description = "IAM instance profile for S3 access"
  type        = string
  default     = ""
}

variable "cs_client_s3_path" {
  description = "S3 path to Cobalt Strike Client archive (e.g., s3://bucket/cs-client.tar.gz)"
  type        = string
  default     = ""
}

# -----------------------------------------------------------------------------
# Tools Repository
# -----------------------------------------------------------------------------

variable "tools_repo_url" {
  description = "Git repository URL for red team tools (cloned to C:\\Tools)"
  type        = string
  default     = "https://github.com/harr-sudo/red-team-tools.git"
}

variable "tools_repo_branch" {
  description = "Git branch to clone for tools repository"
  type        = string
  default     = "main"
}

# -----------------------------------------------------------------------------
# GOAD Key Exchange (only for GOAD-only deployments)
# -----------------------------------------------------------------------------

variable "enable_key_exchange" {
  description = "Enable S3-based SSH key exchange with jumpbox (GOAD deployments only)"
  type        = bool
  default     = false
}

variable "s3_key_prefix" {
  description = "S3 prefix for SSH key exchange (e.g., keys/deployment-id)"
  type        = string
  default     = ""
}

# -----------------------------------------------------------------------------
# Tags
# -----------------------------------------------------------------------------

variable "tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}
