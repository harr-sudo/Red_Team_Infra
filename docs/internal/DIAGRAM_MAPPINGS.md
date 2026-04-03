# Architecture Diagram Mappings

**Date**: 2026-01-22  
**Status**: ✅ Complete - All deployment types now have accurate, specific diagrams

## Overview

Every deployment type in the Red Team Infrastructure project now has its own specific, accurate architecture diagram that matches exactly what gets deployed.

---

## 🎯 C2 Infrastructure Diagrams

### 1. C2 Ad-Hoc
- **Diagram**: `c2-adhoc-architecture.png`
- **Description**: Single team server with HTTP/HTTPS redirectors
- **Components**: 1 Team Server, 2-3 Redirectors, Jump Box
- **Orientation**: Landscape (Left-to-Right)

### 2. C2 Purple Team
- **Diagram**: `c2-purple-architecture.png`
- **Description**: Redundant team servers for high availability
- **Components**: 2 Team Servers, Multiple Redirectors, Admin Infrastructure
- **Orientation**: Landscape (Left-to-Right)

### 3. C2 Full Red Team
- **Diagram**: `c2-full-architecture.png`
- **Description**: Phase-based operations with dedicated servers per phase
- **Components**: 3+ Team Servers (Recon, Initial Access, Persistence), Redirector Layer, Admin Infrastructure
- **Orientation**: Landscape (Left-to-Right)

---

## 🏰 GOAD Training Lab Diagrams

### 1. GOAD Mini (1 VM, 1 Domain)
- **Diagram**: `goad-mini-correct.png`
- **Terraform Lab Type**: `GOAD-Mini`
- **VMs**: 
  - 1 DC (kingslanding)
  - Jump Box, Team Server, Attack Box
- **Domains**: 1 (sevenkingdoms.local)
- **Orientation**: Landscape (Left-to-Right)

### 2. GOAD Light (3 VMs, 2 Domains)
- **Diagram**: `goad-light-correct.png`
- **Terraform Lab Type**: `GOAD-Light`
- **VMs**: 
  - 2 DCs (kingslanding, meereen)
  - 1 Workstation (castelblack)
  - Jump Box, Team Server, Attack Box
- **Domains**: 2 (north.sevenkingdoms.local, essos.local)
- **Orientation**: Landscape (Left-to-Right)

### 3. GOAD Full (5 VMs, 3 Domains, 2 Forests)
- **Diagram**: `goad-full-correct.png`
- **Terraform Lab Type**: `GOAD`
- **VMs**: 
  - 3 DCs (kingslanding, winterfell, meereen)
  - 2 Workstations (castelblack, braavos)
  - Jump Box, Team Server, Attack Box
- **Domains**: 3 across 2 forests
- **Forests**: 
  - north.sevenkingdoms.local (with child domain)
  - essos.local
- **Orientation**: Landscape (Left-to-Right)

### 4. GOAD SCCM (4 VMs, SCCM Lab)
- **Diagram**: `goad-sccm-correct.png`
- **Terraform Lab Type**: `SCCM`
- **VMs**:
  - 1 DC (kingslanding)
  - 1 SCCM Server (meereen)
  - 2 Workstations (winterfell, braavos)
  - Jump Box, Team Server, Attack Box
- **Focus**: System Center Configuration Manager exploitation
- **Domains**: 1 (sccm.lab)
- **Orientation**: Landscape (Left-to-Right)

### 5. GOAD NHA (5 VMs, Challenge Lab)
- **Diagram**: `goad-nha-correct.png`
- **Terraform Lab Type**: `NHA`
- **VMs**:
  - 2 DCs across 2 domains
  - 2 Workstations
  - 1 Application Server
  - Jump Box, Team Server, Attack Box
- **Focus**: CTF-style security challenges
- **Domains**: 2 (ninja.hack, academy.ninja.lan)
- **Orientation**: Landscape (Left-to-Right)

---

## 🔥 Combined C2 + GOAD Deployments

### 1. Combined: C2 Ad-Hoc + GOAD Mini
- **Diagram**: `combined-c2-goad-mini.png`
- **Description**: Single C2 infrastructure connected to GOAD Mini lab
- **VPCs**: 2 (C2 VPC + GOAD VPC)
- **Total VMs**: ~7 (1 C2 Team Server, 2-3 Redirectors, GOAD Mini + support infrastructure)
- **Orientation**: Landscape (Left-to-Right)

### 2. Combined: C2 Ad-Hoc + GOAD Light
- **Diagram**: `combined-full-c2-goad-light.png`
- **Description**: Single C2 infrastructure connected to GOAD Light lab (3 VMs)
- **VPCs**: 2 (C2 VPC + GOAD VPC)
- **Total VMs**: ~9
- **Orientation**: Landscape (Left-to-Right)

