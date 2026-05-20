# Terraform Variables for Red Team Infrastructure

# =============================================================================
# AWS Configuration
# =============================================================================

variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "eu-central-1"
}

# =============================================================================
# Project Configuration
# =============================================================================

variable "project_name" {
  description = "Name of the project (used for resource naming)"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

# =============================================================================
# DEPLOYMENT TYPE - PRIMARY CONTROL
# =============================================================================
# This is the main variable that controls what gets deployed.
# Options:
#   C2-Only:   c2-adhoc, c2-purple, c2-full
#   GOAD-Only: goad-mini, goad-light, goad-sccm, goad-full, goad-nha
#   Combined:  combined-adhoc-mini, combined-adhoc-light, combined-full-full

variable "deployment_type" {
  description = "Primary deployment type controlling what infrastructure to deploy"
  type        = string
  default     = "c2-adhoc"

  validation {
    condition = contains([
      # C2-Only modes
      "c2-adhoc", "c2-purple", "c2-full",
      # GOAD-Only modes (with CS on jumpbox)
      "goad-mini", "goad-light", "goad-sccm", "goad-full", "goad-nha",
      # Combined modes (C2 + GOAD with VPC peering)
      "combined-adhoc-mini", "combined-adhoc-light", "combined-full-full"
    ], var.deployment_type)
    error_message = "Invalid deployment_type. Must be one of: c2-adhoc, c2-purple, c2-full, goad-mini, goad-light, goad-sccm, goad-full, goad-nha, combined-adhoc-mini, combined-adhoc-light, combined-full-full"
  }
}

# =============================================================================
# GOAD Configuration
# =============================================================================

variable "goad_lab_type" {
  description = "GOAD lab type to deploy. Auto-configured from deployment_type if not set."
  type        = string
  default     = ""

  validation {
    condition     = var.goad_lab_type == "" || contains(["GOAD-Mini", "GOAD-Light", "SCCM", "GOAD", "NHA"], var.goad_lab_type)
    error_message = "goad_lab_type must be one of: GOAD-Mini, GOAD-Light, SCCM, GOAD, NHA, or empty (auto-configure)"
  }
}

variable "goad_vpc_cidr" {
  description = "CIDR block for GOAD VPC (used in GOAD-only and combined modes)"
  type        = string
  default     = "192.168.56.0/24"
}

variable "goad_public_subnet_cidr" {
  description = "CIDR block for GOAD public subnet"
  type        = string
  default     = "192.168.56.64/26"
}

variable "goad_private_subnet_cidr" {
  description = "CIDR block for GOAD private subnet"
  type        = string
  default     = "192.168.56.0/26"
}

# =============================================================================
# Cobalt Strike Configuration
# =============================================================================

variable "cobalt_strike_archive_s3_path" {
  description = "S3 path to Cobalt Strike archive (e.g., s3://bucket/cobaltstrike.tar.gz)"
  type        = string
  default     = ""
}

variable "cs_teamserver_password" {
  description = "Password for Cobalt Strike team server"
  type        = string
  default     = ""
  sensitive   = true
}

# =============================================================================
# Domain Configuration
# =============================================================================

variable "primary_domain_name" {
  description = "Primary domain name for C2 infrastructure (e.g., example.com). User must own this domain."
  type        = string
  default     = ""
}

variable "backup_domains" {
  description = "List of backup domain names for redundancy"
  type        = list(string)
  default     = []
}

variable "c2_subdomain" {
  description = "Subdomain prefix for C2 servers (e.g., 'api' creates api.example.com)"
  type        = string
  default     = "api"
}

variable "www_subdomain" {
  description = "Subdomain prefix for web redirectors"
  type        = string
  default     = "www"
}

variable "cdn_subdomain" {
  description = "Subdomain prefix for CDN/content delivery redirectors"
  type        = string
  default     = "cdn"
}

# =============================================================================
# DNS Configuration
# =============================================================================

variable "create_dns_hosted_zone" {
  description = "Create a new Route 53 hosted zone. Set to false if domain is already in Route 53 (default: false, since the webapp selects from existing Route 53 zones)."
  type        = bool
  default     = false
}

variable "dns_ttl" {
  description = "TTL for DNS records in seconds"
  type        = number
  default     = 300
}

variable "enable_www_subdomain" {
  description = "Create www subdomain DNS record"
  type        = bool
  default     = true
}

variable "enable_cdn_subdomain" {
  description = "Create cdn subdomain DNS record"
  type        = bool
  default     = true
}

variable "enable_apex_record" {
  description = "Create apex/root domain DNS record"
  type        = bool
  default     = true
}

variable "create_backup_domain_records" {
  description = "Create CNAME records for backup domains"
  type        = bool
  default     = true
}

variable "enable_spf_record" {
  description = "Create SPF record (helps domain look legitimate)"
  type        = bool
  default     = true
}

variable "enable_dmarc_record" {
  description = "Create DMARC record (helps domain look legitimate)"
  type        = bool
  default     = true
}

# =============================================================================
# SSL/TLS Configuration
# =============================================================================

variable "ssl_provider" {
  description = "SSL certificate provider for redirectors: 'letsencrypt' (recommended) or 'self-signed'"
  type        = string
  default     = "letsencrypt"

  validation {
    condition     = contains(["letsencrypt", "self-signed"], var.ssl_provider)
    error_message = "ssl_provider must be 'letsencrypt' or 'self-signed'"
  }
}

variable "admin_email" {
  description = "Admin email for Let's Encrypt notifications and certificate expiry alerts (required for Let's Encrypt)"
  type        = string
  default     = ""
}

variable "ssl_auto_retry" {
  description = "Automatically retry Let's Encrypt certificate request when DNS propagates"
  type        = bool
  default     = true
}

variable "enable_ssl_certificate" {
  description = "Enable SSL/TLS on redirectors"
  type        = bool
  default     = true
}

variable "malleable_profile" {
  description = "Name of Malleable C2 profile for nginx URI matching (default/amazon/google/microsoft/wikipedia/custom)"
  type        = string
  default     = "default"
}

variable "custom_profile_content" {
  description = "Base64-encoded custom Malleable C2 profile content (only used when malleable_profile = 'custom')"
  type        = string
  default     = ""
  sensitive   = true
}

variable "custom_c2_uris" {
  description = "JSON-encoded custom C2 URIs parsed from the custom profile (e.g. {\"get\":[\"/uri\"],\"post\":[\"/uri\"],\"stager_x86\":[\"/uri\"],\"stager_x64\":[\"/uri\"]})"
  type        = string
  default     = ""
}

variable "decoy_theme" {
  description = "Decoy website theme for redirectors: 'plexura' (Plexura Managed Solutions) or 'meridian-financial' (Meridian Financial Group)"
  type        = string
  default     = "plexura"
}

# =============================================================================
# Domain Fronting Configuration (CloudFront CDN Proxy)
# =============================================================================

variable "enable_domain_fronting" {
  description = "Enable CloudFront domain fronting for C2 traffic. Hides redirector IPs behind CloudFront CDN and makes traffic appear as CDN traffic. Only applicable to C2 deployments."
  type        = bool
  default     = false
}

# =============================================================================
# VPC Configuration (C2 Infrastructure)
# =============================================================================

variable "vpc_cidr" {
  description = "CIDR block for C2 VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of availability zones. If empty, will use first AZ in the selected region."
  type        = list(string)
  default     = []  # Empty = auto-detect from region
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

variable "management_subnet_cidrs" {
  description = "CIDR blocks for management subnets (bastion isolation). Separates bastion from redirectors in DMZ. Empty list disables management subnet and falls back to public subnet."
  type        = list(string)
  default     = ["10.0.0.0/24"]
}

variable "enable_nacls" {
  description = "Enable Network ACLs for defense-in-depth across all subnet tiers (management, DMZ, private). NACLs add subnet-level firewall rules on top of security groups."
  type        = bool
  default     = false
}

variable "enable_nat_gateway" {
  description = "Enable NAT Gateway for private subnets (required for C2 servers to download packages and reach AWS services)"
  type        = bool
  default     = true
}

# =============================================================================
# Security Configuration
# =============================================================================

variable "management_cidr_blocks" {
  description = "CIDR blocks allowed for SSH/management access (your IP)"
  type        = list(string)
  default     = []
}

variable "ssh_port" {
  description = "SSH port number"
  type        = number
  default     = 22
}

variable "c2_server_port" {
  description = "CS client management port (Cobalt Strike default: 50050). Used for operator connections via SSH tunnel."
  type        = number
  default     = 50050
}

variable "c2_listener_port" {
  description = "Port the CS HTTPS beacon listener binds on the team server. Redirectors forward beacon traffic here."
  type        = number
  default     = 443
}

# =============================================================================
# Key Pair Configuration
# =============================================================================

variable "key_pair_name" {
  description = "Name of AWS key pair for SSH access"
  type        = string
  default     = ""
}

# =============================================================================
# SSH Public Key (Phase 5 - Secure Key Management)
# =============================================================================
# User's SSH public key for jumpbox access. The user generates this locally
# and provides it before deployment. Private key stays on user's machine.

variable "user_public_key" {
  description = "User's SSH public key for jumpbox access (Ed25519 or RSA format). User generates key locally with: ssh-keygen -t ed25519 -f ~/.ssh/goad_key"
  type        = string
  default     = ""
  
  validation {
    condition     = var.user_public_key == "" || can(regex("^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp256|ecdsa-sha2-nistp384|ecdsa-sha2-nistp521)\\s+[A-Za-z0-9+/=]+", var.user_public_key))
    error_message = "user_public_key must be a valid SSH public key (ssh-ed25519, ssh-rsa, or ecdsa format) or empty"
  }
}

# =============================================================================
# C2 Deployment Mode Configuration
# =============================================================================
# Auto-configured from deployment_type, but can be overridden
variable "c2_deployment_mode" {
  description = "C2 server deployment mode: 'single', 'redundancy', or 'phases'. Auto-configured from deployment_type if empty."
  type        = string
  default     = ""

  validation {
    condition     = var.c2_deployment_mode == "" || contains(["single", "redundancy", "phases"], var.c2_deployment_mode)
    error_message = "c2_deployment_mode must be 'single', 'redundancy', 'phases', or empty string (for auto-configuration)"
  }
}

# =============================================================================
# C2 Team Server Configuration
# =============================================================================
variable "c2_server_count" {
  description = "Number of C2 team server instances (for single/redundancy modes)"
  type        = number
  default     = 2
}

variable "c2_server_instance_type" {
  description = "EC2 instance type for C2 team servers"
  type        = string
  default     = "t3.medium"
}

variable "c2_server_ami_id" {
  description = "AMI ID for C2 team servers (leave empty to use latest Ubuntu 22.04)"
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
  description = "Custom user data script for C2 servers (overrides centralized CS script if set)"
  type        = string
  default     = ""
}

# =============================================================================
# Phase-Based C2 Configuration (for c2-full / phases mode)
# =============================================================================
variable "c2_phases" {
  description = "Phase-based C2 server configuration. Each phase can have its own settings."
  type = map(object({
    enabled                   = bool
    instance_type             = string
    root_volume_size          = number
    user_data                 = string
    iam_instance_profile_name = string
  }))
  default = {
    staging = {
      enabled                   = true
      instance_type             = "t3.medium"
      root_volume_size          = 20
      user_data                 = ""
      iam_instance_profile_name = ""
    }
    post-ex = {
      enabled                   = true
      instance_type             = "t3.medium"
      root_volume_size          = 20
      user_data                 = ""
      iam_instance_profile_name = ""
    }
    long-haul = {
      enabled                   = true
      instance_type             = "t3.medium"
      root_volume_size          = 20
      user_data                 = ""
      iam_instance_profile_name = ""
    }
  }
}

# =============================================================================
# Proxy/Redirector Configuration
# =============================================================================
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
  description = "AMI ID for proxy/redirector servers (leave empty to use latest Ubuntu 22.04)"
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
  description = "User data script for proxy/redirector configuration"
  type        = string
  default     = ""
}

# =============================================================================
# Bastion Host Configuration (Linux SSH Relay)
# =============================================================================
variable "enable_bastion" {
  description = "Enable bastion host for SSH relay access to private subnets"
  type        = bool
  default     = true
}

variable "bastion_instance_type" {
  description = "EC2 instance type for bastion host (SSH relay only)"
  type        = string
  default     = "t3.micro"
}

variable "bastion_ami_id" {
  description = "AMI ID for bastion host (leave empty to use latest Ubuntu 22.04 LTS)"
  type        = string
  default     = ""
}

variable "bastion_root_volume_size" {
  description = "Root volume size in GB for bastion host"
  type        = number
  default     = 20
}

variable "bastion_iam_instance_profile_name" {
  description = "IAM instance profile name for bastion host"
  type        = string
  default     = ""
}

# =============================================================================
# Attack Box Configuration (Windows Workstation)
# =============================================================================

variable "enable_attack_box" {
  description = "Enable Windows attack box for red team operations (deployed for all deployment types)"
  type        = bool
  default     = true
}

variable "attack_box_instance_type" {
  description = "EC2 instance type for Windows attack box (needs 8GB+ RAM)"
  type        = string
  default     = "t2.large"
}

variable "attack_box_root_volume_size" {
  description = "Root volume size in GB for Windows attack box"
  type        = number
  default     = 40
}

variable "attack_box_admin_password" {
  description = "Windows Administrator password for attack box (empty = auto-generate 30-char)"
  type        = string
  default     = ""
  sensitive   = true
}

# =============================================================================
# Tools Repository Configuration
# =============================================================================
variable "tools_repo_url" {
  description = "Git repository URL for red team tools"
  type        = string
  default     = "https://github.com/harr-sudo/red-team-tools.git"
}

variable "tools_repo_branch" {
  description = "Git branch to clone for tools repository"
  type        = string
  default     = "main"
}

variable "tools_repo_https_token" {
  description = "Personal access token for HTTPS Git access. Leave empty if using SSH."
  type        = string
  default     = ""
  sensitive   = true
}

variable "cobalt_strike_license_secret_name" {
  description = "Name of the AWS Secrets Manager secret containing your CS license key. Store once with: aws secretsmanager create-secret --name cs-license-key --secret-string YOUR_KEY --region YOUR_REGION. Set to empty string for manual activation."
  type        = string
  default     = "cs-license-key"
}

variable "enable_cs_rest_api" {
  description = "Enable Cobalt Strike REST API server (requires CS 4.12+). Starts team server with --experimental-db and runs csrestapi service on port 50443."
  type        = bool
  default     = false
}

# =============================================================================
# File Portal Configuration
# =============================================================================

variable "enable_file_portal" {
  description = "Enable the /login file portal on redirectors for secure file sharing"
  type        = bool
  default     = false
}

variable "portal_username" {
  description = "Portal login username (only used if enable_file_portal = true)"
  type        = string
  default     = "operator"
  sensitive   = true
}

variable "portal_password" {
  description = "Portal login password (only used if enable_file_portal = true)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "portal_session_timeout" {
  description = "Portal session timeout in minutes"
  type        = number
  default     = 60
}

# =============================================================================
# Monitoring Configuration
# =============================================================================
variable "enable_detailed_monitoring" {
  description = "Enable detailed CloudWatch monitoring for all instances"
  type        = bool
  default     = false
}

# =============================================================================
# Terraform Backend Configuration
# =============================================================================
variable "terraform_backend_bucket" {
  description = "S3 bucket name for Terraform state"
  type        = string
  default     = ""
}

variable "terraform_backend_region" {
  description = "AWS region for Terraform backend"
  type        = string
  default     = "eu-central-1"
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

# =============================================================================
# DASHBOARD SERVER
# =============================================================================

variable "enable_dashboard_server" {
  description = "Deploy centralized dashboard server"
  type        = bool
  default     = false
}

variable "dashboard_allowed_ips" {
  description = "Operator IP CIDRs for dashboard SSH access"
  type        = list(string)
  default     = []
}

variable "operator_ssh_public_keys" {
  description = "Map of operator name to SSH public key"
  type        = map(string)
  default     = {}
}

variable "dashboard_instance_type" {
  description = "Dashboard server instance type"
  type        = string
  default     = "t3.medium"
}

# Dashboard peering overrides — use these when the dashboard was created in a
# different workspace (pass the VPC ID, CIDR, and SG ID from the dashboard output)
variable "dashboard_vpc_id" {
  description = "Dashboard VPC ID for peering (override when dashboard is in different workspace)"
  type        = string
  default     = ""
}

variable "dashboard_vpc_cidr" {
  description = "Dashboard VPC CIDR for route tables"
  type        = string
  default     = ""
}

variable "dashboard_sg_id" {
  description = "Dashboard security group ID for ingress rules"
  type        = string
  default     = ""
}

# =============================================================================
# Test Lab (extension on c2-* deployments)
# =============================================================================
# When `enable_test_lab = true` and the deployment is c2-*, the test_lab
# module provisions 4 vulnerable hosts (tldc01, tlms01, tlws01, tllinux01) on
# a new private subnet INSIDE the existing C2 VPC. No new VPC, no peering,
# no new NAT. See docs/internal/TESTLAB_DESIGN.md.

variable "enable_test_lab" {
  description = "When true on a c2-* deployment, provisions the in-VPC test lab subnet + 4 vulnerable hosts."
  type        = bool
  default     = false
}

variable "test_lab_subnet_cidr" {
  description = "CIDR for the test lab private subnet (must be a /24 inside the C2 VPC, must not overlap standard C2 subnets)."
  type        = string
  default     = "10.0.20.0/24"

  validation {
    condition     = can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}/24$", var.test_lab_subnet_cidr))
    error_message = "test_lab_subnet_cidr must be a valid IPv4 /24 CIDR (e.g. 10.0.20.0/24)."
  }
}

variable "test_lab_size" {
  description = "Test lab variant. Only 'mini' (4 hosts) is supported in Phase 1."
  type        = string
  default     = "mini"

  validation {
    condition     = contains(["mini"], var.test_lab_size)
    error_message = "test_lab_size must be 'mini' (the only Phase 1 variant)."
  }
}

# =============================================================================
# Tags
# =============================================================================

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
