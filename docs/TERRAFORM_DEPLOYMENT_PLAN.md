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
  description = "GOAD lab type when deploying GOAD: 'GOAD-Mini', 'MINILAB', 'GOAD-Light', 'SCCM', 'GOAD', 'NHA'"
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
    "goad-minilab" = "MINILAB"
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

```hcl
resource "aws_instance" "jumpbox" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = "t2.medium"
  subnet_id     = aws_subnet.public.id
  key_name      = var.key_pair_name
  
  vpc_security_group_ids = [aws_security_group.jumpbox.id]
  
  user_data = var.install_cobalt_strike ? templatefile("${path.module}/scripts/install_cs.sh", {
    cs_archive_s3_path = var.cobalt_strike_archive
    cs_password        = var.cs_teamserver_password
  }) : file("${path.module}/scripts/jumpbox_init.sh")
  
  tags = merge(var.tags, {
    Name = "${var.project_name}-goad-jumpbox"
    Role = var.install_cobalt_strike ? "jumpbox-cs" : "jumpbox"
  })
}

# Security group for jumpbox
resource "aws_security_group" "jumpbox" {
  name        = "${var.project_name}-goad-jumpbox-sg"
  vpc_id      = aws_vpc.goad.id
  
  # SSH from management
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.management_cidr_blocks
  }
  
  # Cobalt Strike team server (only if CS installed)
  dynamic "ingress" {
    for_each = var.install_cobalt_strike ? [1] : []
    content {
      from_port   = 50050
      to_port     = 50050
      protocol    = "tcp"
      cidr_blocks = var.management_cidr_blocks
    }
  }
  
  # All outbound
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
```

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

---

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `terraform/variables.tf` | Modify | Add deployment_type, goad_lab_type, enable_goad |
| `terraform/main.tf` | Modify | Add locals for mode detection, conditional modules |
| `terraform/outputs.tf` | Modify | Add GOAD outputs |
| `terraform/scripts/install_cobalt_strike.sh` | Create | **Centralized CS setup script (shared by all)** |
| `terraform/modules/goad/` | Create | New GOAD deployment module |
| `terraform/modules/goad/jumpbox.tf` | Create | Uses centralized CS script |
| `terraform/modules/vpc_peering/` | Create | New VPC peering module |
| `terraform/modules/c2_team_server/main.tf` | Modify | Use centralized CS script |
| `webapp/backend/utils/config_parser.py` | Modify | Handle deployment_type mapping |
| `webapp/backend/routes/deploy.py` | Modify | Pass deployment_type to Terraform |

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

## Cost Estimates (Updated)

| Deployment Type | Components | Est. Monthly Cost |
|-----------------|------------|-------------------|
| **C2 Ad-Hoc** | 1 C2 + 2 Redirectors + Bastion | ~$105 |
| **C2 Purple** | 2 C2 + 2 Redirectors + Bastion | ~$135 |
| **C2 Full** | 3 C2 + 2 Redirectors + Bastion | ~$165 |
| **GOAD Mini + CS** | 1 AD VM + Jumpbox w/CS | ~$100 |
| **GOAD MiniLab + CS** | 2 AD VMs + Jumpbox w/CS | ~$175 |
| **GOAD Light + CS** | 3 AD VMs + Jumpbox w/CS | ~$225 |
| **GOAD SCCM + CS** | 4 AD VMs + Jumpbox w/CS | ~$325 |
| **GOAD Full + CS** | 5 AD VMs + Jumpbox w/CS | ~$375 |
| **Full C2 + GOAD Mini** | C2 Ad-Hoc + GOAD Mini | ~$205 |
| **Full C2 + GOAD Light** | C2 Ad-Hoc + GOAD Light | ~$330 |
| **Full C2 + GOAD Full** | C2 Full + GOAD Full | ~$540 |

---

## Implementation Order

1. **Phase 1-2**: Update variables.tf and main.tf locals (1-2 hours)
2. **Phase 3**: Add conditional module loading (2-3 hours)
3. **Phase 4**: Create GOAD module (4-6 hours)
4. **Phase 5**: Create VPC peering module (1-2 hours)
5. **Phase 6**: Backend updates (2-3 hours)
6. **Testing**: Test all deployment modes (4-6 hours)

**Total Estimated Time**: 14-22 hours

---

## Testing Checklist

- [ ] C2 Ad-Hoc deploys correctly
- [ ] C2 Purple deploys correctly
- [ ] C2 Full deploys correctly
- [ ] GOAD Mini + CS deploys correctly
- [ ] GOAD Full + CS deploys correctly
- [ ] Combined Ad-Hoc + Mini deploys correctly
- [ ] Combined Full + Full deploys correctly
- [ ] VPC peering works in combined mode
- [ ] CS client can connect in all modes
- [ ] Beacons work in combined mode
- [ ] Destroy works for all modes

