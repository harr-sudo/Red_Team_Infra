# GOAD Module - Windows AD VMs
# =============================================================================
# Windows Server VMs for Active Directory lab
# =============================================================================

# =============================================================================
# NETWORK INTERFACES
# =============================================================================

resource "aws_network_interface" "windows_vm" {
  for_each = local.selected_vms

  subnet_id       = aws_subnet.private.id
  private_ips     = [each.value.private_ip]
  security_groups = [aws_security_group.goad.id]

  tags = merge(var.tags, {
    Name = "${var.project_name}-${local.lab_identifier}-${each.value.name}-nic"
    Lab  = local.lab_identifier
    VM   = each.value.name
  })
}

# =============================================================================
# WINDOWS VM INSTANCES
# =============================================================================

resource "aws_instance" "windows_vm" {
  for_each = local.selected_vms

  ami           = each.value.ami
  instance_type = each.value.instance_type
  key_name      = aws_key_pair.windows.key_name

  network_interface {
    network_interface_id = aws_network_interface.windows_vm[each.key].id
    device_index         = 0
  }

  # Windows initialization script
  user_data = templatefile("${path.module}/scripts/windows_init.ps1", {
    username    = var.windows_admin_username
    password    = each.value.password
    domain      = each.value.domain
    hostname    = each.value.hostname
    private_key = tls_private_key.windows_ssh.private_key_pem
  })

  root_block_device {
    volume_size           = 50
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true

    tags = merge(var.tags, {
      Name = "${var.project_name}-${local.lab_identifier}-${each.value.name}-root"
      Lab  = local.lab_identifier
    })
  }

  tags = merge(var.tags, {
    Name     = "${var.project_name}-${local.lab_identifier}-${each.value.name}"
    Lab      = local.lab_identifier
    Hostname = each.value.hostname
    Domain   = each.value.domain
    Role     = each.value.role
  })

  # Ensure jumpbox is created first (for Ansible access)
  depends_on = [aws_instance.jumpbox]
}

