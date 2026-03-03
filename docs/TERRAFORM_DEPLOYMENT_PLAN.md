# Terraform Deployment Implementation Plan

## Overview

This document outlines the technical plan to update Terraform to support three deployment modes:
1. **Full C2 Infrastructure** - Internet-facing C2 with redirectors, bastion
2. **GOAD + Cobalt Strike** - Training labs with CS on jumpbox
3. **Full C2 + GOAD** - Combined deployment with VPC peering

---

## Current State

### Our Terraform (`/terraform/`)
```
terraform/
├── main.tf              # Orchestrates modules
├── variables.tf         # Input variables
├── outputs.tf           # Output values
└── modules/
    ├── vpc/             # VPC, subnets, NAT
    ├── security/        # Security groups
    ├── c2_team_server/  # C2 server instances
    ├── proxy_redirector/# Redirector instances
    └── bastion/         # Windows bastion host
```

**Supports:**
- ✅ C2 modes: single, redundancy, phases
- ✅ Redirectors, bastion
- ❌ GOAD deployment
- ❌ Deployment type selection

### GOAD's Terraform (`/tools/goad/template/provider/aws/`)
```
template/provider/aws/
├── main.tf              # Provider config
├── network.tf           # VPC, subnets, security groups
├── jumpbox.tf           # Ubuntu jumpbox
├── windows.tf           # Windows VM template
├── linux.tf             # Linux VM template
├── variables.tf         # Variables
└── outputs.tf           # Outputs
```

**Supports:**
- ✅ GOAD lab VMs
- ✅ Jumpbox with SSH
- ❌ Cobalt Strike installation
- ❌ Integration with our C2

---

## Target Architecture

### Mode 1: Full C2 Infrastructure (`c2-adhoc`, `c2-purple`, `c2-full`)

```
┌─────────────────────────────────────────────────────────────────┐
│                         AWS VPC                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Public Subnets                         │   │
│  │   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │   │
│  │   │ Redirector1 │    │ Redirector2 │    │   Bastion   │  │   │
│  │   │  (Public)   │    │  (Public)   │    │  (Windows)  │  │   │
│  │   └──────┬──────┘    └──────┬──────┘    └─────────────┘  │   │
│  └──────────┼──────────────────┼────────────────────────────┘   │
│             │                  │                                 │
│  ┌──────────┼──────────────────┼────────────────────────────┐   │
│  │          ▼    Private Subnets    ▼                        │   │
│  │   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │   │
│  │   │ C2 Server 1 │    │ C2 Server 2 │    │ C2 Server 3 │  │   │
│  │   │  (Private)  │    │  (Private)  │    │  (Private)  │  │   │
│  │   └─────────────┘    └─────────────┘    └─────────────┘  │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘

Components deployed: VPC, Security Groups, C2 Servers, Redirectors, Bastion
Requires: Domain configuration, Cobalt Strike file
```

### Mode 2: GOAD + Cobalt Strike (`goad-*`)

```
┌─────────────────────────────────────────────────────────────────┐
│                      GOAD AWS VPC                                │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Public Subnet                          │   │
│  │   ┌─────────────────────────────────────────────────────┐│   │
│  │   │              Jumpbox + Cobalt Strike                 ││   │
│  │   │  • Ubuntu Server (t2.medium)                        ││   │
│  │   │  • Cobalt Strike Team Server (port 50050)           ││   │
│  │   │  • SSH access to all GOAD VMs                       ││   │
│  │   │  • Public IP for operator access                    ││   │
│  │   └─────────────────────────────────────────────────────┘│   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│  ┌───────────────────────────┼──────────────────────────────┐   │
│  │          Private Subnet   │                               │   │
│  │   ┌─────────────┐    ┌────┴────┐    ┌─────────────┐      │   │
│  │   │    DC01     │    │  DC02   │    │    DC03     │      │   │
│  │   │  (Win2019)  │    │(Win2019)│    │  (Win2016)  │      │   │
│  │   └─────────────┘    └─────────┘    └─────────────┘      │   │
│  │   ┌─────────────┐    ┌─────────────┐                     │   │
│  │   │   SRV02     │    │    SRV03    │                     │   │
│  │   │  (Win2019)  │    │  (Win2016)  │                     │   │
│  │   └─────────────┘    └─────────────┘                     │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘

Components deployed: GOAD VPC, GOAD VMs, Jumpbox with CS installed
Requires: Cobalt Strike file (no domain needed)
Operator connects: Directly to jumpbox:50050
```

### Mode 3: Full C2 + GOAD (`combined-*`)

```
┌─────────────────────────────────────────────────────────────────┐
│                       C2 VPC (10.0.0.0/16)                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │   │
│  │   │ Redirector1 │    │ Redirector2 │    │   Bastion   │  │   │
│  │   └──────┬──────┘    └──────┬──────┘    └─────────────┘  │   │
│  │          │                  │                             │   │
│  │   ┌──────┴──────────────────┴──────┐                     │   │
│  │   │         C2 Servers             │                     │   │
│  │   └────────────────────────────────┘                     │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────────────┘
                          │ VPC Peering
┌─────────────────────────┴───────────────────────────────────────┐
│                      GOAD VPC (192.168.0.0/16)                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │   ┌─────────────┐                                        │   │
│  │   │   Jumpbox   │  (No CS - just lab management)         │   │
│  │   └─────────────┘                                        │   │
│  │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │   │
│  │   │    DC01     │  │    DC02     │  │    DC03     │     │   │
│  │   └─────────────┘  └─────────────┘  └─────────────┘     │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘

Components: Full C2 infra + GOAD lab with VPC peering
Beacons: Route through redirectors (realistic)
Operator: Connects via bastion SSH tunnel
```

---

## VPC Architecture Decision

### Analysis: Our VPC vs GOAD's VPC

| Feature | Our VPC (`modules/vpc/`) | GOAD VPC (`network.tf`) |
|---------|--------------------------|-------------------------|
| **CIDR** | Configurable (default 10.0.0.0/16) | /24 network (e.g., 192.168.56.0/24) |
| **Subnets** | Multiple public + private | 1 public (/26) + 1 private (/26) |
| **NAT Gateway** | Optional | Always created |
| **Internet Gateway** | Yes | Yes |
| **Security Groups** | Separate per component | Single shared SG |
| **Key Pairs** | Uses existing key pair | Generates new TLS keys |

### Decision: **Separate VPCs with Peering for Combined Mode**

**Rationale:**
1. **Isolation** - GOAD is intentionally vulnerable; keeping it separate protects C2 infra
2. **Simplicity** - Don't need to modify GOAD's networking logic
3. **Flexibility** - Can destroy GOAD without affecting C2
4. **Realistic** - Mirrors real engagement where target network is separate

### VPC CIDR Allocation

| Mode | VPC | CIDR | Notes |
|------|-----|------|-------|
| **C2-Only** | C2 VPC | 10.0.0.0/16 | Standard |
| **GOAD-Only** | GOAD VPC | 192.168.56.0/24 | GOAD default |
| **Combined** | C2 VPC | 10.0.0.0/16 | C2 infrastructure |
| **Combined** | GOAD VPC | 192.168.57.0/24 | Different from default to avoid conflicts |

### Network Flow by Mode

#### GOAD-Only Mode
```
Internet ──► Jumpbox (Public IP) ──► GOAD VMs (Private)
                │
                └── CS Team Server (port 50050)
                
Operator: Direct connection to jumpbox public IP
```

#### C2-Only Mode  
```
Internet ──► Redirectors (Public) ──► C2 Servers (Private)
                                            │
Operator ──► Bastion (Public) ─────────────┘
             via SSH tunnel
```

#### Combined Mode
```
Internet ──► Redirectors (Public) ──► C2 Servers (Private)
                                            │
                                      VPC Peering
                                            │
                                      GOAD VMs (Private)
                                            │
Operator ──► Bastion (Public) ──► Jumpbox ──┘
```

---

## GOAD Integration Strategy

### Challenge: GOAD Uses Jinja Templates

GOAD's Terraform files contain Jinja-style placeholders:
- `{{lab_identifier}}` - Lab name (e.g., "goad-light")
- `{{lab_name}}` - Display name (e.g., "GOAD-Light")
- `{{ip_range}}` - Network prefix (e.g., "192.168.56")
- `{{config.get_value(...)}}` - Config values

**These must be processed BEFORE Terraform runs.**

