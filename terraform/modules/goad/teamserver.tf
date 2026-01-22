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
    Name = "${var.project_name}-${local.lab_identifier}-teamserver-ubuntu-nic"
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
  key_name      = length(aws_key_pair.jumpbox) > 0 ? aws_key_pair.jumpbox[0].key_name : null  # Use jumpbox key pair for initial access

  network_interface {
    network_interface_id = aws_network_interface.teamserver[0].id
    device_index         = 0
  }

  # IAM role for S3 access (CS download + key exchange)
  iam_instance_profile = var.iam_instance_profile_name != "" ? var.iam_instance_profile_name : null

  # User data - Team Server installation + key exchange
  # Downloads jumpbox's PUBLIC key from S3 for authorized_keys
  user_data = templatefile("${path.module}/scripts/teamserver_init.sh", {
    cs_archive_s3_path = var.cobalt_strike_s3_path
    cs_password        = var.cs_teamserver_password
    # Key exchange via S3 - downloads jumpbox's public key
    deployment_bucket  = var.deployment_bucket
    deployment_id      = var.deployment_id
    aws_region         = var.aws_region
    hostname           = "teamserver-ubuntu"
  })

  root_block_device {
    volume_size           = 30
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true

    tags = merge(var.tags, {
      Name = "${var.project_name}-${local.lab_identifier}-teamserver-ubuntu-root"
      Lab  = local.lab_identifier
    })
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${local.lab_identifier}-teamserver-ubuntu"
    Lab         = local.lab_identifier
    Role        = "TeamServer"
    CSInstalled = "true"
  })

  depends_on = [aws_instance.jumpbox]
}

