# Test Lab Module
# =============================================================================
# Provisions 4 vulnerable hosts (tldc01, tlms01, tlws01, tllinux01) on a new
# private subnet inside the EXISTING C2 VPC. Reuses the C2 VPC's NAT Gateway,
# Internet Gateway, and private route table. There is NO new VPC, no peering,
# no new NAT.
#
# Triggered by `enable_test_lab = true` on any c2-* deployment. See
# docs/internal/TESTLAB_DESIGN.md for the authoritative spec.
# =============================================================================

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# =============================================================================
# LOCALS — Host inventory + IP allocation
# =============================================================================

locals {
  # Static private IPs derived from var.subnet_cidr.
  # tldc01 .10, tlms01 .11, tlws01 .12, tllinux01 .13
  dc_private_ip    = cidrhost(var.subnet_cidr, 10)
  ms_private_ip    = cidrhost(var.subnet_cidr, 11)
  ws_private_ip    = cidrhost(var.subnet_cidr, 12)
  linux_private_ip = cidrhost(var.subnet_cidr, 13)

  name_prefix = "${var.project_name}-testlab"

  base_tags = merge(var.tags, {
    Lab     = "test-lab"
    Variant = var.size
    Project = var.project_name
  })

  windows_hosts = {
    tldc01 = {
      role          = "domain_controller"
      private_ip    = local.dc_private_ip
      instance_type = var.windows_server_instance_type
      ami_id        = data.aws_ami.windows_server_2022.id
      user_data = templatefile("${path.module}/user_data/tldc_userdata.ps1.tpl", {
        hostname       = "tldc01"
        admin_password = var.default_admin_password
        dc_private_ip  = local.dc_private_ip
      })
    }
    tlms01 = {
      role          = "member_server"
      private_ip    = local.ms_private_ip
      instance_type = var.windows_server_instance_type
      ami_id        = data.aws_ami.windows_server_2022.id
      user_data = templatefile("${path.module}/user_data/tlhost_userdata.ps1.tpl", {
        hostname       = "tlms01"
        role           = "member_server"
        admin_password = var.default_admin_password
        dc_private_ip  = local.dc_private_ip
      })
    }
    tlws01 = {
      role          = "workstation"
      private_ip    = local.ws_private_ip
      instance_type = var.windows_workstation_instance_type
      ami_id        = data.aws_ami.windows_11_pro.id
      user_data = templatefile("${path.module}/user_data/tlhost_userdata.ps1.tpl", {
        hostname       = "tlws01"
        role           = "workstation"
        admin_password = var.default_admin_password
        dc_private_ip  = local.dc_private_ip
      })
    }
  }
}

