# GOAD Mini - Single DC Training Lab

## Overview

GOAD Mini is the most cost-effective and simplest GOAD deployment, perfect for learning Active Directory attack techniques without the complexity of multi-domain environments.

## Architecture Components

### Infrastructure

| Component | IP Address | Instance Type | Subnet | Purpose |
|-----------|-----------|---------------|--------|---------|
| **Jumpbox** | 192.168.56.100 | t2.micro | Public (.64/26) | SSH gateway with Elastic IP |
| **DC01 (kingslanding)** | 192.168.56.10 | t2.medium | Private (.0/26) | Domain Controller - sevenkingdoms.local |
| **Team Server** | 192.168.56.40 | t2.medium | Private (.0/26) | Cobalt Strike server (port 50050) |
| **Attack Box** | 192.168.56.50 | t2.large | Private (.0/26) | Windows Server 2022 with CS Client + tools |

### Network Architecture

```
GOAD VPC: 192.168.56.0/24
├── Public Subnet: 192.168.56.64/26
│   ├── Jumpbox (.100) — Ubuntu, Elastic IP, SSH gateway
│   ├── Internet Gateway — bidirectional internet for public subnet
│   └── NAT Gateway — outbound-only internet for private subnet
│
└── Private Subnet: 192.168.56.0/26
    ├── DC01 kingslanding (.10) — Win Server 2019, sevenkingdoms.local
    ├── Team Server (.40) — Ubuntu, CS port 50050
    └── Attack Box (.50) — Win Server 2022, CS Client + offensive tools
```

**Two subnets, not one:** The jumpbox sits in the **public subnet** with an Elastic IP. All AD VMs, the Team Server, and Attack Box sit in the **private subnet** with no public IPs. The jumpbox is now a **legacy/fallback SSH gateway** — the primary operator entry point is the AWS-hosted **Dashboard Server**, which peers with this GOAD VPC and reaches every instance directly (see the Dashboard Server section below).

#### NAT Gateway

The NAT Gateway is **physically deployed in the public subnet** (it needs an Elastic IP and IGW access to function), but it **serves the private subnet**. This is standard AWS architecture:

1. Private subnet route table points `0.0.0.0/0 → NAT Gateway`
2. When a private instance (e.g., DC01) needs internet (Windows updates, tool downloads), traffic flows: `DC01 → VPC Router → NAT GW (public subnet) → IGW → Internet`
3. The NAT translates the private IP to its own public EIP for the outbound connection
4. **Inbound connections from the internet cannot reach private instances** — NAT is outbound-only

The jumpbox reaches private instances via **internal VPC routing** (not through the NAT). Subnets in the same VPC communicate directly through the VPC router.

#### Traffic Flows

| Flow | Path | Purpose |
|------|------|---------|
| Operator → Dashboard Server | SSH key + IP allow-list → Dashboard EIP | Primary entry point (jump host) |
| Dashboard → all GOAD instances | VPC peering (direct routes) | Lab access, CS tunnel, RDP/WinRM |
| Operator → Jumpbox (fallback) | SSH → IGW → Jumpbox (public IP) | Legacy management access |
| Jumpbox → AD VMs (fallback) | Internal VPC routing (direct) | Lab access, RDP/WinRM |
| AD VMs → Internet | Private subnet → NAT GW → IGW | Windows updates, downloads |
| Team Server ↔ Attack Box | Internal VPC routing (CS 50050) | CS client to server |

### Security Group

GOAD uses a **single shared security group** (`goad_sg`) for all instances:

```yaml
Inbound Rules:
  - All traffic: From within VPC CIDR (192.168.56.0/24)
  - SSH (22): From management_cidr_blocks
  - RDP (3389): From management_cidr_blocks
  - WinRM (5985/5986): From management_cidr_blocks
Outbound Rules:
  - HTTP/HTTPS (80/443): To anywhere (updates)
  - DNS (53): To anywhere
  - ICMP: To anywhere
  - All traffic: Within VPC CIDR
```

> **Note:** The shared security group is intentional — GOAD labs are deliberately vulnerable training environments where internal traffic should flow freely.

## Key Features

### 1. Single Domain Environment
- **Domain**: sevenkingdoms.local
- **Domain Controller**: DC01 kingslanding (192.168.56.10, Windows Server 2019)
- **Simplified AD structure** for learning fundamentals

