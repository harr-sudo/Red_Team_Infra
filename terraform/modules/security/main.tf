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

  # C2 traffic from proxy/redirectors (internal only)
  ingress {
    description     = "C2 traffic from proxy redirectors"
    from_port       = var.c2_server_port
    to_port         = var.c2_server_port
    protocol        = "tcp"
    security_groups = [aws_security_group.proxy_redirector_sg.id]
  }

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
      Name = "${var.project_name}-${var.environment}-c2-team-server-sg"
      Type = "SecurityGroup"
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

  # HTTP/HTTPS from internet (for CDN/CloudFront)
  ingress {
    description = "HTTP from internet"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS from internet"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Outbound to C2 servers
  egress {
    description     = "Traffic to C2 team servers"
    from_port       = var.c2_server_port
    to_port         = var.c2_server_port
    protocol        = "tcp"
    security_groups = [aws_security_group.c2_team_server_sg.id]
  }

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
      Name = "${var.project_name}-${var.environment}-proxy-redirector-sg"
      Type = "SecurityGroup"
      Component = "ProxyRedirector"
    }
  )
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
      Name = "${var.project_name}-${var.environment}-bastion-sg"
      Type = "SecurityGroup"
      Component = "BastionHost"
    }
  )
}

