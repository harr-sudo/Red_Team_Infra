# CCRTS Lab Module - Variables
# =============================================================================
# Variables for deploying the CCRTS (CREST Registered Tester for Simulated
# Targeted Attacks) exam-mirror lab in eu-central-1 using CREST Community AMIs
# auto-copied from eu-west-2.
# =============================================================================

# =============================================================================
# Lab Sizing
# =============================================================================

variable "lab_size" {
  description = "CCRTS lab variant. 'ccrts-mini' = 4 hosts (kali + windows-ws + elk + NAT). 'ccrts-full' = 6 hosts (adds AD DC + AD-joined workstation on ccrts.local)."
  type        = string

  validation {
    condition     = contains(["ccrts-mini", "ccrts-full"], var.lab_size)
    error_message = "lab_size must be one of: ccrts-mini, ccrts-full."
  }
}

# =============================================================================
# Network Configuration
# =============================================================================

variable "vpc_cidr" {
  description = "CIDR block for the CCRTS lab VPC"
  type        = string
  default     = "192.168.57.0/24"

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr))
    error_message = "vpc_cidr must be a valid IPv4 CIDR (e.g. 192.168.57.0/24)."
  }
}

variable "public_subnet_cidr" {
  description = "CIDR block for the public subnet (NAT + ELK Kibana ingress through dashboard peer)"
  type        = string
  default     = "192.168.57.64/26"
}

variable "private_subnet_cidr" {
  description = "CIDR block for the private subnet (lab hosts: kali, windows ws, AD VMs, ELK)"
  type        = string
  default     = "192.168.57.0/26"
}

variable "availability_zone" {
  description = "AWS availability zone for the lab subnets"
  type        = string
}

variable "peer_vpc_cidr" {
  description = "CIDR block of a peered C2 VPC. Empty string disables peering ingress."
  type        = string
  default     = ""
}

variable "dashboard_vpc_cidr" {
  description = "CIDR block of the dashboard VPC. Used to allow operator-side SSH/RDP/WinRM/Kibana ingress (operator never connects directly from the internet — the dashboard is the jump)."
  type        = string
  default     = ""
}

# =============================================================================
# Project / Naming
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
  description = "Deployment region (where the lab actually runs)"
  type        = string
  default     = "eu-central-1"
}

# =============================================================================
# Access / Keys
# =============================================================================

variable "key_pair_name" {
  description = "Name of an existing AWS key pair. Used as a fallback when user_public_key is empty."
  type        = string
  default     = ""
}

variable "user_public_key" {
  description = "Operator's SSH public key. Used to construct a lab-scoped key pair so operators can SSH to kali via the dashboard."
  type        = string
  default     = ""

  validation {
    condition     = var.user_public_key == "" || can(regex("^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp256|ecdsa-sha2-nistp384|ecdsa-sha2-nistp521)\\s+[A-Za-z0-9+/=]+", var.user_public_key))
    error_message = "user_public_key must be a valid SSH public key (ssh-ed25519, ssh-rsa, or ecdsa format) or empty."
  }
}

# =============================================================================
# IAM / S3
# =============================================================================

variable "iam_instance_profile_name" {
  description = "IAM instance profile name attached to each lab host (used for SSM Session Manager + optional S3 access)"
  type        = string
  default     = ""
}

variable "deployment_bucket" {
  description = "S3 bucket for any deployment artefacts shared with the lab hosts (optional)"
  type        = string
  default     = ""
}

# =============================================================================
# CREST AMI Cross-Region Copy
# =============================================================================
# CREST Community AMIs are published in eu-west-2 (London) only. We use a
# second AWS provider alias pointed at eu-west-2 just to READ the latest
# AMI IDs, then aws_ami_copy duplicates the underlying snapshots into the
# deploy region. NO infrastructure is provisioned in eu-west-2.

variable "crest_ami_source_region" {
  description = "Region the CREST Community AMIs are published in. Read-only — only the AMI snapshot is copied to the deploy region."
  type        = string
  default     = "eu-west-2"
}

variable "crest_kali_ami_override" {
  description = "Pre-staged Kali AMI ID in the deploy region. When set, skips the cross-region copy and uses this AMI directly."
  type        = string
  default     = ""
}

variable "crest_windows_ami_override" {
  description = "Pre-staged Windows workstation AMI ID in the deploy region. When set, skips the cross-region copy and uses this AMI directly."
  type        = string
  default     = ""
}

# =============================================================================
# Lab Credentials
# =============================================================================
# Lab posture — passwords are intentionally NOT vault-grade. The lab is
# self-contained, internet-isolated (via SG ingress restrictions), and
# everything is wiped on terraform destroy.

variable "windows_admin_password" {
  description = "Local Administrator password baked into the Windows workstation. Default is a CCRTS-style weak password."
  type        = string
  default     = "P@ssw0rd1!"
  sensitive   = true
}

variable "dc_admin_password" {
  description = "Domain Administrator password for ccrts.local (only used when lab_size = ccrts-full)."
  type        = string
  default     = "P@ssw0rd1!"
  sensitive   = true
}

variable "low_priv_password" {
  description = "Password for the low-privilege domain user CCRTS\\jdoe (only used when lab_size = ccrts-full)."
  type        = string
  default     = "Welcome1!"
  sensitive   = true
}

# =============================================================================
# Tags
# =============================================================================

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
