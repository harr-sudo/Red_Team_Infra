# Combined: C2 Ad-Hoc + GOAD Light

## Overview

The **Combined Light** deployment (`combined-adhoc-light`) provisions a **C2 Ad-Hoc stack and a GOAD Light multi-domain lab in one apply**, then **peers the two VPCs together** so the C2 infrastructure can run a realistic engagement against a parent-child Active Directory environment. It steps up from [Combined Mini](./combined-mini.md) by replacing the single-DC GOAD Mini lab with **GOAD Light** — two domain controllers, a member server, and a parent-child trust — giving you cross-domain attack practice driven by a real Cobalt Strike team server.

It maps to the Terraform `combined-adhoc-light` deployment type, which deploys C2 in **`single`** mode plus the **GOAD-Light** lab and a VPC peering connection between them.

> ![Combined C2 + GOAD Light Architecture](../../generated-diagrams/combined-full-c2-goad-light.png)

> **Note:** the docs index table labels this deployment "Purple Team C2 + GOAD Light", but the framework wires `combined-adhoc-light` to the **ad-hoc / single** C2 mode (one team server), per `terraform/main.tf` (`c2_mode_map`). This document reflects the actual deployment: ad-hoc C2 + GOAD Light.

## Architecture Components

A combined deployment is **two VPCs** joined by a peering connection. The Dashboard Server (a third VPC) peers with both.

### C2 VPC (10.0.0.0/16) — Ad-Hoc, single mode

| Component | Type | Subnet | Private IP | Public IP | Purpose |
|-----------|------|--------|-----------|-----------|---------|
| **Redirector 1** | t3.small (nginx HTTPS) | DMZ (10.0.1.0/24) | 10.0.1.10 | EIP | Traffic forwarding (primary) |
| **Redirector 2** | t3.small (nginx HTTPS) | DMZ (10.0.2.0/24) | 10.0.2.10 | EIP | Traffic forwarding (backup) |
| **C2 Team Server** | t3.medium (Cobalt Strike) | Private (10.0.10.0/24) | 10.0.10.10 | None | Cobalt Strike team server |
| **Attack Box** | t2.large (Windows 2022) | Private (10.0.10.0/24) | 10.0.10.50 | None | CS Client GUI, red team tools |
| **NAT Gateway** | Managed | Public | — | Auto | Outbound-only internet for private instances |

### GOAD VPC (192.168.56.0/24) — GOAD Light

| Component | Type | OS | Private IP | Domain / Role | Purpose |
|-----------|------|-----|-----------|---------------|---------|
| **Jumpbox** | t2.small (Ubuntu) | Ubuntu 22.04 | 192.168.56.100 | — | GOAD Ansible provisioning host + legacy SSH gateway (EIP) |
| **DC01 (kingslanding)** | t2.medium | Win 2019 | 192.168.56.10 | sevenkingdoms.local (root DC) | Root domain controller |
| **DC02 (winterfell)** | t2.medium | Win 2019 | 192.168.56.11 | north.sevenkingdoms.local (child DC) | Child domain controller |
| **SRV02 (castelblack)** | t2.medium | Win 2019 | 192.168.56.22 | north.sevenkingdoms.local (member) | Member server (File/IIS/SQL) |
| **NAT Gateway** | Managed | — | — | — | Outbound-only internet for the AD lab |

> The combined attack box lives in the **C2 VPC** (10.0.10.50). GOAD Light in combined mode does **not** add a second team server or attack box on the GOAD side — the C2 VPC's team server and attack box drive the engagement across the peering.

### Domain Structure (GOAD Light)

```
Forest: sevenkingdoms.local (Root)
├── DC01 kingslanding (sevenkingdoms.local)
└── DC02 winterfell   (north.sevenkingdoms.local) ← child domain
    └── SRV02 castelblack (member server)

Trust: sevenkingdoms.local ⇄ north.sevenkingdoms.local (parent-child, transitive)
```

