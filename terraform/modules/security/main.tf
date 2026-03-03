# Security Groups Module
# Creates security groups for C2 infrastructure components

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Security Group for C2 Team Servers
resource "aws_security_group" "c2_team_server_sg" {
  name        = "${var.project_name}-${var.environment}-c2-team-server-sg"
  description = "Security group for C2 team servers in private subnets"
  vpc_id      = var.vpc_id

  # SSH access from bastion host (for WSL2 SSH access)
  ingress {
    description     = "SSH from bastion host"
    from_port       = var.ssh_port
    to_port         = var.ssh_port
    protocol        = "tcp"
    security_groups = [aws_security_group.bastion_sg.id]
  }

  # SSH access from management IPs (fallback - can be removed if only using bastion)
  ingress {
    description = "SSH from management CIDR blocks"
    from_port   = var.ssh_port
    to_port     = var.ssh_port
    protocol    = "tcp"
    cidr_blocks = var.management_cidr_blocks
  }

  # NOTE: C2 traffic from proxy/redirectors is added via separate rule below to avoid cycle

  # Outbound - all traffic allowed
  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    var.tags,
    {
      Name      = "${var.project_name}-${var.environment}-c2-team-server-sg"
      Type      = "SecurityGroup"
      Component = "C2TeamServer"
    }
  )
}

# Security Group for Proxy/Redirector Servers
resource "aws_security_group" "proxy_redirector_sg" {
  name        = "${var.project_name}-${var.environment}-proxy-redirector-sg"
  description = "Security group for proxy/redirector servers in public subnets"
  vpc_id      = var.vpc_id

  # SSH access from management IPs only
  ingress {
    description = "SSH from management CIDR blocks"
    from_port   = var.ssh_port
    to_port     = var.ssh_port
    protocol    = "tcp"
    cidr_blocks = var.management_cidr_blocks
  }

  # HTTP/HTTPS rules are defined as separate resources below to support
  # conditional CloudFront-only restriction when domain fronting is enabled

  # NOTE: Egress to C2 servers is added via separate rule below to avoid cycle

  # Outbound - all traffic allowed (for pass-through)
  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    var.tags,
    {
      Name      = "${var.project_name}-${var.environment}-proxy-redirector-sg"
      Type      = "SecurityGroup"
      Component = "ProxyRedirector"
    }
  )
}

# =============================================================================
# REDIRECTOR HTTP/HTTPS RULES - Conditional on domain fronting
# =============================================================================
# When domain fronting is DISABLED: allow HTTP/HTTPS from the internet (0.0.0.0/0)
# When domain fronting is ENABLED: restrict to CloudFront IPs only via managed prefix list

# CloudFront managed prefix list (only needed when domain fronting is enabled)
data "aws_ec2_managed_prefix_list" "cloudfront" {
  count = var.enable_domain_fronting ? 1 : 0
  name  = "com.amazonaws.global.cloudfront.origin-facing"
}

# --- Without domain fronting: open to internet ---

resource "aws_security_group_rule" "redirector_http_public" {
  count             = var.enable_domain_fronting ? 0 : 1
  type              = "ingress"
  from_port         = 80
  to_port           = 80
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.proxy_redirector_sg.id
  description       = "HTTP from internet"
}

resource "aws_security_group_rule" "redirector_https_public" {
  count             = var.enable_domain_fronting ? 0 : 1
  type              = "ingress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.proxy_redirector_sg.id
  description       = "HTTPS from internet"
}

# --- With domain fronting: CloudFront IPs only ---

resource "aws_security_group_rule" "redirector_http_cloudfront" {
  count             = var.enable_domain_fronting ? 1 : 0
  type              = "ingress"
  from_port         = 80
  to_port           = 80
  protocol          = "tcp"
  prefix_list_ids   = [data.aws_ec2_managed_prefix_list.cloudfront[0].id]
  security_group_id = aws_security_group.proxy_redirector_sg.id
  description       = "HTTP from CloudFront only (domain fronting)"
}

resource "aws_security_group_rule" "redirector_https_cloudfront" {
  count             = var.enable_domain_fronting ? 1 : 0
  type              = "ingress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  prefix_list_ids   = [data.aws_ec2_managed_prefix_list.cloudfront[0].id]
  security_group_id = aws_security_group.proxy_redirector_sg.id
  description       = "HTTPS from CloudFront only (domain fronting)"
}

# =============================================================================
# CROSS-REFERENCE RULES (separate to avoid circular dependency)
# =============================================================================

# Allow C2 servers to receive traffic from proxy/redirectors
resource "aws_security_group_rule" "c2_from_proxy" {
  type                     = "ingress"
  from_port                = var.c2_server_port
  to_port                  = var.c2_server_port
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.proxy_redirector_sg.id
  security_group_id        = aws_security_group.c2_team_server_sg.id
  description              = "C2 traffic from proxy redirectors"
}

