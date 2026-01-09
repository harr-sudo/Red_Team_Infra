# GOAD Module - Team Server Configuration
# =============================================================================
# Dedicated Cobalt Strike Team Server ONLY
# Minimal Ubuntu instance running teamserver daemon - nothing else
# =============================================================================

# =============================================================================
# TEAM SERVER NETWORK INTERFACE
# =============================================================================

resource "aws_network_interface" "teamserver" {
  count = var.install_cobalt_strike ? 1 : 0

  subnet_id       = aws_subnet.private.id
  private_ips     = ["${var.ip_range}.40"]
  security_groups = [aws_security_group.goad.id]

  tags = merge(var.tags, {
    Name = "${var.project_name}-${local.lab_identifier}-teamserver-nic"
    Lab  = local.lab_identifier
    Role = "TeamServer"
  })
}

# =============================================================================
# TEAM SERVER INSTANCE (CS Team Server ONLY)
# =============================================================================

resource "aws_instance" "teamserver" {
  count = var.install_cobalt_strike ? 1 : 0

  ami           = data.aws_ami.ubuntu.id
  instance_type = var.teamserver_instance_type
  key_name      = aws_key_pair.internal.key_name  # INTERNAL key - not jumpbox key!

  network_interface {
    network_interface_id = aws_network_interface.teamserver[0].id
    device_index         = 0
  }

  # IAM role for S3 access (CS download)
  iam_instance_profile = var.iam_instance_profile_name != "" ? var.iam_instance_profile_name : null

  # User data - Team Server ONLY installation
  user_data = templatefile("${path.module}/scripts/teamserver_init.sh", {
    cs_archive_s3_path = var.cobalt_strike_s3_path
    cs_password        = var.cs_teamserver_password
  })

  root_block_device {
    volume_size           = 30
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true

    tags = merge(var.tags, {
      Name = "${var.project_name}-${local.lab_identifier}-teamserver-root"
      Lab  = local.lab_identifier
    })
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${local.lab_identifier}-teamserver"
    Lab         = local.lab_identifier
    Role        = "TeamServer"
    CSInstalled = "true"
  })

  depends_on = [aws_instance.jumpbox]
}

