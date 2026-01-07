# GOAD Integration Plan

## Overview

This document outlines the plan to integrate [GOAD (Game Of Active Directory)](https://github.com/Orange-Cyberdefense/GOAD) into our Red Team Infrastructure web application. GOAD is a pentest Active Directory lab project that provides vulnerable AD environments for practicing attack techniques.

### What is GOAD?

GOAD creates realistic, vulnerable Active Directory environments with:
- Multiple forests and domains
- Pre-configured vulnerabilities and misconfigurations
- Various lab sizes for different use cases

### Available Labs

| Lab | VMs | Forests | Domains | Description | Est. AWS Cost |
|-----|-----|---------|---------|-------------|---------------|
| **GOAD** | 5 | 2 | 3 | Full lab - complete AD environment | ~$300-400/mo |
| **GOAD-Light** | 3 | 1 | 2 | Smaller lab for limited resources | ~$180-250/mo |
| **GOAD-Mini** | 1 | 1 | 1 | Minimalist - sevenkingdoms.local only | ~$60-90/mo |
| **SCCM** | 4 | 1 | 1 | Microsoft Configuration Manager lab | ~$250-350/mo |
| **NHA** | 5 | 1 | 2 | Challenge lab (no schema provided) | ~$300-400/mo |
| **MINILAB** | 2 | 1 | 1 | Basic DC + Workstation | ~$120-180/mo |

### Key Discovery: GOAD Already Has a Jump Box!

✅ **Good news**: GOAD's AWS provider **already creates a "jumpbox" VM** that:
- Is created alongside the lab VMs
- Has SSH access to all lab machines
- Stores SSH keys in `goad/workspaces/<instance_folder>/ssh_keys`
- Can be accessed via `ssh_jumpbox` command
- Supports SOCKS proxy via `ssh_jumpbox_proxy <port>`

### Architecture Overview (AWS)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AWS VPC                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        GOAD Network                                  │    │
│  │                                                                      │    │
│  │   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │    │
│  │   │  DC01        │    │  DC02        │    │  DC03        │          │    │
│  │   │  (Win2019)   │    │  (Win2019)   │    │  (Win2016)   │          │    │
│  │   │  10.x.x.10   │    │  10.x.x.11   │    │  10.x.x.12   │          │    │
│  │   └──────────────┘    └──────────────┘    └──────────────┘          │    │
│  │                                                                      │    │
│  │   ┌──────────────┐    ┌──────────────┐                              │    │
│  │   │  SRV02       │    │  SRV03       │                              │    │
│  │   │  (Win2019)   │    │  (Win2019)   │                              │    │
│  │   │  10.x.x.22   │    │  10.x.x.23   │                              │    │
│  │   └──────────────┘    └──────────────┘                              │    │
│  │                                                                      │    │
│  │   ┌──────────────────────────────────────────────────────────────┐  │    │
│  │   │                    GOAD Jumpbox (Ubuntu)                      │  │    │
│  │   │  - Ansible installed                                          │  │    │
│  │   │  - SSH access to all VMs                                      │  │    │
│  │   │  - SOCKS proxy capability                                     │  │    │
│  │   └──────────────────────────────────────────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Our C2 Infrastructure                             │    │
│  │                                                                      │    │
│  │   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │    │
│  │   │  C2 Server   │    │  Redirector  │    │  Our Bastion │          │    │
│  │   │  (Cobalt)    │◄───│  (Public)    │◄───│  (Windows)   │          │    │
│  │   │  Private     │    │  10.x.x.x    │    │  Public IP   │          │    │
│  │   └──────────────┘    └──────────────┘    └──────────────┘          │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│                         VPC Peering / Security Groups                        │
│                    (Allow traffic between C2 and GOAD)                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Foundation & Integration (2-3 weeks)

### 1.1 GOAD Repository Integration

**Objective**: Clone and integrate GOAD into our infrastructure

**Tasks**:
- [ ] Add GOAD as a Git submodule or clone into `tools/goad/`
- [ ] Create wrapper scripts to invoke GOAD with our AWS credentials
- [ ] Modify GOAD's AWS provider configuration to use our VPC/networking
- [ ] Create Terraform modules to peer GOAD VPC with our C2 VPC

**Technical Details**:
```bash
# Add GOAD as submodule
git submodule add https://github.com/Orange-Cyberdefense/GOAD.git tools/goad

# Or clone for more control
git clone https://github.com/Orange-Cyberdefense/GOAD.git tools/goad
```

### 1.2 Web App UI - Lab Selection

**Objective**: Add GOAD lab selection to Configuration page

**New UI Elements**:
```
┌─────────────────────────────────────────────────────────────┐
│  🏰 Target Lab Environment (Optional)                        │
│  ─────────────────────────────────────────────────────────  │
│                                                              │
│  Lab Type: [Dropdown]                                        │
│    ○ None (C2 Infrastructure Only)                          │
│    ○ GOAD (5 VMs, 2 forests, 3 domains) - ~$350/mo          │
│    ○ GOAD-Light (3 VMs, 1 forest, 2 domains) - ~$200/mo     │
│    ○ GOAD-Mini (1 VM, 1 domain) - ~$75/mo                   │
│    ○ SCCM (4 VMs, SCCM environment) - ~$300/mo              │
│    ○ NHA Challenge (5 VMs, no hints) - ~$350/mo             │
│    ○ MINILAB (2 VMs, basic setup) - ~$150/mo                │
│                                                              │
│  [i] Labs provide vulnerable AD environments for testing     │
│      your C2 infrastructure against realistic targets.       │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ 📦 GOAD Lab Overview                                     ││
│  │                                                          ││
│  │  5 VMs  │  2 Forests  │  3 Domains  │  ~$350/mo         ││
│  │                                                          ││
│  │  Domains: sevenkingdoms.local, north.sevenkingdoms.local,││
│  │           essos.local                                    ││
│  │                                                          ││
│  │  Includes: Kerberoasting, AS-REP Roasting, DCSync,      ││
│  │            Pass-the-Hash, NTLM Relay, and more...       ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### 1.3 Backend API Endpoints

**New Endpoints**:
```
POST /api/goad/deploy          - Deploy selected GOAD lab
GET  /api/goad/status          - Get GOAD deployment status
GET  /api/goad/labs            - List available labs with details
POST /api/goad/destroy         - Destroy GOAD lab
GET  /api/goad/credentials     - Get lab credentials/connection info
POST /api/goad/start           - Start stopped lab VMs
POST /api/goad/stop            - Stop lab VMs (save costs)
```

---

## Phase 2: Network Integration & C2 Connectivity (2-3 weeks)

### 2.1 VPC Peering / Network Connectivity

**Objective**: Enable communication between C2 infrastructure and GOAD lab

**Options**:

**Option A: VPC Peering (Recommended)**
```hcl
# Terraform - VPC Peering
resource "aws_vpc_peering_connection" "c2_to_goad" {
  vpc_id        = module.c2_vpc.vpc_id
  peer_vpc_id   = module.goad_vpc.vpc_id
  auto_accept   = true
  
  tags = {
    Name = "C2-to-GOAD-Peering"
  }
}

# Route tables updated to allow traffic
resource "aws_route" "c2_to_goad" {
  route_table_id            = module.c2_vpc.private_route_table_id
  destination_cidr_block    = "192.168.x.0/24"  # GOAD CIDR
  vpc_peering_connection_id = aws_vpc_peering_connection.c2_to_goad.id
}
```

**Option B: Single VPC (Simpler)**
- Deploy GOAD into the same VPC as C2 infrastructure
- Use security groups to control access
- Simpler but less isolated

### 2.2 Security Group Configuration

**Allow C2 to reach GOAD targets**:
```hcl
# Allow C2 server to reach GOAD network
resource "aws_security_group_rule" "c2_to_goad" {
  type              = "egress"
  from_port         = 0
  to_port           = 65535
  protocol          = "tcp"
  cidr_blocks       = ["192.168.x.0/24"]  # GOAD network
  security_group_id = module.c2_server.security_group_id
}

# Allow GOAD to receive traffic from C2
resource "aws_security_group_rule" "goad_from_c2" {
  type              = "ingress"
  from_port         = 0
  to_port           = 65535
  protocol          = "tcp"
  cidr_blocks       = ["10.0.0.0/16"]  # C2 network
  security_group_id = module.goad.security_group_id
}
```

### 2.3 Cobalt Strike → GOAD Connectivity

**How to get initial access to GOAD from Cobalt Strike**:

1. **Via GOAD Jumpbox (Recommended)**:
   ```
   Our Bastion → SSH → GOAD Jumpbox → SOCKS Proxy → GOAD Network
   ```
   - Use GOAD's built-in `ssh_jumpbox_proxy` feature
   - Configure Cobalt Strike to use SOCKS proxy
   - All C2 traffic tunneled through jumpbox

2. **Direct Network Access**:
   ```
   C2 Server → VPC Peering → GOAD Network
   ```
   - Beacon payload delivered to GOAD workstation
   - Beacon calls back through redirector
   - Requires proper routing between VPCs

3. **Initial Access Methods**:
   - **Phishing simulation**: Upload payload to GOAD workstation
   - **SMB/WinRM**: Use known credentials from GOAD
   - **Exploit vulnerabilities**: GOAD has intentional vulns

**GOAD Default Credentials** (from lab config):
```
Domain: sevenkingdoms.local
Users with weak passwords are configured
Check: ad/<lab>/data/inventory file for credentials
```

---

## Phase 3: Web App Features & Polish (2-3 weeks)

### 3.1 Deployment Manager Integration

**Add GOAD section to Deployment Manager page**:

```
┌─────────────────────────────────────────────────────────────┐
│  🏰 Target Lab (GOAD)                                        │
│  ─────────────────────────────────────────────────────────  │
│                                                              │
│  Status: ✅ Running                                          │
│  Lab Type: GOAD (Full)                                       │
│  VMs: 5/5 Running                                            │
│  Uptime: 2h 34m                                              │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ DC01 (sevenkingdoms.local)  │ Running │ 192.168.56.10   ││
│  │ DC02 (north.local)          │ Running │ 192.168.56.11   ││
│  │ DC03 (essos.local)          │ Running │ 192.168.56.12   ││
│  │ SRV02 (Member Server)       │ Running │ 192.168.56.22   ││
│  │ SRV03 (Member Server)       │ Running │ 192.168.56.23   ││
│  │ Jumpbox (Ubuntu)            │ Running │ 3.x.x.x (Public)││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  [⏸ Stop Lab]  [🔄 Restart]  [📋 Credentials]  [🗑 Destroy]  │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Credentials & Connection Info

**Display GOAD credentials and connection commands**:

```
┌─────────────────────────────────────────────────────────────┐
│  📋 Lab Credentials & Access                                 │
│  ─────────────────────────────────────────────────────────  │
│                                                              │
│  🔑 Domain Credentials:                                      │
│  ───────────────────────                                     │
│  Domain: SEVENKINGDOMS                                       │
│  Admin: Administrator / <password>                           │
│                                                              │
│  Domain: NORTH                                               │
│  Admin: Administrator / <password>                           │
│                                                              │
│  🔗 Jumpbox Access:                                          │
│  ───────────────────                                         │
│  ssh -i keys/jumpbox.pem ubuntu@3.x.x.x                     │
│                                                              │
│  🧦 SOCKS Proxy (for C2):                                    │
│  ───────────────────────                                     │
│  ssh -D 1080 -i keys/jumpbox.pem ubuntu@3.x.x.x             │
│  Then configure Cobalt Strike: Proxy → SOCKS4 → 127.0.0.1:1080│
│                                                              │
│  📡 C2 Integration:                                          │
│  ─────────────────                                           │
│  1. Start SOCKS proxy to jumpbox                            │
│  2. Configure CS listener with proxy                         │
│  3. Generate payload for target                              │
│  4. Deliver to GOAD workstation                              │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 Cost Management Features

**Add cost tracking and optimization**:
- Show estimated monthly cost for GOAD lab
- Add "Stop Lab" button to pause VMs (save ~70% cost when not in use)
- Show actual AWS costs if possible (CloudWatch/Cost Explorer API)
- Warning when lab has been running for extended period

---

## Operator Access Methods (Connecting to Your C2 Infrastructure)

This section explains how **YOU** (the operator) connect from your home laptop/workstation to the Cobalt Strike team server. This is separate from how beacons communicate.

### Understanding the Two Types of Connections

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CONNECTION TYPES                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. OPERATOR CONNECTION (You → Team Server)                                 │
│     ─────────────────────────────────────                                   │
│     Your CS Client GUI connects to Team Server on port 50050                │
│     This is for YOU to control the team server                              │
│                                                                              │
│  2. BEACON CONNECTION (Target → Redirector → Team Server)                   │
│     ─────────────────────────────────────────────────                       │
│     Compromised hosts call back through the redirector                      │
│     This is how IMPLANTS communicate                                        │
│                                                                              │
│  ⚠️  These are DIFFERENT paths! Redirectors are for beacons, not for you!   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Access Method Options

The web app will present these options clearly after deployment:

---

#### Option 1: SSH Tunnel through Bastion (Recommended) ✅

**Best for**: Most users, secure remote access, dynamic home IPs

**How it works**:
```
┌──────────────┐     SSH Tunnel      ┌──────────────┐     Internal     ┌──────────────┐
│ Your Laptop  │ ──────────────────► │   Bastion    │ ───────────────► │  C2 Server   │
│              │   Port 50050        │  (Public IP) │                  │ (Private IP) │
│ CS Client    │   Forwarded         │              │                  │  Port 50050  │
│ localhost    │                     │              │                  │              │
└──────────────┘                     └──────────────┘                  └──────────────┘
```

**Steps**:
1. **Open terminal on your laptop**
2. **Create SSH tunnel**:
   ```bash
   ssh -i ~/.ssh/your-key.pem -L 50050:<c2-private-ip>:50050 ubuntu@<bastion-public-ip>
   ```
3. **Keep terminal open** (maintains the tunnel)
4. **Open Cobalt Strike client**
5. **Connect to**: `127.0.0.1:50050`
6. **Enter teamserver password**

**Pros**:
- ✅ Your home IP doesn't need to be whitelisted
- ✅ All traffic encrypted through SSH
- ✅ Works with dynamic IPs
- ✅ Only port 22 exposed on bastion

**Cons**:
- ❌ Requires SSH key management
- ❌ Must keep terminal session open

---

#### Option 2: RDP to Bastion, Run CS Client There

**Best for**: Users who prefer GUI, don't want to install CS locally

**How it works**:
```
┌──────────────┐       RDP          ┌──────────────┐     Internal     ┌──────────────┐
│ Your Laptop  │ ──────────────────►│   Bastion    │ ───────────────► │  C2 Server   │
│              │   Port 3389        │  (Windows)   │                  │ (Private IP) │
│ RDP Client   │                    │              │                  │  Port 50050  │
│              │                    │  CS Client   │                  │              │
└──────────────┘                    │  runs HERE   │                  │              │
                                    └──────────────┘                  └──────────────┘
```

**Steps**:
1. **Open RDP client** (mstsc on Windows, Microsoft Remote Desktop on Mac)
2. **Connect to**: `<bastion-public-ip>:3389`
3. **Login** with Windows credentials (provided after deployment)
4. **Open Cobalt Strike** on the bastion (pre-installed or download)
5. **Connect to team server**: `<c2-private-ip>:50050`

**Pros**:
- ✅ No local CS installation needed
- ✅ Full Windows environment
- ✅ CS artifacts stay on bastion, not your laptop

**Cons**:
- ❌ Latency in GUI operations
- ❌ Requires Windows license on bastion
- ❌ RDP port exposed (should be restricted to your IP)

---

#### Option 3: Direct Connection (Simplest but Least Flexible)

**Best for**: Static IP users, quick testing

**How it works**:
```
┌──────────────┐      Direct        ┌──────────────┐
│ Your Laptop  │ ──────────────────►│  C2 Server   │
│              │   Port 50050       │ (Public IP)  │
│ CS Client    │   (Whitelisted)    │              │
└──────────────┘                    └──────────────┘
```

**Steps**:
1. **Find your public IP**: `curl ifconfig.me`
2. **Add to configuration**: Include your IP in `management_cidr_blocks` (e.g., `203.0.113.50/32`)
3. **Deploy/Update infrastructure**
4. **Open Cobalt Strike client**
5. **Connect to**: `<c2-public-ip>:50050`

**Pros**:
- ✅ Simplest setup
- ✅ No tunneling required
- ✅ Lowest latency

**Cons**:
- ❌ Your IP must be whitelisted
- ❌ If your IP changes, you lose access
- ❌ More exposure of team server port

---

### Web App UI for Access Methods

After deployment, the **Deployment Manager** page will show:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  🔗 Connect to Your C2 Team Server                                          │
│  ───────────────────────────────────────────────────────────────────────── │
│                                                                              │
│  Choose your connection method:                                             │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 🔐 SSH Tunnel (Recommended)                                          │   │
│  │                                                                      │   │
│  │ Run this command in your terminal:                                   │   │
│  │ ┌──────────────────────────────────────────────────────────────────┐│   │
│  │ │ ssh -i ~/.ssh/redteam-key.pem -L 50050:10.0.2.15:50050 \         ││   │
│  │ │     ubuntu@54.123.45.67                                          ││   │
│  │ └──────────────────────────────────────────────────────────────────┘│   │
│  │                                                    [📋 Copy Command] │   │
│  │                                                                      │   │
│  │ Then connect Cobalt Strike to: 127.0.0.1:50050                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 🖥️ RDP to Bastion                                                    │   │
│  │                                                                      │   │
│  │ Bastion IP: 54.123.45.67                                            │   │
│  │ Username: Administrator                                              │   │
│  │ Password: [Click to reveal]                                          │   │
│  │                                                    [📋 Copy RDP File]│   │
│  │                                                                      │   │
│  │ Then connect CS to: 10.0.2.15:50050 (internal)                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 🌐 Direct Connection                                                 │   │
│  │                                                                      │   │
│  │ ⚠️ Requires your IP in management_cidr_blocks                       │   │
│  │                                                                      │   │
│  │ Your current IP: 203.0.113.50                                       │   │
│  │ Status: ✅ Whitelisted / ❌ Not whitelisted [Add Now]               │   │
│  │                                                                      │   │
│  │ Connect CS to: 54.200.100.50:50050                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ───────────────────────────────────────────────────────────────────────── │
│  📝 Team Server Password: ●●●●●●●●●●●● [👁 Show] [📋 Copy]                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Quick Reference Table

| Method | Setup Complexity | Security | Works with Dynamic IP | Latency |
|--------|-----------------|----------|----------------------|---------|
| **SSH Tunnel** | Medium | ⭐⭐⭐⭐⭐ | ✅ Yes | Low |
| **RDP to Bastion** | Low | ⭐⭐⭐⭐ | ✅ Yes | Medium |
| **Direct** | Low | ⭐⭐⭐ | ❌ No | Lowest |

### Troubleshooting Connection Issues

| Problem | Solution |
|---------|----------|
| SSH tunnel won't connect | Check bastion security group allows port 22 from your IP |
| CS client times out | Verify team server is running, check port 50050 is open |
| "Connection refused" | Ensure tunnel is still active, check you're connecting to correct port |
| RDP won't connect | Check port 3389 is open in security group, verify credentials |
| Direct connection fails | Confirm your IP is in `management_cidr_blocks`, redeploy if changed |

---

## Technical Considerations

### Windows Licensing
⚠️ **Important**: GOAD uses free Windows evaluation VMs (180-day limit). After expiration:
- Enter a license key, OR
- Rebuild the lab

### Network Attack Limitations
⚠️ **AWS Limitation**: The following attacks **will NOT work** in AWS:
- LLMNR poisoning
- NBTNS poisoning
- Other broadcast-based attacks

**What WILL work**:
- Network coercion attacks (PetitPotam, PrinterBug, etc.)
- Kerberos attacks (Kerberoasting, AS-REP Roasting)
- NTLM relay (with proper setup)
- Pass-the-Hash, Pass-the-Ticket
- DCSync, DCShadow
- Most AD exploitation techniques

### Resource Requirements
- **GOAD Full**: ~16 GB RAM, 8 vCPUs (t3.large instances)
- **GOAD-Light**: ~10 GB RAM, 4 vCPUs (t3.medium instances)
- **GOAD-Mini**: ~4 GB RAM, 2 vCPUs (t3.medium instance)

---

## Implementation Priority

### Must Have (MVP)
1. Lab selection dropdown in Configuration
2. GOAD deployment via backend
3. Basic status display
4. Jumpbox connection info

### Should Have
1. VPC peering automation
2. Cost estimates in UI
3. Start/Stop functionality
4. Credentials display

### Nice to Have
1. Automatic C2 proxy configuration
2. Attack playbook integration
3. Progress tracking for attacks
4. Lab reset functionality

---

## References

- [GOAD GitHub Repository](https://github.com/Orange-Cyberdefense/GOAD)
- [GOAD Documentation](https://orange-cyberdefense.github.io/GOAD/)
- [GOAD AWS Provider Docs](https://orange-cyberdefense.github.io/GOAD/providers/aws/)
- [GOAD Labs Overview](https://orange-cyberdefense.github.io/GOAD/labs/)

---

## Summary

| Phase | Duration | Key Deliverables |
|-------|----------|------------------|
| **Phase 1** | 2-3 weeks | GOAD integration, UI for lab selection, backend API |
| **Phase 2** | 2-3 weeks | VPC peering, security groups, C2 connectivity |
| **Phase 3** | 2-3 weeks | Deployment Manager integration, credentials UI, cost management |

**Total Estimated Time**: 6-9 weeks

**Key Insight**: GOAD already provides a jumpbox with SOCKS proxy capability, making C2 integration straightforward. We just need to:
1. Deploy GOAD alongside our C2 infrastructure
2. Ensure network connectivity (VPC peering or same VPC)
3. Use the jumpbox as a pivot point for Cobalt Strike traffic

