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

# =============================================================================
# DOMAIN CONFIGURATION (for nginx setup)
# =============================================================================

variable "primary_domain" {
  description = "Primary domain name for the redirector"
  type        = string
  default     = ""
}

variable "c2_subdomain" {
  description = "C2 subdomain prefix"
  type        = string
  default     = "api"
}

variable "c2_server_ip" {
  description = "Internal IP address of the C2 team server"
  type        = string
  default     = ""
}

variable "c2_server_port" {
  description = "Port of the C2 team server"
  type        = number
  default     = 443
}

variable "enable_ssl" {
  description = "Enable SSL/TLS on the redirector"
  type        = bool
  default     = true
}

variable "ssl_provider" {
  description = "SSL certificate provider: 'letsencrypt' or 'self-signed'"
  type        = string
  default     = "letsencrypt"
}

variable "ssl_auto_retry" {
  description = "Auto-retry Let's Encrypt when DNS propagates"
  type        = bool
  default     = true
}

variable "use_letsencrypt" {
  description = "DEPRECATED: Use ssl_provider instead"
  type        = bool
  default     = false
}

variable "admin_email" {
  description = "Admin email for Let's Encrypt notifications"
  type        = string
  default     = ""
}

variable "malleable_profile" {
  description = "Name of Malleable C2 profile for URI matching"
  type        = string
  default     = "default"
}
