# Main Terraform Configuration for Red Team Infrastructure
# Supports three deployment modes:
#   1. C2-Only: Full C2 infrastructure (c2-adhoc, c2-purple, c2-full)
#   2. GOAD-Only: Training lab with CS on jumpbox (goad-*)
#   3. Combined: C2 + GOAD with VPC peering (combined-*)

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }

  # Backend configuration - uncomment and configure for remote state
  # backend "s3" {
  #   bucket         = var.terraform_backend_bucket
  #   key            = var.terraform_backend_key
  #   region         = var.terraform_backend_region
  #   encrypt        = true
  #   dynamodb_table = var.terraform_backend_dynamodb_table
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.enhanced_tags
  }
}

# AWS provider in us-east-1 (required for CloudFront ACM certificates)
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = local.enhanced_tags
  }
}

# =============================================================================
# DATA SOURCES - Get Available Availability Zones
# =============================================================================

data "aws_availability_zones" "available" {
  state = "available"
}

# =============================================================================
# LOCAL VALUES - Deployment Mode Detection
# =============================================================================

locals {
  # -------------------------------------------------------------------------
  # Availability Zones - Auto-detect if not specified
  # -------------------------------------------------------------------------
  availability_zones = length(var.availability_zones) > 0 ? var.availability_zones : data.aws_availability_zones.available.names

  # -------------------------------------------------------------------------
  # Deployment Type Detection
  # -------------------------------------------------------------------------
  is_c2_only   = startswith(var.deployment_type, "c2-")
  is_goad_only = startswith(var.deployment_type, "goad-")
  is_combined  = startswith(var.deployment_type, "combined-")

  # -------------------------------------------------------------------------
  # What to Deploy
  # -------------------------------------------------------------------------
  deploy_c2_infra       = local.is_c2_only || local.is_combined
  deploy_goad           = local.is_goad_only || local.is_combined
  deploy_redirectors    = local.is_c2_only || local.is_combined
  deploy_bastion        = local.is_c2_only || local.is_combined
  deploy_vpc_peering    = local.is_combined
  deploy_domain_fronting = (local.is_c2_only || local.is_combined) && var.enable_domain_fronting
  install_cs_on_jumpbox = local.is_goad_only # Only for GOAD-only mode
  deploy_attack_box     = var.enable_attack_box

  # -------------------------------------------------------------------------
  # Static IP Allocation (C2 VPC)
  # -------------------------------------------------------------------------
  # Management Subnet (10.0.0.0/24): .10 = Bastion
  # DMZ Subnet 1 (10.0.1.0/24): .10 = Redirector 1
  # DMZ Subnet 2 (10.0.2.0/24): .10 = Redirector 2
  # Private Subnet 1 (10.0.10.0/24): .10 = C2 Server 1, .11 = C2 Server 3, .50 = Attack Box
  # Private Subnet 2 (10.0.11.0/24): .10 = C2 Server 2
  bastion_private_ip     = "10.0.0.10"
  attack_box_private_ip  = "10.0.10.50"
  c2_server_private_ips  = ["10.0.10.10", "10.0.11.10"]
  redirector_private_ips = ["10.0.1.10", "10.0.2.10"]

  # Phase-based C2 server subnet and IP mapping (c2-full)
  c2_phase_subnet_indices = {
    staging   = 0
    post-ex   = 1
    long-haul = 0
  }
  c2_phase_private_ips = {
    staging   = ["10.0.10.10"]
    post-ex   = ["10.0.11.10"]
    long-haul = ["10.0.10.11"]
  }

  # GOAD IP range prefix (e.g., "192.168.56")
  goad_ip_range = join(".", slice(split(".", split("/", var.goad_vpc_cidr)[0]), 0, 3))

  # -------------------------------------------------------------------------
  # GOAD Lab Type Mapping
  # -------------------------------------------------------------------------
  goad_lab_map = {
    "goad-mini"            = "GOAD-Mini"
    "goad-light"           = "GOAD-Light"
    "goad-sccm"            = "SCCM"
    "goad-full"            = "GOAD"
    "goad-nha"             = "NHA"
    "combined-adhoc-mini"  = "GOAD-Mini"
    "combined-adhoc-light" = "GOAD-Light"
    "combined-full-full"   = "GOAD"
  }

  goad_lab_type = var.goad_lab_type != "" ? var.goad_lab_type : lookup(local.goad_lab_map, var.deployment_type, "")

  # -------------------------------------------------------------------------
  # C2 Deployment Mode Mapping
  # -------------------------------------------------------------------------
  c2_mode_map = {
    "c2-adhoc"             = "single"
    "c2-purple"            = "redundancy"
    "c2-full"              = "phases"
    "combined-adhoc-mini"  = "single"
    "combined-adhoc-light" = "single"
    "combined-full-full"   = "phases"
  }

  # Use explicit c2_deployment_mode if set, otherwise derive from deployment_type
  c2_deployment_mode = var.c2_deployment_mode != "" ? var.c2_deployment_mode : (
    local.deploy_c2_infra ? lookup(local.c2_mode_map, var.deployment_type, "single") : "none"
  )

  # -------------------------------------------------------------------------
  # C2 Server Count based on mode
  # -------------------------------------------------------------------------
  c2_server_count = local.c2_deployment_mode == "single" ? 1 : (
    local.c2_deployment_mode == "redundancy" ? var.c2_server_count : 0
  )

  # -------------------------------------------------------------------------
  # Dashboard server peering (empty when disabled — no-op for deployment modules)
  # Uses module outputs when dashboard is in this workspace, or direct variable overrides
  # when the dashboard was created in a different workspace (e.g., default)
  # -------------------------------------------------------------------------
  dashboard_vpc_id   = var.dashboard_vpc_id != "" ? var.dashboard_vpc_id : (var.enable_dashboard_server ? module.dashboard_server[0].dashboard_vpc_id : "")
  dashboard_vpc_cidr = var.dashboard_vpc_cidr != "" ? var.dashboard_vpc_cidr : (var.enable_dashboard_server ? module.dashboard_server[0].dashboard_vpc_cidr : "")
  dashboard_sg_id    = var.dashboard_sg_id != "" ? var.dashboard_sg_id : (var.enable_dashboard_server ? module.dashboard_server[0].dashboard_sg_id : "")

  # -------------------------------------------------------------------------
  # Enhanced Tags
  # -------------------------------------------------------------------------
  enhanced_tags = merge(
    var.tags,
    {
      DeploymentType = var.deployment_type
      ManagedBy      = "Terraform"
      Project        = var.project_name
      Environment    = var.environment
    },
    local.is_goad_only || local.is_combined ? {
      GOADLab = local.goad_lab_type
    } : {}
  )
}

