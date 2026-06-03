# C2 Full Red Team - Phase-Based Operations

## Overview

The **C2 Full Red Team** deployment runs **three Cobalt Strike team servers**, one per operational **phase** — **staging**, **post-exploitation**, and **long-haul**. Each phase gets its own dedicated team server so the C2 control plane is compartmentalized by purpose: noisy initial-access activity, hands-on-keyboard post-ex, and slow long-term persistence never share a single server (or a single burned profile).

This is the most capable C2 mode in the framework. It maps to the Terraform `c2-full` deployment type, which selects the **`phases`** C2 deployment mode and instantiates one team server per enabled entry in the `c2_phases` map. It builds on the same network shape as [C2 Ad-Hoc](./c2-adhoc.md) and [C2 Purple Team](./c2-purple.md): shared redundant redirectors, a Windows attack box, and the AWS Dashboard Server as the sole jump host.

> ![C2 Full Red Team Architecture](../../generated-diagrams/c2-full-architecture.png)

## Architecture Components

### Infrastructure (Static IPs)

| Component | Phase | Type | Subnet | Private IP | Public IP | Purpose |
|-----------|-------|------|--------|-----------|-----------|---------|
| **Redirector 1** | — | t3.small (nginx HTTPS) | DMZ (10.0.1.0/24) | 10.0.1.10 | EIP | Traffic forwarding (primary) |
| **Redirector 2** | — | t3.small (nginx HTTPS) | DMZ (10.0.2.0/24) | 10.0.2.10 | EIP | Traffic forwarding (backup) |
| **C2 Team Server (Staging)** | staging | t3.medium | Private 1 (10.0.10.0/24) | 10.0.10.10 | None | Initial access / staging listeners |
| **C2 Team Server (Post-Ex)** | post-ex | t3.medium | Private 2 (10.0.11.0/24) | 10.0.11.10 | None | Hands-on-keyboard post-exploitation |
| **C2 Team Server (Long-Haul)** | long-haul | t3.medium | Private 1 (10.0.10.0/24) | 10.0.10.11 | None | Low-and-slow persistence |
| **Attack Box** | — | t2.large (Windows 2022) | Private 1 (10.0.10.0/24) | 10.0.10.50 | None | CS Client GUI, red team tools |
| **NAT Gateway** | — | Managed | Public | — | Auto | Outbound-only internet for private instances |

The three team servers are spread across both private subnets/AZs: staging and long-haul in 10.0.10.0/24, post-ex in 10.0.11.0/24. The redirectors forward beacon traffic to the **staging** server by default (the entry point for fresh callbacks); the operator migrates beacons to the post-ex and long-haul servers as the engagement progresses.

### Network Architecture

The VPC (`10.0.0.0/16`, region `eu-central-1`) uses the standard three-tier layout:

```
C2 VPC: 10.0.0.0/16
├── DMZ Subnets (public): 10.0.1.0/24, 10.0.2.0/24
│   ├── Redirector 1 (10.0.1.10, EIP) ← Beacon traffic (port 443)
│   ├── Redirector 2 (10.0.2.10, EIP) ← Beacon traffic (port 443)
│   ├── Internet Gateway — bidirectional, public subnets only
│   └── NAT Gateway — outbound-only internet for private subnets
│
└── Private Subnets: 10.0.10.0/24 (AZ-a), 10.0.11.0/24 (AZ-b) — NO public IPs
    ├── C2 Staging   (10.0.10.10) ← Cobalt Strike :50050 / listener :443
    ├── C2 Long-Haul (10.0.10.11) ← Cobalt Strike :50050 / listener :443
    ├── C2 Post-Ex   (10.0.11.10) ← Cobalt Strike :50050 / listener :443
    └── Attack Box   (10.0.10.50) ← Windows workstation (CS Client, tools)
```

**Internet Gateway vs NAT Gateway** — the IGW is bidirectional and serves the redirectors' EIPs (target beacon callbacks arrive here). The NAT Gateway is outbound-only and serves the private subnets. No team server or attack box is ever directly internet-facing.

**Operator access does not touch the redirectors or the IGW.** The AWS-hosted **Dashboard Server** (its own VPC, peered with this C2 VPC) reaches all three team servers (10.0.10.10, 10.0.11.10, 10.0.10.11) and the attack box (10.0.10.50) directly over VPC peering. There is no per-deployment SSH-relay bastion.

### How Phase-Based Operations Work

Each phase is a separate Cobalt Strike team server with its own profile, listeners, and operational tempo. A typical engagement flows across them:

