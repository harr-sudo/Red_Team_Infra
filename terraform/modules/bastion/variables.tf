# Bastion Module Variables

variable "project_name" {
  description = "Name of the project (used for resource naming)"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "public_subnet_id" {
  description = "ID of the subnet for bastion host (management or public)"
  type        = string
}

variable "security_group_id" {
  description = "Security group ID for bastion host"
  type        = string
}

variable "key_pair_name" {
  description = "Name of the EC2 key pair for SSH access"
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type for bastion host"
  type        = string
  default     = "t3.micro" # Sufficient for SSH relay
}

variable "ami_id" {
  description = "AMI ID for bastion host (leave empty to use latest Ubuntu 22.04 LTS)"
  type        = string
  default     = ""
}

variable "root_volume_size" {
  description = "Root volume size in GB"
  type        = number
  default     = 20 # Linux needs less space than Windows
}

variable "enable_detailed_monitoring" {
  description = "Enable detailed CloudWatch monitoring"
  type        = bool
  default     = false
}

variable "iam_instance_profile_name" {
  description = "IAM instance profile name for bastion (optional)"
  type        = string
  default     = ""
}

variable "private_ip" {
  description = "Static private IP address (leave empty for DHCP)"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
