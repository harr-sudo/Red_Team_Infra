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

**Key file: `modules/goad/jumpbox.tf`**

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
| `terraform/modules/goad/` | Create | New GOAD deployment module |
| `terraform/modules/vpc_peering/` | Create | New VPC peering module |
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

