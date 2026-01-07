# Main Terraform Configuration for Red Team Infrastructure
# Orchestrates VPC, Security Groups, C2 Team Servers, and Proxy/Redirectors

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Backend configuration - uncomment and configure
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

# Local values for deployment configuration
locals {
  # Auto-configure deployment mode based on engagement type if not explicitly set
  c2_deployment_mode = var.c2_deployment_mode != "" ? var.c2_deployment_mode : (
    var.engagement_type == "adhoc" ? "single" : (
      var.engagement_type == "purple-team" ? "redundancy" : (
        var.engagement_type == "full-red-team" ? "phases" : "redundancy"  # Default fallback
      )
    )
  )
  
  # Enhanced tags with engagement type
  enhanced_tags = merge(
    var.tags,
    var.engagement_type != "" ? {
      EngagementType = var.engagement_type
    } : {}
  )
}

# Data sources
data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-*-x86_64-gp2"]
  }
}

# VPC Module
module "vpc" {
  source = "./modules/vpc"

  vpc_cidr             = var.vpc_cidr
  availability_zones   = var.availability_zones
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  project_name         = var.project_name
  environment          = var.environment
  enable_nat_gateway    = var.enable_nat_gateway
  tags                 = local.enhanced_tags
}

# Security Groups Module
module "security" {
  source = "./modules/security"

  vpc_id                = module.vpc.vpc_id
  project_name           = var.project_name
  environment            = var.environment
  management_cidr_blocks  = var.management_cidr_blocks
  ssh_port               = var.ssh_port
  c2_server_port        = var.c2_server_port
  tags                   = var.tags
}

# C2 Team Server Module - Single/Redundancy Mode
module "c2_team_server" {
  count = local.c2_deployment_mode == "single" || local.c2_deployment_mode == "redundancy" ? 1 : 0
  
  source = "./modules/c2_team_server"

  c2_server_count          = local.c2_deployment_mode == "single" ? 1 : var.c2_server_count
  instance_type            = var.c2_server_instance_type
  ami_id                   = var.c2_server_ami_id != "" ? var.c2_server_ami_id : data.aws_ami.amazon_linux.id
  key_pair_name            = var.key_pair_name
  private_subnet_ids       = module.vpc.private_subnet_ids
  security_group_id        = module.security.c2_team_server_security_group_id
  project_name             = var.project_name
  environment              = var.environment
  root_volume_size         = var.c2_server_root_volume_size
  enable_detailed_monitoring = var.enable_detailed_monitoring
  enable_elastic_ips       = var.c2_server_enable_elastic_ips
  iam_instance_profile_name = var.c2_server_iam_instance_profile_name
  user_data                = var.c2_server_user_data
  phase                    = ""  # No phase for single/redundancy mode
  tags                     = local.enhanced_tags
}

# C2 Team Server Modules - Phase-Based Mode
module "c2_phase_servers" {
  for_each = local.c2_deployment_mode == "phases" ? {
    for phase_name, phase_config in var.c2_phases : phase_name => phase_config
    if phase_config.enabled
  } : {}

  source = "./modules/c2_team_server"

  c2_server_count          = 1  # One server per phase
  instance_type            = each.value.instance_type
  ami_id                   = var.c2_server_ami_id != "" ? var.c2_server_ami_id : data.aws_ami.amazon_linux.id
  key_pair_name            = var.key_pair_name
  private_subnet_ids       = module.vpc.private_subnet_ids
  security_group_id        = module.security.c2_team_server_security_group_id
  project_name             = var.project_name
  environment              = var.environment
  root_volume_size         = each.value.root_volume_size
  enable_detailed_monitoring = var.enable_detailed_monitoring
  enable_elastic_ips       = false  # Typically not needed for phase-based
  iam_instance_profile_name = each.value.iam_instance_profile_name != "" ? each.value.iam_instance_profile_name : null
  user_data                = each.value.user_data != "" ? each.value.user_data : null
  phase                    = each.key  # Phase name (staging, post-ex, long-haul)
  tags                     = local.enhanced_tags
}

# Proxy/Redirector Module
module "proxy_redirector" {
  source = "./modules/proxy_redirector"

  proxy_redirector_count     = var.proxy_redirector_count
  instance_type             = var.proxy_redirector_instance_type
  ami_id                    = var.proxy_redirector_ami_id != "" ? var.proxy_redirector_ami_id : data.aws_ami.amazon_linux.id
  key_pair_name             = var.key_pair_name
  public_subnet_ids         = module.vpc.public_subnet_ids
  security_group_id         = module.security.proxy_redirector_security_group_id
  project_name              = var.project_name
  environment               = var.environment
  root_volume_size          = var.proxy_redirector_root_volume_size
  enable_detailed_monitoring = var.enable_detailed_monitoring
  iam_instance_profile_name = var.proxy_redirector_iam_instance_profile_name
  user_data                 = var.proxy_redirector_user_data
  tags                      = local.enhanced_tags
}

# Bastion/Jump Box Module (Windows Server with WSL2)
module "bastion" {
  count = var.enable_bastion ? 1 : 0

  source = "./modules/bastion"

  project_name              = var.project_name
  environment               = var.environment
  public_subnet_id          = module.vpc.public_subnet_ids[0]  # Use first public subnet
  security_group_id         = module.security.bastion_security_group_id
  key_pair_name             = var.key_pair_name
  instance_type             = var.bastion_instance_type
  ami_id                    = var.bastion_ami_id
  root_volume_size          = var.bastion_root_volume_size
  enable_detailed_monitoring = var.enable_detailed_monitoring
  iam_instance_profile_name = var.bastion_iam_instance_profile_name
  windows_admin_password    = var.windows_admin_password
  tags                      = local.enhanced_tags
}

