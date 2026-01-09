# GOAD Module - Windows Attack Box Configuration
# =============================================================================
# Windows 10 Attack Box for Red Team Operations
# - Cobalt Strike Client (GUI)
# - PowerShell offensive tools (PowerSploit, etc.)
# - WSL2 with SSH access to Team Server
# - Ansible for GOAD provisioning
# =============================================================================

# =============================================================================
# WINDOWS 10 AMI DATA SOURCE
# =============================================================================

data "aws_ami" "windows_10" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["Windows_Server-2019-English-Full-Base-*"]
    # Note: Using Windows Server 2019 as Windows 10 AMIs are not directly
    # available on AWS. For true Windows 10, use a custom AMI or BYOL.
    # Windows Server 2019 provides similar functionality for attack operations.
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
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
    Name = "${var.project_name}-${local.lab_identifier}-attackbox-nic"
    Lab  = local.lab_identifier
    Role = "AttackBox"
  })
}

# =============================================================================
# ATTACK BOX INSTANCE (Windows - CS Client + Tools)
# =============================================================================

resource "aws_instance" "attackbox" {
  count = var.install_cobalt_strike ? 1 : 0

  ami           = data.aws_ami.windows_10.id
  instance_type = var.attackbox_instance_type
  key_name      = aws_key_pair.windows.key_name

  network_interface {
    network_interface_id = aws_network_interface.attackbox[0].id
    device_index         = 0
  }

  # User data - PowerShell script for tools installation
  # Uses INTERNAL key for SSH to Team Server (not jumpbox key!)
  user_data = templatefile("${path.module}/scripts/attackbox_init.ps1", {
    teamserver_ip      = "${var.ip_range}.40"
    teamserver_port    = "50050"
    admin_password     = var.attackbox_admin_password
    internal_key       = tls_private_key.internal_ssh.private_key_pem  # Internal key, not jumpbox!
  })

  root_block_device {
    volume_size           = var.attackbox_disk_size
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true

    tags = merge(var.tags, {
      Name = "${var.project_name}-${local.lab_identifier}-attackbox-root"
      Lab  = local.lab_identifier
    })
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-${local.lab_identifier}-attackbox"
    Lab  = local.lab_identifier
    Role = "AttackBox"
    OS   = "Windows"
  })

  # Ensure team server is created first
  depends_on = [aws_instance.teamserver]
}
