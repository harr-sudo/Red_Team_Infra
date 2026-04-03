# C2 Traffic Flow Architecture

**Date**: 2026-03-09
**Status**: ✅ Updated - Corrected pull-based C2 model, DNS-01 SSL, complete traffic breakdown

## Overview

All C2 traffic is **pull-based**. The target (compromised host) initiates every connection. The team server **never** opens a connection to the target — commands are delivered as HTTP responses on connections the beacon already opened. This is critical to understand because it means the team server doesn't need direct internet access for C2 operations.

---

## How C2 Traffic Actually Works

### The Key Insight: It's Pull-Based

C2 frameworks like Cobalt Strike use a **polling model** — the beacon on the target periodically "calls home" to check for new commands. The team server simply responds with queued commands. This is identical to how a web browser requests a page from a web server.

**The team server never initiates a connection to the target.**

### Step-by-Step: A Single Beacon Cycle

```
STEP 1: Target beacon opens an HTTPS connection to the redirector
──────────────────────────────────────────────────────────────────
Target ──HTTPS GET──▶ Internet ──▶ IGW ──▶ Redirector (public subnet, port 443)
                                           Elastic IP: 35.x.x.x

STEP 2: Nginx on the redirector opens a SECOND connection to the team server
──────────────────────────────────────────────────────────────────
Redirector ──proxy_pass──▶ Team Server (private subnet, 10.0.10.10:443)
                           (internal VPC traffic — never touches the internet)

STEP 3: Team server responds with any queued commands
──────────────────────────────────────────────────────────────────
Team Server ──HTTP 200 + encrypted commands──▶ Redirector
             (response on the SAME TCP connection from step 2)

STEP 4: Nginx forwards the response back to the target
──────────────────────────────────────────────────────────────────
Redirector ──HTTP response──▶ IGW ──▶ Internet ──▶ Target
             (response on the SAME TCP connection from step 1)

STEP 5: Target executes the command, sends output on NEXT beacon
──────────────────────────────────────────────────────────────────
(Repeats from step 1, this time the beacon POST includes command output)
```

### Why This Matters

1. **Team server stays hidden** — it's in a private subnet with no public IP. It never needs to reach the internet for C2.
2. **NAT Gateway is NOT used for C2 traffic** — it's only for bootstrap (package installs, S3 downloads, license activation).
3. **Firewall/SG rules are simple** — allow inbound 443 to redirector, allow redirector→team server internally. Responses travel back on the same connection.
4. **The operator doesn't send traffic to the target** — the operator uses the CS client (via SSH tunnel to team server) to queue commands. The beacon picks them up on its next check-in.

### The Complete Flow (Simplified)

```
┌──────────────┐         ┌──────────────────┐         ┌──────────────────┐         ┌──────────────┐
│   Operator   │──SSH────▶│     Bastion      │──tunnel─▶│   Team Server    │         │    Target    │
│   Laptop     │  tunnel  │  (management)    │  50050   │   (private)      │         │   (beacon)   │
│              │         │                  │         │                  │         │              │
│  CS Client   │         │                  │         │  queues command  │         │              │
│  localhost   │         │                  │         │       ↕          │         │              │
│   :50050     │         │                  │         │  waits for poll  │         │              │
└──────────────┘         └──────────────────┘         └────────▲─────────┘         └──────┬───────┘
                                                               │                          │
                                                    ┌──────────┴─────────┐                │
                                                    │    Redirector      │◀──HTTPS poll────┘
                                                    │    (public)        │──response + cmd─▶
                                                    │    nginx proxy     │  (same TCP conn)
                                                    └────────────────────┘
```

**Reading the diagram**: The target beacon polls the redirector (bottom right → bottom left). Nginx proxies to the team server (bottom left → middle). The team server responds with commands on the same connection. The operator interacts with the team server separately via SSH tunnel (top left → top right). These are two independent connections — the operator path and the C2 path never share a network link.

---

## Traffic Flow Patterns (By Type)

### 1. C2 Traffic: Beacon Callbacks + Command Delivery (Single Connection)

The beacon callback and command delivery happen on the **same TCP connection**. The target opens it, the team server responds on it.