| Phase | Server | Role | OpSec posture |
|-------|--------|------|---------------|
| **Staging** | 10.0.10.10 | Initial access, payload delivery, first beacons | Most exposed — burns fastest. Disposable profile. |
| **Post-Ex** | 10.0.11.10 | Interactive operations: lateral movement, priv-esc, collection | Migrate trusted beacons here, off the noisy staging server. |
| **Long-Haul** | 10.0.10.11 | Low-and-slow persistence, fallback access | Long sleep times, separate profile/domain. Survives staging burn. |

Compartmentalizing by phase means a detection on the noisy staging infrastructure does not expose your post-ex or long-haul access. Each phase is independently configurable through the `c2_phases` variable (instance type, root volume, user_data, IAM profile) and each can be enabled or disabled.

Because all three servers sit behind the same redirector EIPs and DNS, you control which server a beacon ultimately reaches via redirector/listener configuration — beacons do not need to know the back-end topology.

## Key Features

### 1. Three Team Servers (Phases Mode)
- **One server per phase** — staging (10.0.10.10), post-ex (10.0.11.10), long-haul (10.0.10.11)
- **Compartmentalized OpSec** — a burn in one phase does not cascade to the others
- **Per-phase configuration** — instance type, disk, user_data, and IAM profile are set individually in `c2_phases`
- **AZ spread** — phases distributed across both private subnets/availability zones

### 2. Shared Redundant Redirectors
- **Two redirector instances** (10.0.1.10, 10.0.2.10), each with an Elastic IP
- **Single NIC + 1:1 EIP NAT** at the IGW — the EIP never appears on the instance itself
- Default upstream is the staging server; supports multiple domains and optional domain fronting

### 3. Attack Box (Windows Workstation)
- **Windows Server 2022** optimized for red team operations (Defender disabled, server bloat removed)
- **Cobalt Strike Client GUI** pre-installed from S3 with a desktop shortcut to the staging server (10.0.10.10:50050)
- **Red team tools** cloned to `C:\Tools`, empty `C:\Payloads` for staging, WSL2 + Ubuntu available
- Private subnet only (10.0.10.50) — reached via RDP tunnel through the Dashboard Server

### 4. Operator Access Patterns

The **Dashboard Server is the operator's entry point and jump host.** It lives in its own VPC (10.100.0.0/16) peered with this C2 VPC, so it reaches every instance directly — no SSH-hopping. All tunnels below run THROUGH the dashboard's EIP. The operator's laptop only runs a *dev* instance of the dashboard; production runs on this AWS server.

#### Option A: Dashboard Web UI (Recommended)
```bash
ssh -L 5000:localhost:5000 ubuntu@<dashboard-eip>
http://localhost:5000
# In-browser terminal, topology, CS beacon management across all three phases, deploy/destroy
```

#### Option B: CS Client to ALL THREE phases through the Dashboard
```bash
# Tunnel all three team servers at once through the Dashboard Server
ssh -i key.pem \
    -L 50050:10.0.10.10:50050 \
    -L 50051:10.0.11.10:50050 \
    -L 50052:10.0.10.11:50050 \
    ubuntu@<dashboard-eip>

# In the Cobalt Strike client, add three profiles:
#   Staging   → 127.0.0.1:50050
#   Post-Ex   → 127.0.0.1:50051
#   Long-Haul → 127.0.0.1:50052
```

#### Option C: RDP to Attack Box through the Dashboard
```bash
ssh -i key.pem -L 13389:10.0.10.50:3389 ubuntu@<dashboard-eip>
mstsc /v:localhost:13389
# Attack box has the CS Client pre-installed (shortcut → 10.0.10.10:50050)
```

## Deployment

### Configuration

```hcl
# terraform.tfvars
deployment_type = "c2-full"   # Selects phases mode automatically

# Or explicitly:
c2_deployment_mode = "phases"

# Per-phase configuration (defaults shown — all three enabled, t3.medium, 20GB)
c2_phases = {
  staging = {
    enabled          = true
    instance_type    = "t3.medium"
    root_volume_size = 20
    user_data        = ""
    iam_instance_profile_name = ""
  }
  post-ex = {
    enabled          = true
    instance_type    = "t3.medium"
    root_volume_size = 20
    user_data        = ""
    iam_instance_profile_name = ""
  }
  long-haul = {
    enabled          = true
    instance_type    = "t3.medium"
    root_volume_size = 20
    user_data        = ""
    iam_instance_profile_name = ""
  }
}

# Network (defaults shown)
vpc_cidr             = "10.0.0.0/16"
public_subnet_cidrs  = ["10.0.1.0/24", "10.0.2.0/24"]
private_subnet_cidrs = ["10.0.10.0/24", "10.0.11.0/24"]

# Domains (REQUIRED for C2)
primary_domain_name = "operations.company.com"
backup_domains      = ["cdn.company.com", "static.company.com"]

# Access Control
management_cidr_blocks = ["YOUR.PUBLIC.IP/32"]
```

