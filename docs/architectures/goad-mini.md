# GOAD Mini - Single DC Training Lab

## Overview

GOAD Mini is the most cost-effective and simplest GOAD deployment, perfect for learning Active Directory attack techniques without the complexity of multi-domain environments.

## Architecture Components

### Infrastructure

| Component | Type | Specifications | Purpose |
|-----------|------|---------------|---------|
| **GOAD Jumpbox + CS** | EC2 (t3.medium) | 2 vCPU, 4GB RAM, Public IP | Dual-purpose: Lab access & Cobalt Strike server |
| **DC01** | EC2 (t3.medium) | 2 vCPU, 4GB RAM, Private IP | Domain Controller - sevenkingdoms.local |

### Network Configuration

- **VPC CIDR**: 10.10.0.0/16
- **Public Subnet**: For jumpbox with internet access
- **Private Subnet**: 10.10.1.0/24 for domain controller
- **Internet Gateway**: Provides public internet access to jumpbox

### Security Groups

#### Jumpbox Security Group
```yaml
Inbound Rules:
  - Port 22 (SSH): From management_cidr_blocks
  - Port 50050 (Cobalt Strike): From management_cidr_blocks
Outbound Rules:
  - All traffic: To anywhere (0.0.0.0/0)
```

#### GOAD Lab Security Group
```yaml
Inbound Rules:
  - All traffic: From jumpbox only
  - RDP (3389): From jumpbox
  - WinRM (5985/5986): From jumpbox
  - SMB (445): From jumpbox
  - LDAP (389/636): From jumpbox
Outbound Rules:
  - All traffic: To VPC only
```

## Key Features

### 1. Single Domain Environment
- **Domain**: sevenkingdoms.local
- **Domain Controller**: DC01 (Windows Server 2019)
- **Simplified AD structure** for learning fundamentals

### 2. Integrated Cobalt Strike
- **Team Server runs on jumpbox** - no separate C2 infrastructure needed
- **Direct beacon callbacks** within the same network
- **Port 50050 exposed** for Cobalt Strike client connections
- **Perfect for training** - focus on AD attacks, not C2 infrastructure

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
  goad_lab_type = "GOAD-Mini"
  goad_jumpbox_instance_type = "t3.medium"
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

### 1. SSH to Jumpbox
```bash
ssh -i ~/.ssh/your-key.pem ubuntu@<jumpbox-public-ip>
```

### 2. Cobalt Strike Client Connection
```
Host: <jumpbox-public-ip>
Port: 50050
Password: [Retrieved from deployment output]
```

### 3. RDP to Domain Controller (via Jumpbox)
```bash
# From jumpbox
xfreerdp /v:10.10.1.10 /u:Administrator /p:'<password>' /cert:ignore
```

## Attack Scenarios

### Scenario 1: Initial Enumeration
```bash
# From jumpbox
nmap -p 88,389,445,3389 10.10.1.10
ldapsearch -x -H ldap://10.10.1.10 -b "DC=sevenkingdoms,DC=local"
```

### Scenario 2: Kerberoasting
```bash
# Using Impacket
GetUserSPNs.py sevenkingdoms.local/user:password -dc-ip 10.10.1.10 -request
```

### Scenario 3: BloodHound Collection
```bash
bloodhound-python -d sevenkingdoms.local -u user -p password -ns 10.10.1.10 -c all
```

### Scenario 4: Cobalt Strike Beacon Deployment
1. Generate payload from CS client
2. Upload to DC01 via SMB
3. Execute via WMI/PsExec
4. Beacon calls back to jumpbox CS server

## Cost Breakdown

### Monthly Cost Estimate: ~$75-100

| Resource | Type | Monthly Cost |
|----------|------|--------------|
| Jumpbox | t3.medium (24/7) | ~$30 |
| DC01 | t3.medium (24/7) | ~$30 |
| EBS Storage | 50GB (2x 25GB) | ~$5 |
| Data Transfer | Minimal | ~$5-10 |
| S3 Storage | Scripts & Tools | <$1 |
| **Total** | | **~$75-100** |

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
**Solution**: Verify security group allows port 50050 from your IP
```bash
aws ec2 describe-security-groups --group-ids <sg-id>
```

### Issue: DC01 not responding
**Solution**: Check if domain promotion completed
```bash
ssh jumpbox
ping 10.10.1.10
nslookup sevenkingdoms.local 10.10.1.10
```

### Issue: Beacon won't call back
**Solution**: Verify jumpbox can reach DC01 on all ports
```bash
# From jumpbox
nc -zv 10.10.1.10 445
nc -zv 10.10.1.10 135
```

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
- ✅ **Low cost** (~$75-100/month)
- ✅ **Simple setup** (1 DC + Jumpbox)
- ✅ **Fast deployment** (20-30 minutes)
- ✅ **All essential vulnerabilities** included
- ✅ **Integrated C2** for realistic attack scenarios

Perfect for beginners and budget-conscious learners!
