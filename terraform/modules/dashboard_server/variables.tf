variable "dashboard_allowed_ips" {
  description = "Operator IP CIDRs allowed to SSH into the dashboard"
  type        = list(string)

  validation {
    condition     = length(var.dashboard_allowed_ips) > 0
    error_message = "At least one operator IP CIDR is required for dashboard SSH access."
  }
}

variable "operator_ssh_public_keys" {
  description = "Map of operator name to SSH public key"
  type        = map(string)

  validation {
    condition     = length(var.operator_ssh_public_keys) > 0
    error_message = "At least one operator SSH key is required."
  }

  validation {
    condition     = alltrue([for name, _ in var.operator_ssh_public_keys : can(regex("^[a-z][a-z0-9_-]{0,31}$", name))])
    error_message = "Operator names must be valid Linux usernames: lowercase, start with letter, 1-32 chars, only a-z 0-9 _ -"
  }

  validation {
    condition     = alltrue([for _, key in var.operator_ssh_public_keys : can(regex("^ssh-(ed25519|rsa|ecdsa) ", key))])
    error_message = "SSH keys must start with a valid key type (ssh-ed25519, ssh-rsa, ssh-ecdsa)"
  }
}

variable "instance_type" {
  description = "EC2 instance type for dashboard server"
  type        = string
  default     = "t3.medium"
}

variable "aws_region" {
  description = "AWS region for the dashboard server"
  type        = string
  default     = "eu-central-1"
}

variable "vpc_cidr" {
  description = "VPC CIDR for the dashboard server"
  type        = string
  default     = "10.100.0.0/16"
}

variable "project_name" {
  description = "Project name for resource tagging"
  type        = string
  default     = "redteam-dashboard"
}

variable "ebs_volume_size" {
  description = "Root EBS volume size in GB"
  type        = number
  default     = 50
}

variable "tags" {
  description = "Additional tags for all resources"
  type        = map(string)
  default     = {}
}
