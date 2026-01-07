# GOAD Module - Security Groups
# =============================================================================
# Security groups for GOAD lab VMs
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

# Allow all traffic within GOAD VPC
resource "aws_vpc_security_group_ingress_rule" "goad_internal" {
  security_group_id = aws_security_group.goad.id
  cidr_ipv4         = var.vpc_cidr
  ip_protocol       = "-1"
  description       = "Allow all traffic within GOAD VPC"
}

# Allow SSH from management CIDRs
resource "aws_vpc_security_group_ingress_rule" "ssh" {
  for_each = toset(var.management_cidr_blocks)
  
  security_group_id = aws_security_group.goad.id
  cidr_ipv4         = each.value
  from_port         = 22
  to_port           = 22
  ip_protocol       = "tcp"
  description       = "SSH from management"
}

# Allow RDP from management CIDRs
resource "aws_vpc_security_group_ingress_rule" "rdp" {
  for_each = toset(var.management_cidr_blocks)
  
  security_group_id = aws_security_group.goad.id
  cidr_ipv4         = each.value
  from_port         = 3389
  to_port           = 3389
  ip_protocol       = "tcp"
  description       = "RDP from management"
}

# Allow WinRM from management CIDRs
resource "aws_vpc_security_group_ingress_rule" "winrm" {
  for_each = toset(var.management_cidr_blocks)
  
  security_group_id = aws_security_group.goad.id
  cidr_ipv4         = each.value
  from_port         = 5985
  to_port           = 5986
  ip_protocol       = "tcp"
  description       = "WinRM from management"
}

# Allow Cobalt Strike team server (only if CS installed on jumpbox)
resource "aws_vpc_security_group_ingress_rule" "cobalt_strike" {
  for_each = var.install_cobalt_strike ? toset(var.management_cidr_blocks) : toset([])
  
  security_group_id = aws_security_group.goad.id
  cidr_ipv4         = each.value
  from_port         = 50050
  to_port           = 50050
  ip_protocol       = "tcp"
  description       = "Cobalt Strike team server"
}

# Egress - Allow HTTP (for Windows updates)
resource "aws_vpc_security_group_egress_rule" "http" {
  security_group_id = aws_security_group.goad.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
  description       = "HTTP outbound"
}

# Egress - Allow HTTPS (for Windows updates)
resource "aws_vpc_security_group_egress_rule" "https" {
  security_group_id = aws_security_group.goad.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  description       = "HTTPS outbound"
}

# Egress - Allow DNS
resource "aws_vpc_security_group_egress_rule" "dns" {
  security_group_id = aws_security_group.goad.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 53
  to_port           = 53
  ip_protocol       = "udp"
  description       = "DNS outbound"
}

# Egress - Allow all to GOAD VPC
resource "aws_vpc_security_group_egress_rule" "goad_internal" {
  security_group_id = aws_security_group.goad.id
  cidr_ipv4         = var.vpc_cidr
  ip_protocol       = "-1"
  description       = "All traffic within GOAD VPC"
}

# Egress - Allow ICMP
resource "aws_vpc_security_group_egress_rule" "icmp" {
  security_group_id = aws_security_group.goad.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = -1
  to_port           = -1
  ip_protocol       = "icmp"
  description       = "ICMP outbound"
}

