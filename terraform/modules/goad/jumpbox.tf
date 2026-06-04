# GOAD Module - Jumpbox Configuration
# =============================================================================
# Minimal SSH Gateway (Bastion Host) for accessing internal GOAD resources
# This is a hardened, minimal instance - NOT for running tools
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
    Name = "${var.project_name}-${local.lab_identifier}-jumpbox-ubuntu-nic"
    Lab  = local.lab_identifier
    Role = "Jumpbox"
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
    Name = "${var.project_name}-${local.lab_identifier}-jumpbox-ubuntu-eip"
    Lab  = local.lab_identifier
  })

  depends_on = [aws_internet_gateway.goad]
}

# =============================================================================
# JUMPBOX INSTANCE (Minimal SSH Gateway)
# =============================================================================

resource "aws_instance" "jumpbox" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = var.jumpbox_instance_type
  key_name      = length(aws_key_pair.jumpbox) > 0 ? aws_key_pair.jumpbox[0].key_name : null # User's public key (if provided)

  network_interface {
    network_interface_id = aws_network_interface.jumpbox.id
    device_index         = 0
  }

  # IAM role for S3 access (key exchange)
  iam_instance_profile = var.iam_instance_profile_name != "" ? var.iam_instance_profile_name : null

  # Enforce IMDSv2 (MED): the jumpbox is internet-facing and carries an S3 role.
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  # User data - generates internal key ON THE HOST (not from Terraform)
  # Internal key is uploaded to S3 for Team Server/Attack Box to download
  user_data = templatefile("${path.module}/scripts/jumpbox_init.sh", {
    username      = var.jumpbox_username
    attackbox_ip  = var.install_cobalt_strike ? "${var.ip_range}.50" : ""
    teamserver_ip = var.install_cobalt_strike ? "${var.ip_range}.40" : ""
    install_cs    = var.install_cobalt_strike
    ip_range      = var.ip_range
    # SECURITY: internal_key is NO LONGER passed from Terraform
    # The jumpbox generates its own key during bootstrap
    deployment_bucket = var.deployment_bucket
    deployment_id     = var.deployment_id
    aws_region        = var.aws_region
    hostname          = "jumpbox-ubuntu"
  })

  root_block_device {
    volume_size           = 20 # Minimal disk - just SSH gateway
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true

    tags = merge(var.tags, {
      Name = "${var.project_name}-${local.lab_identifier}-jumpbox-ubuntu-root"
      Lab  = local.lab_identifier
    })
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-${local.lab_identifier}-jumpbox-ubuntu"
    Lab  = local.lab_identifier
    Role = "Jumpbox"
  })
}

