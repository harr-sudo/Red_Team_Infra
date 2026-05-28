# CCRTS Lab Module - Main Configuration
# =============================================================================
# Provisions the CCRTS exam-mirror lab in eu-central-1.
#
# CREST Community AMIs (owner 126620636130) are published in eu-west-2 only.
# We read them via a second provider alias (aws.crest_source) and copy the
# underlying snapshots into the deploy region with aws_ami_copy. No EC2
# instances, VPCs, or networking are ever provisioned in eu-west-2.
#
# Phases:
#   ccrts-mini  = kali + windows workstation + ELK + NAT (4 hosts incl. NAT)
#   ccrts-full  = mini + ccrts.local domain controller + AD-joined workstation
# =============================================================================

terraform {
  required_providers {
    aws = {
      source                = "hashicorp/aws"
      version               = "~> 5.0"
      configuration_aliases = [aws.crest_source]
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}

# =============================================================================
# DATA SOURCES — AMI lookups
# =============================================================================

# CREST Kali AMI in eu-west-2 (read-only via crest_source alias)
data "aws_ami" "crest_kali_source" {
  count       = var.crest_kali_ami_override == "" ? 1 : 0
  provider    = aws.crest_source
  most_recent = true
  owners      = ["126620636130"]

  filter {
    name   = "name"
    values = ["CREST RTS Kali Candidate Image*"]
  }
}

# CREST Windows AMI in eu-west-2 (read-only via crest_source alias)
data "aws_ami" "crest_windows_source" {
  count       = var.crest_windows_ami_override == "" ? 1 : 0
  provider    = aws.crest_source
  most_recent = true
  owners      = ["126620636130"]

  filter {
    name   = "name"
    values = ["CREST RTS Windows*"]
  }
}

# Windows Server 2022 — used for the optional AD DC and the AD-joined workstation
# in ccrts-full. No CREST AMI is needed for the DC because the DC role does not
# come pre-baked; promotion happens in dc_init.ps1.
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

# Ubuntu 22.04 — used for the ELK host
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
# CROSS-REGION AMI COPY
# =============================================================================
# aws_ami_copy issues AWS's CopyImage API call. Only EBS snapshot bytes move
# (region -> region) — no compute is ever provisioned in the source region.

resource "aws_ami_copy" "crest_kali" {
  count             = var.crest_kali_ami_override == "" ? 1 : 0
  name              = "ccrts-kali-${replace(data.aws_ami.crest_kali_source[0].name, " ", "-")}"
  description       = "Copy of ${data.aws_ami.crest_kali_source[0].name} from ${var.crest_ami_source_region}"
  source_ami_id     = data.aws_ami.crest_kali_source[0].id
  source_ami_region = var.crest_ami_source_region
  encrypted         = false

  tags = merge(var.tags, {
    Name         = "${var.project_name}-ccrts-kali-copy"
    Component    = "CCRTS"
    SourceAMI    = data.aws_ami.crest_kali_source[0].id
    SourceRegion = var.crest_ami_source_region
  })
}

resource "aws_ami_copy" "crest_windows" {
  count             = var.crest_windows_ami_override == "" ? 1 : 0
  name              = "ccrts-windows-${replace(data.aws_ami.crest_windows_source[0].name, " ", "-")}"
  description       = "Copy of ${data.aws_ami.crest_windows_source[0].name} from ${var.crest_ami_source_region}"
  source_ami_id     = data.aws_ami.crest_windows_source[0].id
  source_ami_region = var.crest_ami_source_region
  encrypted         = false

  tags = merge(var.tags, {
    Name         = "${var.project_name}-ccrts-windows-copy"
    Component    = "CCRTS"
    SourceAMI    = data.aws_ami.crest_windows_source[0].id
    SourceRegion = var.crest_ami_source_region
  })
}

# =============================================================================
# LOCALS — Lab inventory + IP allocation + AMI selection
# =============================================================================

locals {
  lab_identifier = "ccrts"
  name_prefix    = "${var.project_name}-${local.lab_identifier}"

  # IP range prefix derived from vpc_cidr (e.g. "192.168.57")
  ip_range = join(".", slice(split(".", split("/", var.vpc_cidr)[0]), 0, 3))

  base_tags = merge(var.tags, {
    Lab       = local.lab_identifier
    LabSize   = var.lab_size
    Component = "CCRTS"
  })

  # Resolved AMI IDs (operator override > cross-region copy)
  kali_ami_id    = var.crest_kali_ami_override != "" ? var.crest_kali_ami_override : aws_ami_copy.crest_kali[0].id
  windows_ami_id = var.crest_windows_ami_override != "" ? var.crest_windows_ami_override : aws_ami_copy.crest_windows[0].id

  # AD VMs - only deployed when lab_size = ccrts-full
  ad_vms = var.lab_size == "ccrts-full" ? {
    dc01 = {
      hostname      = "dc01"
      role          = "domain_controller"
      private_ip    = "${local.ip_range}.40"
      ami           = data.aws_ami.windows_server_2022.id
      instance_type = "t3.medium"
      user_data = templatefile("${path.module}/scripts/dc_init.ps1", {
        hostname          = "dc01"
        domain            = "ccrts.local"
        netbios           = "CCRTS"
        admin_password    = var.dc_admin_password
        low_priv_password = var.low_priv_password
      })
    }
    ad_ws01 = {
      hostname      = "ad-ws01"
      role          = "ad_workstation"
      private_ip    = "${local.ip_range}.41"
      ami           = data.aws_ami.windows_server_2022.id
      instance_type = "t3.medium"
      user_data = templatefile("${path.module}/scripts/ad_ws_init.ps1", {
        hostname       = "ad-ws01"
        domain         = "ccrts.local"
        netbios        = "CCRTS"
        admin_password = var.windows_admin_password
        dc_private_ip  = "${local.ip_range}.40"
        join_user      = "Administrator"
        join_password  = var.dc_admin_password
      })
    }
  } : {}

  # Static lab VM summary (consumed by outputs.lab_vms)
  base_vms = [
    {
      hostname      = "kali"
      ip            = "${local.ip_range}.20"
      role          = "attacker"
      os            = "Kali (CREST AMI)"
      instance_type = "t3.medium"
    },
    {
      hostname      = "windows-ws"
      ip            = "${local.ip_range}.30"
      role          = "workstation"
      os            = "Windows (CREST AMI)"
      instance_type = "t3.large"
    },
    {
      hostname      = "elk"
      ip            = "${local.ip_range}.50"
      role          = "telemetry"
      os            = "Ubuntu 22.04 + ELK 8.19.0"
      instance_type = "t3.large"
    },
  ]

  ad_vm_summary = [
    for k, v in local.ad_vms : {
      hostname      = v.hostname
      ip            = v.private_ip
      role          = v.role
      os            = "Windows Server 2022"
      instance_type = v.instance_type
    }
  ]
}

# =============================================================================
# SSH KEY PAIR — Operator's public key, scoped to this lab
# =============================================================================

resource "aws_key_pair" "ccrts" {
  count = var.user_public_key != "" ? 1 : 0

  key_name   = "${local.name_prefix}-key"
  public_key = var.user_public_key

  tags = merge(local.base_tags, {
    Name = "${local.name_prefix}-key"
  })
}

locals {
  effective_key_pair_name = length(aws_key_pair.ccrts) > 0 ? aws_key_pair.ccrts[0].key_name : (var.key_pair_name != "" ? var.key_pair_name : null)
}
