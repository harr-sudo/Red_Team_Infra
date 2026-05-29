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
  description = "CS client management port (50050). Used for operator connections via the dashboard server / attack box."
  type        = number
  default     = 50050
}

variable "c2_listener_port" {
  description = "Port the CS HTTPS beacon listener binds on the team server. Redirectors forward beacon traffic here."
  type        = number
  default     = 443
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

# =============================================================================
# Domain Fronting Configuration
# =============================================================================

variable "enable_domain_fronting" {
  description = "When true, restrict redirector HTTP/HTTPS to CloudFront IPs only (via managed prefix list)"
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "enable_cs_rest_api" {
  description = "Enable REST API port (50443) access from the dashboard server to C2 servers"
  type        = bool
  default     = false
}

# Dashboard server peering (optional — empty = no peering)
variable "dashboard_vpc_id" {
  description = "Dashboard server VPC ID for peering (empty = disabled)"
  type        = string
  default     = ""
}

variable "dashboard_vpc_cidr" {
  description = "Dashboard server VPC CIDR for security group rules"
  type        = string
  default     = ""
}

variable "dashboard_sg_id" {
  description = "Dashboard server security group ID for ingress rules"
  type        = string
  default     = ""
}

