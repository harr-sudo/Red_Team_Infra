# GOAD Module - Security Groups
# =============================================================================
# Security groups for GOAD lab VMs with proper architecture:
# - Jumpbox: SSH Gateway (public subnet, SSH from internet)
# - Team Server: CS Team Server (private subnet, SSH via jumpbox)
# - Attack Box: Windows workstation (private subnet, RDP via jumpbox)
# - AD VMs: Domain controllers (private subnet, internal access only)
# =============================================================================

# =============================================================================
# GOAD Security Group (shared by all GOAD VMs)
# =============================================================================

resource "aws_security_group" "goad" {
  name        = "${var.project_name}-${local.lab_identifier}-sg"
  description = "Security group for GOAD lab VMs"
  vpc_id      = aws_vpc.goad.id

  tags = merge(var.tags, {
    Name = "${var.project_name}-${local.lab_identifier}-sg"
    Lab  = local.lab_identifier
  })
}

# =============================================================================
# Ingress Rules
# =============================================================================

# Allow all traffic within GOAD VPC (for internal communication)
# This covers:
# - Jumpbox -> Team Server (SSH)
# - Jumpbox -> Attack Box (RDP)
# - Attack Box -> Team Server (CS Client on port 50050)
# - Attack Box -> AD VMs (WinRM, RDP, AD protocols)
resource "aws_vpc_security_group_ingress_rule" "goad_internal" {
  security_group_id = aws_security_group.goad.id
  cidr_ipv4         = var.vpc_cidr
  ip_protocol       = "-1"
  description       = "Allow all traffic within GOAD VPC"
}

# Allow SSH from management CIDRs (to Jumpbox only - it has public IP)
resource "aws_vpc_security_group_ingress_rule" "ssh" {
  for_each = toset(var.management_cidr_blocks)

  security_group_id = aws_security_group.goad.id
  cidr_ipv4         = each.value
  from_port         = 22
  to_port           = 22
  ip_protocol       = "tcp"
  description       = "SSH from management"
}

# Allow RDP from management CIDRs (direct access if needed)
# Note: Typically accessed via SSH tunnel through jumpbox
resource "aws_vpc_security_group_ingress_rule" "rdp" {
  for_each = toset(var.management_cidr_blocks)

  security_group_id = aws_security_group.goad.id
  cidr_ipv4         = each.value
  from_port         = 3389
  to_port           = 3389
  ip_protocol       = "tcp"
  description       = "RDP from management"
}

# Allow all traffic from C2 VPC (for combined mode with VPC peering)
# Only created when peer_vpc_cidr is provided (combined deployments)
resource "aws_vpc_security_group_ingress_rule" "c2_vpc_peering" {
  count = var.peer_vpc_cidr != "" ? 1 : 0

  security_group_id = aws_security_group.goad.id
  cidr_ipv4         = var.peer_vpc_cidr
  ip_protocol       = "-1"
  description       = "Allow all traffic from C2 VPC (VPC peering)"
}

# Allow WinRM from management CIDRs (for Ansible provisioning)
resource "aws_vpc_security_group_ingress_rule" "winrm" {
  for_each = toset(var.management_cidr_blocks)

  security_group_id = aws_security_group.goad.id
  cidr_ipv4         = each.value
  from_port         = 5985
  to_port           = 5986
  ip_protocol       = "tcp"
  description       = "WinRM from management"
}

# =============================================================================
# Egress Rules
# =============================================================================

# Egress - Allow HTTP (for Windows updates, package downloads, Chocolatey)
resource "aws_vpc_security_group_egress_rule" "http" {
  security_group_id = aws_security_group.goad.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
  description       = "HTTP outbound"
}

# Egress - Allow HTTPS (for Windows updates, S3 access, GitHub, Chocolatey)
resource "aws_vpc_security_group_egress_rule" "https" {
  security_group_id = aws_security_group.goad.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  description       = "HTTPS outbound"
}

# Egress - Allow DNS (UDP)
resource "aws_vpc_security_group_egress_rule" "dns_udp" {
  security_group_id = aws_security_group.goad.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 53
  to_port           = 53
  ip_protocol       = "udp"
  description       = "DNS outbound (UDP)"
}

# Egress - Allow DNS (TCP)
resource "aws_vpc_security_group_egress_rule" "dns_tcp" {
  security_group_id = aws_security_group.goad.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 53
  to_port           = 53
  ip_protocol       = "tcp"
  description       = "DNS outbound (TCP)"
}

# Egress - Allow all to GOAD VPC (internal communication)
resource "aws_vpc_security_group_egress_rule" "goad_internal" {
  security_group_id = aws_security_group.goad.id
  cidr_ipv4         = var.vpc_cidr
  ip_protocol       = "-1"
  description       = "All traffic within GOAD VPC"
}

# Egress - Allow ICMP (for ping/traceroute)
resource "aws_vpc_security_group_egress_rule" "icmp" {
  security_group_id = aws_security_group.goad.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = -1
  to_port           = -1
  ip_protocol       = "icmp"
  description       = "ICMP outbound"
}
