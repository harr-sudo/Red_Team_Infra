# GOAD Module - Outputs
# =============================================================================
# Outputs for GOAD lab deployment
# =============================================================================

# =============================================================================
# VPC Outputs
# =============================================================================

output "vpc_id" {
  description = "ID of the GOAD VPC"
  value       = aws_vpc.goad.id
}

output "vpc_cidr" {
  description = "CIDR block of the GOAD VPC"
  value       = aws_vpc.goad.cidr_block
}

output "public_subnet_id" {
  description = "ID of the public subnet"
  value       = aws_subnet.public.id
}

output "private_subnet_id" {
  description = "ID of the private subnet"
  value       = aws_subnet.private.id
}

output "route_table_ids" {
  description = "Route table IDs for VPC peering"
  value       = [aws_route_table.public.id, aws_route_table.private.id]
}

output "security_group_id" {
  description = "ID of the GOAD security group"
  value       = aws_security_group.goad.id
}

# =============================================================================
# Jumpbox Outputs
# =============================================================================

output "jumpbox_public_ip" {
  description = "Public IP address of the jumpbox"
  value       = aws_eip.jumpbox.public_ip
}

output "jumpbox_private_ip" {
  description = "Private IP address of the jumpbox"
  value       = aws_network_interface.jumpbox.private_ip
}

output "jumpbox_instance_id" {
  description = "Instance ID of the jumpbox"
  value       = aws_instance.jumpbox.id
}

output "jumpbox_ssh_command" {
  description = "SSH command to connect to jumpbox"
  value       = "ssh -i goad-jumpbox.pem ${var.jumpbox_username}@${aws_eip.jumpbox.public_ip}"
}

# =============================================================================
# SSH Key Outputs
# =============================================================================

output "jumpbox_ssh_private_key" {
  description = "SSH private key for jumpbox access"
  value       = tls_private_key.jumpbox_ssh.private_key_pem
  sensitive   = true
}

output "jumpbox_ssh_public_key" {
  description = "SSH public key for jumpbox"
  value       = tls_private_key.jumpbox_ssh.public_key_openssh
}

output "windows_ssh_private_key" {
  description = "SSH private key for Windows VMs"
  value       = tls_private_key.windows_ssh.private_key_pem
  sensitive   = true
}

# =============================================================================
# Windows VM Outputs
# =============================================================================

output "windows_vm_ids" {
  description = "Instance IDs of Windows VMs"
  value       = { for k, v in aws_instance.windows_vm : k => v.id }
}

output "windows_vm_private_ips" {
  description = "Private IP addresses of Windows VMs"
  value       = { for k, v in aws_instance.windows_vm : k => v.private_ip }
}

output "lab_vms" {
  description = "Detailed information about all GOAD lab VMs"
  value = [
    for k, v in local.selected_vms : {
      id         = k
      hostname   = v.hostname
      role       = v.role
      domain     = v.domain
      private_ip = v.private_ip
    }
  ]
}

# =============================================================================
# Lab Information
# =============================================================================

output "lab_type" {
  description = "GOAD lab type deployed"
  value       = var.lab_type
}

output "lab_identifier" {
  description = "Lab identifier used for resource naming"
  value       = local.lab_identifier
}

output "vm_count" {
  description = "Number of Windows VMs deployed"
  value       = length(local.selected_vms)
}

# =============================================================================
# Credentials (for UI display)
# =============================================================================

output "credentials" {
  description = "Default lab credentials"
  value = {
    windows_admin = {
      username = var.windows_admin_username
      note     = "Password varies per VM - see lab documentation"
    }
    jumpbox = {
      username = var.jumpbox_username
      note     = "Use SSH key for authentication"
    }
    domain_users = {
      note = "See GOAD documentation for domain user credentials"
      url  = "https://orange-cyberdefense.github.io/GOAD/"
    }
  }
}

output "domain_info" {
  description = "Domain information for the lab"
  value = {
    for k, v in local.selected_vms : v.domain => {
      dc = k
    } if v.role == "DC"
  }
}

# =============================================================================
# Connection Information
# =============================================================================

output "cs_connection" {
  description = "Cobalt Strike connection info (if installed)"
  value = var.install_cobalt_strike ? {
    host   = aws_eip.jumpbox.public_ip
    port   = 50050
    method = "direct"
  } : null
}

output "access_instructions" {
  description = "How to access the GOAD lab"
  value = var.install_cobalt_strike ? [
    "1. Connect Cobalt Strike client to ${aws_eip.jumpbox.public_ip}:50050",
    "2. SSH to jumpbox: ssh -i goad-jumpbox.pem ${var.jumpbox_username}@${aws_eip.jumpbox.public_ip}",
    "3. From jumpbox, access Windows VMs via RDP or WinRM",
    "4. Run Ansible to provision AD: cd /opt/goad && ansible-playbook main.yml"
    ] : [
    "1. SSH to jumpbox: ssh -i goad-jumpbox.pem ${var.jumpbox_username}@${aws_eip.jumpbox.public_ip}",
    "2. From jumpbox, access Windows VMs via RDP or WinRM",
    "3. Run Ansible to provision AD: cd /opt/goad && ansible-playbook main.yml"
  ]
}

