# GOAD Module - Outputs
# =============================================================================
# Outputs for GOAD lab deployment with proper architecture separation:
# - Jumpbox: SSH Gateway (minimal)
# - Team Server: CS Team Server ONLY (Ubuntu)
# - Attack Box: Windows workstation with CS Client + Tools
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
# Jumpbox Outputs (SSH Gateway ONLY)
# =============================================================================

output "jumpbox_public_ip" {
  description = "Public IP address of the jumpbox (SSH gateway)"
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
  value       = "ssh -i goad-jumpbox.pem ubuntu@${aws_eip.jumpbox.public_ip}"
}

# =============================================================================
# Team Server Outputs (CS Team Server ONLY - Ubuntu)
# =============================================================================

output "teamserver_private_ip" {
  description = "Private IP address of the team server (CS only)"
  value       = var.install_cobalt_strike ? aws_instance.teamserver[0].private_ip : null
}

output "teamserver_instance_id" {
  description = "Instance ID of the team server"
  value       = var.install_cobalt_strike ? aws_instance.teamserver[0].id : null
}

output "teamserver_ssh_command" {
  description = "SSH command to connect to team server (from jumpbox)"
  value       = var.install_cobalt_strike ? "ssh ubuntu@${var.ip_range}.40" : null
}

# =============================================================================
# Attack Box Outputs (Windows - CS Client + Tools)
# =============================================================================

output "attackbox_private_ip" {
  description = "Private IP address of the Windows attack box"
  value       = var.install_cobalt_strike ? aws_instance.attackbox[0].private_ip : null
}

output "attackbox_instance_id" {
  description = "Instance ID of the Windows attack box"
  value       = var.install_cobalt_strike ? aws_instance.attackbox[0].id : null
}

output "attackbox_rdp_tunnel" {
  description = "SSH tunnel command for RDP to attack box"
  value       = var.install_cobalt_strike ? "ssh -i goad-jumpbox.pem -L 3389:${var.ip_range}.50:3389 ubuntu@${aws_eip.jumpbox.public_ip}" : null
}

# =============================================================================
# SSH Key Outputs - Separate keys for different trust boundaries
# =============================================================================

# EXTERNAL KEY - For user's machine to access Jumpbox
output "jumpbox_ssh_private_key" {
  description = "SSH private key for EXTERNAL access (User → Jumpbox only)"
  value       = tls_private_key.jumpbox_ssh.private_key_pem
  sensitive   = true
}

output "jumpbox_ssh_public_key" {
  description = "SSH public key for Jumpbox"
  value       = tls_private_key.jumpbox_ssh.public_key_openssh
}

# INTERNAL KEY - For Jumpbox/Attack Box to access Team Server
output "internal_ssh_private_key" {
  description = "SSH private key for INTERNAL access (Jumpbox/AttackBox → TeamServer)"
  value       = var.install_cobalt_strike ? tls_private_key.internal_ssh.private_key_pem : null
  sensitive   = true
}

output "internal_ssh_public_key" {
  description = "SSH public key for internal hosts"
  value       = var.install_cobalt_strike ? tls_private_key.internal_ssh.public_key_openssh : null
}

# WINDOWS KEY - For Windows VM access
output "windows_ssh_private_key" {
  description = "SSH private key for Windows VMs"
  value       = tls_private_key.windows_ssh.private_key_pem
  sensitive   = true
}

output "key_pair_name" {
  description = "Name of the external SSH key pair (for Jumpbox)"
  value       = aws_key_pair.jumpbox.key_name
}

output "internal_key_pair_name" {
  description = "Name of the internal SSH key pair (for Team Server)"
  value       = var.install_cobalt_strike ? aws_key_pair.internal.key_name : null
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
      username = "ubuntu"
      note     = "SSH key auth only - minimal SSH gateway"
    }
    teamserver = var.install_cobalt_strike ? {
      username = "ubuntu"
      note     = "SSH key auth - CS Team Server only"
      ip       = "${var.ip_range}.40"
      port     = 50050
    } : null
    attackbox = var.install_cobalt_strike ? {
      username = "Administrator"
      password = var.attackbox_admin_password
      note     = "Windows attack box - RDP via jumpbox tunnel"
      ip       = "${var.ip_range}.50"
    } : null
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
    teamserver_ip   = "${var.ip_range}.40"
    teamserver_port = 50050
    attackbox_ip    = "${var.ip_range}.50"
    method          = "RDP to Attack Box, then connect CS Client to Team Server"
    rdp_tunnel_cmd  = "ssh -i goad-jumpbox.pem -L 3389:${var.ip_range}.50:3389 ubuntu@${aws_eip.jumpbox.public_ip}"
    cs_tunnel_cmd   = "ssh -i goad-jumpbox.pem -L 50050:${var.ip_range}.40:50050 ubuntu@${aws_eip.jumpbox.public_ip}"
  } : null
}

