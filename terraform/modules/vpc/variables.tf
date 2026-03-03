# VPC Module Variables

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
}

variable "availability_zones" {
  description = "List of availability zones"
  type        = list(string)
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets"
  type        = list(string)
}

variable "management_subnet_cidrs" {
  description = "CIDR blocks for management subnets (bastion isolation). Empty list disables management subnet."
  type        = list(string)
  default     = []
}

variable "enable_nacls" {
  description = "Enable Network ACLs for defense-in-depth across all subnet tiers"
  type        = bool
  default     = false
}

variable "management_cidr_blocks" {
  description = "Operator IP CIDR blocks for NACL rules (SSH/RDP ingress to management subnet)"
  type        = list(string)
  default     = []
}

variable "c2_server_port" {
  description = "C2 server port for NACL rules"
  type        = number
  default     = 50050
}

variable "ssh_port" {
  description = "SSH port for NACL rules"
  type        = number
  default     = 22
}

variable "project_name" {
  description = "Name of the project (used for resource naming)"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "enable_nat_gateway" {
  description = "Enable NAT Gateway for private subnets"
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

