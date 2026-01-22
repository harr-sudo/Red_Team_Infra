# GOAD Module - Windows Attack Box Configuration
# =============================================================================
# Windows Server 2022 Attack Box for Red Team Operations
# - Cobalt Strike Client (GUI)
# - PowerShell offensive tools (PowerSploit, etc.)
# - WSL2 with SSH access to Team Server
# - Windows Terminal for better shell experience
# - Optimized for workstation use (server bloat removed)
# =============================================================================

# =============================================================================
# WINDOWS SERVER 2022 AMI DATA SOURCE
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
# ATTACK BOX NETWORK INTERFACE
# =============================================================================

resource "aws_network_interface" "attackbox" {
  count = var.install_cobalt_strike ? 1 : 0

  subnet_id       = aws_subnet.private.id
  private_ips     = ["${var.ip_range}.50"]
  security_groups = [aws_security_group.goad.id]

  tags = merge(var.tags, {
    Name = "${var.project_name}-${local.lab_identifier}-attackbox-windows-nic"
    Lab  = local.lab_identifier
    Role = "AttackBox"
  })
}

# =============================================================================
# ATTACK BOX INSTANCE (Windows - CS Client + Tools)
# =============================================================================

resource "aws_instance" "attackbox" {
  count = var.install_cobalt_strike ? 1 : 0

  ami           = data.aws_ami.windows_2022.id
  instance_type = var.attackbox_instance_type
  # Note: Windows instances don't use SSH key pairs in the same way
  # The attack box will download jumpbox's public key from S3 during bootstrap

  network_interface {
    network_interface_id = aws_network_interface.attackbox[0].id
    device_index         = 0
  }

  # IAM role for S3 access (key exchange)
  iam_instance_profile = var.iam_instance_profile_name != "" ? var.iam_instance_profile_name : null

  # User data - Lightweight bootstrap that downloads full init script from S3
  # This avoids the 16KB EC2 user_data size limit
  # The full initialization script is stored in S3 (see attackbox_scripts.tf)
  user_data = templatefile("${path.module}/scripts/attackbox_bootstrap.ps1", {
    deployment_bucket  = var.deployment_bucket
    deployment_id      = var.deployment_id
    aws_region         = var.aws_region
  })

  root_block_device {
    volume_size           = var.attackbox_disk_size
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true

    tags = merge(var.tags, {
      Name = "${var.project_name}-${local.lab_identifier}-attackbox-windows-root"
      Lab  = local.lab_identifier
    })
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-${local.lab_identifier}-attackbox-windows"
    Lab  = local.lab_identifier
    Role = "AttackBox"
    OS   = "Windows"
  })

  # Ensure team server is created first and init script is uploaded to S3
  depends_on = [
    aws_instance.teamserver,
    aws_s3_object.attackbox_init_script
  ]
}