### VPC Peering

```
Dashboard VPC (10.100.0.0/16)
   ├── peering ──► C2 VPC   (10.0.0.0/16)
   └── peering ──► GOAD VPC (192.168.56.0/24)

C2 VPC (10.0.0.0/16) ◄────── peering ──────► GOAD VPC (192.168.56.0/24)
```

The `vpc_peering` module connects the C2 VPC and the GOAD VPC and writes the cross-VPC routes onto **all** route tables on both sides. The C2 team server (10.0.10.10) and attack box (10.0.10.50) therefore have a **direct routed path** to the whole GOAD AD lab (192.168.56.0/24) — the path beacons and tools use to attack across the parent-child trust. The Dashboard Server peers separately with each VPC for operator access.

### Network Architecture

```
                         Operator Laptop (dev dashboard only)
                                  │ SSH tunnel :5000
                                  ▼
                    Dashboard VPC 10.100.0.0/16 (Dashboard Server, EIP)
                          │ peering              │ peering
        ┌─────────────────┘                      └──────────────────┐
        ▼                                                            ▼
┌──────────────────────────────────┐   peering   ┌────────────────────────────────────┐
│  C2 VPC  10.0.0.0/16             │◄───────────►│  GOAD VPC  192.168.56.0/24          │
│  DMZ (10.0.1.0/24, 10.0.2.0/24) │             │  Public (192.168.56.64/26)          │
│   ├── Redirector 1 (10.0.1.10)  │             │   ├── Jumpbox (.100, EIP)           │
│   └── Redirector 2 (10.0.2.10)  │             │   ├── Internet Gateway              │
│  Private (10.0.10.0/24)          │             │   └── NAT Gateway                   │
│   ├── C2 Team Server (10.0.10.10)│             │  Private (192.168.56.0/26)          │
│   └── Attack Box (10.0.10.50)    │  ── attack ─►│   ├── DC01 kingslanding (.10)       │
│  NAT Gateway → Internet          │             │   ├── DC02 winterfell   (.11)       │
└──────────────────────────────────┘             │   └── SRV02 castelblack (.22)       │
                                                  └────────────────────────────────────┘

Beacon traffic:  Target → HTTPS :443 → Redirector 1/2 → C2 Team Server :443
Attack path:     C2 / Attack Box → VPC peering → GOAD AD lab (192.168.56.0/24)
```

Both VPCs keep their standard internal layout. Neither lab host nor team server is directly internet-facing; the redirector EIPs and the jumpbox EIP are the only public addresses, and operator access is via the dashboard.

## Key Features

### 1. Cross-Domain Engagement with Realistic C2
- **Beacons callback through redirectors** to the team server, then pivot across VPC peering into the AD lab
- Practice the full chain: payload delivery → callback → lateral movement → **child-to-parent domain escalation**

### 2. C2 Ad-Hoc (single team server)
- One t3.medium Cobalt Strike server (10.0.10.10) behind two redundant redirectors
- Same network shape and SSL/redirector behaviour as the standalone [C2 Ad-Hoc](./c2-adhoc.md)

### 3. GOAD Light (multi-domain lab)
- **Parent domain** sevenkingdoms.local (DC01) and **child domain** north.sevenkingdoms.local (DC02)
- **Member server** SRV02 castelblack for lateral movement, file shares, IIS, SQL, and coercion attacks
- Automatic parent-child trust — practise cross-domain Kerberoasting, SID history, trust-key extraction

### 4. Single Attack Box (C2 VPC)
- Windows Server 2022 (10.0.10.50) with CS Client + tools, reached via RDP tunnel through the Dashboard Server

## Deployment

### Configuration