# =============================================================================
# AMI DATA SOURCES
# =============================================================================
# Windows Server 2022 — used for tldc01 (DC) + tlms01 (member server).
data "aws_ami" "windows_server_2022" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["Windows_Server-2022-English-Full-Base-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

# Windows 11 Pro — used for tlws01 (workstation).
# AMI matches the SSM public parameter
# /aws/service/ami-windows-latest/Windows_11-English-Full-Pro. Available in
# eu-central-1 (confirmed via the AWS public parameter store).
data "aws_ami" "windows_11_pro" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["Windows_11-English-Full-Pro-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

# Ubuntu 22.04 LTS — used for tllinux01.
data "aws_ami" "ubuntu_22_04" {
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
# NETWORK — New private subnet in the existing C2 VPC
# =============================================================================

resource "aws_subnet" "test_lab" {
  vpc_id            = var.vpc_id
  cidr_block        = var.subnet_cidr
  availability_zone = var.availability_zone

  # No public IPs on lab hosts — ingress is dashboard server / SSM only.
  map_public_ip_on_launch = false

  tags = merge(local.base_tags, {
    Name = "${local.name_prefix}-subnet"
    Tier = "TestLabPrivate"
    Type = "PrivateSubnet"
  })
}

# Associate the new subnet with the C2 VPC's existing private route table so it
# inherits the existing 0.0.0.0/0 -> NAT GW route. No new NAT, no new IGW.
resource "aws_route_table_association" "test_lab" {
  subnet_id      = aws_subnet.test_lab.id
  route_table_id = var.c2_private_route_table_id
}

# =============================================================================
# SECURITY GROUPS
# =============================================================================
# One SG per host-role family plus one shared "lab fabric" SG that every host
# is also a member of — the fabric SG carries the intra-lab self-reference for
# AD replication, SMB, WinRM, ICMP, etc.

# Lab fabric: free intra-SG comms. Every lab host is a member.
resource "aws_security_group" "test_lab_fabric" {
  name        = "${local.name_prefix}-fabric-sg"
  description = "Intra-lab traffic (AD, SMB, WinRM, ICMP) between test lab hosts"
  vpc_id      = var.vpc_id

  egress {
    description = "All outbound (bolt-ons fetch payloads from GitHub etc)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.base_tags, {
    Name      = "${local.name_prefix}-fabric-sg"
    Type      = "SecurityGroup"
    Component = "TestLab"
  })
}

# Self-referential ingress: every lab host can talk to every other lab host on
# every port. Required for AD replication, SMB, WinRM, and bolt-on lateral
# movement testing.
resource "aws_security_group_rule" "fabric_self" {
  type              = "ingress"
  description       = "All traffic from other lab hosts (AD/SMB/WinRM/ICMP)"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  security_group_id = aws_security_group.test_lab_fabric.id
  self              = true
}

# Per-host SGs — hold the role-specific ingress (RDP from dashboard, WinRM from
# jumpbox, SSH from dashboard). Keeping them separate so future bolt-on rules
# (e.g. exposing port 80 on tlms01 IIS to operator IPs) only touch the right
# host.

resource "aws_security_group" "tldc01" {
  name        = "${local.name_prefix}-tldc01-sg"
  description = "tldc01 (Windows Server 2022, Domain Controller)"
  vpc_id      = var.vpc_id

  dynamic "ingress" {
    for_each = var.c2_bastion_sg_id == "" || var.c2_bastion_sg_id == null ? [] : [var.c2_bastion_sg_id]
    content {
      description     = "RDP from dashboard server"
      from_port       = 3389
      to_port         = 3389
      protocol        = "tcp"
      security_groups = [ingress.value]
    }
  }

  dynamic "ingress" {
    for_each = var.c2_jumpbox_sg_id == null ? [] : [var.c2_jumpbox_sg_id]
    content {
      description     = "WinRM HTTP/HTTPS from GOAD jumpbox (combined-* only)"
      from_port       = 5985
      to_port         = 5986
      protocol        = "tcp"
      security_groups = [ingress.value]
    }
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.base_tags, {
    Name      = "${local.name_prefix}-tldc01-sg"
    Type      = "SecurityGroup"
    Component = "TestLab"
    Hostname  = "tldc01"
    Role      = "domain_controller"
  })
}

resource "aws_security_group" "tlms01" {
  name        = "${local.name_prefix}-tlms01-sg"
  description = "tlms01 (Windows Server 2022, Member Server)"
  vpc_id      = var.vpc_id

  dynamic "ingress" {
    for_each = var.c2_bastion_sg_id == "" || var.c2_bastion_sg_id == null ? [] : [var.c2_bastion_sg_id]
    content {
      description     = "RDP from dashboard server"
      from_port       = 3389
      to_port         = 3389
      protocol        = "tcp"
      security_groups = [ingress.value]
    }
  }

  dynamic "ingress" {
    for_each = var.c2_jumpbox_sg_id == null ? [] : [var.c2_jumpbox_sg_id]
    content {
      description     = "WinRM HTTP/HTTPS from GOAD jumpbox (combined-* only)"
      from_port       = 5985
      to_port         = 5986
      protocol        = "tcp"
      security_groups = [ingress.value]
    }
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.base_tags, {
    Name      = "${local.name_prefix}-tlms01-sg"
    Type      = "SecurityGroup"
    Component = "TestLab"
    Hostname  = "tlms01"
    Role      = "member_server"
  })
}

resource "aws_security_group" "tlws01" {
  name        = "${local.name_prefix}-tlws01-sg"
  description = "tlws01 (Windows 11 Pro Workstation)"
  vpc_id      = var.vpc_id

  dynamic "ingress" {
    for_each = var.c2_bastion_sg_id == "" || var.c2_bastion_sg_id == null ? [] : [var.c2_bastion_sg_id]
    content {
      description     = "RDP from dashboard server"
      from_port       = 3389
      to_port         = 3389
      protocol        = "tcp"
      security_groups = [ingress.value]
    }
  }

  dynamic "ingress" {
    for_each = var.c2_jumpbox_sg_id == null ? [] : [var.c2_jumpbox_sg_id]
    content {
      description     = "WinRM HTTP/HTTPS from GOAD jumpbox (combined-* only)"
      from_port       = 5985
      to_port         = 5986
      protocol        = "tcp"
      security_groups = [ingress.value]
    }
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.base_tags, {
    Name      = "${local.name_prefix}-tlws01-sg"
    Type      = "SecurityGroup"
    Component = "TestLab"
    Hostname  = "tlws01"
    Role      = "workstation"
  })
}

resource "aws_security_group" "tllinux01" {
  name        = "${local.name_prefix}-tllinux01-sg"
  description = "tllinux01 (Ubuntu 22.04, Linux Member)"
  vpc_id      = var.vpc_id

  dynamic "ingress" {
    for_each = var.c2_bastion_sg_id == "" || var.c2_bastion_sg_id == null ? [] : [var.c2_bastion_sg_id]
    content {
      description     = "SSH from dashboard server"
      from_port       = 22
      to_port         = 22
      protocol        = "tcp"
      security_groups = [ingress.value]
    }
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.base_tags, {
    Name      = "${local.name_prefix}-tllinux01-sg"
    Type      = "SecurityGroup"
    Component = "TestLab"
    Hostname  = "tllinux01"
    Role      = "linux_member"
  })
}

# =============================================================================
# IAM — SSM-only instance profile.
# Lab hosts don't need S3 bootstrap (their user-data is inlined) but they DO
# need SSM Session Manager so the operator can manage them without RDP/SSH.
# =============================================================================

resource "aws_iam_role" "test_lab_instance" {
  name = "${local.name_prefix}-instance-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = merge(local.base_tags, {
    Name = "${local.name_prefix}-instance-role"
  })
}

