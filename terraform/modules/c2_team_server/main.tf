# C2 Team Server Module
# Creates EC2 instances for C2 team servers in private subnets

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# C2 Team Server Instances
resource "aws_instance" "c2_team_server" {
  count = var.c2_server_count

  ami                    = var.ami_id
  instance_type          = var.instance_type
  key_name               = var.key_pair_name
  subnet_id              = var.private_subnet_ids[count.index % length(var.private_subnet_ids)]
  vpc_security_group_ids = [var.security_group_id]

  # Use ephemeral storage only (no persistent EBS)
  root_block_device {
    volume_type = "gp3"
    volume_size = var.root_volume_size
    encrypted   = true
    delete_on_termination = true
  }

  # Disable detailed monitoring to reduce costs (can be enabled if needed)
  monitoring = var.enable_detailed_monitoring

  # IAM role for instance (if provided)
  iam_instance_profile = var.iam_instance_profile_name != "" ? var.iam_instance_profile_name : null

  # User data for initial configuration
  user_data = var.user_data != "" ? var.user_data : null

  tags = merge(
    var.tags,
    {
      Name = var.phase != "" ? "${var.project_name}-${var.environment}-c2-${var.phase}-server" : "${var.project_name}-${var.environment}-c2-team-server-${count.index + 1}"
      Type = "C2TeamServer"
      Component = "C2Infrastructure"
      ServerNumber = count.index + 1
      Phase = var.phase != "" ? var.phase : "generic"
    }
  )
}

# Elastic IPs for C2 servers (optional - typically not needed in private subnets)
resource "aws_eip" "c2_team_server_eip" {
  count = var.enable_elastic_ips ? var.c2_server_count : 0

  domain = "vpc"
  instance = aws_instance.c2_team_server[count.index].id

  tags = merge(
    var.tags,
    {
      Name = var.phase != "" ? "${var.project_name}-${var.environment}-c2-${var.phase}-server-eip" : "${var.project_name}-${var.environment}-c2-team-server-${count.index + 1}-eip"
      Type = "ElasticIP"
      Component = "C2Infrastructure"
      Phase = var.phase != "" ? var.phase : "generic"
    }
  )
}