```hcl
# terraform.tfvars
deployment_type = "combined-adhoc-light"   # C2 single mode + GOAD-Light + VPC peering

# Network (defaults shown — two distinct CIDRs)
vpc_cidr      = "10.0.0.0/16"        # C2 VPC
goad_vpc_cidr = "192.168.56.0/24"    # GOAD VPC

# Domains (REQUIRED for the C2 side)
primary_domain_name = "operations.company.com"
backup_domains      = ["cdn.company.com"]

# Access Control
management_cidr_blocks = ["YOUR.PUBLIC.IP/32"]
```

### Via Web Application

1. Navigate to **Configuration**
2. Set **Deployment Type**: "C2 + GOAD Light"
3. Upload the **Cobalt Strike distribution** archive
4. Configure the **Domain** (required for the C2 side)
5. Click **Deploy**

### Via Command Line

```bash
cd terraform
terraform init -var-file=../configs/terraform.tfvars
terraform apply -var="deployment_type=combined-adhoc-light"
```

### Provisioning timeline

1. **Infrastructure (~15-20 min)** — both VPCs, the peering connection, the C2 stack, and the GOAD Light hosts.
2. **GOAD provisioning (~45-60 min)** — the jumpbox runs the GOAD-Light Ansible playbook: promote DC01/DC02, configure the parent-child trust, join SRV02, seed vulnerabilities. Trigger from the dashboard's GOAD provisioning view.

## Security Groups

Each VPC keeps its own security groups; the peering routes plus these rules permit the cross-VPC attack path.