```
Target ──HTTPS request (beacon data)──▶ Redirector ──proxy──▶ Team Server
Target ◀──HTTPS response (commands)──── Redirector ◀──────── Team Server
         (same TCP socket)               (same TCP socket)
```

- **Initiated by**: Target (always)
- **Ports**: 443 inbound to redirector, 443 redirector→team server (internal)
- **Security Groups**: Internet → Redirector SG (443), Redirector SG → C2 SG (443)
- **Frequency**: Every beacon interval (e.g., 60 seconds)
- **NAT Gateway**: NOT involved — traffic enters via IGW to redirector EIP

### 2. Operator Access (SSH Tunnel)

```
Operator ──SSH──▶ Bastion (port 22) ──tunnel──▶ Team Server (port 50050)
```

- **Initiated by**: Operator
- **Command**: `ssh -L 50050:10.0.10.10:50050 ubuntu@bastion_ip`
- **Security Groups**: Management CIDR → Bastion SG (22), Bastion SG → C2 SG (50050)
- **CS Client**: Connects to `localhost:50050` (tunneled to team server)

### 3. SSL Certificate Validation (DNS-01 via Route53)

Each redirector independently obtains a Let's Encrypt certificate using DNS-01 validation. This works with round-robin DNS (multiple redirectors) unlike HTTP-01.

```
Redirector ──AWS API──▶ Route53: creates _acme-challenge TXT record
Let's Encrypt validates TXT record → issues certificate
Redirector: installs cert, updates nginx, reloads
```

- **Initiated by**: Redirector (at boot, retried every 5 min if failed)
- **IAM**: route53:ChangeResourceRecordSets, route53:ListHostedZones, route53:GetChange
- **Why DNS-01**: HTTP-01 fails with round-robin DNS (LE challenge hits wrong server 50% of the time)

### 4. Bootstrap & Key Exchange (S3)

```
All instances ──VPC endpoint / NAT──▶ S3: setup scripts, SSH public keys, CS archive
```

### 5. Domain Fronting (Optional)

```
Target ──HTTPS to front domain──▶ CloudFront Edge ──origin──▶ Redirector ──proxy──▶ Team Server
Target ◀──response──────────────── CloudFront ◀────response── Redirector ◀──────── Team Server
```

---

## Domain Fronting Traffic Flow (Optional)

When CloudFront domain fronting is enabled, traffic takes an additional hop through the CDN before reaching the redirector. This hides the redirector's IP from blue team analysis.

### 4. Domain Fronting Flow (CloudFront)

```
┌─────────────┐                 ┌──────────────┐                 ┌──────────────┐                 ┌──────────────┐
│   Target    │──HTTPS to──────▶│  CloudFront  │────Origin───────▶│  Redirector  │────Forward─────▶│ Team Server  │
│   Network   │  front domain   │  (CDN Edge)  │    Request       │  (Public)    │                 │  (Private)   │
│             │                 │              │                 │              │                 │              │
│             │◀──Response──────│              │◀───Response──────│              │◀───Commands─────│              │
└─────────────┘                 └──────────────┘                 └──────────────┘                 └──────────────┘
```