# Allow proxy/redirectors to send traffic to C2 servers
resource "aws_security_group_rule" "proxy_to_c2" {
  type                     = "egress"
  from_port                = var.c2_server_port
  to_port                  = var.c2_server_port
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.c2_team_server_sg.id
  security_group_id        = aws_security_group.proxy_redirector_sg.id
  description              = "Traffic to C2 team servers"
}

# Security Group for Bastion/Jump Box
resource "aws_security_group" "bastion_sg" {
  name        = "${var.project_name}-${var.environment}-bastion-sg"
  description = "Security group for bastion/jump box in public subnet"
  vpc_id      = var.vpc_id

  # RDP access from management IPs only
  ingress {
    description = "RDP from management CIDR blocks"
    from_port   = 3389
    to_port     = 3389
    protocol    = "tcp"
    cidr_blocks = var.management_cidr_blocks
  }

  # SSH access from management IPs (for OpenSSH server on Windows)
  ingress {
    description = "SSH from management CIDR blocks"
    from_port   = var.ssh_port
    to_port     = var.ssh_port
    protocol    = "tcp"
    cidr_blocks = var.management_cidr_blocks
  }

  # Outbound - all traffic allowed (for SSH to C2 servers, internet access, etc.)
  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    var.tags,
    {
      Name      = "${var.project_name}-${var.environment}-bastion-sg"
      Type      = "SecurityGroup"
      Component = "BastionHost"
    }
  )
}

# Security Group for Attack Box (Windows Workstation)
resource "aws_security_group" "attack_box_sg" {
  name        = "${var.project_name}-${var.environment}-attack-box-sg"
  description = "Security group for Windows attack box in private subnet"
  vpc_id      = var.vpc_id

  # RDP access from bastion host only
  ingress {
    description     = "RDP from bastion host"
    from_port       = 3389
    to_port         = 3389
    protocol        = "tcp"
    security_groups = [aws_security_group.bastion_sg.id]
  }

  # SSH access from bastion host (for OpenSSH on Windows)
  ingress {
    description     = "SSH from bastion host"
    from_port       = var.ssh_port
    to_port         = var.ssh_port
    protocol        = "tcp"
    security_groups = [aws_security_group.bastion_sg.id]
  }

  # Outbound - all traffic allowed (for tool downloads, C2 connections, etc.)
  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    var.tags,
    {
      Name      = "${var.project_name}-${var.environment}-attack-box-sg"
      Type      = "SecurityGroup"
      Component = "AttackBox"
    }
  )
}

# =============================================================================
# VPC PEERING RULES (for Combined Mode)
# =============================================================================
# These rules allow C2 servers to communicate with GOAD VMs when peered

# Allow C2 servers to reach GOAD VMs
resource "aws_security_group_rule" "c2_to_goad_all" {
  count = var.enable_vpc_peering && var.goad_vpc_cidr != "" ? 1 : 0

  type              = "egress"
  from_port         = 0
  to_port           = 65535
  protocol          = "tcp"
  cidr_blocks       = [var.goad_vpc_cidr]
  security_group_id = aws_security_group.c2_team_server_sg.id
  description       = "Allow C2 servers to reach GOAD VMs via VPC peering"
}

# Allow C2 servers to receive from GOAD VMs (beacon callbacks)
resource "aws_security_group_rule" "c2_from_goad" {
  count = var.enable_vpc_peering && var.goad_vpc_cidr != "" ? 1 : 0

  type              = "ingress"
  from_port         = 0
  to_port           = 65535
  protocol          = "tcp"
  cidr_blocks       = [var.goad_vpc_cidr]
  security_group_id = aws_security_group.c2_team_server_sg.id
  description       = "Allow beacon callbacks from GOAD VMs"
}

# Allow bastion to reach GOAD VMs (for management)
resource "aws_security_group_rule" "bastion_to_goad" {
  count = var.enable_vpc_peering && var.goad_vpc_cidr != "" ? 1 : 0

  type              = "egress"
  from_port         = 0
  to_port           = 65535
  protocol          = "tcp"
  cidr_blocks       = [var.goad_vpc_cidr]
  security_group_id = aws_security_group.bastion_sg.id
  description       = "Allow bastion to reach GOAD VMs via VPC peering"
}

# Allow attack box to reach GOAD VMs (for direct operations)
resource "aws_security_group_rule" "attack_box_to_goad" {
  count = var.enable_vpc_peering && var.goad_vpc_cidr != "" ? 1 : 0

  type              = "egress"
  from_port         = 0
  to_port           = 65535
  protocol          = "tcp"
  cidr_blocks       = [var.goad_vpc_cidr]
  security_group_id = aws_security_group.attack_box_sg.id
  description       = "Allow attack box to reach GOAD VMs via VPC peering"
}

