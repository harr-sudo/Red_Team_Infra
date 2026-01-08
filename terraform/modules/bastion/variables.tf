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
  description = "ID of the public subnet for bastion host"
  type        = string
}

variable "security_group_id" {
  description = "Security group ID for bastion host"
  type        = string
}

variable "key_pair_name" {
  description = "Name of the EC2 key pair for SSH access (for retrieving Windows password)"
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type for bastion host"
  type        = string
  default     = "t3.medium" # Windows needs more resources than Linux
}

variable "ami_id" {
  description = "AMI ID for Windows Server (leave empty to use latest Windows Server 2022)"
  type        = string
  default     = ""
}

variable "root_volume_size" {
  description = "Root volume size in GB"
  type        = number
  default     = 30 # Windows needs more space
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

variable "windows_admin_password" {
  description = "Windows administrator password (leave empty to retrieve from AWS Systems Manager)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