**How it works:**
1. Beacon sends HTTPS request to **front domain** (e.g. `grid.crowdstrike.com`) — legitimate third-party domain
2. TLS connection uses front domain's certificate — looks like normal CDN traffic
3. HTTP `Host` header contains our **back domain** (e.g. `api.our-domain.com`)
4. CloudFront routes based on Host header to our distribution
5. CloudFront forwards to **origin** (redirector's Elastic IP)
6. Redirector forwards to C2 team server in private subnet

**What the blue team sees:**
- DNS resolution: `grid.crowdstrike.com` → CloudFront IP (legitimate)
- TLS SNI: `grid.crowdstrike.com` (legitimate certificate)
- They do NOT see our domain or redirector IP in network logs

### SSL Chain with Domain Fronting

```
Target ──── Front Domain Cert ──── CloudFront ──── ACM Cert ──── Redirector ──── Self-Signed ──── C2 Server
         (not ours, borrowed)                   (auto, free)                  (CF doesn't verify)
```

| Segment | Certificate | Provider | Notes |
|---------|------------|----------|-------|
| Target → CloudFront | Front domain's cert | Third party | Borrowed reputation |
| CloudFront → Redirector | ACM certificate | AWS (free) | Auto-provisioned via DNS validation |
| Redirector → C2 Server | Self-signed | Generated at setup | Internal VPC traffic only |

### SSL Without Domain Fronting

| Option | Certificate | OPSEC Impact |
|--------|------------|--------------|
| **Let's Encrypt** | Trusted, auto-renewed | Good — trusted by browsers/proxies. Appears in CT logs. |
| **Self-Signed** | Untrusted, generated locally | Poor — flagged by Shodan/Censys, blocked by corporate proxies |

### Domain Rotation with CloudFront

When a domain is burned mid-engagement:

1. **Instant switch** — Change CS malleable profile to use a pre-configured backup domain. All backup domains are already CloudFront aliases with valid ACM certs.
2. **Add new backup** — Update web app → redeploy. ACM validates new domain via DNS (~2-5 min). CloudFront propagates (~15-30 min).

---

## Updated Diagram Traffic Flows

### C2 Ad-Hoc Architecture

**Bidirectional Connections**:
1. **Internet Gateway ↔ HTTP Redirector**
   - Inbound: Beacon callbacks (blue)
   - Outbound: Commands to targets (red dashed)

2. **HTTP Redirector ↔ Team Server**
   - Inbound: Proxy traffic (green)
   - Outbound: C2 commands (green dashed)

3. **Internet Gateway ↔ HTTPS Redirector**
   - Same pattern as HTTP

**Components**:
- 1 HTTP Redirector (Port 80)
- 1 HTTPS Redirector (Port 443)
- 1 Cobalt Strike Team Server

**With Domain Fronting (Optional)**:
- Add CloudFront distribution between Internet and Redirectors
- Redirector ingress restricted to CloudFront IPs (AWS managed prefix list)
- ACM certificate handles public SSL (no Let's Encrypt needed)
- Traffic: Internet → CloudFront → Internet Gateway → Redirector → Team Server

---

### C2 Purple Team Architecture

**Bidirectional Connections**:
1. **Internet Gateway ↔ All Redirectors (4 total)**
   - HTTP Redirector 1 ↔ Team Server 1
   - HTTP Redirector 2 ↔ Team Server 2
   - HTTPS Redirector 1 ↔ Team Server 1
   - HTTPS Redirector 2 ↔ Team Server 2

**Redundancy Pattern**:
- Each team server has dedicated redirectors
- Load balancer distributes operator access
- Sync connection between team servers (orange dotted)

**Components**:
- 2 HTTP Redirectors (Port 80)
- 2 HTTPS Redirectors (Port 443)
- 2 Cobalt Strike Team Servers (Primary + Backup)

---

### C2 Full Red Team Architecture (Phase-Based)

**Bidirectional Connections**:
1. **Internet Gateway ↔ Multi-Protocol Redirectors**
   - HTTP Redirector ↔ Recon Phase Team Server
   - HTTPS Redirector ↔ Initial Access Team Server
   - DNS Redirector ↔ Persistence Phase Team Server

**Phase Progression**:
- Recon → Initial Access → Persistence (orange dotted)
- Different redirectors for different phases
- Isolation between operational phases

**Components**:
- 1 HTTP Redirector → Recon Phase TS
- 1 HTTPS Redirector → Initial Access TS
- 1 DNS Redirector → Persistence Phase TS
- 3 Phase-specific Team Servers

---

### Combined Deployments (C2 + GOAD)

**All combined deployments include**:
1. **C2 VPC**: Full bidirectional C2 traffic (as above)
2. **GOAD VPC**: GOAD lab environment with training infrastructure
3. **VPC Peering**: Allows C2 team servers to target GOAD lab VMs

**Bidirectional Flows**:
- C2 VPC: Internet ↔ Redirectors ↔ Team Servers ↔ Targets
- GOAD VPC: Attack Box ↔ GOAD VMs, GOAD Team Server ↔ GOAD VMs
- VPC Peering: C2 Team Servers ↔ GOAD VMs (for realistic attack simulation)

---

## Color Coding Legend

### Traffic Direction Colors

| Color | Meaning | Example |
|-------|---------|---------|
| **Blue** | Inbound beacon callbacks | Target → Redirector |
| **Green (Solid)** | Proxy forwarding | Redirector → Team Server |
| **Green (Dashed)** | Command delivery (internal) | Team Server → Redirector |
| **Red (Dashed)** | Commands out to internet | Redirector → Internet |
| **Dark Red (Solid)** | Traffic to targets | Internet → Targets |
| **Orange (Dotted)** | Sync/Phase progression | TS1 ↔ TS2, Phase1 → Phase2 |

### Component Colors (AWS Icons)

| Component | Icon | Location |
|-----------|------|----------|
| **Redirector** | EC2 (Orange) | Public Subnet |
| **Team Server** | EC2 (Orange) | Private Subnet |
| **Jump Box** | EC2 (Orange) | Public or Private |
| **S3 Buckets** | S3 (Green) | Regional Service |
| **IAM Roles** | IAM (Pink) | Global Service |
| **Internet Gateway** | EC2 (Orange) | VPC Edge |
| **NAT Gateway** | EC2 (Orange) | Public Subnet |

---

## Security Group Rules (Summary)

All C2 traffic is pull-based, so the SG rules are straightforward:

| Rule | Source | Dest | Port | Why |
|------|--------|------|------|-----|
| Beacon inbound | 0.0.0.0/0 (or CloudFront) | Redirector SG | 443 | Target beacons check in |
| Proxy forward | Redirector SG | C2 Team Server SG | 443 | Nginx forwards to TS |
| Operator SSH | Management CIDR | Bastion SG | 22 | SSH tunnel entry point |
| CS client tunnel | Bastion SG | C2 Team Server SG | 50050 | Tunneled CS client |
| Bootstrap/updates | All instances | 0.0.0.0/0 (egress) | all | S3, packages, DNS-01 |

**Note**: No inbound rules needed for command delivery — commands ride back as HTTP responses on the same TCP connection the beacon opened. AWS security groups are stateful, so return traffic is automatically allowed.

---

## Example: A Complete Beacon Cycle (HTTP Level)

This shows exactly what happens at the HTTP level during one beacon check-in:

```
STEP 1 — Target beacon sends check-in (HTTPS GET)
┌──────────────────────────────────────────────────────────────────┐
│  Target → Redirector                                             │
│  GET /jquery-3.3.1.min.js HTTP/1.1                               │
│  Host: api.yourdomain.com                                        │
│  Cookie: session=<base64-encoded-beacon-metadata>                │
│  User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)          │
│                                                                  │
│  (Looks like a normal jQuery download to any network monitor)    │
└──────────────────────────────────────────────────────────────────┘
                               ↓ nginx proxy_pass
┌──────────────────────────────────────────────────────────────────┐
│  Redirector → Team Server (internal, 10.0.10.10:443)             │
│  Same request forwarded with X-Forwarded-For header added        │
└──────────────────────────────────────────────────────────────────┘
                               ↓ team server processes
┌──────────────────────────────────────────────────────────────────┐
│  Team Server → Redirector (HTTP response on same connection)     │
│  HTTP 200 OK                                                     │
│  Content-Type: application/javascript                            │
│  Body: <encrypted commands disguised as JavaScript>              │
│                                                                  │
│  (If no commands queued, returns empty/noop response)            │
└──────────────────────────────────────────────────────────────────┘
                               ↓ nginx forwards response
┌──────────────────────────────────────────────────────────────────┐
│  Redirector → Target (HTTP response on same connection)          │
│  Target receives, decrypts, executes command                     │
│  Output is sent on the NEXT beacon check-in (repeats from top)  │
└──────────────────────────────────────────────────────────────────┘
```

**All 4 steps happen on the SAME TCP connection** that the target opened. The team server never opens a connection outbound.

```bash
# The SSH tunnel command:
ssh -L 50050:10.0.10.10:50050 ubuntu@bastion_public_ip
# Then CS client connects to localhost:50050
```

- **Direction**: Inbound (operator initiates)
- **Protocol**: SSH (port 22) + tunneled CS traffic (port 50050)
- **Security Groups**: Management CIDR → Bastion SG (22), Bastion SG → C2 SG (50050)
- **What it carries**: CS client GUI traffic (operator commands, beacon list, screenshots)

### Traffic Type 4: SSL Certificate Validation (Redirector → Route53)

Each redirector independently obtains a Let's Encrypt certificate using DNS-01 validation.

```
Redirector ──AWS API──▶ Route53 (creates _acme-challenge TXT record)
                        Let's Encrypt checks TXT record → issues certificate
```

- **Direction**: Outbound API call (redirector → AWS API endpoints)
- **Protocol**: HTTPS (AWS SDK/CLI)
- **Security Groups**: Egress 0.0.0.0/0 (already allowed)
- **IAM Permissions**: route53:ChangeResourceRecordSets, route53:ListHostedZones, route53:GetChange
- **When**: At boot, then every 60-90 days for renewal
- **Why DNS-01**: With multiple redirectors behind round-robin DNS, HTTP-01 validation fails because the LE challenge request might hit the wrong server. DNS-01 validates via a TXT record — works regardless of which server runs certbot.

### Traffic Type 5: Bootstrap & Key Exchange (Instances → S3)

All instances download setup scripts and exchange SSH keys via S3.

```
Instance ──VPC Endpoint──▶ S3 Bucket (setup scripts, SSH public keys)
```

- **Direction**: Outbound (instance → S3)
- **Protocol**: HTTPS via VPC endpoint (never leaves AWS network)
- **IAM Permissions**: s3:GetObject, s3:PutObject (VPC-restricted)

### Traffic Type 6: Domain Fronting (Optional)

When enabled, C2 traffic is routed through CloudFront to hide the redirector's IP.

```
Target ──HTTPS──▶ CloudFront Edge ──origin──▶ Redirector ──proxy──▶ Team Server
 (front domain)    (CDN, looks legit)          (hidden IP)
```

- **Security Groups**: Redirector SG locked to CloudFront IPs only (AWS managed prefix list)
- **Certificates**: ACM cert on CloudFront (auto), self-signed on redirector (CF doesn't verify origin)

### Summary Table

| # | Traffic Type | Source → Dest | Protocol | Ports | Initiated By |
|---|-------------|--------------|----------|-------|-------------|
| 1 | Beacon Callbacks | Target → Redirector → Team Server | HTTPS | 443 → 443 | Target (pull) |
| 2 | Command Delivery | Team Server → Redirector → Target | HTTPS response | same conn | Response only |
| 3 | Operator Access | Laptop → Bastion → Team Server | SSH tunnel | 22, 50050 | Operator |
| 4 | SSL Validation | Redirector → Route53 → Let's Encrypt | AWS API + DNS | 443 (API) | Redirector |
| 5 | Bootstrap/Keys | All Instances → S3 | HTTPS (VPC EP) | 443 | Instance |
| 6 | Domain Fronting | Target → CloudFront → Redirector → TS | HTTPS | 443 | Target (pull) |

---

## Key Takeaways

1. **Redirectors are proxies**: They forward traffic in **both directions**
2. **Beacons come IN**: Targets initiate connections to redirectors (pull-based)
3. **Commands go OUT as responses**: Team servers NEVER initiate connections to targets
4. **SSL uses DNS-01**: Each redirector gets its own Let's Encrypt cert via Route53 — works with round-robin DNS
5. **Operator access via SSH tunnel**: CS client never directly reaches the team server — always through bastion
6. **Color-coded diagrams**: Blue = inbound beacons, Red = outbound commands, Green = internal proxy traffic

---

## References

- **Cobalt Strike Documentation**: https://www.cobaltstrike.com/help-redirectors
- **AWS Security Groups**: VPC Firewall rules for bidirectional traffic
- **C2 Opsec Best Practices**: Domain fronting, CDN integration, legitimate traffic patterns
- **Red Team Infrastructure Guide**: https://github.com/bluscreenofjeff/Red-Team-Infrastructure-Wiki

---

## Notes

This update ensures the diagrams accurately represent the **technical reality** of C2 infrastructure. Understanding bidirectional traffic flow is critical for:
- Configuring security groups correctly
- Implementing effective OPSEC
- Troubleshooting connectivity issues
- Explaining the architecture to stakeholders
