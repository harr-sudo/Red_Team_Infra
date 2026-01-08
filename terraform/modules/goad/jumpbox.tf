# GOAD Module - Jumpbox Configuration
# =============================================================================
# Ubuntu jumpbox for GOAD lab management
# Optionally includes Cobalt Strike for GOAD-only deployments
# =============================================================================

# =============================================================================
# DATA SOURCES
# =============================================================================

# Ubuntu 22.04 LTS AMI
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

# =============================================================================
# JUMPBOX NETWORK INTERFACE
# =============================================================================

resource "aws_network_interface" "jumpbox" {
  subnet_id       = aws_subnet.public.id
  private_ips     = ["${var.ip_range}.100"]
  security_groups = [aws_security_group.goad.id]

  tags = merge(var.tags, {
    Name = "${var.project_name}-${local.lab_identifier}-jumpbox-nic"
    Lab  = local.lab_identifier
  })
}

# =============================================================================
# JUMPBOX ELASTIC IP
# =============================================================================

resource "aws_eip" "jumpbox" {
  domain                    = "vpc"
  network_interface         = aws_network_interface.jumpbox.id
  associate_with_private_ip = "${var.ip_range}.100"

  tags = merge(var.tags, {
    Name = "${var.project_name}-${local.lab_identifier}-jumpbox-eip"
    Lab  = local.lab_identifier
  })

  depends_on = [aws_internet_gateway.goad]
}

# =============================================================================
# JUMPBOX INSTANCE
# =============================================================================

resource "aws_instance" "jumpbox" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = var.jumpbox_instance_type
  key_name      = aws_key_pair.jumpbox.key_name

  network_interface {
    network_interface_id = aws_network_interface.jumpbox.id
    device_index         = 0
  }

  # IAM role for S3 access (CS download)
  iam_instance_profile = var.iam_instance_profile_name != "" ? var.iam_instance_profile_name : null

  # User data - with or without Cobalt Strike
  user_data = var.install_cobalt_strike ? templatefile("${path.root}/scripts/install_cobalt_strike.sh", {
    cs_archive_s3_path = var.cobalt_strike_s3_path
    cs_password        = var.cs_teamserver_password
    tools_repo_url     = var.tools_repo_url
    tools_repo_branch  = var.tools_repo_branch
    server_role        = "jumpbox"
    }) : templatefile("${path.module}/scripts/jumpbox_init.sh", {
    username = var.jumpbox_username
  })

  root_block_device {
    volume_size           = var.jumpbox_disk_size
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true

    tags = merge(var.tags, {
      Name = "${var.project_name}-${local.lab_identifier}-jumpbox-root"
      Lab  = local.lab_identifier
    })
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${local.lab_identifier}-jumpbox"
    Lab         = local.lab_identifier
    Role        = var.install_cobalt_strike ? "JumpboxWithCS" : "Jumpbox"
    CSInstalled = var.install_cobalt_strike ? "true" : "false"
  })
}

