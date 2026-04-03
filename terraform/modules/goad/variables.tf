# GOAD Module Variables
# =============================================================================
# Variables for deploying GOAD (Game Of Active Directory) lab
# =============================================================================

# =============================================================================
# Lab Configuration
# =============================================================================

variable "lab_type" {
  description = "GOAD lab type: GOAD-Mini, GOAD-Light, SCCM, GOAD, NHA"
  type        = string

  validation {
    condition     = contains(["GOAD-Mini", "GOAD-Light", "SCCM", "GOAD", "NHA"], var.lab_type)
    error_message = "lab_type must be one of: GOAD-Mini, GOAD-Light, SCCM, GOAD, NHA"
  }
}

variable "lab_identifier" {
  description = "Lab identifier (lowercase, used for resource naming)"
  type        = string
  default     = ""
}

# =============================================================================
# Network Configuration
# =============================================================================

variable "vpc_cidr" {
  description = "CIDR block for GOAD VPC"
  type        = string
  default     = "192.168.56.0/24"
}

variable "public_subnet_cidr" {
  description = "CIDR block for public subnet (jumpbox)"
  type        = string
  default     = "192.168.56.64/26"
}

variable "private_subnet_cidr" {
  description = "CIDR block for private subnet (AD VMs)"
  type        = string
  default     = "192.168.56.0/26"
}

variable "ip_range" {
  description = "IP range prefix for VMs (e.g., 192.168.56)"
  type        = string
  default     = "192.168.56"
}

variable "availability_zone" {
  description = "AWS availability zone for resources"
  type        = string
}

variable "peer_vpc_cidr" {
  description = "CIDR block of the peered C2 VPC (empty string = no peering, no ingress rule)"
  type        = string
  default     = ""
}

# =============================================================================
# Cobalt Strike / Attack Box Configuration
# =============================================================================

variable "install_cobalt_strike" {
  description = "Deploy Attack Box with Cobalt Strike (separate from jumpbox)"
  type        = bool
  default     = false
}

variable "cobalt_strike_s3_path" {
  description = "S3 path to Cobalt Strike archive (for Team Server)"
  type        = string
  default     = ""
}


variable "cs_teamserver_password" {
  description = "Password for Cobalt Strike team server"
  type        = string
  default     = ""
  sensitive   = true
}

variable "cs_license_secret_name" {
  description = "Secrets Manager secret name for CS license key (empty = manual activation)"
  type        = string
  default     = ""
}

# =============================================================================
# Access Configuration
# =============================================================================

variable "management_cidr_blocks" {
  description = "CIDR blocks allowed for SSH/RDP access"
  type        = list(string)
  default     = []
}

variable "key_pair_name" {
  description = "AWS key pair name for SSH access (optional - will generate if not provided)"
  type        = string
  default     = ""
}

# =============================================================================
# User SSH Public Key (Secure Key Management)
# =============================================================================
# Users must provide their own public key for jumpbox access.
# This follows SSH security best practices:
#   - Private keys are generated locally by the user
#   - Only public keys are shared with the infrastructure
#   - Private keys never leave the user's machine

variable "user_public_key" {
  description = "User's SSH public key for jumpbox access (Ed25519 or RSA format). User generates key locally with: ssh-keygen -t ed25519 -f ~/.ssh/goad_key"
  type        = string
  default     = ""
  
  validation {
    condition     = var.user_public_key == "" || can(regex("^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp256|ecdsa-sha2-nistp384|ecdsa-sha2-nistp521)\\s+[A-Za-z0-9+/=]+", var.user_public_key))
    error_message = "user_public_key must be a valid SSH public key (ssh-ed25519, ssh-rsa, or ecdsa format) or empty"
  }
}

# =============================================================================
# Tools Configuration
# =============================================================================

variable "tools_repo_url" {
  description = "Git repository URL for red team tools"
  type        = string
  default     = ""
}

variable "tools_repo_branch" {
  description = "Git branch to clone"
  type        = string
  default     = "main"
}

# =============================================================================
# Project Configuration
# =============================================================================

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

# =============================================================================
# Instance Configuration
# =============================================================================

variable "jumpbox_instance_type" {
  description = "Instance type for jumpbox (SSH gateway + Ansible controller for GOAD provisioning)"
  type        = string
  default     = "t2.small"  # 2GB RAM needed for Ansible GOAD provisioning
}

variable "jumpbox_disk_size" {
  description = "Root disk size for jumpbox in GB"
  type        = number
  default     = 20  # Minimal disk
}

variable "jumpbox_username" {
  description = "Username for jumpbox SSH access (Ubuntu AMI default user)"
  type        = string
  default     = "ubuntu"
}

# =============================================================================
# Team Server Configuration (Ubuntu - CS Only)
# =============================================================================

variable "teamserver_instance_type" {
  description = "Instance type for team server (CS Team Server only)"
  type        = string
  default     = "t2.medium"  # 4GB RAM for CS
}

variable "teamserver_disk_size" {
  description = "Root disk size for team server in GB"
  type        = number
  default     = 30
}

# NOTE: Attack box variables migrated to standalone module (terraform/modules/attack_box/)
# Attack box instance_type, disk_size, and admin_password are now root-level variables.

variable "windows_admin_username" {
  description = "Windows administrator username for AD VMs"
  type        = string
  default     = "goadmin"
}

# =============================================================================
# IAM Configuration
# =============================================================================

variable "iam_instance_profile_name" {
  description = "IAM instance profile for jumpbox (for S3 access)"
  type        = string
  default     = ""
}

# =============================================================================
# Secure Key Exchange Configuration (S3-based)
# =============================================================================

variable "deployment_bucket" {
  description = "S3 bucket name for deployment artifacts and key exchange"
  type        = string
  default     = ""
}

variable "deployment_id" {
  description = "Unique deployment identifier for S3 key paths"
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