- **C2 side** — `proxy_redirector_sg`, `c2_team_server_sg`, `attack_box_sg` behave exactly as in [C2 Ad-Hoc](./c2-adhoc.md#security-groups), with the team-server SG permitting egress to the GOAD CIDR for the attack path.
- **GOAD side** — the shared `goad_sg` allows all traffic from within the GOAD VPC **and from the peer C2 VPC CIDR (10.0.0.0/16)**, plus SSH/RDP/WinRM from `management_cidr_blocks`. This is what lets C2 beacons and attack-box tools reach DC01/DC02/SRV02.

> The GOAD shared SG is intentional — it is a deliberately vulnerable training lab. Isolation comes from the private subnet and the management IP allow-list.

## Access Methods

The **Dashboard Server** is the operator entry point and jump host for **both** VPCs.

```bash
# Dashboard UI (single tunnel)
ssh -L 5000:localhost:5000 ubuntu@<dashboard-eip>
# http://localhost:5000 — terminal, topology (both VPCs), CS beacons, GOAD provisioning

# CS Client → team server (C2 VPC) through the dashboard
ssh -L 50050:10.0.10.10:50050 -i ~/.ssh/key.pem ubuntu@<dashboard-eip>

# RDP → attack box (C2 VPC) through the dashboard
ssh -L 13389:10.0.10.50:3389 -i ~/.ssh/key.pem ubuntu@<dashboard-eip>

# RDP → DC01 / DC02 (GOAD VPC) through the dashboard
ssh -L 3391:192.168.56.10:3389 -i ~/.ssh/key.pem ubuntu@<dashboard-eip>
xfreerdp /v:localhost:3391 /u:Administrator /d:sevenkingdoms /p:'password'
ssh -L 3392:192.168.56.11:3389 -i ~/.ssh/key.pem ubuntu@<dashboard-eip>
xfreerdp /v:localhost:3392 /u:Administrator /d:north /p:'password'

# SOCKS proxy for sweeping the AD subnet
ssh -D 1080 -i ~/.ssh/key.pem ubuntu@<dashboard-eip>
proxychains crackmapexec smb 192.168.56.0/26
```

> **Legacy fallback:** the GOAD jumpbox EIP still works as an SSH gateway into the GOAD VPC if the dashboard is unavailable. It is otherwise the Ansible provisioning host, not an access path.

## Cost Breakdown

### Monthly Cost Estimate: ~$350-420

| Resource | Type | Cost/Month |
|----------|------|------------|
| C2 Team Server | t3.medium | ~$30 |
| Redirector 1 / 2 | t3.small x2 | ~$30 |
| Attack Box | t2.large | ~$50 |
| GOAD Jumpbox | t2.small | ~$17 |
| GOAD DC01 / DC02 | t2.medium x2 | ~$66 |
| GOAD SRV02 | t2.medium | ~$33 |
| NAT Gateways | 2 (one per VPC) | ~$64 |
| EBS Storage | combined | ~$20 |
| Data Transfer | minimal | ~$10-15 |
| S3 / VPC peering | peering has no hourly charge | ~$5 |
| **Total** | | **~$350-420** |

> Two NAT Gateways (one per VPC) plus the extra GOAD Light VMs drive the cost above Combined Mini. **Stop instances when idle** to save ~70%.

## Dashboard Server (Production Control Plane)

The dashboard runs on a dedicated AWS EC2 instance in its own VPC. It is the **production control plane and sole SSH jump host**, peering independently with **both** the C2 and GOAD VPCs so it reaches every instance directly. There is no per-deployment SSH-relay bastion; the GOAD jumpbox is the Ansible provisioning host. The operator's laptop only runs a *dev* instance of the dashboard.

### VPC Peering Summary

| Peering | CIDRs | Purpose |
|---------|-------|---------|
| Dashboard ⇄ C2 | 10.100.0.0/16 ⇄ 10.0.0.0/16 | Operator access to redirectors, team server, attack box |
| Dashboard ⇄ GOAD | 10.100.0.0/16 ⇄ 192.168.56.0/24 | Operator access to jumpbox + DCs + SRV02 |
| **C2 ⇄ GOAD** | 10.0.0.0/16 ⇄ 192.168.56.0/24 | **Attack path** — beacons/tools reach the AD lab |

### Dashboard Access to Instances

| Target | VPC | Ports | Purpose |
|--------|-----|-------|---------|
| Redirector 1/2 (10.0.1.10 / 10.0.2.10) | C2 | SSH/22 | nginx config, health checks |
| C2 Team Server (10.0.10.10) | C2 | SSH/22, CS/50050, REST/50443 | Shell, CS client tunnel, REST API |
| Attack Box (10.0.10.50) | C2 | SSH/22 | Management shell, RDP tunnel |
| Jumpbox (192.168.56.100) | GOAD | SSH/22 | Ansible provisioning |
| DC01 / DC02 (.10 / .11) | GOAD | RDP/3389, WinRM/5985 | Lab access via dashboard tunnel |
| SRV02 castelblack (.22) | GOAD | RDP/3389, WinRM/5985 | Lab access via dashboard tunnel |

## Related Documentation

- [C2 Ad-Hoc Architecture](./c2-adhoc.md) — the C2 half of this deployment
- [GOAD Light Architecture](./goad-light.md) — the lab half of this deployment
- [Combined Mini (C2 + GOAD Mini)](./combined-mini.md) — the lower-cost combined option
- [Combined Full (C2 Full + GOAD Full)](./combined-full.md) — the largest combined deployment
- [Deployment Modes](../DEPLOYMENT_MODES.md) — all 12 deployment types
- [GOAD Quick Start](../GOAD_QUICK_START.md) — provisioning + CS-to-GOAD connection
- [Diagrams Index](./DIAGRAMS_INDEX.md) — all architecture diagrams

## Summary

Combined Light is **C2 Ad-Hoc + GOAD Light, peered** — a realistic C2 engagement against a multi-domain AD estate.

- ✅ Two peered VPCs: C2 (10.0.0.0/16) attacks GOAD (192.168.56.0/24)
- ✅ Single team server, redundant redirectors, one attack box (C2 VPC)
- ✅ Parent-child lab: sevenkingdoms.local + north.sevenkingdoms.local + SRV02 (GOAD VPC)
- ✅ Dashboard Server peers with both — sole jump host, no per-deployment bastion

**Cost**: ~$350-420/month. Ideal for intermediate training with cross-domain attacks and realistic C2.
