# GOAD Module Variables
# =============================================================================
# Variables for deploying GOAD (Game Of Active Directory) lab
# =============================================================================

# =============================================================================
# Lab Configuration
# =============================================================================

variable "lab_type" {
  description = "GOAD lab type: GOAD-Mini, MINILAB, GOAD-Light, SCCM, GOAD, NHA"
  type        = string

  validation {
    condition     = contains(["GOAD-Mini", "MINILAB", "GOAD-Light", "SCCM", "GOAD", "NHA"], var.lab_type)
    error_message = "lab_type must be one of: GOAD-Mini, MINILAB, GOAD-Light, SCCM, GOAD, NHA"
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

# =============================================================================
# Cobalt Strike / Attack Box Configuration
# =============================================================================

variable "install_cobalt_strike" {
  description = "Deploy Attack Box with Cobalt Strike (separate from jumpbox)"
  type        = bool
  default     = false
}

variable "cobalt_strike_s3_path" {
  description = "S3 path to Cobalt Strike archive"
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
  description = "Instance type for jumpbox (minimal SSH gateway)"
  type        = string
  default     = "t2.micro"  # Minimal - just SSH gateway
}

variable "jumpbox_disk_size" {
  description = "Root disk size for jumpbox in GB"
  type        = number
  default     = 20  # Minimal disk
}

variable "jumpbox_username" {
  description = "Username for jumpbox SSH access"
  type        = string
  default     = "goad"
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

# =============================================================================
# Attack Box Configuration (Windows - CS Client + Tools)
# =============================================================================

variable "attackbox_instance_type" {
  description = "Instance type for Windows attack box (CS Client + Tools)"
  type        = string
  default     = "t2.large"  # 8GB RAM for Windows + tools
}

variable "attackbox_disk_size" {
  description = "Root disk size for Windows attack box in GB"
  type        = number
  default     = 100  # Windows needs more space
}

variable "attackbox_admin_password" {
  description = "Administrator password for Windows attack box"
  type        = string
  default     = "AttackB0x!2024"
  sensitive   = true
}

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
# Tags
# =============================================================================

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