output "access_instructions" {
  description = "How to access the GOAD lab"
  value = var.install_cobalt_strike ? [
    "=== Architecture ===",
    "Jumpbox (${aws_eip.jumpbox.public_ip}): SSH Gateway - minimal bastion",
    "Team Server (${var.ip_range}.40): CS Team Server ONLY - Ubuntu",
    "Attack Box (${var.ip_range}.50): Windows - CS Client + PowerSploit + Tools",
    "",
    "=== METHOD 1: Use Windows Attack Box (Recommended) ===",
    "Step 1: Create RDP tunnel through jumpbox:",
    "   ssh -i goad-jumpbox.pem -L 3389:${var.ip_range}.50:3389 ubuntu@${aws_eip.jumpbox.public_ip}",
    "Step 2: RDP to localhost:3389",
    "Step 3: Login: Administrator / ${var.attackbox_admin_password}",
    "Step 4: On Windows, open WSL terminal and type: ssh teamserver",
    "Step 5: Or launch CS Client GUI and connect to: ${var.ip_range}.40:50050",
    "",
    "=== METHOD 2: Run CS Client from YOUR Local Machine ===",
    "Step 1: Create SSH tunnel to Team Server:",
    "   ssh -i goad-jumpbox.pem -L 50050:${var.ip_range}.40:50050 ubuntu@${aws_eip.jumpbox.public_ip}",
    "Step 2: Keep terminal open",
    "Step 3: Launch your local Cobalt Strike client",
    "Step 4: Connect to: localhost:50050",
    "",
    "=== METHOD 3: SSH Access to Team Server ===",
    "Step 1: SSH to Jumpbox:",
    "   ssh -i goad-jumpbox.pem ubuntu@${aws_eip.jumpbox.public_ip}",
    "Step 2: From Jumpbox, SSH to Team Server:",
    "   ssh ubuntu@${var.ip_range}.40",
    "Step 3: Check team server status:",
    "   /opt/cobaltstrike/check-status.sh",
    "",
    "=== Attack GOAD Lab (from Windows Attack Box) ===",
    "1. Import PowerView:",
    "   Import-Module C:\\Tools\\PowerSploit\\Recon\\PowerView.ps1",
    "2. Enumerate domain:",
    "   Get-DomainUser -Domain sevenkingdoms.local",
    "",
    "=== Windows AD VMs (via RDP tunnel) ===",
    "DC01: ${var.ip_range}.10 - sevenkingdoms.local",
    "RDP tunnel: ssh -i goad-jumpbox.pem -L 3389:${var.ip_range}.10:3389 ubuntu@${aws_eip.jumpbox.public_ip}"
    ] : [
    "=== SSH Access ===",
    "1. SSH to Jumpbox: ssh -i goad-jumpbox.pem ubuntu@${aws_eip.jumpbox.public_ip}",
    "",
    "=== Windows RDP (via SSH tunnel) ===",
    "1. Create tunnel: ssh -i goad-jumpbox.pem -L 3389:${var.ip_range}.10:3389 ubuntu@${aws_eip.jumpbox.public_ip}",
    "2. RDP to localhost:3389"
  ]
}

# =============================================================================
# Summary Output
# =============================================================================

output "deployment_summary" {
  description = "Summary of deployed infrastructure"
  value = {
    architecture = var.install_cobalt_strike ? "GOAD + Cobalt Strike" : "GOAD Only"
    jumpbox = {
      role   = var.install_cobalt_strike ? "SSH Gateway (minimal)" : "SSH Gateway"
      ip     = aws_eip.jumpbox.public_ip
      access = "SSH with key"
    }
    teamserver = var.install_cobalt_strike ? {
      role   = "CS Team Server ONLY"
      ip     = "${var.ip_range}.40"
      port   = 50050
      access = "SSH via jumpbox (internal key)"
    } : null
    attackbox = var.install_cobalt_strike ? {
      role   = "Windows Attack Workstation"
      ip     = "${var.ip_range}.50"
      os     = "Windows Server 2019"
      tools  = ["PowerSploit", "WSL2", "CS Client ready"]
      access = "RDP via jumpbox tunnel"
    } : null
    goad_lab = {
      type = var.lab_type
      vms  = length(local.selected_vms)
    }
  }
}
