# Bastion/Jump Box Module
# Creates a Windows Server jump box with WSL2 (Ubuntu) for management access
# Provides RDP access for Windows management and WSL2 for SSH access to C2 servers

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Data source for Windows Server AMI
data "aws_ami" "windows_server" {
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
}

# Windows Bastion/Jump Box Instance
resource "aws_instance" "bastion" {
  ami                    = var.ami_id != "" ? var.ami_id : data.aws_ami.windows_server.id
  instance_type          = var.instance_type
  key_name               = var.key_pair_name
  subnet_id              = var.public_subnet_id
  vpc_security_group_ids = [var.security_group_id]

  # Root volume configuration
  root_block_device {
    volume_type = "gp3"
    volume_size = var.root_volume_size
    encrypted   = true
    delete_on_termination = true
  }

  # Enable detailed monitoring (optional)
  monitoring = var.enable_detailed_monitoring

  # IAM role for instance (if provided)
  iam_instance_profile = var.iam_instance_profile_name != "" ? var.iam_instance_profile_name : null

  # User data script to configure Windows and install WSL2
  user_data = base64encode(file("${path.module}/user_data.ps1"))

  # Get Windows password from AWS Systems Manager Parameter Store
  get_password_data = var.windows_admin_password == "" ? true : false

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-${var.environment}-bastion-jumpbox"
      Type = "BastionHost"
      Component = "Management"
      OS = "WindowsServer"
      WSL2 = "Enabled"
    }
  )
}

# Elastic IP for bastion (always needed for RDP access)
resource "aws_eip" "bastion_eip" {
  domain = "vpc"
  instance = aws_instance.bastion.id

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-${var.environment}-bastion-eip"
      Type = "ElasticIP"
      Component = "Management"
    }
  )
}