# =============================================================================
# DATA SOURCES
# =============================================================================

# Note: aws_availability_zones.available is defined earlier in the file (line ~43)

# Ubuntu 22.04 LTS AMI (for C2 servers and redirectors)
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Amazon Linux 2 AMI (fallback)
data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-*-x86_64-gp2"]
  }
}

# =============================================================================
# SSH KEY PAIRS - Auto-created from user's public key
# =============================================================================
# Linux instances: user's uploaded SSH public key (ed25519 or RSA)
# Windows instances: auto-generated RSA key (ed25519 not supported on Windows)

resource "aws_key_pair" "deployer" {
  count = var.user_public_key != "" ? 1 : 0

  key_name   = "${var.project_name}-${var.environment}-key"
  public_key = var.user_public_key

  tags = merge(local.enhanced_tags, {
    Name      = "${var.project_name}-${var.environment}-key"
    Component = "SSH"
  })
}

# Auto-generated RSA key for Windows instances (AWS requires RSA for Windows AMIs)
resource "tls_private_key" "windows" {
  count     = local.deploy_attack_box || local.deploy_bastion ? 1 : 0
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "aws_key_pair" "windows" {
  count = local.deploy_attack_box || local.deploy_bastion ? 1 : 0

  key_name   = "${var.project_name}-${var.environment}-windows-key"
  public_key = tls_private_key.windows[0].public_key_openssh

  tags = merge(local.enhanced_tags, {
    Name      = "${var.project_name}-${var.environment}-windows-key"
    Component = "SSH"
  })
}

locals {
  # Linux: user's key (ed25519/RSA) or manual key_pair_name
  effective_key_pair_name = var.user_public_key != "" ? aws_key_pair.deployer[0].key_name : var.key_pair_name
  # Windows: auto-generated RSA key, or fall back to manual key_pair_name
  windows_key_pair_name = length(aws_key_pair.windows) > 0 ? aws_key_pair.windows[0].key_name : var.key_pair_name
}

# =============================================================================
# DEPLOYMENT STORAGE MODULE - S3 bucket, IAM, and Secrets
# =============================================================================
# Stores: CS archives, init scripts, SSH keys, bootstrap status, secrets
# Option C: Separate IAM Roles Per VPC (Maximum Security)
# - C2 VPC instances use cs_download_c2 role
# - GOAD VPC instances use cs_download_goad role
# - Each role is restricted to its specific VPC
# - Confused deputy attack: BLOCKED

module "cs_storage" {
  count  = var.cobalt_strike_archive_s3_path != "" || local.deploy_c2_infra || local.is_goad_only ? 1 : 0
  source = "./modules/deployment_storage"

  project_name = var.project_name
  environment  = var.environment
  tags         = local.enhanced_tags
  aws_region   = var.aws_region

  # ==========================================================================
  # SECURITY: Option C - Separate IAM Roles Per VPC
  # ==========================================================================
  # C2 VPC Role (for C2-only and Combined modes)
  enable_c2_role = local.deploy_c2_infra
  c2_vpc_id      = local.deploy_c2_infra ? module.vpc[0].vpc_id : ""

  # GOAD VPC Role (for GOAD-only and Combined modes)
  enable_goad_role = local.deploy_goad
  goad_vpc_id      = local.deploy_goad ? module.goad[0].vpc_id : ""

  # Note: In Combined mode, BOTH roles are created, each restricted to its VPC
  # This provides maximum security - no cross-VPC access possible

  # GitHub token for Secrets Manager (attack box retrieves at runtime)
  github_token = var.tools_repo_https_token

  # CS license secret name (pre-existing Secrets Manager secret, team servers retrieve at runtime)
  cs_license_secret_name = var.cobalt_strike_license_secret_name

  # Route53 DNS-01 validation (for Let's Encrypt on redirectors with round-robin DNS)
  # Enabled when we're deploying redirectors with a domain and Let's Encrypt SSL
  enable_route53_dns_validation = local.deploy_redirectors && var.primary_domain_name != "" && var.ssl_provider == "letsencrypt"
}

# =============================================================================
# VPC MODULE - C2 Infrastructure VPC
# =============================================================================

module "vpc" {
  count  = local.deploy_c2_infra ? 1 : 0
  source = "./modules/vpc"

  vpc_cidr                = var.vpc_cidr
  availability_zones      = local.availability_zones
  public_subnet_cidrs     = var.public_subnet_cidrs
  private_subnet_cidrs    = var.private_subnet_cidrs
  management_subnet_cidrs = var.management_subnet_cidrs
  project_name            = var.project_name
  environment             = var.environment
  aws_region              = var.aws_region
  enable_nat_gateway      = var.enable_nat_gateway
  enable_nacls            = var.enable_nacls
  management_cidr_blocks  = var.management_cidr_blocks
  c2_server_port          = var.c2_server_port
  c2_listener_port        = var.c2_listener_port
  ssh_port                = var.ssh_port
  tags                    = local.enhanced_tags
}

# =============================================================================
# SECURITY GROUPS MODULE
# =============================================================================

module "security" {
  count  = local.deploy_c2_infra ? 1 : 0
  source = "./modules/security"

  vpc_id                 = module.vpc[0].vpc_id
  project_name           = var.project_name
  environment            = var.environment
  management_cidr_blocks = var.management_cidr_blocks
  ssh_port               = var.ssh_port
  c2_server_port         = var.c2_server_port
  c2_listener_port       = var.c2_listener_port

  # VPC Peering configuration (for combined mode)
  enable_vpc_peering = local.deploy_vpc_peering
  goad_vpc_cidr      = local.deploy_vpc_peering ? var.goad_vpc_cidr : ""

  # Domain fronting (restrict redirector to CloudFront IPs only)
  enable_domain_fronting = var.enable_domain_fronting

  enable_cs_rest_api = var.enable_cs_rest_api

  # Dashboard server peering
  dashboard_vpc_id   = local.dashboard_vpc_id
  dashboard_vpc_cidr = local.dashboard_vpc_cidr
  dashboard_sg_id    = local.dashboard_sg_id

  tags = var.tags
}

# =============================================================================
# C2 TEAM SERVER MODULE - Single/Redundancy Mode
# =============================================================================

module "c2_team_server" {
  count = local.deploy_c2_infra && (local.c2_deployment_mode == "single" || local.c2_deployment_mode == "redundancy") ? 1 : 0

  source = "./modules/c2_team_server"

  c2_server_count            = local.c2_server_count
  instance_type              = var.c2_server_instance_type
  ami_id                     = var.c2_server_ami_id != "" ? var.c2_server_ami_id : data.aws_ami.ubuntu.id
  key_pair_name              = local.effective_key_pair_name
  private_subnet_ids         = module.vpc[0].private_subnet_ids
  security_group_id          = module.security[0].c2_team_server_security_group_id
  private_ips                = local.c2_server_private_ips
  project_name               = var.project_name
  environment                = var.environment
  root_volume_size           = var.c2_server_root_volume_size
  enable_detailed_monitoring = var.enable_detailed_monitoring
  enable_elastic_ips         = var.c2_server_enable_elastic_ips
  # SECURITY: Use C2-specific instance profile (Option C - VPC-restricted)
  iam_instance_profile_name = length(module.cs_storage) > 0 ? module.cs_storage[0].instance_profile_name_c2 : var.c2_server_iam_instance_profile_name
  phase                     = "" # No phase for single/redundancy mode
  tags                      = local.enhanced_tags

  # Cobalt Strike configuration
  cobalt_strike_s3_path  = var.cobalt_strike_archive_s3_path
  cs_teamserver_password = var.cs_teamserver_password

  # S3 bootstrap (bypasses 16KB user_data limit)
  enable_s3_bootstrap = length(module.cs_storage) > 0
  deployment_bucket   = length(module.cs_storage) > 0 ? module.cs_storage[0].bucket_name : ""
  deployment_id       = var.project_name
  aws_region          = var.aws_region

  # Domain configuration (for CS Listener Guide auto-generation)
  primary_domain         = var.primary_domain_name
  c2_subdomain           = var.c2_subdomain
  malleable_profile        = var.malleable_profile
  custom_profile_content   = var.custom_profile_content
  cs_license_secret_name   = length(module.cs_storage) > 0 ? module.cs_storage[0].cs_license_secret_name : ""
  enable_rest_api        = var.enable_cs_rest_api

  # Custom user_data overrides centralized script if provided
  user_data = var.c2_server_user_data

  # Ensure NAT Gateway + route are ready before instance boots (user_data needs internet)
  depends_on = [module.vpc, module.cs_storage]
}

# =============================================================================
# C2 TEAM SERVER MODULES - Phase-Based Mode (c2-full)
# =============================================================================

module "c2_phase_servers" {
  for_each = local.deploy_c2_infra && local.c2_deployment_mode == "phases" ? {
    for phase_name, phase_config in var.c2_phases : phase_name => phase_config
    if phase_config.enabled
  } : {}

  source = "./modules/c2_team_server"

  c2_server_count            = 1 # One server per phase
  instance_type              = each.value.instance_type
  ami_id                     = var.c2_server_ami_id != "" ? var.c2_server_ami_id : data.aws_ami.ubuntu.id
  key_pair_name              = local.effective_key_pair_name
  # Route each phase to its designated subnet
  private_subnet_ids         = [module.vpc[0].private_subnet_ids[lookup(local.c2_phase_subnet_indices, each.key, 0) % length(module.vpc[0].private_subnet_ids)]]
  security_group_id          = module.security[0].c2_team_server_security_group_id
  private_ips                = lookup(local.c2_phase_private_ips, each.key, [])
  project_name               = var.project_name
  environment                = var.environment
  root_volume_size           = each.value.root_volume_size
  enable_detailed_monitoring = var.enable_detailed_monitoring
  enable_elastic_ips         = false
  # SECURITY: Use C2-specific instance profile (Option C - VPC-restricted)
  iam_instance_profile_name = each.value.iam_instance_profile_name != "" ? each.value.iam_instance_profile_name : (length(module.cs_storage) > 0 ? module.cs_storage[0].instance_profile_name_c2 : null)
  phase                     = each.key # Phase name (staging, post-ex, long-haul)
  tags                      = local.enhanced_tags

  # Cobalt Strike configuration
  cobalt_strike_s3_path  = var.cobalt_strike_archive_s3_path
  cs_teamserver_password = var.cs_teamserver_password

  # S3 bootstrap (bypasses 16KB user_data limit)
  enable_s3_bootstrap = length(module.cs_storage) > 0
  deployment_bucket   = length(module.cs_storage) > 0 ? module.cs_storage[0].bucket_name : ""
  deployment_id       = var.project_name
  aws_region          = var.aws_region

  # Domain configuration (for CS Listener Guide auto-generation)
  primary_domain         = var.primary_domain_name
  c2_subdomain           = var.c2_subdomain
  malleable_profile        = var.malleable_profile
  custom_profile_content   = var.custom_profile_content
  cs_license_secret_name   = length(module.cs_storage) > 0 ? module.cs_storage[0].cs_license_secret_name : ""
  enable_rest_api        = var.enable_cs_rest_api

  # Custom user_data per phase
  user_data = each.value.user_data != "" ? each.value.user_data : ""

  # Ensure NAT Gateway + route are ready before instance boots (user_data needs internet)
  depends_on = [module.vpc, module.cs_storage]
}

# =============================================================================
# PROXY/REDIRECTOR MODULE
# =============================================================================

module "proxy_redirector" {
  count  = local.deploy_redirectors ? 1 : 0
  source = "./modules/proxy_redirector"

  proxy_redirector_count     = var.proxy_redirector_count
  instance_type              = var.proxy_redirector_instance_type
  ami_id                     = var.proxy_redirector_ami_id != "" ? var.proxy_redirector_ami_id : data.aws_ami.ubuntu.id
  key_pair_name              = local.effective_key_pair_name
  public_subnet_ids          = module.vpc[0].public_subnet_ids
  security_group_id          = module.security[0].proxy_redirector_security_group_id
  private_ips                = local.redirector_private_ips
  project_name               = var.project_name
  environment                = var.environment
  root_volume_size           = var.proxy_redirector_root_volume_size
  enable_detailed_monitoring = var.enable_detailed_monitoring
  # SECURITY: Use C2 instance profile for S3 bootstrap access (same VPC), fall back to user-provided
  iam_instance_profile_name  = length(module.cs_storage) > 0 ? module.cs_storage[0].instance_profile_name_c2 : var.proxy_redirector_iam_instance_profile_name
  user_data                  = var.proxy_redirector_user_data
  tags                       = local.enhanced_tags

  # S3 bootstrap (bypasses 16KB user_data limit)
  enable_s3_bootstrap = length(module.cs_storage) > 0
  deployment_bucket   = length(module.cs_storage) > 0 ? module.cs_storage[0].bucket_name : ""
  deployment_id       = var.project_name
  aws_region          = var.aws_region

  # Domain configuration for nginx redirector setup
  primary_domain = var.primary_domain_name
  c2_subdomain   = var.c2_subdomain
  # For single/redundancy mode, use the module output. For phases mode, use the staging server IP.
  c2_server_ip   = length(module.c2_team_server) > 0 ? module.c2_team_server[0].first_server_private_ip : (
    local.c2_deployment_mode == "phases" ? local.c2_phase_private_ips["staging"][0] : ""
  )
  c2_server_port = var.c2_listener_port

  # SSL configuration
  enable_ssl        = var.enable_ssl_certificate
  ssl_provider      = var.ssl_provider
  ssl_auto_retry    = var.ssl_auto_retry
  admin_email       = var.admin_email
  malleable_profile = var.malleable_profile
  custom_c2_uris    = var.custom_c2_uris
  decoy_theme       = var.decoy_theme

  # File Portal
  enable_file_portal     = var.enable_file_portal
  portal_username        = var.portal_username
  portal_password        = var.portal_password
  portal_session_timeout = var.portal_session_timeout
}

# =============================================================================
# BASTION HOST MODULE (Linux SSH Relay)
# =============================================================================

module "bastion" {
  count = local.deploy_bastion && var.enable_bastion ? 1 : 0

  source = "./modules/bastion"

  project_name               = var.project_name
  environment                = var.environment
  # OPSEC: Bastion in management subnet (isolated from redirectors in DMZ)
  # Falls back to public subnet if management subnet is not configured
  public_subnet_id           = length(module.vpc[0].management_subnet_ids) > 0 ? module.vpc[0].management_subnet_ids[0] : module.vpc[0].public_subnet_ids[0]
  security_group_id          = module.security[0].bastion_security_group_id
  key_pair_name              = local.effective_key_pair_name
  instance_type              = var.bastion_instance_type
  ami_id                     = var.bastion_ami_id
  root_volume_size           = var.bastion_root_volume_size
  enable_detailed_monitoring = var.enable_detailed_monitoring
  iam_instance_profile_name  = var.bastion_iam_instance_profile_name != "" ? var.bastion_iam_instance_profile_name : (length(module.cs_storage) > 0 ? module.cs_storage[0].instance_profile_name_c2 : "")
  private_ip                 = local.bastion_private_ip
  tags                       = local.enhanced_tags
}

# =============================================================================
# ATTACK BOX MODULE - Windows Attack Workstation
# =============================================================================
# Deployed for ALL deployment types:
#   C2-only & Combined: C2 VPC private subnet (10.0.10.50)
#   GOAD-only: GOAD VPC private subnet (x.x.x.50)

module "attack_box" {
  count  = local.deploy_attack_box ? 1 : 0
  source = "./modules/attack_box"

  project_name = var.project_name
  environment  = var.environment

  # Network placement: C2 VPC for C2/combined, GOAD VPC for GOAD-only
  subnet_id         = local.is_goad_only ? (length(module.goad) > 0 ? module.goad[0].private_subnet_id : "") : (length(module.vpc) > 0 ? module.vpc[0].private_subnet_ids[0] : "")
  security_group_id = local.is_goad_only ? (length(module.goad) > 0 ? module.goad[0].security_group_id : "") : (length(module.security) > 0 ? module.security[0].attack_box_security_group_id : "")
  private_ip        = local.is_goad_only ? "${local.goad_ip_range}.50" : local.attack_box_private_ip

  # Instance configuration
  instance_type              = var.attack_box_instance_type
  root_volume_size           = var.attack_box_root_volume_size
  admin_password             = var.attack_box_admin_password
  key_pair_name              = local.windows_key_pair_name
  user_public_key            = var.user_public_key
  enable_detailed_monitoring = var.enable_detailed_monitoring

  # C2 Server connection (for CS Client shortcut)
  c2_server_ip   = local.is_goad_only ? "${local.goad_ip_range}.40" : local.c2_server_private_ips[0]
  c2_server_port = var.c2_server_port

  # Domain configuration (for CS Listener Guide auto-generation)
  primary_domain         = var.primary_domain_name
  c2_subdomain           = var.c2_subdomain
  malleable_profile      = var.malleable_profile
  github_token_secret_name = length(module.cs_storage) > 0 ? module.cs_storage[0].github_token_secret_name : ""
  cs_license_secret_name   = length(module.cs_storage) > 0 ? module.cs_storage[0].cs_license_secret_name : ""

  # S3 / Deployment artifacts
  enable_s3_bootstrap       = length(module.cs_storage) > 0
  deployment_bucket         = length(module.cs_storage) > 0 ? module.cs_storage[0].bucket_name : ""
  deployment_id             = var.project_name
  aws_region                = var.aws_region
  iam_instance_profile_name = length(module.cs_storage) > 0 ? (local.is_goad_only ? module.cs_storage[0].instance_profile_name_goad : module.cs_storage[0].instance_profile_name_c2) : ""
  cs_client_s3_path         = var.cobalt_strike_archive_s3_path

  # Tools repository
  tools_repo_url    = var.tools_repo_url
  tools_repo_branch = var.tools_repo_branch

  # Key exchange (GOAD-only: S3-based SSH key exchange with jumpbox)
  enable_key_exchange = local.is_goad_only
  s3_key_prefix       = local.is_goad_only ? "keys/${var.project_name}" : ""

  tags = local.enhanced_tags

  depends_on = [module.vpc, module.goad, module.cs_storage]
}

# =============================================================================
# GOAD MODULE - Vulnerable AD Lab
# =============================================================================

module "goad" {
  count  = local.deploy_goad ? 1 : 0
  source = "./modules/goad"

  lab_type            = local.goad_lab_type
  vpc_cidr            = var.goad_vpc_cidr
  public_subnet_cidr  = var.goad_public_subnet_cidr
  private_subnet_cidr = var.goad_private_subnet_cidr
  ip_range            = split("/", var.goad_vpc_cidr)[0] != "" ? join(".", slice(split(".", split("/", var.goad_vpc_cidr)[0]), 0, 3)) : "192.168.56"
  availability_zone   = local.availability_zones[0]
  peer_vpc_cidr       = local.deploy_vpc_peering ? var.vpc_cidr : ""

  # Attack Box with Cobalt Strike (separate from jumpbox, for GOAD-only mode)
  install_cobalt_strike  = local.install_cs_on_jumpbox
  cobalt_strike_s3_path  = var.cobalt_strike_archive_s3_path
  cs_teamserver_password = var.cs_teamserver_password

  # Access configuration
  management_cidr_blocks = var.management_cidr_blocks
  key_pair_name          = local.effective_key_pair_name

  # User's SSH public key (for jumpbox access)
  user_public_key = var.user_public_key

  # Tools
  tools_repo_url    = var.tools_repo_url
  tools_repo_branch = var.tools_repo_branch

  # Project
  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  # IAM (for S3 access - CS download + key exchange)
  # SECURITY: Use GOAD-specific instance profile (Option C - VPC-restricted)
  iam_instance_profile_name = length(module.cs_storage) > 0 ? module.cs_storage[0].instance_profile_name_goad : ""

  # S3 Key Exchange (Phase 5 - Secure Key Management)
  # Jumpbox uploads its PUBLIC key to S3, Team Server/Attack Box download it
  deployment_bucket = length(module.cs_storage) > 0 ? module.cs_storage[0].bucket_name : ""
  deployment_id     = var.project_name # Use project name as unique deployment ID

  # CS license key for automated activation (team server retrieves at runtime)
  cs_license_secret_name = length(module.cs_storage) > 0 ? module.cs_storage[0].cs_license_secret_name : ""

  tags = local.enhanced_tags
}

# =============================================================================
# VPC PEERING MODULE - For Combined Mode
# =============================================================================

module "vpc_peering" {
  count  = local.deploy_vpc_peering ? 1 : 0
  source = "./modules/vpc_peering"

  c2_vpc_id  = module.vpc[0].vpc_id
  goad_vpc_id = module.goad[0].vpc_id
  # BUG FIX: Include ALL route tables so bastion + redirectors can reach GOAD VMs
  # Previously only private RT had peering routes — bastion couldn't reach GOAD
  c2_route_table_ids = concat(
    module.vpc[0].private_route_table_ids,
    [module.vpc[0].public_route_table_id],
    length(module.vpc[0].management_subnet_ids) > 0 ? [module.vpc[0].management_route_table_id] : []
  )
  goad_route_table_ids = module.goad[0].route_table_ids
  c2_cidr              = var.vpc_cidr
  goad_cidr            = var.goad_vpc_cidr
  project_name         = var.project_name
  tags                 = local.enhanced_tags

  depends_on = [module.vpc, module.goad]
}

# =============================================================================
# DASHBOARD SERVER (Optional — centralized multi-operator dashboard)
# =============================================================================

module "dashboard_server" {
  count  = var.enable_dashboard_server ? 1 : 0
  source = "./modules/dashboard_server"

  dashboard_allowed_ips    = var.dashboard_allowed_ips
  operator_ssh_public_keys = var.operator_ssh_public_keys
  instance_type            = var.dashboard_instance_type
  aws_region               = var.aws_region
  project_name             = "redteam-dashboard"  # Fixed name — not the deployment project name

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# =============================================================================
# DASHBOARD VPC PEERING (connects dashboard server to deployment VPCs)
# Only created when dashboard VPC ID is provided (via module output or variable override)
# =============================================================================

resource "aws_vpc_peering_connection" "dashboard_to_deployment" {
  count       = local.dashboard_vpc_id != "" && length(module.vpc) > 0 ? 1 : 0
  vpc_id      = local.dashboard_vpc_id       # Dashboard VPC (requester)
  peer_vpc_id = module.vpc[0].vpc_id         # Deployment VPC (accepter)
  auto_accept = true                         # Same account

  tags = merge(local.enhanced_tags, {
    Name = "${var.project_name}-dashboard-peering"
  })
}

# Route: Dashboard VPC → Deployment VPC (added to dashboard route table)
resource "aws_route" "dashboard_to_deployment" {
  count                     = local.dashboard_vpc_id != "" && length(module.vpc) > 0 ? 1 : 0
  route_table_id            = data.aws_route_tables.dashboard[0].ids[0]
  destination_cidr_block    = module.vpc[0].vpc_cidr_block
  vpc_peering_connection_id = aws_vpc_peering_connection.dashboard_to_deployment[0].id
}

# Route: Deployment VPC → Dashboard VPC (on all deployment route tables)
resource "aws_route" "deployment_to_dashboard_public" {
  count                     = local.dashboard_vpc_id != "" && length(module.vpc) > 0 ? 1 : 0
  route_table_id            = module.vpc[0].public_route_table_id
  destination_cidr_block    = local.dashboard_vpc_cidr
  vpc_peering_connection_id = aws_vpc_peering_connection.dashboard_to_deployment[0].id
}

resource "aws_route" "deployment_to_dashboard_private" {
  count                     = local.dashboard_vpc_id != "" && length(module.vpc) > 0 ? 1 : 0
  route_table_id            = module.vpc[0].private_route_table_id
  destination_cidr_block    = local.dashboard_vpc_cidr
  vpc_peering_connection_id = aws_vpc_peering_connection.dashboard_to_deployment[0].id
}

resource "aws_route" "deployment_to_dashboard_management" {
  count                     = local.dashboard_vpc_id != "" && length(module.vpc) > 0 && try(length(module.vpc[0].management_route_table_id) > 0, false) ? 1 : 0
  route_table_id            = length(module.vpc) > 0 ? module.vpc[0].management_route_table_id : ""
  destination_cidr_block    = local.dashboard_vpc_cidr
  vpc_peering_connection_id = aws_vpc_peering_connection.dashboard_to_deployment[0].id
}

# Data source: find the dashboard VPC's route table (for adding the return route)
data "aws_route_tables" "dashboard" {
  count  = local.dashboard_vpc_id != "" ? 1 : 0
  vpc_id = local.dashboard_vpc_id
}

# =============================================================================
# DNS MODULE - Route 53 for C2 Domain Management
# =============================================================================

module "dns" {
  count  = local.deploy_c2_infra && var.primary_domain_name != "" ? 1 : 0
  source = "./modules/dns"

  primary_domain_name = var.primary_domain_name
  backup_domains      = var.backup_domains
  c2_subdomain        = var.c2_subdomain
  www_subdomain       = var.www_subdomain
  cdn_subdomain       = var.cdn_subdomain

  # Point DNS records to redirector IPs
  redirector_ips = length(module.proxy_redirector) > 0 ? module.proxy_redirector[0].proxy_redirector_public_ips : []

  # Hosted zone settings
  create_hosted_zone = var.create_dns_hosted_zone
  dns_ttl            = var.dns_ttl

  # Record options
  enable_www_subdomain         = var.enable_www_subdomain
  enable_cdn_subdomain         = var.enable_cdn_subdomain
  enable_apex_record           = var.enable_apex_record
  create_backup_domain_records = var.create_backup_domain_records
  enable_domain_fronting       = var.enable_domain_fronting
  enable_file_portal           = var.enable_file_portal
  enable_spf_record            = var.enable_spf_record
  enable_dmarc_record          = var.enable_dmarc_record

  project_name = var.project_name
  environment  = var.environment
  tags         = local.enhanced_tags

  depends_on = [module.proxy_redirector]
}

# =============================================================================
# ACM CERTIFICATE MODULE - SSL for C2 Traffic
# =============================================================================

module "certificates" {
  count  = local.deploy_c2_infra && var.primary_domain_name != "" && var.enable_ssl_certificate ? 1 : 0
  source = "./modules/certificates"

  primary_domain_name = var.primary_domain_name
  route53_zone_id     = length(module.dns) > 0 ? module.dns[0].zone_id : ""

  project_name = var.project_name
  environment  = var.environment
  tags         = local.enhanced_tags

  depends_on = [module.dns]
}

# =============================================================================
# DOMAIN FRONTING - CloudFront CDN Proxy for C2 Traffic
# =============================================================================
# Hides redirector IPs behind CloudFront. Enables domain fronting where
# beacons connect to a front domain (e.g. grid.crowdstrike.com) but the
# Host header routes traffic to our CloudFront distribution.
#
# CloudFront requires ACM certificates in us-east-1, so we create a
# separate certificate here (independent of the regional cert above).
# =============================================================================

# ACM Certificate in us-east-1 for CloudFront
resource "aws_acm_certificate" "cloudfront_cert" {
  count    = local.deploy_domain_fronting && var.primary_domain_name != "" ? 1 : 0
  provider = aws.us_east_1

  domain_name       = var.primary_domain_name
  validation_method = "DNS"

  # OPSEC: Wildcard-only SANs to minimize CT log exposure.
  # Explicit subdomain SANs are publicly visible in Certificate Transparency logs.
  # The wildcard covers all subdomains without revealing which are active.
  subject_alternative_names = concat(
    ["*.${var.primary_domain_name}"],
    var.backup_domains,
  )

  tags = merge(local.enhanced_tags, {
    Name      = "${var.project_name}-${var.environment}-cloudfront-cert"
    Component = "DomainFronting"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# DNS validation records for CloudFront certificate
resource "aws_route53_record" "cloudfront_cert_validation" {
  for_each = local.deploy_domain_fronting && var.primary_domain_name != "" ? {
    for dvo in aws_acm_certificate.cloudfront_cert[0].domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  } : {}

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = length(module.dns) > 0 ? module.dns[0].zone_id : ""

  depends_on = [module.dns]
}

resource "aws_acm_certificate_validation" "cloudfront_cert" {
  count    = local.deploy_domain_fronting && var.primary_domain_name != "" ? 1 : 0
  provider = aws.us_east_1

  certificate_arn         = aws_acm_certificate.cloudfront_cert[0].arn
  validation_record_fqdns = [for record in aws_route53_record.cloudfront_cert_validation : record.fqdn]

  timeouts {
    create = "30m"
  }
}

# CloudFront Domain Fronting Module
module "domain_fronting" {
  count  = local.deploy_domain_fronting && var.primary_domain_name != "" ? 1 : 0
  source = "./modules/domain_fronting"

  primary_domain_name = var.primary_domain_name
  c2_subdomain        = var.c2_subdomain
  www_subdomain       = var.www_subdomain
  cdn_subdomain       = var.cdn_subdomain
  backup_domains      = var.backup_domains

  # Origins: existing redirector public IPs
  origin_ips = length(module.proxy_redirector) > 0 ? module.proxy_redirector[0].proxy_redirector_public_ips : []

  # ACM certificate from us-east-1
  acm_certificate_arn = aws_acm_certificate_validation.cloudfront_cert[0].certificate_arn

  # Route 53 zone for DNS alias records
  route53_zone_id = length(module.dns) > 0 ? module.dns[0].zone_id : ""

  # Subdomain toggles
  enable_www_subdomain = var.enable_www_subdomain
  enable_cdn_subdomain = var.enable_cdn_subdomain
  enable_apex_record   = var.enable_apex_record

  project_name = var.project_name
  environment  = var.environment
  tags         = local.enhanced_tags

  depends_on = [
    module.proxy_redirector,
    module.dns,
    aws_acm_certificate_validation.cloudfront_cert
  ]
}

# =============================================================================
# EBS SNAPSHOT BACKUP (DLM)
# Daily automated snapshots for critical volumes (team server + attack box).
# Targets volumes tagged Backup=true (set in c2_team_server and attack_box modules).
# =============================================================================

resource "aws_iam_role" "dlm" {
  count = local.deploy_c2_infra ? 1 : 0
  name  = "${var.project_name}-${var.environment}-dlm-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "dlm.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = local.enhanced_tags
}

resource "aws_iam_role_policy_attachment" "dlm" {
  count      = local.deploy_c2_infra ? 1 : 0
  role       = aws_iam_role.dlm[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSDataLifecycleManagerServiceRole"
}

resource "aws_dlm_lifecycle_policy" "daily_snapshots" {
  count              = local.deploy_c2_infra ? 1 : 0
  description        = "Daily snapshots for critical C2 instances"
  execution_role_arn = aws_iam_role.dlm[0].arn
  state              = "ENABLED"

  policy_details {
    resource_types = ["VOLUME"]

    target_tags = {
      Backup = "true"
    }

    schedule {
      name = "DailySnapshot"

      create_rule {
        interval      = 24
        interval_unit = "HOURS"
        times         = ["03:00"]
      }

      retain_rule {
        count = 7
      }

      tags_to_add = {
        CreatedBy = "DLM"
        Type      = "automated-backup"
      }

      copy_tags = true
    }
  }

  tags = merge(local.enhanced_tags, {
    Name = "${var.project_name}-${var.environment}-daily-snapshots"
  })
}
