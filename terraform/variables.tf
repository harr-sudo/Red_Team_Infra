# Terraform Variables for Red Team Infrastructure

# AWS Configuration
variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

# Project Configuration
variable "project_name" {
  description = "Name of the project (used for resource naming)"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

# Engagement Type Configuration
variable "engagement_type" {
  description = "Type of engagement: 'adhoc', 'purple-team', or 'full-red-team'. This can auto-configure deployment mode."
  type        = string
  default     = ""
  
  validation {
    condition     = var.engagement_type == "" || contains(["adhoc", "purple-team", "full-red-team"], var.engagement_type)
    error_message = "engagement_type must be 'adhoc', 'purple-team', 'full-red-team', or empty string"
  }
}

# VPC Configuration
variable "vpc_cidr" {
  description = "CIDR block for VPC"
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

variable "enable_nat_gateway" {
  description = "Enable NAT Gateway for private subnets"
  type        = bool
  default     = false
}

# Security Configuration
variable "management_cidr_blocks" {
  description = "CIDR blocks allowed for SSH/management access"
  type        = list(string)
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

# Key Pair Configuration
variable "key_pair_name" {
  description = "Name of AWS key pair for SSH access"
  type        = string
}

# C2 Deployment Mode Configuration
# If engagement_type is set, it will auto-configure deployment_mode unless explicitly overridden
variable "c2_deployment_mode" {
  description = "C2 server deployment mode: 'single', 'redundancy', or 'phases'. Leave empty to auto-configure based on engagement_type."
  type        = string
  default     = ""
  
  validation {
    condition     = var.c2_deployment_mode == "" || contains(["single", "redundancy", "phases"], var.c2_deployment_mode)
    error_message = "c2_deployment_mode must be 'single', 'redundancy', 'phases', or empty string (for auto-configuration)"
  }
}

# C2 Team Server Configuration (for single/redundancy modes)
variable "c2_server_count" {
  description = "Number of C2 team server instances (used for single/redundancy modes)"
  type        = number
  default     = 2
}

variable "c2_server_instance_type" {
  description = "EC2 instance type for C2 team servers"
  type        = string
  default     = "t3.medium"
}

variable "c2_server_ami_id" {
  description = "AMI ID for C2 team servers (leave empty to use latest Amazon Linux 2)"
  type        = string
  default     = ""
}

variable "c2_server_root_volume_size" {
  description = "Root volume size in GB for C2 team servers"
  type        = number
  default     = 20
}

variable "c2_server_enable_elastic_ips" {
  description = "Enable Elastic IPs for C2 servers (typically not needed in private subnets)"
  type        = bool
  default     = false
}

variable "c2_server_iam_instance_profile_name" {
  description = "IAM instance profile name for C2 team servers"
  type        = string
  default     = ""
}

variable "c2_server_user_data" {
  description = "User data script for C2 team server initialization (used for single/redundancy modes)"
  type        = string
  default     = ""
}

# Phase-Based C2 Configuration (for phases mode)
variable "c2_phases" {
  description = "Phase-based C2 server configuration. Each phase can have its own settings."
  type = map(object({
    enabled          = bool
    instance_type    = string
    root_volume_size = number
    user_data        = string
    iam_instance_profile_name = string
  }))
  default = {
    staging = {
      enabled          = true
      instance_type    = "t3.medium"
      root_volume_size = 20
      user_data        = ""
      iam_instance_profile_name = ""
    }
    post-ex = {
      enabled          = true
      instance_type    = "t3.medium"
      root_volume_size = 20
      user_data        = ""
      iam_instance_profile_name = ""
    }
    long-haul = {
      enabled          = true
      instance_type    = "t3.medium"
      root_volume_size = 20
      user_data        = ""
      iam_instance_profile_name = ""
    }
  }
}

# Proxy/Redirector Configuration
variable "proxy_redirector_count" {
  description = "Number of proxy/redirector instances"
  type        = number
  default     = 2
}

variable "proxy_redirector_instance_type" {
  description = "EC2 instance type for proxy/redirector servers"
  type        = string
  default     = "t3.small"
}

variable "proxy_redirector_ami_id" {
  description = "AMI ID for proxy/redirector servers (leave empty to use latest Amazon Linux 2)"
  type        = string
  default     = ""
}

variable "proxy_redirector_root_volume_size" {
  description = "Root volume size in GB for proxy/redirector servers (minimal for pass-through)"
  type        = number
  default     = 8
}

variable "proxy_redirector_iam_instance_profile_name" {
  description = "IAM instance profile name for proxy/redirector servers"
  type        = string
  default     = ""
}

variable "proxy_redirector_user_data" {
  description = "User data script for proxy/redirector configuration (pass-through setup)"
  type        = string
  default     = ""
}

# Bastion/Jump Box Configuration
variable "enable_bastion" {
  description = "Enable bastion/jump box for management access"
  type        = bool
  default     = true
}

variable "bastion_instance_type" {
  description = "EC2 instance type for bastion host (Windows Server)"
  type        = string
  default     = "t3.medium"
}

variable "bastion_ami_id" {
  description = "AMI ID for bastion host (leave empty to use latest Windows Server 2022)"
  type        = string
  default     = ""
}

variable "bastion_root_volume_size" {
  description = "Root volume size in GB for bastion host"
  type        = number
  default     = 30
}

variable "bastion_iam_instance_profile_name" {
  description = "IAM instance profile name for bastion host"
  type        = string
  default     = ""
}

variable "windows_admin_password" {
  description = "Windows administrator password (leave empty to retrieve from AWS Systems Manager using key pair)"
  type        = string
  default     = ""
  sensitive   = true
}

# Tools Repository Configuration
variable "tools_repo_url" {
  description = "Git repository URL for tools (e.g., git@github.com:org/red-team-tools.git or https://github.com/org/red-team-tools.git)"
  type        = string
  default     = ""
}

variable "tools_repo_branch" {
  description = "Git branch to clone for tools repository"
  type        = string
  default     = "main"
}

variable "tools_repo_ssh_key" {
  description = "SSH private key for Git access (stored in AWS SSM Parameter Store). Leave empty if using HTTPS with token."
  type        = string
  default     = ""
  sensitive   = true
}

variable "tools_repo_https_token" {
  description = "Personal access token for HTTPS Git access (stored in AWS SSM Parameter Store). Leave empty if using SSH."
  type        = string
  default     = ""
  sensitive   = true
}

# Monitoring Configuration
variable "enable_detailed_monitoring" {
  description = "Enable detailed CloudWatch monitoring for all instances"
  type        = bool
  default     = false
}

# Terraform Backend Configuration
variable "terraform_backend_bucket" {
  description = "S3 bucket name for Terraform state"
  type        = string
  default     = ""
}

variable "terraform_backend_region" {
  description = "AWS region for Terraform backend"
  type        = string
  default     = "us-east-1"
}

variable "terraform_backend_key" {
  description = "S3 key for Terraform state file"
  type        = string
  default     = "terraform.tfstate"
}

variable "terraform_backend_dynamodb_table" {
  description = "DynamoDB table name for Terraform state locking"
  type        = string
  default     = "terraform-state-lock"
}

# Tags
variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