### 3. Combined: Full C2 Red Team + GOAD Full
- **Diagram**: `combined-full-c2-goad-full.png`
- **Description**: Phase-based C2 infrastructure connected to complete GOAD environment
- **VPCs**: 2 (C2 VPC + GOAD VPC with VPC Peering)
- **Total VMs**: ~15+
- **Features**:
  - 3 Phase-based Team Servers (Recon, Initial Access, Persistence)
  - Multiple Redirectors (HTTP, HTTPS, DNS)
  - Full GOAD environment (5 VMs, 3 domains, 2 forests)
  - VPC Peering for realistic attack paths
- **Orientation**: Landscape (Left-to-Right)

---

## 📐 Component Architecture Diagrams

### 1. Windows Attack Box
- **Diagram**: `attackbox-architecture.png`
- **Description**: Detailed breakdown of the Windows Attack Box
- **Shows**: Tool repository access, S3 integration, RDP access, security boundaries

### 2. IAM Security Architecture
- **Diagram**: `iam-security-architecture.png`
- **Description**: IAM roles and permissions per VPC
- **Shows**: Separate roles for C2 VPC and GOAD VPC, S3 bucket policies, least privilege access

### 3. SSH Key Management
- **Diagram**: `ssh-key-architecture.png`
- **Description**: Automated SSH key distribution and management
- **Shows**: Ansible-based key distribution, jump box access, secure key storage

---

## Key Architecture Features (All Diagrams)

### Network Segmentation
- **Public Subnets**: Jump boxes, redirectors (internet-facing)
- **Private Subnets**: Team servers, GOAD labs, attack infrastructure
- **VPC Peering**: Connects C2 and GOAD environments in combined deployments

### Security Components
- **IAM Roles**: Separate roles per VPC with least privilege access
- **Security Groups**: Strict ingress/egress rules
- **NAT Gateways**: Private subnet internet access
- **Jump Boxes**: Single point of entry with SSH key authentication

### Storage
- **S3 Buckets**: 
  - Cobalt Strike artifacts and payloads
  - Tools repository
  - GOAD provisioning scripts
- **IAM-based Access**: Role-based S3 bucket access

### Support Infrastructure
- **Jump Box**: Linux-based SSH entry point with Ansible
- **Team Server**: Cobalt Strike C2 server (Linux)
- **Attack Box**: Windows-based attack platform with pre-loaded tools

---

## Diagram Naming Convention

All diagrams follow this pattern:
- GOAD variants: `goad-{variant}-correct.png`
- C2 variants: `c2-{type}-architecture.png`
- Combined: `combined-{c2-type}-{goad-type}.png`
- Components: `{component-name}-architecture.png`

---

## Terraform Lab Type Mapping

| UI Display Name | Terraform `lab_type` Variable | Diagram File |
|----------------|------------------------------|--------------|
| GOAD Mini | `GOAD-Mini` | `goad-mini-correct.png` |
| GOAD Light | `GOAD-Light` | `goad-light-correct.png` |
| GOAD Full | `GOAD` | `goad-full-correct.png` |
| GOAD SCCM | `SCCM` | `goad-sccm-correct.png` |
| GOAD NHA | `NHA` | `goad-nha-correct.png` |

---

## Usage in Web Application

All diagrams are served via Flask API endpoints:
- **Endpoint**: `/api/architecture/diagram/<filename>`
- **Defined in**: `webapp/backend/routes/architecture.py`
- **JavaScript mapping**: `webapp/frontend/js/architecture.js`

### JavaScript Architecture Object

Each deployment type maps to:
```javascript
{
    diagram: '/api/architecture/diagram/{diagram-file}.png',
    markdownFile: '{documentation}.md',
    title: 'Display Title'
}
```

---

## Generation Details

All diagrams generated using:
- **Tool**: AWS Diagram MCP Server (Kiro CLI)
- **Package**: Python `diagrams` package
- **Services**: AWS icons (EC2, S3, IAM, VPC, etc.)
- **Orientation**: Landscape (Left-to-Right) for better screen utilization
- **Date**: January 22, 2026

---

## Notes

1. **Accuracy**: All diagrams accurately reflect the Terraform configurations in `terraform/modules/`
2. **Consistency**: All GOAD diagrams show the three-tier infrastructure:
   - Jump Box (public subnet)
   - GOAD Lab VMs (private subnet)
   - Team Server + Attack Box (private subnet)
3. **VPC Clarity**: Public vs Private subnet placement is clearly marked in all diagrams
4. **Landscape Orientation**: All diagrams use left-to-right flow for better visibility
5. **Markdown Separation**: Diagram display is separate from documentation to avoid duplicate images

---

## Future Enhancements

Potential future additions:
- Monitoring/logging architecture diagram
- Network traffic flow diagram
- Backup and disaster recovery architecture
- Multi-region deployment architecture
