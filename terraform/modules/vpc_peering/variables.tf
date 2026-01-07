# VPC Peering Module - Variables
# =============================================================================

variable "c2_vpc_id" {
  description = "ID of the C2 infrastructure VPC"
  type        = string
}

variable "goad_vpc_id" {
  description = "ID of the GOAD lab VPC"
  type        = string
}

variable "c2_route_table_ids" {
  description = "List of route table IDs in the C2 VPC"
  type        = list(string)
}

variable "goad_route_table_ids" {
  description = "List of route table IDs in the GOAD VPC"
  type        = list(string)
}

variable "c2_cidr" {
  description = "CIDR block of the C2 VPC"
  type        = string
}

variable "goad_cidr" {
  description = "CIDR block of the GOAD VPC"
  type        = string
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

