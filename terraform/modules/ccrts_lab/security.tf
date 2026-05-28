# CCRTS Lab Module - Security Groups
# =============================================================================
# Per-host-class security groups + a shared "lab fabric" SG that allows free
# intra-lab traffic. Operator ingress comes ONLY from the dashboard VPC CIDR
# (no inbound from the internet — the dashboard is the jump). Optional peer
# VPC ingress for combined C2 + CCRTS variants.
# =============================================================================

# =============================================================================
# LAB FABRIC SG — every lab host is a member. Self-ref ingress allows all
# intra-lab protocols (SMB, WinRM, AD replication, ICMP, ELK shippers, etc.)
# =============================================================================

resource "aws_security_group" "lab_fabric" {
  name        = "${local.name_prefix}-fabric-sg"
  description = "Intra-lab traffic (all protocols) between CCRTS hosts"
  vpc_id      = aws_vpc.ccrts.id

  egress {
    description = "All outbound (lab hosts fetch tools, ELK images, AD packages)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.base_tags, {
    Name = "${local.name_prefix}-fabric-sg"
    Type = "SecurityGroup"
  })
}

resource "aws_security_group_rule" "lab_fabric_self" {
  type              = "ingress"
  description       = "All traffic from other lab hosts"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  security_group_id = aws_security_group.lab_fabric.id
  self              = true
}

# =============================================================================
# KALI SG — operator SSH access via dashboard VPC peer + (optional) C2 VPC
# =============================================================================

resource "aws_security_group" "kali" {
  name        = "${local.name_prefix}-kali-sg"
  description = "CCRTS Kali attacker host"
  vpc_id      = aws_vpc.ccrts.id

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.base_tags, {
    Name     = "${local.name_prefix}-kali-sg"
    Hostname = "kali"
    Role     = "attacker"
  })
}

resource "aws_security_group_rule" "kali_ssh_from_dashboard" {
  count             = var.dashboard_vpc_cidr != "" ? 1 : 0
  type              = "ingress"
  description       = "SSH from dashboard VPC (operator jump path)"
  from_port         = 22
  to_port           = 22
  protocol          = "tcp"
  cidr_blocks       = [var.dashboard_vpc_cidr]
  security_group_id = aws_security_group.kali.id
}

resource "aws_security_group_rule" "kali_ssh_from_peer" {
  count             = var.peer_vpc_cidr != "" ? 1 : 0
  type              = "ingress"
  description       = "SSH from peered C2 VPC (combined-* deployments)"
  from_port         = 22
  to_port           = 22
  protocol          = "tcp"
  cidr_blocks       = [var.peer_vpc_cidr]
  security_group_id = aws_security_group.kali.id
}

# =============================================================================
# WINDOWS WORKSTATION SG — RDP + WinRM from dashboard / peer VPC
# =============================================================================

resource "aws_security_group" "win_ws" {
  name        = "${local.name_prefix}-win-ws-sg"
  description = "CCRTS Windows workstation (CREST AMI)"
  vpc_id      = aws_vpc.ccrts.id

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.base_tags, {
    Name     = "${local.name_prefix}-win-ws-sg"
    Hostname = "windows-ws"
    Role     = "workstation"
  })
}

resource "aws_security_group_rule" "win_ws_rdp_from_dashboard" {
  count             = var.dashboard_vpc_cidr != "" ? 1 : 0
  type              = "ingress"
  description       = "RDP from dashboard VPC"
  from_port         = 3389
  to_port           = 3389
  protocol          = "tcp"
  cidr_blocks       = [var.dashboard_vpc_cidr]
  security_group_id = aws_security_group.win_ws.id
}

resource "aws_security_group_rule" "win_ws_winrm_from_dashboard" {
  count             = var.dashboard_vpc_cidr != "" ? 1 : 0
  type              = "ingress"
  description       = "WinRM HTTP/HTTPS from dashboard VPC"
  from_port         = 5985
  to_port           = 5986
  protocol          = "tcp"
  cidr_blocks       = [var.dashboard_vpc_cidr]
  security_group_id = aws_security_group.win_ws.id
}

resource "aws_security_group_rule" "win_ws_rdp_from_peer" {
  count             = var.peer_vpc_cidr != "" ? 1 : 0
  type              = "ingress"
  description       = "RDP from peered C2 VPC"
  from_port         = 3389
  to_port           = 3389
  protocol          = "tcp"
  cidr_blocks       = [var.peer_vpc_cidr]
  security_group_id = aws_security_group.win_ws.id
}

# =============================================================================
# AD DC SG (ccrts-full only) — WinRM + RDP from dashboard, AD replication
# inside the fabric SG
# =============================================================================

