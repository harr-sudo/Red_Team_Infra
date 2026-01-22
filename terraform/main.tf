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
  install_cs_on_jumpbox = local.is_goad_only # Only for GOAD-only mode

  # -------------------------------------------------------------------------
  # GOAD Lab Type Mapping
  # -------------------------------------------------------------------------
  goad_lab_map = {
    "goad-mini"            = "GOAD-Mini"
    "goad-minilab"         = "MINILAB"
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
# CS STORAGE MODULE - S3 bucket for Cobalt Strike files
# =============================================================================
# Option C: Separate IAM Roles Per VPC (Maximum Security)
# - C2 VPC instances use cs_download_c2 role
# - GOAD VPC instances use cs_download_goad role
# - Each role is restricted to its specific VPC
# - Confused deputy attack: BLOCKED

module "cs_storage" {
  count  = var.cobalt_strike_archive_s3_path != "" || local.deploy_c2_infra || local.is_goad_only ? 1 : 0
  source = "./modules/cs_storage"

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
}

# =============================================================================
# VPC MODULE - C2 Infrastructure VPC
# =============================================================================

module "vpc" {
  count  = local.deploy_c2_infra ? 1 : 0
  source = "./modules/vpc"

  vpc_cidr             = var.vpc_cidr
  availability_zones   = local.availability_zones
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  project_name         = var.project_name
  environment          = var.environment
  enable_nat_gateway   = var.enable_nat_gateway
  tags                 = local.enhanced_tags
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

  # VPC Peering configuration (for combined mode)
  enable_vpc_peering = local.deploy_vpc_peering
  goad_vpc_cidr      = local.deploy_vpc_peering ? var.goad_vpc_cidr : ""

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
  key_pair_name              = var.key_pair_name
  private_subnet_ids         = module.vpc[0].private_subnet_ids
  security_group_id          = module.security[0].c2_team_server_security_group_id
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
  tools_repo_url         = var.tools_repo_url
  tools_repo_branch      = var.tools_repo_branch

  # Custom user_data overrides centralized script if provided
  user_data = var.c2_server_user_data
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
  key_pair_name              = var.key_pair_name
  private_subnet_ids         = module.vpc[0].private_subnet_ids
  security_group_id          = module.security[0].c2_team_server_security_group_id
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
  tools_repo_url         = var.tools_repo_url
  tools_repo_branch      = var.tools_repo_branch

  # Custom user_data per phase
  user_data = each.value.user_data != "" ? each.value.user_data : ""
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
  key_pair_name              = var.key_pair_name
  public_subnet_ids          = module.vpc[0].public_subnet_ids
  security_group_id          = module.security[0].proxy_redirector_security_group_id
  project_name               = var.project_name
  environment                = var.environment
  root_volume_size           = var.proxy_redirector_root_volume_size
  enable_detailed_monitoring = var.enable_detailed_monitoring
  iam_instance_profile_name  = var.proxy_redirector_iam_instance_profile_name
  user_data                  = var.proxy_redirector_user_data
  tags                       = local.enhanced_tags

  # Domain configuration for nginx redirector setup
  primary_domain = var.primary_domain_name
  c2_subdomain   = var.c2_subdomain
  c2_server_ip   = length(module.c2_team_server) > 0 ? module.c2_team_server[0].private_ips[0] : ""
  c2_server_port = var.c2_server_port

  # SSL configuration
  enable_ssl        = var.enable_ssl_certificate
  ssl_provider      = var.ssl_provider
  ssl_auto_retry    = var.ssl_auto_retry
  admin_email       = var.admin_email
  malleable_profile = var.malleable_profile
}

# =============================================================================
# BASTION/JUMP BOX MODULE (Windows Server)
# =============================================================================

module "bastion" {
  count = local.deploy_bastion && var.enable_bastion ? 1 : 0

  source = "./modules/bastion"

  project_name               = var.project_name
  environment                = var.environment
  public_subnet_id           = module.vpc[0].public_subnet_ids[0]
  security_group_id          = module.security[0].bastion_security_group_id
  key_pair_name              = var.key_pair_name
  instance_type              = var.bastion_instance_type
  ami_id                     = var.bastion_ami_id
  root_volume_size           = var.bastion_root_volume_size
  enable_detailed_monitoring = var.enable_detailed_monitoring
  iam_instance_profile_name  = var.bastion_iam_instance_profile_name
  windows_admin_password     = var.windows_admin_password
  tags                       = local.enhanced_tags
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

  # Attack Box with Cobalt Strike (separate from jumpbox, for GOAD-only mode)
  install_cobalt_strike  = local.install_cs_on_jumpbox
  cobalt_strike_s3_path  = var.cobalt_strike_archive_s3_path
  cs_teamserver_password = var.cs_teamserver_password

  # Access configuration
  management_cidr_blocks = var.management_cidr_blocks
  key_pair_name          = var.key_pair_name

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

  tags = local.enhanced_tags
}

# =============================================================================
# VPC PEERING MODULE - For Combined Mode
# =============================================================================

module "vpc_peering" {
  count  = local.deploy_vpc_peering ? 1 : 0
  source = "./modules/vpc_peering"

  c2_vpc_id            = module.vpc[0].vpc_id
  goad_vpc_id          = module.goad[0].vpc_id
  c2_route_table_ids   = module.vpc[0].private_route_table_ids
  goad_route_table_ids = module.goad[0].route_table_ids
  c2_cidr              = var.vpc_cidr
  goad_cidr            = var.goad_vpc_cidr
  project_name         = var.project_name
  tags                 = local.enhanced_tags

  depends_on = [module.vpc, module.goad]
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
  redirector_ips = length(module.proxy_redirector) > 0 ? module.proxy_redirector[0].public_ips : []

  # Hosted zone settings
  create_hosted_zone = var.create_dns_hosted_zone
  dns_ttl            = var.dns_ttl

  # Record options
  enable_www_subdomain         = var.enable_www_subdomain
  enable_cdn_subdomain         = var.enable_cdn_subdomain
  enable_apex_record           = var.enable_apex_record
  create_backup_domain_records = var.create_backup_domain_records
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
  c2_subdomain        = var.c2_subdomain
  www_subdomain       = var.www_subdomain
  cdn_subdomain       = var.cdn_subdomain

  route53_zone_id = length(module.dns) > 0 ? module.dns[0].zone_id : ""

  project_name = var.project_name
  environment  = var.environment
  tags         = local.enhanced_tags

  depends_on = [module.dns]
}