### 2. Cobalt Strike Infrastructure
- **Team Server** (192.168.56.40) — dedicated Ubuntu instance in private subnet running CS on port 50050
- **Attack Box** (192.168.56.50) — Windows Server 2022 with CS Client GUI, PowerSploit, VS Code, WSL2, and red team tools
- **Access**: Operator tunnels through the **Dashboard Server** to reach Team Server (`ssh -L 50050:192.168.56.40:50050 ubuntu@<dashboard-eip>`); the jumpbox is a legacy fallback
- **Attack Box access**: RDP tunnel through the Dashboard Server (`ssh -L 13389:192.168.56.50:3389 ubuntu@<dashboard-eip>`)

### 3. Built-in Vulnerabilities

The GOAD Mini lab includes common AD misconfigurations:

- ✅ **Kerberoasting** - Service accounts with SPNs
- ✅ **AS-REP Roasting** - Users with "Do not require Kerberos preauthentication"
- ✅ **Weak Passwords** - Common password patterns
- ✅ **Misconfigured Permissions** - Over-privileged users
- ✅ **Unconstrained Delegation** - Computer accounts trusted for delegation

## Deployment

### Prerequisites
- AWS Account with appropriate permissions
- terraform.tfvars configured with:
  ```hcl
  deployment_type = "goad-mini"
  ```

### Deployment Steps

1. **Configure via Web App**:
   ```
   Navigate to: http://localhost:5000
   Configuration → GOAD Lab Type → Select "GOAD Mini"
   Deploy → Start Deployment
   ```

2. **Or via CLI**:
   ```bash
   cd terraform
   terraform init
   terraform plan
   terraform apply
   ```

3. **Wait for provisioning** (approximately 20-30 minutes)
   - Jumpbox provisions first
   - DC01 provisions and promotes to domain controller
   - Lab configuration scripts run automatically

## Access Methods

The **Dashboard Server** (AWS-hosted, own VPC peered with this lab) is the operator entry point and jump host. All tunnels below run THROUGH the dashboard's EIP, which reaches every lab instance directly over VPC peering. The jumpbox remains only as a legacy fallback.

### 1. Dashboard Web UI (Recommended)
```bash
ssh -L 5000:localhost:5000 ubuntu@<dashboard-eip>
# Open http://localhost:5000 — in-browser terminal, topology, CS beacons, Ansible provisioning
```

### 2. Cobalt Strike Client Connection
```bash
# SSH tunnel to Team Server through the Dashboard Server (from operator laptop)
ssh -L 50050:192.168.56.40:50050 -i ~/.ssh/your-key.pem ubuntu@<dashboard-eip>

# Then connect CS Client to localhost:50050
# Password: [Retrieved from deployment output]
```

### 3. RDP to Attack Box (via Dashboard tunnel)
```bash
# SSH tunnel for RDP (from operator laptop)
ssh -L 13389:192.168.56.50:3389 -i ~/.ssh/your-key.pem ubuntu@<dashboard-eip>

# Then RDP to localhost:13389
# User: Administrator | Password: [From deployment output]
```

### 4. RDP to Domain Controller (via Dashboard)
```bash
# SSH tunnel for DC01 RDP
ssh -L 3391:192.168.56.10:3389 -i ~/.ssh/your-key.pem ubuntu@<dashboard-eip>

# Then RDP to localhost:3391
xfreerdp /v:localhost:3391 /u:Administrator /p:'<password>' /cert:ignore
```

> **Legacy fallback (jumpbox):** if the Dashboard Server is unavailable, the jumpbox EIP still works as the SSH gateway — swap `<dashboard-eip>` for `<jumpbox-eip>` in any tunnel above, or `ssh -i ~/.ssh/your-key.pem ubuntu@<jumpbox-eip>` for a direct shell.

## Attack Scenarios

### Scenario 1: Initial Enumeration
```bash
# From jumpbox
nmap -p 88,389,445,3389 192.168.56.10
ldapsearch -x -H ldap://192.168.56.10 -b "DC=sevenkingdoms,DC=local"
```

### Scenario 2: Kerberoasting
```bash
# Using Impacket
GetUserSPNs.py sevenkingdoms.local/user:password -dc-ip 192.168.56.10 -request
```

### Scenario 3: BloodHound Collection
```bash
bloodhound-python -d sevenkingdoms.local -u user -p password -ns 192.168.56.10 -c all
```

### Scenario 4: Cobalt Strike Beacon Deployment
1. Generate payload from CS client
2. Upload to DC01 via SMB
3. Execute via WMI/PsExec
4. Beacon calls back to the Team Server (192.168.56.40)

## Cost Breakdown

