# GOAD Architecture Diagram Analysis & Corrections

## Executive Summary

After reviewing the GOAD architecture diagrams against the actual Terraform code, **critical architectural errors** were identified and corrected. The original diagrams showed a simplified "Jumpbox + Cobalt Strike" combined instance, when in reality the infrastructure deploys **THREE separate instances** with distinct roles.

---

## Critical Issues Found

### ❌ Issue #1: Missing Components

**Problem**: Original diagram showed only 2 instances:
- Jumpbox + Cobalt Strike (combined)
- DC01

**Reality**: Infrastructure deploys 4 instances:
1. **Jumpbox** (Ubuntu, `10.10.1.100`, Public subnet) - SSH gateway ONLY
2. **Team Server** (Ubuntu, `10.10.1.40`, Private subnet) - Cobalt Strike server daemon
3. **Attack Box** (Windows 2022, `10.10.1.50`, Private subnet) - CS Client GUI + Tools
4. **DC01** (Windows 2019, `10.10.1.10`, Private subnet) - Domain Controller

### ❌ Issue #2: Incorrect Architecture Pattern

**Problem**: Diagram implied operator connects directly to jumpbox for Cobalt Strike operations.

**Reality**: Multi-layer architecture with distinct separation of concerns:

```
Operator (Your Laptop)
    ↓
    SSH (port 22) → Jumpbox (Public IP, 10.10.1.100)
    ↓
    RDP Tunnel → Attack Box (Private, 10.10.1.50)
    ↓
    CS Client connects to → Team Server (Private, 10.10.1.40:50050)
    ↓
    Beacons deployed to → DC01 / GOAD Lab (Private, 10.10.1.10)
```

### ❌ Issue #3: Network Segmentation Not Clear

**Problem**: Diagram didn't clearly distinguish public vs private subnets.

**Reality**: 
- **Public Subnet** (`10.10.0.0/24`): Jumpbox ONLY - internet-facing
- **Private Subnet** (`10.10.1.0/24`): Everything else - no direct internet access

### ❌ Issue #4: Missing Component Details

**Missing from original diagram**:
- Attack Box as Windows workstation with GUI tools
- Team Server as dedicated Linux daemon (no GUI)
- S3 bucket for SSH key exchange between instances
- Separate security groups for public vs private resources
- WSL2 on Attack Box for Linux tool access

---

## Corrected Architecture

### GOAD Mini - Correct Components

| Component | Type | IP | Subnet | Purpose |
|-----------|------|------|--------|---------|
| **Jumpbox** | Ubuntu 22.04, t3.small | 10.10.1.100 | Public | SSH bastion gateway ONLY |
| **Team Server** | Ubuntu 22.04, t3.medium | 10.10.1.40 | Private | Cobalt Strike server daemon (headless) |
| **Attack Box** | Windows 2022, t3.xlarge | 10.10.1.50 | Private | CS Client GUI, Tools, WSL2 |
| **DC01** | Windows 2019, t3.medium | 10.10.1.10 | Private | Domain Controller - sevenkingdoms.local |

### Network Flow (Correct)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Operator Access Flow                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Your Laptop                                                     │
│      │                                                           │
│      │ (1) SSH to Jumpbox                                       │
│      ├──────────────► Jumpbox (Public IP)                       │
│      │                  22/tcp                                   │
│      │                                                           │
│      │ (2) RDP Tunnel through SSH                               │
│      ├──────────────► Attack Box (via Jumpbox)                  │
│      │                  3389/tcp tunneled                        │
│      │                                                           │
│      │ (3) CS Client connects                                   │
│      │     (from Attack Box RDP session)                        │
│      └──────────────► Team Server                               │
│                         50050/tcp                                │
│                                                                  │
│  Beacon Deployment:                                              │
│      Team Server ──► DC01 (Beacon callbacks to TS:50050)        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Key Architectural Principles

1. **Defense in Depth**: Multiple layers (Jumpbox → Attack Box → Team Server → Targets)
2. **Least Privilege**: Each instance has minimal required permissions
3. **Network Segmentation**: Public/Private subnet separation
4. **Separation of Concerns**:
   - Jumpbox = SSH gateway (minimal, hardened)
   - Team Server = CS daemon ONLY (headless)
   - Attack Box = GUI workstation (CS client, tools, RDP)
5. **Key Exchange via S3**: Automated SSH key distribution using S3 bucket

---

## Comparison: Wrong vs Correct

### Original (WRONG) Diagram

```
Operator → SSH → [Jumpbox + CS Combined] → DC01
               (Single Ubuntu instance
                with CS Server + SSH)
```

**Problems**:
- Conflates multiple roles into one instance
- No separation between gateway and tooling
- Missing Windows attack workstation
- Implies operator runs CS client from CLI on jumpbox

### Corrected Diagram

```
Operator → SSH → Jumpbox (Gateway Only)
              ↓
            RDP → Attack Box (Windows GUI)
              ↓
       CS Client → Team Server (CS Daemon)
              ↓
          Beacons → DC01 (Target)
```

**Benefits**:
- Clear separation of roles
- Realistic operator workflow (RDP to Windows GUI)
- Mirrors real-world red team infrastructure
- Better security (each component is isolated)

---

## Technical Details from Terraform Code

