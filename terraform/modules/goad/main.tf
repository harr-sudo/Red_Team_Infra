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
    "MINILAB" = {
      "dc01" = {
        name          = "dc01"
        hostname      = "dc01"
        domain        = "minilab.local"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.10"
        password      = "Admin123!"
        role          = "DC"
      }
      "ws01" = {
        name          = "ws01"
        hostname      = "ws01"
        domain        = "minilab.local"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.20"
        password      = "Admin123!"
        role          = "Workstation"
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
    "SCCM" = {
      "dc01" = {
        name          = "dc01"
        hostname      = "dc01"
        domain        = "sccm.lab"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.10"
        password      = "Admin123!"
        role          = "DC"
      }
      "sccm" = {
        name          = "sccm"
        hostname      = "sccm"
        domain        = "sccm.lab"
        ami           = local.ami_windows_2019
        instance_type = "t2.large"
        private_ip    = "${var.ip_range}.11"
        password      = "Admin123!"
        role          = "SCCM"
      }
      "mssql" = {
        name          = "mssql"
        hostname      = "mssql"
        domain        = "sccm.lab"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.12"
        password      = "Admin123!"
        role          = "SQL"
      }
      "client" = {
        name          = "client"
        hostname      = "client"
        domain        = "sccm.lab"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.20"
        password      = "Admin123!"
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
    "NHA" = {
      "dc01" = {
        name          = "dc01"
        hostname      = "dc-academy"
        domain        = "academy.yourcompany.local"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.10"
        password      = "Admin123!"
        role          = "DC"
      }
      "dc02" = {
        name          = "dc02"
        hostname      = "dc-yourcompany"
        domain        = "yourcompany.local"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.11"
        password      = "Admin123!"
        role          = "DC"
      }
      "sql" = {
        name          = "sql"
        hostname      = "sql"
        domain        = "yourcompany.local"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.12"
        password      = "Admin123!"
        role          = "SQL"
      }
      "web" = {
        name          = "web"
        hostname      = "web"
        domain        = "yourcompany.local"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.20"
        password      = "Admin123!"
        role          = "Web"
      }
      "share" = {
        name          = "share"
        hostname      = "share"
        domain        = "yourcompany.local"
        ami           = local.ami_windows_2019
        instance_type = "t2.medium"
        private_ip    = "${var.ip_range}.21"
        password      = "Admin123!"
        role          = "FileServer"
      }
    }
  }

  # Get VM config for selected lab
  selected_vms = lookup(local.vm_configs, var.lab_type, {})
}

# =============================================================================
# SSH KEYS
# =============================================================================

# SSH key for jumpbox
resource "tls_private_key" "jumpbox_ssh" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

# SSH key for Windows VMs
resource "tls_private_key" "windows_ssh" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

# AWS Key Pairs
resource "aws_key_pair" "jumpbox" {
  key_name   = "${var.project_name}-${local.lab_identifier}-jumpbox-key"
  public_key = tls_private_key.jumpbox_ssh.public_key_openssh

  tags = merge(var.tags, {
    Name = "${var.project_name}-${local.lab_identifier}-jumpbox-key"
    Lab  = local.lab_identifier
  })
}

resource "aws_key_pair" "windows" {
  key_name   = "${var.project_name}-${local.lab_identifier}-windows-key"
  public_key = tls_private_key.windows_ssh.public_key_openssh

  tags = merge(var.tags, {
    Name = "${var.project_name}-${local.lab_identifier}-windows-key"
    Lab  = local.lab_identifier
  })
}