### Monthly Cost Estimate: ~$125-175

| Resource | Type | Monthly Cost |
|----------|------|--------------|
| Jumpbox | t2.micro (24/7) | ~$8 |
| DC01 | t2.medium (24/7) | ~$33 |
| Team Server | t2.medium (24/7) | ~$33 |
| Attack Box | t2.large (24/7) | ~$67 |
| EBS Storage | 100GB (attack box) + 30GB x3 | ~$15 |
| NAT Gateway | Always on | ~$32 |
| Data Transfer | Minimal | ~$5-10 |
| S3 Storage | Scripts & Tools | <$1 |
| **Total** | | **~$125-175** |

### Cost Optimization Tips

1. **Stop when not in use**:
   ```bash
   aws ec2 stop-instances --instance-ids <jumpbox-id> <dc01-id>
   # Saves ~70% while preserving data
   ```

2. **Use scheduled shutdowns**:
   - Implement auto-stop at night
   - Auto-start during business hours
   - Potential savings: 50-60%

3. **Delete when finished**:
   ```bash
   terraform destroy
   # Complete cleanup
   ```

## Troubleshooting

### Issue: Cannot connect to Cobalt Strike
**Solution**: SSH tunnel through the Dashboard Server to Team Server (jumpbox tunnel is a fallback)
```bash
# Ensure tunnel is active
ssh -L 50050:192.168.56.40:50050 -i ~/.ssh/key.pem ubuntu@<dashboard-eip>
# Then connect CS Client to localhost:50050
```

### Issue: DC01 not responding
**Solution**: Check if domain promotion completed (can take 10-15 min after instance boot)
```bash
# From jumpbox
ssh ubuntu@<jumpbox-eip>
ping 192.168.56.10
nslookup sevenkingdoms.local 192.168.56.10
```

### Issue: Beacon won't call back
**Solution**: Verify Team Server can reach DC01 (both in private subnet, should route directly)
```bash
# From jumpbox, SSH to team server
ssh ubuntu@192.168.56.40
nc -zv 192.168.56.10 445
nc -zv 192.168.56.10 135
```

## Dashboard Server (Production Control Plane)

