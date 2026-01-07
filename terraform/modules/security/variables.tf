# Security Groups Module Variables

variable "vpc_id" {
  description = "ID of the VPC"
  type        = string
}

variable "project_name" {
  description = "Name of the project (used for resource naming)"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "management_cidr_blocks" {
  description = "CIDR blocks allowed for SSH/management access"
  type        = list(string)
  default     = []
}

variable "ssh_port" {
  description = "SSH port number"
  type        = number
  default     = 22
}

variable "c2_server_port" {
  description = "Port used by C2 team servers"
  type        = number
  default     = 50050
}

# =============================================================================
# VPC Peering Configuration (for Combined Mode)
# =============================================================================

variable "enable_vpc_peering" {
  description = "Enable VPC peering rules (for combined C2 + GOAD mode)"
  type        = bool
  default     = false
}

variable "goad_vpc_cidr" {
  description = "CIDR block of the GOAD VPC (for peering rules)"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