### Solution: Template Processing Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Deployment Flow                               │
│                                                                      │
│  1. User selects "GOAD Light + CS" in Web UI                        │
│                    │                                                 │
│                    ▼                                                 │
│  2. Backend processes GOAD templates                                │
│     - Reads tools/goad/ad/GOAD-Light/providers/aws/*.tf             │
│     - Replaces {{placeholders}} with actual values                  │
│     - Writes to terraform/modules/goad/generated/                   │
│                    │                                                 │
│                    ▼                                                 │
│  3. Terraform runs with processed files                             │
│     - Our main.tf calls module "goad" { source = "./modules/goad" } │
│     - GOAD module uses the generated .tf files                      │
│                    │                                                 │
│                    ▼                                                 │
│  4. Post-Terraform: Ansible provisioning (async)                    │
│     - Runs on jumpbox                                               │
│     - Configures AD domains                                         │
│     - Takes 30-60 minutes                                           │
└─────────────────────────────────────────────────────────────────────┘
```

### Template Processor

**File: `webapp/backend/utils/goad_template_processor.py`**

```python
import os
import glob
import shutil

# GOAD lab configurations
GOAD_LABS = {
    'GOAD-Mini': {
        'source_dir': 'tools/goad/ad/GOAD-Mini/providers/aws',
        'ip_range': '192.168.56',
        'lab_identifier': 'goad-mini',
    },
    'GOAD-Light': {
        'source_dir': 'tools/goad/ad/GOAD-Light/providers/aws',
        'ip_range': '192.168.56',
        'lab_identifier': 'goad-light',
    },
    'SCCM': {
        'source_dir': 'tools/goad/ad/SCCM/providers/aws',
        'ip_range': '192.168.56',
        'lab_identifier': 'sccm',
    },
    'GOAD': {
        'source_dir': 'tools/goad/ad/GOAD/providers/aws',
        'ip_range': '192.168.56',
        'lab_identifier': 'goad',
    },
    'NHA': {
        'source_dir': 'tools/goad/ad/NHA/providers/aws',
        'ip_range': '192.168.56',
        'lab_identifier': 'nha',
    },
}

def process_goad_templates(lab_type: str, aws_region: str, aws_zone: str, 
                           ip_range: str = None, output_dir: str = None) -> str:
    """
    Process GOAD Jinja templates and output Terraform-ready files.
    
    Args:
        lab_type: GOAD lab type (e.g., 'GOAD-Light')
        aws_region: AWS region (e.g., 'us-east-1')
        aws_zone: AWS availability zone (e.g., 'us-east-1a')
        ip_range: Override IP range (default from GOAD_LABS)
        output_dir: Output directory (default: terraform/modules/goad/generated)
    
    Returns:
        Path to generated Terraform files
    """
    if lab_type not in GOAD_LABS:
        raise ValueError(f"Unknown GOAD lab type: {lab_type}")
    
    config = GOAD_LABS[lab_type]
    source_dir = config['source_dir']
    ip_range = ip_range or config['ip_range']
    lab_identifier = config['lab_identifier']
    
    output_dir = output_dir or 'terraform/modules/goad/generated'
    
    # Clear and recreate output directory
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    
    # Replacements
    replacements = {
        '{{lab_identifier}}': lab_identifier,
        '{{lab_name}}': lab_type,
        '{{ip_range}}': ip_range,
        "{{config.get_value('aws', 'aws_region', 'eu-west-3')}}": aws_region,
        "{{config.get_value('aws', 'aws_zone', 'eu-west-3c')}}": aws_zone,
    }
    
    # Process all .tf and .tpl files
    for pattern in ['*.tf', '*.tpl']:
        for src_file in glob.glob(os.path.join(source_dir, pattern)):
            filename = os.path.basename(src_file)
            
            with open(src_file, 'r') as f:
                content = f.read()
            
            # Apply replacements
            for placeholder, value in replacements.items():
                content = content.replace(placeholder, value)
            
            # Write to output
            dst_file = os.path.join(output_dir, filename)
            with open(dst_file, 'w') as f:
                f.write(content)
    
    return output_dir
```

---

## Cobalt Strike File Handling

### Challenge: Getting CS Archive to EC2 Instances

The CS archive needs to be available to EC2 instances during boot (user_data).

### Solution: S3 Upload with IAM Role

```
┌─────────────────────────────────────────────────────────────────────┐
│                     CS File Flow                                     │
│                                                                      │
│  1. User uploads cobaltstrike.tar.gz via Web UI                     │
│                    │                                                 │
│                    ▼                                                 │
│  2. Backend uploads to S3 bucket                                    │
│     s3://{project}-cs-files/cobaltstrike-{timestamp}.tar.gz         │
│                    │                                                 │
│                    ▼                                                 │
│  3. Terraform creates EC2 with IAM role                             │
│     - Role allows s3:GetObject from cs-files bucket                 │
│                    │                                                 │
│                    ▼                                                 │
│  4. EC2 user_data downloads from S3                                 │
│     aws s3 cp s3://bucket/cobaltstrike.tar.gz /tmp/                 │
│                    │                                                 │
│                    ▼                                                 │
│  5. Install script extracts and configures CS                       │
└─────────────────────────────────────────────────────────────────────┘
```

### Terraform Resources for S3

**File: `terraform/modules/cs_storage/main.tf`**

```hcl
# S3 bucket for CS files
resource "aws_s3_bucket" "cs_files" {
  bucket = "${var.project_name}-cs-files-${random_id.bucket_suffix.hex}"
  
  tags = var.tags
}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# Encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "cs_files" {
  bucket = aws_s3_bucket.cs_files.id
  
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block public access
resource "aws_s3_bucket_public_access_block" "cs_files" {
  bucket = aws_s3_bucket.cs_files.id
  
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle - delete files after 7 days
resource "aws_s3_bucket_lifecycle_configuration" "cs_files" {
  bucket = aws_s3_bucket.cs_files.id
  
  rule {
    id     = "delete-old-files"
    status = "Enabled"
    
    expiration {
      days = 7
    }
  }
}

# IAM role for EC2 to access S3
resource "aws_iam_role" "cs_download" {
  name = "${var.project_name}-cs-download-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "cs_download" {
  name = "${var.project_name}-cs-download-policy"
  role = aws_iam_role.cs_download.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["s3:GetObject"]
      Resource = "${aws_s3_bucket.cs_files.arn}/*"
    }]
  })
}

resource "aws_iam_instance_profile" "cs_download" {
  name = "${var.project_name}-cs-download-profile"
  role = aws_iam_role.cs_download.name
}
```

### Backend Upload Function

**File: `webapp/backend/utils/s3_upload.py`**

```python
import boto3
import os
from datetime import datetime

def upload_cs_file(file_path: str, project_name: str, region: str) -> str:
    """
    Upload Cobalt Strike archive to S3.
    
    Returns:
        S3 URI (s3://bucket/key)
    """
    s3 = boto3.client('s3', region_name=region)
    
    # Find the bucket (created by Terraform)
    bucket_name = None
    for bucket in s3.list_buckets()['Buckets']:
        if bucket['Name'].startswith(f"{project_name}-cs-files-"):
            bucket_name = bucket['Name']
            break
    
    if not bucket_name:
        raise ValueError(f"CS files bucket not found for project: {project_name}")
    
    # Upload with timestamp
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    key = f"cobaltstrike-{timestamp}.tar.gz"
    
    s3.upload_file(file_path, bucket_name, key)
    
    return f"s3://{bucket_name}/{key}"
```

---

## Implementation Tasks

### Phase 1: Variable Updates

**File: `terraform/variables.tf`**

Add new variables:

```hcl
variable "deployment_type" {
  description = "Deployment type: 'c2-adhoc', 'c2-purple', 'c2-full', 'goad-mini', 'goad-full', 'combined-adhoc-mini', etc."
  type        = string
  default     = "c2-adhoc"
}

variable "goad_lab_type" {
  description = "GOAD lab type when deploying GOAD: 'GOAD-Mini', 'GOAD-Light', 'SCCM', 'GOAD', 'NHA'"
  type        = string
  default     = ""
}

variable "enable_goad" {
  description = "Enable GOAD lab deployment"
  type        = bool
  default     = false
}

variable "goad_vpc_cidr" {
  description = "CIDR block for GOAD VPC (only for combined mode)"
  type        = string
  default     = "192.168.0.0/16"
}

variable "install_cs_on_jumpbox" {
  description = "Install Cobalt Strike on GOAD jumpbox (for GOAD-only mode)"
  type        = bool
  default     = false
}
```

### Phase 2: Locals for Mode Detection

**File: `terraform/main.tf`**

Add deployment mode detection:

```hcl
locals {
  # Parse deployment type
  is_c2_only = startswith(var.deployment_type, "c2-")
  is_goad_only = startswith(var.deployment_type, "goad-")
  is_combined = startswith(var.deployment_type, "combined-")
  
  # Determine what to deploy
  deploy_c2_infra = local.is_c2_only || local.is_combined
  deploy_goad = local.is_goad_only || local.is_combined
  deploy_redirectors = local.is_c2_only || local.is_combined
  deploy_bastion = local.is_c2_only || local.is_combined
  install_cs_on_jumpbox = local.is_goad_only  # Only for GOAD-only mode
  
  # Map deployment type to GOAD lab
  goad_lab_map = {
    "goad-mini"    = "GOAD-Mini"
    "goad-light"   = "GOAD-Light"
    "goad-sccm"    = "SCCM"
    "goad-full"    = "GOAD"
    "goad-nha"     = "NHA"
    "combined-adhoc-mini"  = "GOAD-Mini"
    "combined-adhoc-light" = "GOAD-Light"
    "combined-full-full"   = "GOAD"
  }
  
  goad_lab_type = lookup(local.goad_lab_map, var.deployment_type, "")
  
  # Map deployment type to C2 mode
  c2_mode_map = {
    "c2-adhoc"  = "single"
    "c2-purple" = "redundancy"
    "c2-full"   = "phases"
    "combined-adhoc-mini"  = "single"
    "combined-adhoc-light" = "single"
    "combined-full-full"   = "phases"
  }
  
  c2_deployment_mode = lookup(local.c2_mode_map, var.deployment_type, "single")
}
```

### Phase 3: Conditional Module Loading

**File: `terraform/main.tf`**

Update module counts:

```hcl
# C2 Team Server - only for C2 and combined modes
module "c2_team_server" {
  count = local.deploy_c2_infra && (local.c2_deployment_mode == "single" || local.c2_deployment_mode == "redundancy") ? 1 : 0
  # ... existing config
}

# Proxy Redirectors - only for C2 and combined modes
module "proxy_redirector" {
  count = local.deploy_redirectors ? 1 : 0
  # ... existing config
}

# Bastion - only for C2 and combined modes
module "bastion" {
  count = local.deploy_bastion && var.enable_bastion ? 1 : 0
  # ... existing config
}

# GOAD Lab - for GOAD-only and combined modes
module "goad" {
  count = local.deploy_goad ? 1 : 0
  source = "./modules/goad"
  
  lab_type              = local.goad_lab_type
  vpc_cidr              = local.is_combined ? var.goad_vpc_cidr : var.vpc_cidr
  install_cobalt_strike = local.install_cs_on_jumpbox
  cobalt_strike_archive = var.cobalt_strike_archive_path
  management_cidr_blocks = var.management_cidr_blocks
  key_pair_name         = var.key_pair_name
  project_name          = var.project_name
  environment           = var.environment
  tags                  = local.enhanced_tags
}

# VPC Peering - only for combined mode
module "vpc_peering" {
  count = local.is_combined ? 1 : 0
  source = "./modules/vpc_peering"
  
  c2_vpc_id            = module.vpc.vpc_id
  goad_vpc_id          = module.goad[0].vpc_id
  c2_route_table_ids   = module.vpc.private_route_table_ids
  goad_route_table_ids = module.goad[0].route_table_ids
  c2_cidr              = var.vpc_cidr
  goad_cidr            = var.goad_vpc_cidr
  tags                 = local.enhanced_tags
}
```

### Phase 4: New GOAD Module

**Create: `terraform/modules/goad/`**

```
modules/goad/
├── main.tf           # Main GOAD deployment
├── variables.tf      # Input variables
├── outputs.tf        # Outputs (VPC ID, jumpbox IP, etc.)
├── jumpbox.tf        # Jumpbox with optional CS
├── network.tf        # GOAD VPC and subnets
├── security.tf       # Security groups
└── scripts/
    └── install_cs.sh # Cobalt Strike installation script
```

---

## Centralized Cobalt Strike Setup (CRITICAL)

### Existing C2 Server Setup

We already have a centralized Cobalt Strike installation script used by the C2 team server module. This script:

1. **Downloads CS archive** from uploaded file
2. **Clones tools repo** (`harr-sudo/red-team-tools`)
3. **Installs dependencies** (Java, etc.)
4. **Configures team server** with password
5. **Sets up systemd service** for auto-start

**Location**: `terraform/modules/c2_team_server/` (user_data or provisioner)

### Reusing for GOAD Jumpbox

For GOAD-only deployments, the jumpbox needs the **same CS setup**. We will:

1. **Extract the CS setup into a shared script** at `terraform/scripts/install_cobalt_strike.sh`
2. **Reference from both modules**:
   - `modules/c2_team_server/` - existing C2 servers
   - `modules/goad/jumpbox.tf` - GOAD jumpbox (when `install_cobalt_strike = true`)

### Shared Script Structure

**File: `terraform/scripts/install_cobalt_strike.sh`**

```bash
#!/bin/bash
# Centralized Cobalt Strike Installation Script
# Used by: C2 Team Servers, GOAD Jumpbox (training mode)

set -e

# Variables passed via templatefile()
CS_ARCHIVE_PATH="${cs_archive_path}"
CS_PASSWORD="${cs_password}"
TOOLS_REPO_URL="${tools_repo_url}"
TOOLS_REPO_BRANCH="${tools_repo_branch}"

echo "=== Installing Cobalt Strike ==="

# 1. Install dependencies
apt-get update
apt-get install -y openjdk-11-jdk git unzip

# 2. Create CS directory
mkdir -p /opt/cobaltstrike
cd /opt/cobaltstrike

# 3. Download and extract CS archive
aws s3 cp "$CS_ARCHIVE_PATH" /tmp/cobaltstrike.tar.gz
tar -xzf /tmp/cobaltstrike.tar.gz -C /opt/cobaltstrike --strip-components=1

# 4. Clone tools repository
if [ -n "$TOOLS_REPO_URL" ]; then
    echo "=== Cloning tools repository ==="
    git clone --branch "$TOOLS_REPO_BRANCH" "$TOOLS_REPO_URL" /opt/tools
fi

# 5. Create systemd service for team server
cat > /etc/systemd/system/teamserver.service << 'EOF'
[Unit]
Description=Cobalt Strike Team Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/cobaltstrike
ExecStart=/opt/cobaltstrike/teamserver 0.0.0.0 ${cs_password}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 6. Enable and start service
systemctl daemon-reload
systemctl enable teamserver
systemctl start teamserver

echo "=== Cobalt Strike Installation Complete ==="
echo "Team server running on port 50050"
```

### Module Usage

**C2 Team Server Module** (`modules/c2_team_server/main.tf`):

```hcl
resource "aws_instance" "c2_server" {
  # ... existing config ...
  
  user_data = templatefile("${path.root}/scripts/install_cobalt_strike.sh", {
    cs_archive_path   = var.cobalt_strike_archive
    cs_password       = var.cs_teamserver_password
    tools_repo_url    = var.tools_repo_url
    tools_repo_branch = var.tools_repo_branch
  })
}
```

**GOAD Jumpbox** (`modules/goad/jumpbox.tf`):

```hcl
resource "aws_instance" "jumpbox" {
  # ... existing config ...
  
  # Use same centralized script when CS is enabled
  user_data = var.install_cobalt_strike ? templatefile("${path.root}/scripts/install_cobalt_strike.sh", {
    cs_archive_path   = var.cobalt_strike_archive
    cs_password       = var.cs_teamserver_password
    tools_repo_url    = var.tools_repo_url
    tools_repo_branch = var.tools_repo_branch
  }) : templatefile("${path.module}/scripts/jumpbox_basic.sh", {})
}
```

### Key Benefits

1. **Single source of truth** - One script to maintain
2. **Consistent setup** - Same CS config across all deployment types
3. **Tools repo included** - All deployments get the tools repo
4. **Easy updates** - Change once, applies everywhere
5. **Future extensibility** - Add more tools to the script, all deployments benefit

### Variables Required

Both modules need access to these variables:

```hcl
variable "cobalt_strike_archive" {
  description = "S3 path or local path to CS archive"
  type        = string
}

variable "cs_teamserver_password" {
  description = "Password for CS team server"
  type        = string
  sensitive   = true
}

variable "tools_repo_url" {
  description = "Git URL for tools repository"
  type        = string
  default     = "https://github.com/harr-sudo/red-team-tools.git"
}

variable "tools_repo_branch" {
  description = "Branch to clone from tools repo"
  type        = string
  default     = "main"
}
```

---

### Phase 5: VPC Peering Module

**Create: `terraform/modules/vpc_peering/`**

```hcl
# modules/vpc_peering/main.tf

resource "aws_vpc_peering_connection" "c2_to_goad" {
  vpc_id        = var.c2_vpc_id
  peer_vpc_id   = var.goad_vpc_id
  auto_accept   = true
  
  tags = merge(var.tags, {
    Name = "${var.project_name}-c2-to-goad-peering"
  })
}

# Update C2 route tables to reach GOAD
resource "aws_route" "c2_to_goad" {
  count                     = length(var.c2_route_table_ids)
  route_table_id            = var.c2_route_table_ids[count.index]
  destination_cidr_block    = var.goad_cidr
  vpc_peering_connection_id = aws_vpc_peering_connection.c2_to_goad.id
}

# Update GOAD route tables to reach C2
resource "aws_route" "goad_to_c2" {
  count                     = length(var.goad_route_table_ids)
  route_table_id            = var.goad_route_table_ids[count.index]
  destination_cidr_block    = var.c2_cidr
  vpc_peering_connection_id = aws_vpc_peering_connection.c2_to_goad.id
}
```

### Phase 6: Backend Updates

**File: `webapp/backend/utils/config_parser.py`**

Update to handle `deployment_type`:

```python
# Map web app deployment type to Terraform variables
DEPLOYMENT_TYPE_MAP = {
    'c2-adhoc': {'deploy_c2': True, 'deploy_goad': False, 'c2_mode': 'single'},
    'c2-purple': {'deploy_c2': True, 'deploy_goad': False, 'c2_mode': 'redundancy'},
    'c2-full': {'deploy_c2': True, 'deploy_goad': False, 'c2_mode': 'phases'},
    'goad-mini': {'deploy_c2': False, 'deploy_goad': True, 'goad_lab': 'GOAD-Mini'},
    # ... etc
}
```

### Phase 7: Security Group Updates for VPC Peering

**File: `terraform/modules/security/main.tf`**

Add rules to allow traffic between VPCs in combined mode:

```hcl
# Allow C2 servers to reach GOAD VMs (combined mode only)
resource "aws_security_group_rule" "c2_to_goad_egress" {
  count = var.enable_vpc_peering ? 1 : 0
  
  type              = "egress"
  from_port         = 0
  to_port           = 65535
  protocol          = "tcp"
  cidr_blocks       = [var.goad_vpc_cidr]
  security_group_id = aws_security_group.c2_team_server.id
  description       = "Allow C2 to reach GOAD VMs via VPC peering"
}

# Allow GOAD VMs to receive beacon callbacks from C2
resource "aws_security_group_rule" "goad_from_c2_ingress" {
  count = var.enable_vpc_peering ? 1 : 0
  
  type              = "ingress"
  from_port         = 0
  to_port           = 65535
  protocol          = "tcp"
  cidr_blocks       = [var.c2_vpc_cidr]
  security_group_id = var.goad_security_group_id
  description       = "Allow traffic from C2 VPC"
}

# Allow bastion to SSH to GOAD jumpbox
resource "aws_security_group_rule" "bastion_to_goad_jumpbox" {
  count = var.enable_vpc_peering ? 1 : 0
  
  type              = "egress"
  from_port         = 22
  to_port           = 22
  protocol          = "tcp"
  cidr_blocks       = [var.goad_vpc_cidr]
  security_group_id = aws_security_group.bastion.id
  description       = "Allow bastion SSH to GOAD jumpbox"
}
```

### Phase 8: GOAD Ansible Provisioning

After Terraform deploys the GOAD VMs, Ansible configures Active Directory. This is a **critical step** that takes 30-60 minutes.

#### Provisioning Strategy

```
┌─────────────────────────────────────────────────────────────────────┐
│                  GOAD Ansible Provisioning Flow                      │
│                                                                      │
│  1. Terraform deploys VMs (5-10 minutes)                            │
│                    │                                                 │
│                    ▼                                                 │
│  2. Terraform outputs VM IPs                                        │
│                    │                                                 │
│                    ▼                                                 │
│  3. Backend generates Ansible inventory from outputs                │
│                    │                                                 │
│                    ▼                                                 │
│  4. Backend triggers Ansible on jumpbox (async)                     │
│     - SSH to jumpbox                                                │
│     - Run: ansible-playbook -i inventory main.yml                   │
│                    │                                                 │
│                    ▼                                                 │
│  5. UI shows "Provisioning in progress..." (30-60 mins)             │
│     - Poll /api/deploy/goad-status for progress                     │
│                    │                                                 │
│                    ▼                                                 │
│  6. Ansible completes - AD domains configured                       │
│     - UI shows "Ready" with credentials                             │
└─────────────────────────────────────────────────────────────────────┘
```

#### Terraform Provisioner (Optional - Run Ansible Automatically)

**File: `terraform/modules/goad/provisioner.tf`**

```hcl
# Wait for jumpbox to be ready
resource "null_resource" "wait_for_jumpbox" {
  depends_on = [aws_instance.jumpbox, aws_eip.jumpbox]
  
  provisioner "remote-exec" {
    connection {
      type        = "ssh"
      host        = aws_eip.jumpbox.public_ip
      user        = "ubuntu"
      private_key = tls_private_key.ssh.private_key_pem
      timeout     = "5m"
    }
    
    inline = ["echo 'Jumpbox is ready'"]
  }
}

# Run GOAD Ansible provisioning (async - runs in background)
resource "null_resource" "goad_ansible" {
  count      = var.auto_provision ? 1 : 0
  depends_on = [null_resource.wait_for_jumpbox, aws_instance.goad_vms]
  
  connection {
    type        = "ssh"
    host        = aws_eip.jumpbox.public_ip
    user        = "ubuntu"
    private_key = tls_private_key.ssh.private_key_pem
  }
  
  # Copy GOAD ansible files to jumpbox
  provisioner "file" {
    source      = "${path.module}/ansible/"
    destination = "/home/ubuntu/goad-ansible"
  }
  
  # Run ansible in background with nohup
  provisioner "remote-exec" {
    inline = [
      "cd /home/ubuntu/goad-ansible",
      "chmod +x run_provisioning.sh",
      "nohup ./run_provisioning.sh > /var/log/goad-provision.log 2>&1 &",
      "echo 'Ansible provisioning started in background'",
      "echo 'Check /var/log/goad-provision.log for progress'"
    ]
  }
}
```

#### Backend Status Endpoint

**File: `webapp/backend/routes/deploy.py`**

```python
@deploy_bp.route('/goad-status', methods=['GET'])
def get_goad_provisioning_status():
    """Check GOAD Ansible provisioning status."""
    try:
        # Get jumpbox IP from Terraform outputs
        result = subprocess.run(
            ['terraform', 'output', '-json', 'goad_jumpbox_public_ip'],
            cwd=TERRAFORM_DIR,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            return jsonify({'status': 'unknown', 'error': 'No GOAD deployment found'})
        
        jumpbox_ip = json.loads(result.stdout).get('value')
        if not jumpbox_ip:
            return jsonify({'status': 'not_deployed'})
        
        # SSH to jumpbox and check provisioning status
        ssh_key_path = get_ssh_key_path()  # Get from config
        
        check_cmd = f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=no ubuntu@{jumpbox_ip} 'cat /var/log/goad-provision.log | tail -20'"
        check_result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
        
        log_output = check_result.stdout
        
        # Parse status from log
        if 'PLAY RECAP' in log_output and 'failed=0' in log_output:
            status = 'completed'
        elif 'PLAY RECAP' in log_output:
            status = 'failed'
        elif 'TASK' in log_output:
            status = 'in_progress'
        else:
            status = 'pending'
        
        return jsonify({
            'status': status,
            'jumpbox_ip': jumpbox_ip,
            'log_tail': log_output
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)})
```

---

## Deployment Manager UI - Access Details Display

The Deployment Manager page must clearly display all connection information, IP addresses, and credentials after deployment. This is **critical** for usability.

### Required Terraform Outputs

**File: `terraform/outputs.tf`**

```hcl
# =============================================================================
# Deployment Type Output (CRITICAL - needed by UI)
# =============================================================================

output "deployment_type" {
  description = "The deployment type that was used"
  value       = var.deployment_type
}

# =============================================================================
# C2 Infrastructure Outputs (for C2-only and Combined modes)
# =============================================================================

output "c2_server_private_ip" {
  description = "C2 team server private IP"
  value       = local.deploy_c2_infra ? module.c2_team_server[0].private_ip : null
}

output "c2_server_public_ip" {
  description = "C2 team server public IP (if direct access enabled)"
  value       = local.deploy_c2_infra ? module.c2_team_server[0].public_ip : null
}

output "redirector_public_ips" {
  description = "Public IPs of proxy redirectors"
  value       = local.deploy_redirectors ? module.proxy_redirector[0].public_ips : []
}

output "bastion_public_ip" {
  description = "Windows bastion public IP"
  value       = local.deploy_bastion ? module.bastion[0].public_ip : null
}

output "bastion_password" {
  description = "Windows bastion administrator password"
  value       = local.deploy_bastion ? module.bastion[0].admin_password : null
  sensitive   = true
}

# =============================================================================
# GOAD Lab Outputs (for GOAD-only and Combined modes)
# =============================================================================

output "goad_jumpbox_public_ip" {
  description = "GOAD jumpbox public IP (for SSH and CS client connection)"
  value       = local.deploy_goad ? module.goad[0].jumpbox_public_ip : null
}

output "goad_jumpbox_private_ip" {
  description = "GOAD jumpbox private IP"
  value       = local.deploy_goad ? module.goad[0].jumpbox_private_ip : null
}

output "goad_lab_vms" {
  description = "GOAD lab VM details (hostname, IP, role)"
  value       = local.deploy_goad ? module.goad[0].lab_vms : []
}

output "goad_domain_info" {
  description = "GOAD domain information"
  value       = local.deploy_goad ? module.goad[0].domain_info : null
}

output "goad_credentials" {
  description = "GOAD lab default credentials"
  value       = local.deploy_goad ? module.goad[0].credentials : null
  sensitive   = true
}

# =============================================================================
# Cobalt Strike Connection Info
# =============================================================================

output "cs_connection_info" {
  description = "How to connect Cobalt Strike client"
  value = {
    host     = local.is_goad_only ? module.goad[0].jumpbox_public_ip : (local.deploy_c2_infra ? module.c2_team_server[0].private_ip : null)
    port     = 50050
    method   = local.is_goad_only ? "direct" : "ssh_tunnel"
    password = var.cs_teamserver_password
  }
  sensitive = true
}

# =============================================================================
# Access Instructions (Human-readable)
# =============================================================================

output "access_instructions" {
  description = "Step-by-step access instructions for the deployment"
  value = local.is_goad_only ? {
    type = "goad-only"
    steps = [
      "1. Connect Cobalt Strike client to ${module.goad[0].jumpbox_public_ip}:50050",
      "2. Use password configured during deployment",
      "3. SSH to jumpbox: ssh -i <key> ubuntu@${module.goad[0].jumpbox_public_ip}",
      "4. From jumpbox, access GOAD VMs via internal IPs"
    ]
  } : local.is_combined ? {
    type = "combined"
    steps = [
      "1. RDP to bastion: ${module.bastion[0].public_ip}",
      "2. SSH tunnel through bastion to C2 server",
      "3. Connect CS client through tunnel to ${module.c2_team_server[0].private_ip}:50050",
      "4. SSH to GOAD jumpbox: ${module.goad[0].jumpbox_public_ip}",
      "5. GOAD VMs accessible via VPC peering"
    ]
  } : {
    type = "c2-only"
    steps = [
      "1. RDP to bastion: ${module.bastion[0].public_ip}",
      "2. SSH tunnel: ssh -L 50050:${module.c2_team_server[0].private_ip}:50050 -i <key> ubuntu@bastion",
      "3. Connect CS client to localhost:50050",
      "4. Redirectors available at: ${join(", ", module.proxy_redirector[0].public_ips)}"
    ]
  }
}
```

### Deployment Manager Page Updates

**File: `webapp/frontend/index.html`** - Add deployment details section:

```html
<!-- Deployment Details Panel (shown after successful deployment) -->
<div id="deployment-details" style="display: none;">
    
    <!-- Connection Quick Reference -->
    <div class="card" style="margin-bottom: 20px; border: 2px solid #4caf50;">
        <h3>🔗 Quick Connect</h3>
        <div id="quick-connect-info">
            <!-- Dynamically populated based on deployment type -->
        </div>
    </div>
    
    <!-- Cobalt Strike Connection -->
    <div class="card" style="margin-bottom: 20px;">
        <h3>🎯 Cobalt Strike Connection</h3>
        <table class="info-table">
            <tr>
                <td><strong>Host:</strong></td>
                <td id="cs-host">-</td>
                <td><button onclick="copyToClipboard('cs-host')">📋 Copy</button></td>
            </tr>
            <tr>
                <td><strong>Port:</strong></td>
                <td id="cs-port">50050</td>
                <td><button onclick="copyToClipboard('cs-port')">📋 Copy</button></td>
            </tr>
            <tr>
                <td><strong>Password:</strong></td>
                <td id="cs-password">••••••••</td>
                <td>
                    <button onclick="togglePassword('cs-password')">👁️ Show</button>
                    <button onclick="copyToClipboard('cs-password')">📋 Copy</button>
                </td>
            </tr>
            <tr>
                <td><strong>Connection Method:</strong></td>
                <td id="cs-method">-</td>
                <td></td>
            </tr>
        </table>
    </div>
    
    <!-- Infrastructure IPs -->
    <div class="card" style="margin-bottom: 20px;">
        <h3>🖥️ Infrastructure IPs</h3>
        <div id="infra-ips-section">
            <!-- C2 Server (if deployed) -->
            <div id="c2-server-info" style="display: none;">
                <h4>C2 Team Server</h4>
                <table class="info-table">
                    <tr>
                        <td>Private IP:</td>
                        <td id="c2-private-ip">-</td>
                        <td><button onclick="copyToClipboard('c2-private-ip')">📋</button></td>
                    </tr>
                    <tr>
                        <td>Public IP:</td>
                        <td id="c2-public-ip">-</td>
                        <td><button onclick="copyToClipboard('c2-public-ip')">📋</button></td>
                    </tr>
                </table>
            </div>
            
            <!-- Redirectors (if deployed) -->
            <div id="redirectors-info" style="display: none;">
                <h4>Redirectors</h4>
                <div id="redirector-list">
                    <!-- Dynamically populated -->
                </div>
            </div>
            
            <!-- Bastion (if deployed) -->
            <div id="bastion-info" style="display: none;">
                <h4>Windows Bastion</h4>
                <table class="info-table">
                    <tr>
                        <td>Public IP:</td>
                        <td id="bastion-ip">-</td>
                        <td><button onclick="copyToClipboard('bastion-ip')">📋</button></td>
                    </tr>
                    <tr>
                        <td>Username:</td>
                        <td>Administrator</td>
                        <td></td>
                    </tr>
                    <tr>
                        <td>Password:</td>
                        <td id="bastion-password">••••••••</td>
                        <td>
                            <button onclick="togglePassword('bastion-password')">👁️</button>
                            <button onclick="copyToClipboard('bastion-password')">📋</button>
                        </td>
                    </tr>
                </table>
            </div>
            
            <!-- GOAD Jumpbox (if deployed) -->
            <div id="goad-jumpbox-info" style="display: none;">
                <h4>GOAD Jumpbox</h4>
                <table class="info-table">
                    <tr>
                        <td>Public IP:</td>
                        <td id="jumpbox-public-ip">-</td>
                        <td><button onclick="copyToClipboard('jumpbox-public-ip')">📋</button></td>
                    </tr>
                    <tr>
                        <td>SSH Command:</td>
                        <td id="jumpbox-ssh-cmd">ssh -i key.pem ubuntu@IP</td>
                        <td><button onclick="copyToClipboard('jumpbox-ssh-cmd')">📋</button></td>
                    </tr>
                </table>
            </div>
        </div>
    </div>
    
    <!-- GOAD Lab VMs (if deployed) -->
    <div id="goad-vms-section" class="card" style="display: none; margin-bottom: 20px;">
        <h3>🏰 GOAD Lab VMs</h3>
        <table class="info-table" id="goad-vm-table">
            <thead>
                <tr>
                    <th>Hostname</th>
                    <th>Role</th>
                    <th>Private IP</th>
                    <th>Domain</th>
                </tr>
            </thead>
            <tbody id="goad-vm-list">
                <!-- Dynamically populated -->
            </tbody>
        </table>
    </div>
    
    <!-- GOAD Credentials (if deployed) -->
    <div id="goad-creds-section" class="card" style="display: none; margin-bottom: 20px;">
        <h3>🔐 GOAD Lab Credentials</h3>
        <div style="background: #fff3e0; padding: 15px; border-radius: 8px; margin-bottom: 15px;">
            <strong>⚠️ Default Lab Credentials</strong>
            <p style="margin: 5px 0 0 0; font-size: 0.9em;">These are intentionally weak for training purposes.</p>
        </div>
        <table class="info-table" id="goad-creds-table">
            <thead>
                <tr>
                    <th>Account</th>
                    <th>Username</th>
                    <th>Password</th>
                    <th></th>
                </tr>
            </thead>
            <tbody id="goad-creds-list">
                <!-- Dynamically populated -->
            </tbody>
        </table>
    </div>
    
    <!-- Step-by-Step Access Instructions -->
    <div class="card" style="margin-bottom: 20px; background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);">
        <h3>📋 Access Instructions</h3>
        <ol id="access-steps" style="margin: 0; padding-left: 20px; line-height: 2;">
            <!-- Dynamically populated based on deployment type -->
        </ol>
    </div>
    
</div>
```

### Backend API Endpoint

**File: `webapp/backend/routes/deploy.py`**

Add endpoint to fetch deployment details:

```python
@deploy_bp.route('/deployment-details', methods=['GET'])
def get_deployment_details():
    """Get all deployment details including IPs and credentials."""
    try:
        # Read Terraform outputs
        result = subprocess.run(
            ['terraform', 'output', '-json'],
            cwd=TERRAFORM_DIR,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            return jsonify({'error': 'Failed to get deployment details'}), 500
        
        outputs = json.loads(result.stdout)
        
        # Parse and structure the response
        deployment_type = outputs.get('deployment_type', {}).get('value', '')
        
        response = {
            'deployment_type': deployment_type,
            'cobalt_strike': {
                'host': outputs.get('cs_connection_info', {}).get('value', {}).get('host'),
                'port': 50050,
                'method': outputs.get('cs_connection_info', {}).get('value', {}).get('method'),
                'password': outputs.get('cs_connection_info', {}).get('value', {}).get('password')
            },
            'infrastructure': {
                'c2_server': {
                    'private_ip': outputs.get('c2_server_private_ip', {}).get('value'),
                    'public_ip': outputs.get('c2_server_public_ip', {}).get('value')
                },
                'redirectors': outputs.get('redirector_public_ips', {}).get('value', []),
                'bastion': {
                    'ip': outputs.get('bastion_public_ip', {}).get('value'),
                    'password': outputs.get('bastion_password', {}).get('value')
                }
            },
            'goad': {
                'jumpbox': {
                    'public_ip': outputs.get('goad_jumpbox_public_ip', {}).get('value'),
                    'private_ip': outputs.get('goad_jumpbox_private_ip', {}).get('value')
                },
                'vms': outputs.get('goad_lab_vms', {}).get('value', []),
                'domain_info': outputs.get('goad_domain_info', {}).get('value'),
                'credentials': outputs.get('goad_credentials', {}).get('value')
            },
            'access_instructions': outputs.get('access_instructions', {}).get('value', {})
        }
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
```

### JavaScript to Populate UI

**File: `webapp/frontend/js/app.js`**

```javascript
async function loadDeploymentDetails() {
    try {
        const response = await fetch('/api/deploy/deployment-details');
        const data = await response.json();
        
        if (data.error) {
            console.error('Failed to load deployment details:', data.error);
            return;
        }
        
        // Show the deployment details panel
        document.getElementById('deployment-details').style.display = 'block';
        
        // Populate Cobalt Strike connection
        document.getElementById('cs-host').textContent = data.cobalt_strike.host || '-';
        document.getElementById('cs-port').textContent = data.cobalt_strike.port;
        document.getElementById('cs-password').dataset.value = data.cobalt_strike.password || '';
        document.getElementById('cs-method').textContent = 
            data.cobalt_strike.method === 'direct' ? '🔗 Direct Connection' : '🔒 SSH Tunnel Required';
        
        // Populate infrastructure IPs based on what's deployed
        const deploymentType = data.deployment_type;
        const isGoadOnly = deploymentType.startsWith('goad-');
        const isCombined = deploymentType.startsWith('combined-');
        const isC2Only = deploymentType.startsWith('c2-');
        
        // C2 Server info
        if (isC2Only || isCombined) {
            document.getElementById('c2-server-info').style.display = 'block';
            document.getElementById('c2-private-ip').textContent = data.infrastructure.c2_server.private_ip || '-';
            document.getElementById('c2-public-ip').textContent = data.infrastructure.c2_server.public_ip || 'N/A (private only)';
        }
        
        // Redirectors
        if ((isC2Only || isCombined) && data.infrastructure.redirectors.length > 0) {
            document.getElementById('redirectors-info').style.display = 'block';
            const list = document.getElementById('redirector-list');
            list.innerHTML = data.infrastructure.redirectors.map((ip, i) => `
                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 5px;">
                    <span>Redirector ${i + 1}:</span>
                    <code id="redirector-${i}">${ip}</code>
                    <button onclick="copyToClipboard('redirector-${i}')">📋</button>
                </div>
            `).join('');
        }
        
        // Bastion
        if ((isC2Only || isCombined) && data.infrastructure.bastion.ip) {
            document.getElementById('bastion-info').style.display = 'block';
            document.getElementById('bastion-ip').textContent = data.infrastructure.bastion.ip;
            document.getElementById('bastion-password').dataset.value = data.infrastructure.bastion.password || '';
        }
        
        // GOAD Jumpbox
        if ((isGoadOnly || isCombined) && data.goad.jumpbox.public_ip) {
            document.getElementById('goad-jumpbox-info').style.display = 'block';
            document.getElementById('jumpbox-public-ip').textContent = data.goad.jumpbox.public_ip;
            document.getElementById('jumpbox-ssh-cmd').textContent = `ssh -i ~/.ssh/your-key.pem ubuntu@${data.goad.jumpbox.public_ip}`;
        }
        
        // GOAD VMs
        if ((isGoadOnly || isCombined) && data.goad.vms.length > 0) {
            document.getElementById('goad-vms-section').style.display = 'block';
            const vmList = document.getElementById('goad-vm-list');
            vmList.innerHTML = data.goad.vms.map(vm => `
                <tr>
                    <td><strong>${vm.hostname}</strong></td>
                    <td>${vm.role}</td>
                    <td><code>${vm.private_ip}</code></td>
                    <td>${vm.domain || '-'}</td>
                </tr>
            `).join('');
        }
        
        // GOAD Credentials
        if ((isGoadOnly || isCombined) && data.goad.credentials) {
            document.getElementById('goad-creds-section').style.display = 'block';
            const credsList = document.getElementById('goad-creds-list');
            credsList.innerHTML = Object.entries(data.goad.credentials).map(([account, creds]) => `
                <tr>
                    <td>${account}</td>
                    <td><code>${creds.username}</code></td>
                    <td>
                        <span class="password-field" data-value="${creds.password}">••••••••</span>
                    </td>
                    <td>
                        <button onclick="togglePassword(this.parentElement.previousElementSibling.querySelector('.password-field'))">👁️</button>
                    </td>
                </tr>
            `).join('');
        }
        
        // Access Instructions
        if (data.access_instructions && data.access_instructions.steps) {
            const stepsList = document.getElementById('access-steps');
            stepsList.innerHTML = data.access_instructions.steps.map(step => `<li>${step}</li>`).join('');
        }
        
        // Quick Connect summary
        updateQuickConnect(data);
        
    } catch (error) {
        console.error('Error loading deployment details:', error);
    }
}

function updateQuickConnect(data) {
    const quickConnect = document.getElementById('quick-connect-info');
    const deploymentType = data.deployment_type;
    
    let html = '';
    
    if (deploymentType.startsWith('goad-')) {
        // GOAD-only: Direct connection
        html = `
            <div style="background: #e8f5e9; padding: 15px; border-radius: 8px;">
                <h4 style="margin: 0 0 10px 0;">🎯 Connect Cobalt Strike Client</h4>
                <code style="font-size: 1.2em; background: #fff; padding: 10px; display: block; border-radius: 4px;">
                    ${data.cobalt_strike.host}:50050
                </code>
                <p style="margin: 10px 0 0 0; font-size: 0.9em;">Direct connection - no tunnel needed!</p>
            </div>
        `;
    } else if (deploymentType.startsWith('c2-') || deploymentType.startsWith('combined-')) {
        // C2 or Combined: SSH tunnel required
        html = `
            <div style="background: #fff3e0; padding: 15px; border-radius: 8px;">
                <h4 style="margin: 0 0 10px 0;">🔒 SSH Tunnel Required</h4>
                <p style="margin: 0 0 10px 0;">Step 1: Create tunnel through bastion</p>
                <code style="font-size: 0.9em; background: #fff; padding: 10px; display: block; border-radius: 4px; word-break: break-all;">
                    ssh -L 50050:${data.infrastructure.c2_server.private_ip}:50050 -i key.pem ubuntu@${data.infrastructure.bastion.ip}
                </code>
                <p style="margin: 10px 0 10px 0;">Step 2: Connect CS client to</p>
                <code style="font-size: 1.2em; background: #fff; padding: 10px; display: block; border-radius: 4px;">
                    localhost:50050
                </code>
            </div>
        `;
    }
    
    quickConnect.innerHTML = html;
}

// Utility functions
function copyToClipboard(elementId) {
    const element = document.getElementById(elementId);
    const text = element.dataset?.value || element.textContent;
    navigator.clipboard.writeText(text);
    
    // Visual feedback
    const originalText = element.textContent;
    element.textContent = '✓ Copied!';
    setTimeout(() => element.textContent = originalText, 1000);
}

function togglePassword(elementOrId) {
    const element = typeof elementOrId === 'string' 
        ? document.getElementById(elementOrId) 
        : elementOrId;
    
    if (element.textContent === '••••••••') {
        element.textContent = element.dataset.value;
    } else {
        element.textContent = '••••••••';
    }
}
```

### Summary of Deployment Manager Outputs

| Deployment Type | What's Displayed |
|-----------------|------------------|
| **GOAD-Only** | Jumpbox IP, CS direct connect, GOAD VMs, Lab credentials, SSH command |
| **C2-Only** | C2 server IP, Redirector IPs, Bastion IP/password, SSH tunnel command |
| **Combined** | All of the above + VPC peering info |

### Key UX Features

1. **Copy buttons** - One-click copy for IPs and commands
2. **Password toggle** - Show/hide sensitive credentials
3. **Quick Connect** - Prominent connection instructions
4. **Step-by-step guide** - Clear numbered instructions
5. **Visual grouping** - Organized by component type
6. **Context-aware** - Only shows relevant info for deployment type

---

## File Changes Summary

### Terraform Files

| File | Action | Description |
|------|--------|-------------|
| `terraform/variables.tf` | Modify | Add deployment_type, goad_lab_type, goad_vpc_cidr, cs vars |
| `terraform/main.tf` | Modify | Add locals for mode detection, conditional modules |
| `terraform/outputs.tf` | Modify | Add deployment_type, all IPs, credentials, access instructions |
| `terraform/scripts/install_cobalt_strike.sh` | Create | **Centralized CS setup script (shared by all)** |
| `terraform/modules/goad/` | Create | New GOAD deployment module |
| `terraform/modules/goad/main.tf` | Create | Main GOAD orchestration |
| `terraform/modules/goad/jumpbox.tf` | Create | Jumpbox with optional CS |
| `terraform/modules/goad/network.tf` | Create | GOAD VPC (from processed templates) |
| `terraform/modules/goad/provisioner.tf` | Create | Ansible provisioning trigger |
| `terraform/modules/goad/generated/` | Generated | Processed GOAD templates (runtime) |
| `terraform/modules/vpc_peering/` | Create | VPC peering for combined mode |
| `terraform/modules/cs_storage/` | Create | S3 bucket for CS files + IAM role |
| `terraform/modules/security/main.tf` | Modify | Add VPC peering security rules |
| `terraform/modules/c2_team_server/main.tf` | Modify | Use centralized CS script, IAM profile |

### Backend Files

| File | Action | Description |
|------|--------|-------------|
| `webapp/backend/utils/config_parser.py` | Modify | Handle deployment_type mapping |
| `webapp/backend/utils/goad_template_processor.py` | Create | Process GOAD Jinja templates |
| `webapp/backend/utils/s3_upload.py` | Create | Upload CS file to S3 |
| `webapp/backend/routes/deploy.py` | Modify | Add `/deployment-details`, `/goad-status` endpoints |

### Frontend Files

| File | Action | Description |
|------|--------|-------------|
| `webapp/frontend/index.html` | Modify | Add deployment details panel |
| `webapp/frontend/js/app.js` | Modify | Add `loadDeploymentDetails()`, status polling |

---

## Deployment Flow

### GOAD-Only Mode

```
1. User selects "GOAD Mini + CS" in web app
2. Backend sets:
   - deployment_type = "goad-mini"
   - enable_goad = true
   - install_cs_on_jumpbox = true
3. Terraform deploys:
   - GOAD VPC and subnets
   - GOAD Windows VMs
   - Jumpbox with Cobalt Strike
4. User connects CS client to jumpbox:50050
```

### Full C2 Mode

```
1. User selects "C2 Ad-Hoc" in web app
2. Backend sets:
   - deployment_type = "c2-adhoc"
   - enable_goad = false
3. Terraform deploys:
   - C2 VPC and subnets
   - C2 servers, redirectors, bastion
4. User connects via SSH tunnel through bastion
```

### Combined Mode

```
1. User selects "Full C2 + GOAD Mini" in web app
2. Backend sets:
   - deployment_type = "combined-adhoc-mini"
   - enable_goad = true
   - install_cs_on_jumpbox = false
3. Terraform deploys:
   - C2 VPC with full infrastructure
   - GOAD VPC with lab VMs
   - VPC peering between them
4. User connects via bastion, beacons route through redirectors
```

---

## Cost Estimates (Verified January 2026 from AWS Pricing Page)

### AWS EC2 Instance Pricing (US East Ohio, On-Demand)

**Linux Instances:**

| Instance Type | vCPU | Memory | Hourly | Monthly (730 hrs) |
|---------------|------|--------|--------|-------------------|
| t3.micro | 2 | 1 GB | $0.0104 | ~$8 |
| t3.small | 2 | 2 GB | $0.0208 | ~$15 |
| t3.medium | 2 | 4 GB | $0.0416 | ~$30 |
| t3.large | 2 | 8 GB | $0.0832 | ~$61 |
| t3.xlarge | 4 | 16 GB | $0.1664 | ~$121 |
| t3.2xlarge | 8 | 32 GB | $0.3328 | ~$243 |

**Windows Server Instances (GOAD VMs):**

| Instance Type | vCPU | Memory | Hourly | Monthly (730 hrs) |
|---------------|------|--------|--------|-------------------|
| t3.micro | 2 | 1 GB | $0.0196 | ~$14 |
| t3.small | 2 | 2 GB | $0.0392 | ~$29 |
| t3.medium | 2 | 4 GB | $0.0600 | ~$44 |
| t3.large | 2 | 8 GB | $0.1108 | ~$81 |
| t3.xlarge | 4 | 16 GB | $0.2400 | ~$175 |
| t3.2xlarge | 8 | 32 GB | $0.4800 | ~$350 |

### Additional AWS Costs

| Service | Cost |
|---------|------|
| NAT Gateway | $0.045/hr + $0.045/GB = ~$33/mo base |
| Elastic IP (unattached) | $0.005/hr = ~$3.60/mo |
| S3 Storage | $0.023/GB/mo |
| Data Transfer (out) | First 100GB free, then $0.09/GB |
| VPC Peering | Free (data transfer charges apply) |

---

### Deployment Cost Breakdown

#### C2 Infrastructure Only

| Deployment | Components | Instance Types | Est. Monthly |
|------------|------------|----------------|--------------|
| **C2 Ad-Hoc** | 1 C2 Server (t3.medium) | t3.medium | |
| | 2 Redirectors (t3.micro) | t3.micro x2 | |
| | 1 Bastion (t3.medium Windows) | t3.medium Win | |
| | NAT Gateway | | |
| | **Total** | | **~$125** |
| **C2 Purple** | 2 C2 Servers (t3.medium) | t3.medium x2 | |
| | 2 Redirectors (t3.micro) | t3.micro x2 | |
| | 1 Bastion (t3.medium Windows) | t3.medium Win | |
| | NAT Gateway | | |
| | **Total** | | **~$155** |
| **C2 Full** | 3 C2 Servers (t3.medium) | t3.medium x3 | |
| | 2 Redirectors (t3.micro) | t3.micro x2 | |
| | 1 Bastion (t3.medium Windows) | t3.medium Win | |
| | NAT Gateway | | |
| | **Total** | | **~$185** |

#### GOAD Labs Only (with Jumpbox + CS)

| Lab Type | VMs | Windows Instances | Jumpbox | Est. Monthly |
|----------|-----|-------------------|---------|--------------|
| **GOAD Mini** | 1 DC | t3.large x1 (~$81) | t3.medium (~$30) | **~$145** |
| **GOAD Light** | 3 VMs | t3.large x3 (~$243) | t3.medium (~$30) | **~$310** |
| **SCCM** | 4 VMs | t3.xlarge x4 (~$700) | t3.medium (~$30) | **~$765** |
| **GOAD Full** | 5 VMs | t3.large x5 (~$405) | t3.medium (~$30) | **~$470** |
| **NHA** | 5 VMs | t3.large x5 (~$405) | t3.medium (~$30) | **~$470** |

*Note: GOAD labs include NAT Gateway (~$33) in estimates. SCCM requires larger instances (t3.xlarge).*

#### Combined (C2 + GOAD)

| Combination | Components | Est. Monthly |
|-------------|------------|--------------|
| **C2 Ad-Hoc + GOAD Mini** | C2 (~$125) + GOAD Mini (~$145) - shared NAT | **~$240** |
| **C2 Ad-Hoc + GOAD Light** | C2 (~$125) + GOAD Light (~$310) - shared NAT | **~$400** |
| **C2 Full + GOAD Full** | C2 (~$185) + GOAD Full (~$470) - shared NAT | **~$620** |

---

### Cost Optimization Tips

1. **Use Spot Instances**: Up to 90% savings for interruptible workloads (redirectors)
2. **Stop When Not in Use**: EC2 charges only when running
3. **Right-size Instances**: Start small, scale up if needed
4. **Reserved Instances**: 30-60% savings for 1-3 year commitments
5. **NAT Gateway Alternatives**: NAT instances (~$8/mo) or IPv6 egress-only

### Hourly Burn Rate

| Deployment | Hourly Cost | Daily (8 hrs) | Weekly |
|------------|-------------|---------------|--------|
| C2 Ad-Hoc | ~$0.17 | ~$1.36 | ~$9.50 |
| GOAD Light | ~$0.42 | ~$3.36 | ~$23.50 |
| Full C2 + GOAD Full | ~$0.85 | ~$6.80 | ~$47.60 |

*Tip: Destroy infrastructure when not actively testing to minimize costs.*

*Source: [AWS EC2 On-Demand Pricing](https://aws.amazon.com/ec2/pricing/on-demand/) - Verified January 2026*

---

## Implementation Phases

### Phase 1: Terraform Core Updates (8-10 hours)

**Goal:** Update existing Terraform to support deployment type selection and conditional module loading.

| Task | Files | Est. Time |
|------|-------|-----------|
| Add new variables (deployment_type, goad_lab_type, etc.) | `terraform/variables.tf` | 1 hr |
| Add locals for mode detection | `terraform/main.tf` | 1 hr |
| Add conditional module loading (count/for_each) | `terraform/main.tf` | 2 hrs |
| Create centralized CS install script | `terraform/scripts/install_cobalt_strike.sh` | 1 hr |
| Create S3 storage module for CS files | `terraform/modules/cs_storage/` | 1 hr |
| Update C2 team server to use centralized script | `terraform/modules/c2_team_server/main.tf` | 1 hr |
| Add all outputs (IPs, credentials, instructions) | `terraform/outputs.tf` | 1 hr |

**Deliverable:** Existing C2 deployments work with new `deployment_type` variable.

---

### Phase 2: GOAD Module & VPC Peering (8-10 hours)

**Goal:** Create GOAD module, template processor, and VPC peering for combined mode.

| Task | Files | Est. Time |
|------|-------|-----------|
| Create GOAD template processor | `webapp/backend/utils/goad_template_processor.py` | 2 hrs |
| Create GOAD Terraform module | `terraform/modules/goad/` | 3 hrs |
| Create VPC peering module | `terraform/modules/vpc_peering/` | 1.5 hrs |
| Add security group rules for peering | `terraform/modules/security/main.tf` | 1 hr |
| Add Ansible provisioning trigger | `terraform/modules/goad/provisioner.tf` | 1.5 hrs |

**Deliverable:** GOAD-only and Combined deployments work via Terraform.

---

### Phase 3: Backend & Frontend Integration (4-6 hours)

**Goal:** Connect web UI to new Terraform capabilities.

| Task | Files | Est. Time |
|------|-------|-----------|
| Update config parser for deployment_type | `webapp/backend/utils/config_parser.py` | 1 hr |
| Add S3 upload utility | `webapp/backend/utils/s3_upload.py` | 1 hr |
| Add /deployment-details endpoint | `webapp/backend/routes/deploy.py` | 1 hr |
| Add /goad-status endpoint | `webapp/backend/routes/deploy.py` | 1 hr |
| Update frontend deployment details panel | `webapp/frontend/index.html`, `app.js` | 1.5 hrs |

**Deliverable:** Full end-to-end deployment via web UI.

---

## Total Estimated Time

| Phase | Time |
|-------|------|
| Phase 1: Terraform Core | 8-10 hours |
| Phase 2: GOAD Module & Peering | 8-10 hours |
| Phase 3: Backend & Frontend | 4-6 hours |
| **Total** | **20-26 hours** |

### Challenge: GOAD Generates Its Own Keys

GOAD creates TLS keys at deploy time:
- `tls_private_key.ssh` - For jumpbox and Linux VMs
- `tls_private_key.windows` - For Windows VMs

### Solution: Use Our Key Pair + Store GOAD Keys

1. **Jumpbox**: Use our existing AWS key pair (configurable)
2. **GOAD VMs**: Let GOAD generate keys, but expose them via outputs

**Terraform Output:**

```hcl
output "goad_ssh_private_key" {
  description = "SSH private key for GOAD jumpbox (generated)"
  value       = local.deploy_goad ? module.goad[0].ssh_private_key : null
  sensitive   = true
}

output "goad_windows_private_key" {
  description = "SSH private key for GOAD Windows VMs"
  value       = local.deploy_goad ? module.goad[0].windows_private_key : null
  sensitive   = true
}
```

**Backend: Save Keys to File**

```python
def save_goad_keys(outputs: dict, project_name: str):
    """Save GOAD SSH keys to files for user download."""
    keys_dir = f"data/deployments/{project_name}/ssh_keys"
    os.makedirs(keys_dir, exist_ok=True)
    
    if outputs.get('goad_ssh_private_key'):
        with open(f"{keys_dir}/goad-jumpbox.pem", 'w') as f:
            f.write(outputs['goad_ssh_private_key'])
        os.chmod(f"{keys_dir}/goad-jumpbox.pem", 0o600)
    
    if outputs.get('goad_windows_private_key'):
        with open(f"{keys_dir}/goad-windows.pem", 'w') as f:
            f.write(outputs['goad_windows_private_key'])
        os.chmod(f"{keys_dir}/goad-windows.pem", 0o600)
```

---

## Destroy Behavior

### Important: Different Modes Have Different Destroy Behavior

| Mode | Destroy Time | Notes |
|------|--------------|-------|
| **C2-Only** | ~5 minutes | Standard Linux instances |
| **GOAD-Only** | ~10-15 minutes | Windows VMs take longer |
| **Combined** | ~15-20 minutes | Must destroy peering first |

### Terraform Destroy Order (Combined Mode)

Terraform handles dependencies automatically, but the order is:

1. VPC Peering connection
2. GOAD VMs and jumpbox
3. GOAD VPC resources
4. C2 servers and redirectors
5. C2 VPC resources
6. S3 bucket (if empty)

### Backend Destroy Endpoint

```python
@deploy_bp.route('/destroy', methods=['POST'])
def destroy_infrastructure():
    """Destroy all deployed infrastructure."""
    try:
        # Run terraform destroy with auto-approve
        result = subprocess.run(
            ['terraform', 'destroy', '-auto-approve'],
            cwd=TERRAFORM_DIR,
            capture_output=True,
            text=True,
            timeout=1800  # 30 minute timeout
        )
        
        if result.returncode != 0:
            return jsonify({
                'success': False, 
                'error': result.stderr
            }), 500
        
        return jsonify({
            'success': True,
            'message': 'Infrastructure destroyed successfully'
        })
        
    except subprocess.TimeoutExpired:
        return jsonify({
            'success': False,
            'error': 'Destroy timed out after 30 minutes'
        }), 500
```

