# Bastion Host Module
# Lightweight Linux SSH relay for tunneling to private subnets (C2 servers, attack box)
# SSH-only access — no RDP, no heavy tools. All operations happen on the attack box.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Data source for Ubuntu 22.04 LTS AMI
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

# Linux Bastion Host Instance
resource "aws_instance" "bastion" {
  ami                    = var.ami_id != "" ? var.ami_id : data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  key_name               = var.key_pair_name
  subnet_id              = var.public_subnet_id
  vpc_security_group_ids = [var.security_group_id]
  private_ip             = var.private_ip != "" ? var.private_ip : null

  # Root volume configuration
  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_size
    encrypted             = true
    delete_on_termination = true
  }

  # Require IMDSv2 (prevents SSRF-based credential theft from instance metadata)
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  # Enable detailed monitoring (optional)
  monitoring = var.enable_detailed_monitoring

  # IAM role for instance (if provided)
  iam_instance_profile = var.iam_instance_profile_name != "" ? var.iam_instance_profile_name : null

  # User data script for SSH hardening and basic setup
  user_data = templatefile("${path.module}/user_data.sh", {
    hostname = "${var.project_name}-gw"
  })

  tags = merge(
    var.tags,
    {
      Name      = "${var.project_name}-${var.environment}-bastion"
      Type      = "Gateway"
      Component = "Management"
    }
  )
}

# Elastic IP for bastion (always needed for SSH access)
resource "aws_eip" "bastion_eip" {
  domain   = "vpc"
  instance = aws_instance.bastion.id

  tags = merge(
    var.tags,
    {
      Name      = "${var.project_name}-${var.environment}-bastion-eip"
      Type      = "ElasticIP"
      Component = "Management"
    }
  )
}