### Jumpbox Configuration
```hcl
# jumpbox.tf
resource "aws_instance" "jumpbox" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = var.jumpbox_instance_type  # t3.small
  
  network_interface {
    subnet_id   = aws_subnet.public.id       # PUBLIC subnet
    private_ips = ["${var.ip_range}.100"]    # 10.10.1.100
  }
  
  # Role: SSH Gateway ONLY - minimal, hardened
}
```

### Team Server Configuration
```hcl
# teamserver.tf
resource "aws_instance" "teamserver" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = var.teamserver_instance_type  # t3.medium
  
  network_interface {
    subnet_id   = aws_subnet.private.id         # PRIVATE subnet
    private_ips = ["${var.ip_range}.40"]        # 10.10.1.40
  }
  
  # Role: Cobalt Strike server daemon (headless)
  # Listens on port 50050 for CS client connections
}
```

### Attack Box Configuration
```hcl
# attackbox.tf
resource "aws_instance" "attackbox" {
  ami           = data.aws_ami.windows_2022.id
  instance_type = var.attackbox_instance_type  # t3.xlarge
  
  network_interface {
    subnet_id   = aws_subnet.private.id         # PRIVATE subnet
    private_ips = ["${var.ip_range}.50"]        # 10.10.1.50
  }
  
  # Role: Windows workstation with:
  # - Cobalt Strike GUI client
  # - PowerShell tools (PowerSploit, etc.)
  # - WSL2 with Ubuntu
  # - Windows Terminal
  # - RDP access for operator
}
```

---

## Security Implications

### Original (Wrong) Architecture Issues

1. **Single Point of Failure**: If jumpbox compromised, entire CS infrastructure compromised
2. **No Role Separation**: Gateway function mixed with attack tooling
3. **Reduced Defense in Depth**: Only one layer between operator and targets
4. **Poor OpSec**: Running CS GUI tools over SSH CLI is awkward and error-prone

### Corrected Architecture Benefits

1. ✅ **Layered Security**: Compromise of jumpbox doesn't immediately expose CS infrastructure
2. ✅ **Role-Based Access Control**: Each instance has specific, limited function
3. ✅ **Better OpSec**: Proper GUI environment for CS client operations
4. ✅ **Audit Trail**: Separate logging for gateway vs attack operations
5. ✅ **Incident Response**: Can isolate compromised layer without losing entire infrastructure

---

## Cost Comparison

### Original (Misunderstood) vs Reality

| Component | Type | Monthly Cost |
|-----------|------|--------------|
| **Original Assumption** | | |
| Jumpbox + CS (combined) | Ubuntu t3.medium | ~$30 |
| DC01 | Windows t3.medium | ~$30 |
| **Total** | | **~$60** |
| | | |
| **Actual Architecture** | | |
| Jumpbox (separate) | Ubuntu t3.small | ~$15 |
| Team Server | Ubuntu t3.medium | ~$30 |
| Attack Box | Windows t3.xlarge | ~$120 |
| DC01 | Windows t3.medium | ~$30 |
| **Total** | | **~$195** |

**Note**: Attack Box requires `t3.xlarge` for GUI performance (Windows + WSL2 + CS Client + tools).

---

## Updated Diagrams Generated

1. ✅ **goad-mini-correct.png** - Shows all 4 instances correctly
2. ✅ **goad-light-correct.png** - Shows 6 instances (adds DC02, SRV02)
3. ✅ **goad-full-correct.png** - Shows 8 instances (adds DC03, SRV03)

All diagrams now correctly depict:
- Separate jumpbox, team server, and attack box
- Public vs private subnet placement
- Correct IP addressing (`10.10.1.x`)
- Proper security group relationships
- S3 key exchange mechanism
- Actual data flow for operator access

---

## Recommendations

### For Documentation

1. ✅ Update all GOAD documentation to reflect 3-instance architecture
2. ✅ Clarify operator workflow (SSH → RDP → CS Client)
3. ✅ Document cost implications of Attack Box (larger instance needed)
4. ✅ Add section on "Why 3 instances instead of 1?"

### For Deployment

1. Ensure terraform code deploys all 3 instances when CS is enabled
2. Validate SSH key exchange via S3 works between all instances
3. Test RDP tunneling from operator laptop → Attack Box
4. Verify CS client on Attack Box can connect to Team Server

### For Training

1. Emphasize the role separation in training materials
2. Practice the multi-hop access pattern
3. Understand why professional red teams use this architecture
4. Compare to simplified "all-in-one" architectures (explain trade-offs)

---

## Conclusion

The corrected diagrams now **accurately represent the actual infrastructure** deployed by the Terraform code. This is a significant architectural pattern that reflects **real-world red team infrastructure best practices**:

- **Jumpbox**: Hardened gateway (minimal attack surface)
- **Team Server**: Dedicated C2 daemon (headless, stable)
- **Attack Box**: Operator workstation (GUI tools, comfortable environment)

This separation provides better **security, maintainability, and operational effectiveness** compared to cramming everything into a single instance.

---

**Files Updated**:
- ✅ `generated-diagrams/goad-mini-correct.png`
- ✅ `generated-diagrams/goad-light-correct.png`
- ✅ `generated-diagrams/goad-full-correct.png`
- ✅ `webapp/frontend/js/architecture.js` (diagram paths updated)

**Next Steps**:
- Refresh browser to see corrected diagrams
- Update markdown documentation to reflect 3-instance architecture
- Add troubleshooting section for multi-hop access patterns