> **Disabling a phase:** set `enabled = false` on any phase to skip its server. For example, a two-phase engagement might disable `long-haul`. The redirectors always target the staging IP, so keep `staging` enabled.

### Via Web Application

1. Navigate to **Configuration**
2. Set **Deployment Type**: "C2 Full Red Team"
3. Upload the **Cobalt Strike distribution** archive
4. Configure the **Domain** (required; consider multiple backup domains for per-phase separation)
5. Click **Deploy** and wait ~20-25 minutes (three team servers bootstrap in parallel)

### Via Command Line

```bash
cd terraform
terraform init -var-file=../configs/terraform.tfvars
terraform apply -var="deployment_type=c2-full"
terraform output c2_connection_info
```

## Security Groups

### Redirector Security Group (`proxy_redirector_sg`)
```yaml
Inbound:
  - Port 80 (HTTP): 0.0.0.0/0          # or CloudFront prefix list if domain fronting
  - Port 443 (HTTPS): 0.0.0.0/0        # or CloudFront prefix list if domain fronting
  - Port 22 (SSH): management_cidr_blocks
  - Port 22 (SSH): dashboard_sg        # Dashboard Server via VPC peering (nginx config mgmt)
Outbound:
  - Port 443: c2_team_server_sg        # Beacon traffic to the phase listeners
  - All traffic: 0.0.0.0/0             # Updates
```

### C2 Server Security Group (`c2_team_server_sg`)

All three phase servers share this group:
```yaml
Inbound:
  - Port 443: proxy_redirector_sg   # Beacon traffic from redirectors (listener port)
  - Port 50050: dashboard_sg        # CS client tunnel from Dashboard Server (via peering)
  - Port 50050: attack_box_sg       # CS client from attack box (direct)
  - Port 50443: dashboard_sg        # CS REST API from Dashboard Server (via peering)
  - Port 22: dashboard_sg           # SSH management from Dashboard Server (via peering)
  - Port 22: attack_box_sg          # SSH from attack box
  - Port 22: management_cidr_blocks # SSH break-glass fallback
Outbound:
  - All traffic: 0.0.0.0/0
```

> Phase isolation is operational (separate servers, profiles, listeners), not network-level — the three servers share one SG. Subnet/AZ separation provides the network-layer split.

### Attack Box Security Group (`attack_box_sg`)
```yaml
Inbound:
  - Port 3389 (RDP): dashboard_sg   # RDP tunnel from Dashboard Server (via peering)
  - Port 22 (SSH): dashboard_sg     # SSH from Dashboard Server (via peering)
  - Port 5985 (WinRM): dashboard_sg # TESTING ONLY
Outbound:
  - All traffic: 0.0.0.0/0
```

## SSL/TLS Options

Same options as the other C2 modes — Let's Encrypt (standard), ACM with domain fronting (advanced), or self-signed (testing only). See the [C2 Ad-Hoc SSL/TLS section](./c2-adhoc.md#ssltls-options) for the full comparison and certificate-flow diagrams. With phase-based operations you will commonly pair **different domains** with different phases (e.g., a disposable domain on staging, a clean long-haul domain) so a single domain burn only affects one phase.

## Cost Breakdown

### Monthly Cost: ~$220-260

| Resource | Type | Cost/Month |
|----------|------|------------|
| C2 Server (Staging) | t3.medium (24/7) | ~$30 |
| C2 Server (Post-Ex) | t3.medium (24/7) | ~$30 |
| C2 Server (Long-Haul) | t3.medium (24/7) | ~$30 |
| Redirector 1 | t3.small (24/7) | ~$15 |
| Redirector 2 | t3.small (24/7) | ~$15 |
| Attack Box | t2.large (24/7) | ~$50 |
| NAT Gateway | Always on | ~$32 |
| EBS Storage | ~120GB total | ~$12 |
| Data Transfer | Minimal | ~$5-10 |
| S3 | CS files + scripts | <$1 |
| **Total** | | **~$220-260** |

The delta over purple team (~$30/month) is the third t3.medium team server. Disabling a phase (`enabled = false`) removes its server and its cost. Long-haul servers, by design, run for the longest — factor that into engagement budgeting and stop the staging/post-ex servers when an engagement enters its persistence phase.

## When to Use

**Choose C2 Full Red Team if:**
- The engagement runs **4+ weeks** and needs phase-based compartmentalization
- You want a dedicated server (and profile/domain) per operational phase
- OpSec requirements demand that a staging burn never exposes post-ex or long-haul access
- You are running a full red-team simulation rather than a scoped pentest

