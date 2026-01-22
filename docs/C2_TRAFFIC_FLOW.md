# C2 Traffic Flow Architecture

**Date**: 2026-01-22  
**Status**: ✅ Updated - All C2 diagrams now show bidirectional traffic flow

## Overview

All C2 infrastructure diagrams have been updated to accurately reflect **bidirectional traffic flow** between redirectors, team servers, and target networks. This is critical because C2 redirectors act as **proxies**, not just forwarders.

---

## Understanding C2 Traffic Flow

### The Problem with Unidirectional Arrows

Initial diagrams showed traffic flowing in only one direction (e.g., Target → Redirector → Team Server). This was **inaccurate** because:

1. **Beacon Callbacks**: Targets (compromised hosts) send beacon callbacks **TO** the redirector
2. **Command Delivery**: The team server sends commands **THROUGH** the redirector **TO** the target
3. **Bidirectional Communication**: Modern C2 frameworks use bidirectional channels (HTTP GET/POST, HTTPS, DNS queries/responses)

### The Correct Model: Bidirectional Proxy

Redirectors are **reverse proxies** that:
- Receive inbound beacon callbacks from targets
- Forward callbacks to the team server
- Receive commands from the team server
- Forward commands back to targets

---

## Traffic Flow Patterns

### 1. Inbound Traffic (Beacon Callbacks)

```
Target Network → Internet → IGW → Redirector → Team Server
```

**Color in Diagrams**: Blue arrows  
**Label**: "Beacon Callbacks"

**What Happens**:
1. Compromised host sends HTTP/HTTPS/DNS beacon to redirector's public IP
2. Redirector receives the beacon on public subnet
3. Redirector validates and forwards to team server in private subnet
4. Team server processes the beacon and queues commands

### 2. Outbound Traffic (Command Delivery)

```
Team Server → Redirector → IGW → Internet → Target Network
```

**Color in Diagrams**: Red/Green dashed arrows  
**Label**: "Commands Out" / "C2 Commands"

**What Happens**:
1. Team server sends commands to redirector
2. Redirector formats commands into HTTP/HTTPS/DNS responses
3. Redirector sends response through IGW to target
4. Target receives and executes commands

### 3. The Complete Bidirectional Flow

```
┌─────────────┐                 ┌──────────────┐                 ┌──────────────┐
│   Target    │────Beacon──────▶│  Redirector  │────Forward─────▶│ Team Server  │
│   Network   │                 │  (Public)    │                 │  (Private)   │
│             │◀───Commands─────│              │◀───Commands─────│              │
└─────────────┘                 └──────────────┘                 └──────────────┘
```

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

## Network Security Considerations

### Why Bidirectional Flow Matters

1. **Firewall Rules**: Security groups must allow:
   - Inbound: 80/443/53 to redirectors
   - Outbound: 80/443/53 from redirectors to internet
   - Inbound: Custom ports from redirectors to team servers
   - Outbound: Custom ports from team servers to redirectors

2. **Monitoring**: IDS/IPS must inspect:
   - Inbound traffic patterns (beacon intervals)
   - Outbound command delivery (data exfiltration)
   - Proxy behavior (redirector traffic analysis)

3. **Opsec**: Bidirectional flow means:
   - Both inbound and outbound traffic can be detected
   - Redirectors must appear legitimate (domain fronting, valid certs)
   - Team servers remain isolated in private subnets

---

## Updated Diagrams List

All diagrams regenerated with bidirectional traffic flow:

### C2 Infrastructure
- ✅ `c2-adhoc-architecture.png` - Single team server, bidirectional redirectors
- ✅ `c2-purple-architecture.png` - Redundant servers, 4 bidirectional redirectors
- ✅ `c2-full-architecture.png` - Phase-based, 3 bidirectional redirectors

### Combined Deployments
- ✅ `combined-c2-goad-mini.png` - C2 + GOAD Mini with bidirectional flows
- ✅ `combined-full-c2-goad-light.png` - C2 + GOAD Light with bidirectional flows
- ✅ `combined-full-c2-goad-full.png` - Full C2 + Full GOAD with bidirectional flows

---

## Example: HTTP Redirector Traffic Flow

### Inbound Beacon Callback

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Target sends HTTP GET to redirector:                         │
│    GET /updates/check.php HTTP/1.1                              │
│    Host: legitimate-cdn.example.com                             │
│    Cookie: session=<base64-encoded-beacon-data>                 │
└─────────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. Redirector receives, validates, forwards to team server:     │
│    POST /beacon HTTP/1.1                                        │
│    Host: 10.0.1.10:50050                                        │
│    Body: <decoded-beacon-data>                                  │
└─────────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. Team server processes beacon, returns commands                │
│    HTTP 200 OK                                                   │
│    Body: <encrypted-commands>                                    │
└─────────────────────────────────────────────────────────────────┘
```

### Outbound Command Delivery

```
┌─────────────────────────────────────────────────────────────────┐
│ 4. Team server sends commands back to redirector                │
│    (Response to the POST /beacon request)                       │
└─────────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. Redirector formats response for target:                      │
│    HTTP 200 OK                                                   │
│    Content-Type: text/html                                      │
│    Body: <legitimate-looking-content-with-hidden-commands>       │
└─────────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. Target receives HTTP response, extracts commands, executes   │
│    Next beacon will include command output                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Takeaways

1. ✅ **Redirectors are proxies**: They forward traffic in **both directions**
2. ✅ **Beacons come IN**: Targets initiate connections to redirectors
3. ✅ **Commands go OUT**: Team servers send commands through redirectors
4. ✅ **All diagrams updated**: Every C2 diagram now shows bidirectional arrows
5. ✅ **Color-coded**: Blue = inbound beacons, Red = outbound commands, Green = internal proxy traffic

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
