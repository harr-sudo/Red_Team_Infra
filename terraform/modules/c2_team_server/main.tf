# C2 Team Server Module
# =============================================================================
# Creates EC2 instances for C2 team servers in private subnets
# Uses centralized Cobalt Strike installation script
# =============================================================================

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# =============================================================================
# Local Values
# =============================================================================

locals {
  # Determine if we should use the centralized CS script
  use_cs_script = var.cobalt_strike_s3_path != "" && var.user_data == ""

  # Generate user_data from template if using CS script
  cs_user_data = local.use_cs_script ? templatefile("${path.root}/scripts/install_cobalt_strike.sh", {
    cs_archive_s3_path = var.cobalt_strike_s3_path
    cs_password        = var.cs_teamserver_password
    tools_repo_url     = var.tools_repo_url
    tools_repo_branch  = var.tools_repo_branch
    server_role        = "c2_server"
    hostname           = var.phase != "" ? "c2-${var.phase}-ubuntu" : "c2-teamserver-ubuntu"
  }) : null

  # Final user_data: custom > CS script > none
  final_user_data = var.user_data != "" ? var.user_data : (
    local.use_cs_script ? local.cs_user_data : null
  )
}

# =============================================================================
# C2 Team Server Instances
# =============================================================================

resource "aws_instance" "c2_team_server" {
  count = var.c2_server_count

  ami                    = var.ami_id
  instance_type          = var.instance_type
  key_name               = var.key_pair_name
  subnet_id              = var.private_subnet_ids[count.index % length(var.private_subnet_ids)]
  vpc_security_group_ids = [var.security_group_id]
  private_ip             = length(var.private_ips) > count.index ? var.private_ips[count.index] : null

  # Root volume - encrypted and deleted on termination
  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_size
    encrypted             = true
    delete_on_termination = true

    tags = merge(var.tags, {
      Name = var.phase != "" ? "${var.project_name}-${var.environment}-c2-${var.phase}-ubuntu-root" : "${var.project_name}-${var.environment}-c2-server-ubuntu-${count.index + 1}-root"
    })
  }

  # CloudWatch monitoring
  monitoring = var.enable_detailed_monitoring

  # IAM role for S3 access (CS download)
  iam_instance_profile = var.iam_instance_profile_name != "" ? var.iam_instance_profile_name : null

  # User data for Cobalt Strike installation
  user_data = local.final_user_data

  tags = merge(
    var.tags,
    {
      Name         = var.phase != "" ? "${var.project_name}-${var.environment}-c2-${var.phase}-ubuntu" : "${var.project_name}-${var.environment}-c2-teamserver-ubuntu-${count.index + 1}"
      Type         = "C2TeamServer"
      Component    = "C2Infrastructure"
      ServerNumber = count.index + 1
      Phase        = var.phase != "" ? var.phase : "generic"
      CSInstalled  = local.use_cs_script ? "true" : "false"
    }
  )

  # Ensure instance is replaced if user_data changes
  lifecycle {
    create_before_destroy = true
  }
}

# =============================================================================
# Elastic IPs (Optional - typically not needed in private subnets)
# =============================================================================

resource "aws_eip" "c2_team_server_eip" {
  count = var.enable_elastic_ips ? var.c2_server_count : 0

  domain   = "vpc"
  instance = aws_instance.c2_team_server[count.index].id

  tags = merge(
    var.tags,
    {
      Name      = var.phase != "" ? "${var.project_name}-${var.environment}-c2-${var.phase}-ubuntu-eip" : "${var.project_name}-${var.environment}-c2-teamserver-ubuntu-${count.index + 1}-eip"
      Type      = "ElasticIP"
      Component = "C2Infrastructure"
      Phase     = var.phase != "" ? var.phase : "generic"
    }
  )
}