resource "aws_security_group" "ad_dc" {
  count       = var.lab_size == "ccrts-full" ? 1 : 0
  name        = "${local.name_prefix}-ad-dc-sg"
  description = "CCRTS Active Directory domain controller (ccrts.local)"
  vpc_id      = aws_vpc.ccrts.id

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.base_tags, {
    Name     = "${local.name_prefix}-ad-dc-sg"
    Hostname = "dc01"
    Role     = "domain_controller"
  })
}

resource "aws_security_group_rule" "ad_dc_rdp_from_dashboard" {
  count             = var.lab_size == "ccrts-full" && var.dashboard_vpc_cidr != "" ? 1 : 0
  type              = "ingress"
  description       = "RDP from dashboard VPC"
  from_port         = 3389
  to_port           = 3389
  protocol          = "tcp"
  cidr_blocks       = [var.dashboard_vpc_cidr]
  security_group_id = aws_security_group.ad_dc[0].id
}

resource "aws_security_group_rule" "ad_dc_winrm_from_dashboard" {
  count             = var.lab_size == "ccrts-full" && var.dashboard_vpc_cidr != "" ? 1 : 0
  type              = "ingress"
  description       = "WinRM HTTP/HTTPS from dashboard VPC"
  from_port         = 5985
  to_port           = 5986
  protocol          = "tcp"
  cidr_blocks       = [var.dashboard_vpc_cidr]
  security_group_id = aws_security_group.ad_dc[0].id
}

# =============================================================================
# AD WORKSTATION SG (ccrts-full only) — RDP + WinRM from dashboard
# =============================================================================

resource "aws_security_group" "ad_ws" {
  count       = var.lab_size == "ccrts-full" ? 1 : 0
  name        = "${local.name_prefix}-ad-ws-sg"
  description = "CCRTS AD-joined Windows workstation"
  vpc_id      = aws_vpc.ccrts.id

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.base_tags, {
    Name     = "${local.name_prefix}-ad-ws-sg"
    Hostname = "ad-ws01"
    Role     = "ad_workstation"
  })
}

resource "aws_security_group_rule" "ad_ws_rdp_from_dashboard" {
  count             = var.lab_size == "ccrts-full" && var.dashboard_vpc_cidr != "" ? 1 : 0
  type              = "ingress"
  description       = "RDP from dashboard VPC"
  from_port         = 3389
  to_port           = 3389
  protocol          = "tcp"
  cidr_blocks       = [var.dashboard_vpc_cidr]
  security_group_id = aws_security_group.ad_ws[0].id
}

resource "aws_security_group_rule" "ad_ws_winrm_from_dashboard" {
  count             = var.lab_size == "ccrts-full" && var.dashboard_vpc_cidr != "" ? 1 : 0
  type              = "ingress"
  description       = "WinRM HTTP/HTTPS from dashboard VPC"
  from_port         = 5985
  to_port           = 5986
  protocol          = "tcp"
  cidr_blocks       = [var.dashboard_vpc_cidr]
  security_group_id = aws_security_group.ad_ws[0].id
}

# =============================================================================
# ELK SG — SSH (admin) + Kibana 5601 from dashboard / peer
# =============================================================================

resource "aws_security_group" "elk" {
  name        = "${local.name_prefix}-elk-sg"
  description = "CCRTS ELK telemetry stack (Elasticsearch + Kibana + Logstash)"
  vpc_id      = aws_vpc.ccrts.id

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.base_tags, {
    Name     = "${local.name_prefix}-elk-sg"
    Hostname = "elk"
    Role     = "telemetry"
  })
}

resource "aws_security_group_rule" "elk_ssh_from_dashboard" {
  count             = var.dashboard_vpc_cidr != "" ? 1 : 0
  type              = "ingress"
  description       = "SSH from dashboard VPC"
  from_port         = 22
  to_port           = 22
  protocol          = "tcp"
  cidr_blocks       = [var.dashboard_vpc_cidr]
  security_group_id = aws_security_group.elk.id
}

resource "aws_security_group_rule" "elk_kibana_from_dashboard" {
  count             = var.dashboard_vpc_cidr != "" ? 1 : 0
  type              = "ingress"
  description       = "Kibana UI from dashboard VPC"
  from_port         = 5601
  to_port           = 5601
  protocol          = "tcp"
  cidr_blocks       = [var.dashboard_vpc_cidr]
  security_group_id = aws_security_group.elk.id
}

resource "aws_security_group_rule" "elk_kibana_from_peer" {
  count             = var.peer_vpc_cidr != "" ? 1 : 0
  type              = "ingress"
  description       = "Kibana UI from peered C2 VPC"
  from_port         = 5601
  to_port           = 5601
  protocol          = "tcp"
  cidr_blocks       = [var.peer_vpc_cidr]
  security_group_id = aws_security_group.elk.id
}
