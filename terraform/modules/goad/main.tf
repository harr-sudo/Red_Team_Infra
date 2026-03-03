# GOAD Module - Main Configuration
# =============================================================================
# Deploys GOAD (Game Of Active Directory) vulnerable lab environment
# 
# This module creates:
#   - VPC with public and private subnets
#   - Ubuntu jumpbox (with optional Cobalt Strike)
#   - Windows AD VMs (DCs and member servers)
#   - Security groups
#   - SSH keys
# =============================================================================

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}

# NOTE: Attack box resources migrated to standalone module (terraform/modules/attack_box/)
# The attack box is now instantiated at the root level for all deployment types.

# =============================================================================
# DATA SOURCES - Dynamic AMI Lookup
# =============================================================================

# Windows Server 2019 AMI (used by most GOAD VMs)
data "aws_ami" "windows_2019" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["Windows_Server-2019-English-Full-Base-*"]
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

# Windows Server 2016 AMI (used by some GOAD VMs like dc03/meereen, srv03/braavos)
data "aws_ami" "windows_2016" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["Windows_Server-2016-English-Full-Base-*"]
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

# =============================================================================
# Local Values
# =============================================================================

locals {
  lab_identifier = var.lab_identifier != "" ? var.lab_identifier : lower(replace(var.lab_type, "-", ""))

  # Dynamic AMI references
  ami_windows_2019 = data.aws_ami.windows_2019.id
  ami_windows_2016 = data.aws_ami.windows_2016.id

  # Lab-specific VM configurations
  # Note: Passwords are intentionally weak - this is a vulnerable lab for training
  vm_configs = {
    "GOAD-Mini" = {
      "dc01" = {
        name          = "dc01"
        hostname      = "kingslanding"
        domain        = "sevenkingdoms.local"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.10"
        password      = "8dCT-DJjgScp"
        role          = "DC"
      }
    }
    "GOAD-Light" = {
      "dc01" = {
        name          = "dc01"
        hostname      = "kingslanding"
        domain        = "sevenkingdoms.local"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.10"
        password      = "8dCT-DJjgScp"
        role          = "DC"
      }
      "dc02" = {
        name          = "dc02"
        hostname      = "winterfell"
        domain        = "north.sevenkingdoms.local"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.11"
        password      = "NgtI75cKV+Pu"
        role          = "DC"
      }
      "srv02" = {
        name          = "srv02"
        hostname      = "castelblack"
        domain        = "north.sevenkingdoms.local"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.22"
        password      = "NgtI75cKV+Pu"
        role          = "Server"
      }
    }
    # SCCM - Aligned with upstream GOAD
    # https://github.com/Orange-Cyberdefense/GOAD/tree/main/ad/SCCM
    # Passwords match upstream inventory (ad/SCCM/providers/aws/inventory)
    "SCCM" = {
      "dc01" = {
        name          = "dc01"
        hostname      = "dc01"
        domain        = "sccm.lab"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.10"
        password      = "AZERTY*qsdfg"
        role          = "DC"
      }
      "srv01" = {
        name          = "srv01"
        hostname      = "srv01"
        domain        = "sccm.lab"
        ami           = local.ami_windows_2019
        instance_type = "t2.large"
        private_ip    = "${var.ip_range}.11"
        password      = "NgtI75cKV+Pu"
        role          = "SCCM"
      }
      "srv02" = {
        name          = "srv02"
        hostname      = "srv02"
        domain        = "sccm.lab"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.12"
        password      = "NgtazecKV+Pu"
        role          = "SQL"
      }
      "ws01" = {
        name          = "ws01"
        hostname      = "ws01"
        domain        = "sccm.lab"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.13"
        password      = "EP+xh7Rk6j90"
        role          = "Client"
      }
    }
    "GOAD" = {
      "dc01" = {
        name          = "dc01"
        hostname      = "kingslanding"
        domain        = "sevenkingdoms.local"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.10"
        password      = "8dCT-DJjgScp"
        role          = "DC"
      }
      "dc02" = {
        name          = "dc02"
        hostname      = "winterfell"
        domain        = "north.sevenkingdoms.local"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.11"
        password      = "NgtI75cKV+Pu"
        role          = "DC"
      }
      "dc03" = {
        name          = "dc03"
        hostname      = "meereen"
        domain        = "essos.local"
        ami           = local.ami_windows_2016 # Windows Server 2016 for essos domain
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.12"
        password      = "Ufe-bVXSx9rk"
        role          = "DC"
      }
      "srv02" = {
        name          = "srv02"
        hostname      = "castelblack"
        domain        = "north.sevenkingdoms.local"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.22"
        password      = "NgtI75cKV+Pu"
        role          = "Server"
      }
      "srv03" = {
        name          = "srv03"
        hostname      = "braavos"
        domain        = "essos.local"
        ami           = local.ami_windows_2016 # Windows Server 2016 for essos domain
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.23"
        password      = "978i2pF43UJ-"
        role          = "Server"
      }
    }
    # NHA (Network Hacking Academy) - Aligned with upstream GOAD
    # https://github.com/Orange-Cyberdefense/GOAD/tree/main/ad/NHA
    "NHA" = {
      "dc01" = {
        name          = "dc01"
        hostname      = "dc01"
        domain        = "ninja.hack"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.10"
        password      = "8dCT-6546541qsdDJjgScp"
        role          = "DC"
      }
      "dc02" = {
        name          = "dc02"
        hostname      = "dc02"
        domain        = "academy.ninja.lan"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.20"
        password      = "Ufe-qsdaz789bVXSx9rk"
        role          = "DC"
      }
      "srv01" = {
        name          = "srv01"
        hostname      = "srv01"
        domain        = "academy.ninja.lan"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.21"
        password      = "EaqsdP+xh7sdfzaRk6j90"
        role          = "SQL"
      }
      "srv02" = {
        name          = "srv02"
        hostname      = "srv02"
        domain        = "academy.ninja.lan"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.22"
        password      = "978i2pF43UqsdqsdJ-qsd"
        role          = "Web"
      }
      "srv03" = {
        name          = "srv03"
        hostname      = "srv03"
        domain        = "academy.ninja.lan"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.23"
        password      = "EalwxkfhqsdP+xh7sdfzaRk6j90"
        role          = "FileServer"
      }
    }
  }

  # Get VM config for selected lab
  selected_vms = lookup(local.vm_configs, var.lab_type, {})
}