resource "aws_iam_role_policy_attachment" "ssm_managed_core" {
  role       = aws_iam_role.test_lab_instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "test_lab" {
  name = "${local.name_prefix}-instance-profile"
  role = aws_iam_role.test_lab_instance.name

  tags = local.base_tags
}

# =============================================================================
# EC2 INSTANCES
# =============================================================================
# Three Windows hosts driven from local.windows_hosts via for_each so the SG +
# AMI + user-data plumbing stays uniform. tllinux01 is a separate resource
# because its user-data + AMI shape is different enough that for_each over
# both OS families muddies the AMI selector.

resource "aws_instance" "windows" {
  for_each = local.windows_hosts

  ami           = each.value.ami_id
  instance_type = each.value.instance_type
  key_name      = var.key_pair_name
  subnet_id     = aws_subnet.test_lab.id
  private_ip    = each.value.private_ip

  vpc_security_group_ids = [
    aws_security_group.test_lab_fabric.id,
    each.key == "tldc01" ? aws_security_group.tldc01.id : (
      each.key == "tlms01" ? aws_security_group.tlms01.id : aws_security_group.tlws01.id
    ),
  ]

  iam_instance_profile = aws_iam_instance_profile.test_lab.name
  user_data            = each.value.user_data

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_size
    encrypted             = true
    delete_on_termination = true

    tags = merge(local.base_tags, {
      Name     = "${local.name_prefix}-${each.key}-root"
      Hostname = each.key
    })
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  tags = merge(local.base_tags, {
    Name     = "${local.name_prefix}-${each.key}"
    Hostname = each.key
    Role     = each.value.role
    OS       = each.key == "tlws01" ? "Windows11Pro" : "WindowsServer2022"
  })

  # Static private IPs mean AWS rejects a replacement until the old instance
  # releases the IP — keep default destroy-then-create.
}

resource "aws_instance" "tllinux01" {
  ami           = data.aws_ami.ubuntu_22_04.id
  instance_type = var.linux_instance_type
  key_name      = var.key_pair_name
  subnet_id     = aws_subnet.test_lab.id
  private_ip    = local.linux_private_ip

  vpc_security_group_ids = [
    aws_security_group.test_lab_fabric.id,
    aws_security_group.tllinux01.id,
  ]

  iam_instance_profile = aws_iam_instance_profile.test_lab.name

  user_data = templatefile("${path.module}/user_data/tllinux_userdata.sh.tpl", {
    hostname      = "tllinux01"
    dc_private_ip = local.dc_private_ip
  })

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_size
    encrypted             = true
    delete_on_termination = true

    tags = merge(local.base_tags, {
      Name     = "${local.name_prefix}-tllinux01-root"
      Hostname = "tllinux01"
    })
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  tags = merge(local.base_tags, {
    Name     = "${local.name_prefix}-tllinux01"
    Hostname = "tllinux01"
    Role     = "linux_member"
    OS       = "Ubuntu2204"
  })
}
