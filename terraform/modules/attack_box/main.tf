# Attack Box Module - Standalone Windows Attack Workstation
# =============================================================================
# Windows Server 2022 workstation for red team operations:
# - Cobalt Strike Client (GUI)
# - Red team tools from GitHub repository (C:\Tools)
# - Payload staging directory (C:\Payloads)
# - PowerSploit, WSL2, VS Code, Windows Terminal
# - Optimized for workstation use (server bloat removed, Defender disabled)
#
# Used by ALL deployment types:
# - C2-only: Placed in C2 VPC private subnet, accessed via dashboard-server RDP tunnel
# - GOAD-only: Placed in GOAD VPC private subnet, accessed via jumpbox SSH tunnel
# - Combined: Placed in C2 VPC private subnet, accessed via dashboard-server RDP tunnel
# =============================================================================

terraform {
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
}

# =============================================================================
# WINDOWS SERVER 2022 AMI
# =============================================================================

data "aws_ami" "windows_2022" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["Windows_Server-2022-English-Full-Base-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

# =============================================================================
# RANDOM PASSWORD FOR ADMINISTRATOR ACCOUNT
# =============================================================================

resource "random_password" "attack_box" {
  length  = 20
  special = false # Alphanumeric only — user resets on first RDP login
}

locals {
  admin_password   = var.admin_password != "" ? var.admin_password : random_password.attack_box.result
  use_s3_bootstrap = var.enable_s3_bootstrap
}

# =============================================================================
# UPLOAD INIT SCRIPT TO S3 (bypasses 16KB EC2 user_data limit)
# =============================================================================

resource "aws_s3_object" "attack_box_init_script" {
  count = local.use_s3_bootstrap ? 1 : 0

  bucket = var.deployment_bucket
  key    = "${var.deployment_id}/scripts/attack_box_init.ps1"

  content = templatefile("${path.module}/scripts/attack_box_init.ps1", {
    c2_server_ip             = var.c2_server_ip
    c2_server_port           = var.c2_server_port
    deployment_bucket        = var.deployment_bucket
    deployment_id            = var.deployment_id
    aws_region               = var.aws_region
    hostname                 = "attackbox-windows"
    cs_client_s3_path        = var.cs_client_s3_path
    tools_repo_url           = var.tools_repo_url
    tools_repo_branch        = var.tools_repo_branch
    enable_key_exchange      = var.enable_key_exchange ? "true" : "false"
    s3_key_prefix            = var.s3_key_prefix
    primary_domain           = var.primary_domain
    c2_subdomain             = var.c2_subdomain
    malleable_profile        = var.malleable_profile
    github_token_secret_name = var.github_token_secret_name
    cs_license_secret_name   = var.cs_license_secret_name
  })

  content_type = "text/plain"

  tags = merge(var.tags, {
    Name      = "${var.project_name}-${var.environment}-attack-box-init-script"
    Component = "AttackBox"
  })
}

# =============================================================================
# NETWORK INTERFACE (static private IP)
# =============================================================================

resource "aws_network_interface" "attack_box" {
  count = var.private_ip != "" ? 1 : 0

  subnet_id       = var.subnet_id
  private_ips     = [var.private_ip]
  security_groups = [var.security_group_id]

  tags = merge(var.tags, {
    Name      = "${var.project_name}-${var.environment}-attackbox-nic"
    Component = "AttackBox"
  })
}

# =============================================================================
# ATTACK BOX INSTANCE
# =============================================================================

resource "aws_instance" "attack_box" {
  ami           = var.ami_id != "" ? var.ami_id : data.aws_ami.windows_2022.id
  instance_type = var.instance_type

  # Use dedicated NIC for static IP, or direct subnet assignment for DHCP
  dynamic "network_interface" {
    for_each = var.private_ip != "" ? [1] : []
    content {
      network_interface_id = aws_network_interface.attack_box[0].id
      device_index         = 0
    }
  }

  # Only set these when NOT using a dedicated network interface
  subnet_id              = var.private_ip == "" ? var.subnet_id : null
  vpc_security_group_ids = var.private_ip == "" ? [var.security_group_id] : null
  key_name               = var.key_pair_name != "" ? var.key_pair_name : null

  # IAM role for S3 access (CS files, tools, scripts)
  iam_instance_profile = var.iam_instance_profile_name != "" ? var.iam_instance_profile_name : null

  # User data — lightweight bootstrap downloads full init script from S3
  user_data = local.use_s3_bootstrap ? templatefile("${path.module}/scripts/attack_box_bootstrap.ps1", {
    deployment_bucket = var.deployment_bucket
    deployment_id     = var.deployment_id
    aws_region        = var.aws_region
    ssh_public_key    = var.user_public_key
  }) : null

  root_block_device {
    volume_size           = var.root_volume_size
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true

    tags = merge(var.tags, {
      Name      = "${var.project_name}-${var.environment}-attackbox-root"
      Component = "AttackBox"
      Backup    = "true"
    })
  }

  monitoring = var.enable_detailed_monitoring

  # Require IMDSv2 (prevents SSRF-based credential theft from instance metadata)
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  # Prevent instance recreation when init script changes (use taint to force rebuild)
  lifecycle {
    ignore_changes = [user_data]
  }

  tags = merge(var.tags, {
    Name      = "${var.project_name}-${var.environment}-attackbox-windows"
    Type      = "Workstation"
    Component = "Operations"
  })

  # Ensure S3 script is uploaded before instance launches
  depends_on = [aws_s3_object.attack_box_init_script]
}