# =============================================================================
# SSH KEYS - Secure Key Management Architecture
# =============================================================================
# Security Architecture (Phase 1 - Secure Key Management):
#   - User provides their own public key for jumpbox access
#   - Internal keys are generated ON THE HOSTS during bootstrap (not in Terraform)
#   - Private keys NEVER leave the host that generates them
#   - Only public keys are exchanged via S3
#
# Key Flow:
#   1. User generates key locally: ssh-keygen -t ed25519 -f ~/.ssh/goad_key
#   2. User provides public key via var.user_public_key
#   3. Jumpbox generates internal key on first boot, uploads PUBLIC key to S3
#   4. Team Server/Attack Box download jumpbox's PUBLIC key from S3
#
# This ensures:
#   - No private keys in Terraform state
#   - No private keys transmitted via API
#   - Each host controls its own private key
# =============================================================================

# AWS Key Pair for Jumpbox - uses USER's public key (not Terraform-generated)
# Only created if user has provided their public key
resource "aws_key_pair" "jumpbox" {
  count = var.user_public_key != "" ? 1 : 0
  
  key_name   = "${var.project_name}-${local.lab_identifier}-jumpbox-ubuntu-key"
  public_key = var.user_public_key  # User's own public key

  tags = merge(var.tags, {
    Name = "${var.project_name}-${local.lab_identifier}-jumpbox-ubuntu-key"
    Lab  = local.lab_identifier
    Type = "External-UserProvided"
  })
}

# Note: Internal and Windows key pairs are NO LONGER created in Terraform.
# These keys are generated on the hosts during bootstrap and exchanged via S3.
# See: scripts/jumpbox_init.sh, scripts/teamserver_init.sh, scripts/windows_init.ps1