**Step down to [C2 Purple Team](./c2-purple.md) if** you only need redundancy/parallel operators without phase separation, or to [C2 Ad-Hoc](./c2-adhoc.md) for a short single-server engagement.

## Dashboard Server (Production Control Plane)

The dashboard runs on a dedicated AWS EC2 instance in its own VPC. It is the **production control plane and sole SSH jump host** — the operator's entry point for this and every other deployment. There is no per-deployment SSH-relay bastion. (The operator's laptop only runs a *dev* instance of the dashboard.)

### Dashboard Infrastructure

| Component | Type | VPC / Subnet | Private IP | Public IP | Purpose |
|-----------|------|-------------|-----------|-----------|---------|
| **Dashboard Server** | t3.medium (Ubuntu 22.04) | Dashboard VPC (10.100.0.0/16) / 10.100.1.0/24 | 10.100.1.10 | EIP (Elastic IP) | Web UI, SSH jump to all deployment instances |

### Network Connectivity

- **VPC Peering:** Dashboard VPC (10.100.0.0/16) <-> C2 VPC (10.0.0.0/16)
- Route tables on both sides carry the peering routes so traffic flows without NAT or tunnels

### Dashboard Access to C2 Instances

| Target | Ports | Purpose |
|--------|-------|---------|
| Redirector 1 (10.0.1.10) | SSH/22 | nginx config, health checks |
| Redirector 2 (10.0.2.10) | SSH/22 | nginx config, health checks |
| C2 Staging (10.0.10.10) | SSH/22, CS/50050, REST/50443 | Shell, CS client tunnel, REST API |
| C2 Post-Ex (10.0.11.10) | SSH/22, CS/50050, REST/50443 | Shell, CS client tunnel, REST API |
| C2 Long-Haul (10.0.10.11) | SSH/22, CS/50050, REST/50443 | Shell, CS client tunnel, REST API |
| Attack Box (10.0.10.50) | SSH/22 | Management shell, RDP tunnel |

### Full Architecture with Dashboard

```
Operator Laptop  (dev instance of dashboard only — production runs in AWS)
   │ SSH key + IP allow-list, tunnel port 5000
   ▼
┌─────────────────────────────────────────────────┐
│  Dashboard VPC  10.100.0.0/16  (PRODUCTION)     │
│  Dashboard Server (10.100.1.10, EIP)            │
│    - Flask web UI on :5000                      │
│    - Control plane + SSH jump host              │
│    - REST API client to CS on :50443            │
└──────────────────────┬──────────────────────────┘
                       │ VPC Peering (10.100.0.0/16 ↔ 10.0.0.0/16)
                       ▼
┌─────────────────────────────────────────────────┐
│  C2 VPC  10.0.0.0/16                            │
│  DMZ (10.0.1.0/24, 10.0.2.0/24)                │
│    ├── Redirector 1 (10.0.1.10, EIP) ← :443    │
│    └── Redirector 2 (10.0.2.10, EIP) ← :443    │
│  Private (10.0.10.0/24, 10.0.11.0/24)           │
│    ├── C2 Staging   (10.0.10.10)                │
│    ├── C2 Long-Haul (10.0.10.11)                │
│    ├── C2 Post-Ex   (10.0.11.10)                │
│    └── Attack Box   (10.0.10.50)                │
│  NAT Gateway → Internet (outbound only)         │
└─────────────────────────────────────────────────┘

Beacon traffic (from targets):
  Target → HTTPS :443 → Redirector 1/2 → C2 Staging :443 (then migrate to post-ex / long-haul)
```

## Related Documentation

- [C2 Ad-Hoc Architecture](./c2-adhoc.md) — single-server baseline (shares the network design)
- [C2 Purple Team Architecture](./c2-purple.md) — two-server redundancy mode
- [Deployment Modes](../DEPLOYMENT_MODES.md) — all 12 deployment types and how modes map
- [C2 Traffic Flow](../C2_TRAFFIC_FLOW.md) — beacon/redirector/domain-fronting traffic paths
- [Windows Attack Box](./attackbox.md) — attack box internals
- [Diagrams Index](./DIAGRAMS_INDEX.md) — all architecture diagrams

## Summary

C2 Full Red Team is **three team servers, one per phase** — staging, post-exploitation, and long-haul — behind shared redundant redirectors.

- ✅ Phase compartmentalization (10.0.10.10 / 10.0.11.10 / 10.0.10.11) limits detection blast radius
- ✅ Per-phase profiles/domains; each phase independently configurable and toggleable
- ✅ Same clean network shape as ad-hoc and purple, scaled to three servers
- ✅ Dashboard Server is the sole jump host — no per-deployment bastion

**Cost**: ~$220-260/month. The right choice for long, OpSec-sensitive, full red-team engagements.