The dashboard runs on a dedicated AWS EC2 instance in its own VPC. This is the **production control plane and SSH jump host** — the operator entry point that all deployments (including this lab) branch from. It reaches every GOAD instance directly over VPC peering, so no SSH-hopping through the jumpbox is needed; the jumpbox is a legacy fallback. (The operator's laptop only runs a *dev* instance of the dashboard for development.)

### Dashboard Infrastructure

| Component | Type | VPC / Subnet | Private IP | Public IP | Purpose |
|-----------|------|-------------|-----------|-----------|---------|
| **Dashboard Server** | t3.medium (Ubuntu 22.04) | Dashboard VPC (10.100.0.0/16) / 10.100.1.0/24 | 10.100.1.10 | EIP (Elastic IP) | Web UI, SSH relay to all GOAD instances |

### Network Connectivity

The Dashboard VPC peers with the GOAD VPC, giving the dashboard server direct routable access to every instance in the lab:

- **VPC Peering:** Dashboard VPC (10.100.0.0/16) <-> GOAD VPC (192.168.56.0/24)
- Route tables on both sides carry the peering routes so traffic flows without NAT or tunnels

### Dashboard Access to GOAD Instances

| Target | Ports | Purpose |
|--------|-------|---------|
| Jumpbox (192.168.56.100) | SSH/22 | Ansible provisioning, lab management |
| Team Server (192.168.56.40) | SSH/22, CS/50050 | Shell, CS client tunnel |
| Attack Box (192.168.56.50) | SSH/22 | Management shell, RDP tunnel |
| DC01 kingslanding (192.168.56.10) | RDP/3389, WinRM/5985 | Lab access (via dashboard tunnel) |

Security groups allow inbound traffic from the dashboard's security group (or the Dashboard VPC CIDR) on the ports listed above.

### Operator Access via Dashboard

The operator creates a single tunnel to the dashboard and uses the web UI — the dashboard reaches every GOAD instance directly over VPC peering (no jumpbox hop):

```bash
# SSH tunnel from operator laptop to dashboard (port 5000)
ssh -i key.pem -L 5000:127.0.0.1:5000 ubuntu@<dashboard-eip>

# Open browser
http://localhost:5000
```

From the web UI the operator can:
- **Terminal tab** — in-browser SSH to the jumpbox, team server, or attack box
- **Topology graph** — visual map of the GOAD lab with live instance status
- **Beacon management** — interact with CS beacons via the REST API
- **GOAD provisioning** — trigger and monitor Ansible provisioning runs

### Full Architecture with Dashboard

```
Operator Laptop  (dev instance of dashboard only — production runs in AWS)
   │
   │ SSH key + IP allow-list, tunnel port 5000
   ▼
┌─────────────────────────────────────────────────┐
│  Dashboard VPC  10.100.0.0/16  (PRODUCTION)     │
│  Subnet 10.100.1.0/24                           │
│                                                 │
│  Dashboard Server (10.100.1.10, EIP)            │
│    - Flask web UI on :5000                      │
│    - Control plane + SSH jump host              │
│    - Direct SSH to all GOAD instances           │
└──────────────────────┬──────────────────────────┘
                       │ VPC Peering
                       │ (10.100.0.0/16 ↔ 192.168.56.0/24)
                       ▼
┌─────────────────────────────────────────────────┐
│  GOAD VPC  192.168.56.0/24                      │
│                                                 │
│  Public Subnet (192.168.56.64/26)               │
│    ├── Jumpbox (.100, EIP) — Ansible, SSH GW    │
│    ├── Internet Gateway                         │
│    └── NAT Gateway (outbound for private)       │
│                                                 │
│  Private Subnet (192.168.56.0/26)               │
│    ├── DC01 kingslanding (.10) — sevenkingdoms   │
│    ├── Team Server (.40) — CS :50050            │
│    └── Attack Box (.50) — CS Client + tools     │
└─────────────────────────────────────────────────┘
```

### Dashboard vs Jumpbox

| | Dashboard Server (Primary) | Jumpbox (Legacy / Fallback) |
|---|---|---|
| **Role** | Production control plane + SSH jump host | Fallback SSH gateway only |
| **Operator connects to** | Dashboard EIP via SSH tunnel (:5000) | Jumpbox EIP via SSH (fallback) |
| **Reaches private instances via** | Direct from dashboard (VPC peering) | SSH hop from jumpbox shell |
| **CS client access** | Terminal tab in web UI, or `ssh -L 50050:192.168.56.40:50050 ...@<dashboard-eip>` | `ssh -L 50050:192.168.56.40:50050 ...@<jumpbox-eip>` |
| **Management UI** | Full web UI (topology, terminal, beacons) | None (CLI only) |
| **Primary entry point?** | Yes — all deployments branch from here | No — only if the dashboard is unavailable |

## Learning Path

### Week 1: Reconnaissance
- Network scanning
- LDAP enumeration
- User enumeration
- Share enumeration

### Week 2: Credential Attacks
- Kerberoasting
- AS-REP Roasting
- Password spraying
- Credential stuffing

### Week 3: Lateral Movement
- Pass-the-Hash
- Pass-the-Ticket
- WMI/PsExec
- RDP hijacking

### Week 4: Persistence & Domain Admin
- DCSync
- Golden Ticket
- Silver Ticket
- Skeleton Key

## Best Practices

### Security
- ✅ **Always restrict management IPs** in security groups
- ✅ **Use strong passwords** for teamserver
- ✅ **Never expose to public internet** without IP restrictions
- ✅ **Destroy when not in use** to prevent unauthorized access

### Operations
- ✅ **Take EC2 snapshots** before risky operations
- ✅ **Document your attacks** for reporting practice
- ✅ **Practice cleanup** - remove artifacts after exploitation
- ✅ **Use the lab responsibly** - it's for learning only

## References

- [GOAD GitHub Repository](https://github.com/Orange-Cyberdefense/GOAD)
- [GOAD Documentation](https://orange-cyberdefense.github.io/GOAD/)
- [Cobalt Strike Documentation](https://hstechdocs.helpsystems.com/manuals/cobaltstrike/)
- [Active Directory Attack Cheatsheet](https://github.com/S1ckB0y1337/Active-Directory-Exploitation-Cheat-Sheet)

## Summary

GOAD Mini is the **perfect starting point** for learning AD attacks:
- ✅ **Low cost** (~$125-175/month, or ~$40 with stop/start)
- ✅ **Simple setup** (1 DC + Jumpbox + Team Server + Attack Box)
- ✅ **Fast deployment** (20-30 minutes)
- ✅ **All essential vulnerabilities** included
- ✅ **Dedicated Attack Box** with CS Client, PowerSploit, and red team tools
- ✅ **Proper network isolation** — private subnet for lab, public for access only

Perfect for beginners and budget-conscious learners!
