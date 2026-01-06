# Proxy/Redirector Module Variables

variable "proxy_redirector_count" {
  description = "Number of proxy/redirector instances to create"
  type        = number
  default     = 2
}

variable "instance_type" {
  description = "EC2 instance type for proxy/redirector servers"
  type        = string
  default     = "t3.small"
}

variable "ami_id" {
  description = "AMI ID for proxy/redirector servers"
  type        = string
}

variable "key_pair_name" {
  description = "Name of the AWS key pair for SSH access"
  type        = string
}

variable "public_subnet_ids" {
  description = "List of public subnet IDs for proxy/redirector placement"
  type        = list(string)
}

variable "security_group_id" {
  description = "Security group ID for proxy/redirector servers"
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

variable "root_volume_size" {
  description = "Size of root volume in GB (minimal for pass-through only)"
  type        = number
  default     = 8
}

variable "enable_detailed_monitoring" {
  description = "Enable detailed CloudWatch monitoring"
  type        = bool
  default     = false
}

variable "iam_instance_profile_name" {
  description = "IAM instance profile name for proxy/redirector servers"
  type        = string
  default     = ""
}

variable "user_data" {
  description = "User data script for proxy configuration (pass-through setup)"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

