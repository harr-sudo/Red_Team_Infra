# GOAD Quick Start Guide

Get a vulnerable Active Directory lab running alongside your C2 infrastructure in minutes.

## What is GOAD?

[GOAD (Game Of Active Directory)](https://github.com/Orange-Cyberdefense/GOAD) is a pentest Active Directory lab project that provides realistic, vulnerable AD environments for practicing attack techniques.

**Included in this repository**: `tools/goad/`

## Available Labs

| Lab | VMs | Description | Est. Monthly Cost | Best For |
|-----|-----|-------------|-------------------|----------|
| **GOAD-Mini** | 1 | Single domain controller | ~$75/mo | Quick testing, learning basics |
| **GOAD-Light** | 3 | 2 domains, 1 forest | ~$200/mo | Most common scenarios |
| **SCCM** | 4 | SCCM/ConfigMgr (sccm.lab) | ~$300/mo | SCCM-specific attacks |
| **GOAD** | 5 | Full lab - 3 domains, 2 forests | ~$350/mo | Complete AD training |
| **NHA** | 5 | CTF challenge (ninja.hack) | ~$350/mo | Challenge-mode practice |

## Quick Start

### Option 1: Via Web Application (Recommended)

1. **Connect to the Dashboard Server** (AWS-hosted control plane + jump):
   ```bash
   ssh -L 5000:localhost:5000 ubuntu@<dashboard-eip>
   # Open http://localhost:5000
   ```

2. **Go to Configuration page**

3. **Select GOAD Lab** in the "Target Lab Environment" section

4. **Deploy** from the Deploy page

5. **Access credentials** shown in Deployment Manager after deployment

### Option 2: Command Line (Manual)

```bash
# Navigate to GOAD directory
cd tools/goad

# Install dependencies
pip install -r requirements.txt
ansible-galaxy install -r requirements.yml

# Configure for AWS
cd ad/GOAD-Light/providers/aws

# Edit terraform.tfvars with your settings
cp terraform.tfvars.example terraform.tfvars
vim terraform.tfvars

# Deploy
terraform init
terraform apply

# Provision with Ansible (from jumpbox)
# See GOAD documentation for details
```

## Connecting Cobalt Strike to GOAD

After deployment, you have several options to reach the GOAD network from your C2 infrastructure:

### Method 1: SOCKS Proxy via GOAD Jumpbox (Recommended)

```bash
# Create SOCKS proxy through GOAD jumpbox
ssh -D 1080 -i ~/.ssh/goad-key.pem ubuntu@<goad-jumpbox-ip>

# Configure Cobalt Strike:
# Cobalt Strike → Listeners → Add → SOCKS Proxy
# Host: 127.0.0.1
# Port: 1080
```

### Method 2: VPC Peering (Direct Access)

If VPC peering is configured between your C2 VPC and GOAD VPC:
- Beacons can call back directly through the redirector
- No proxy needed, but requires proper routing

### Method 3: Through the Dashboard Server (jump host)

The AWS-hosted Dashboard Server is the primary jump into the GOAD network — tunnel through its EIP. (See [Server Mode Access](#server-mode-access) below for the in-browser Terminal tab, which needs no manual tunnel.)

```bash
# SSH tunnel from your laptop to the GOAD jumpbox, through the Dashboard Server:
ssh -L 1080:<goad-jumpbox-private-ip>:22 ubuntu@<dashboard-eip>

# Then create SOCKS proxy through the tunnel
ssh -D 1080 -p 1080 localhost
```

> The Dashboard Server is the only SSH jump into the GOAD network — there is no per-deployment bastion. The GOAD jumpbox itself is reached *through* the Dashboard Server (it provisions the AD lab via Ansible; it is not an access bastion).

## Accessing the GOAD Lab

### Server Mode Access

When running the dashboard in server mode, access to the GOAD lab is simplified by VPC peering between the dashboard VPC (10.100.0.0/16) and the GOAD VPC (192.168.56.0/24).

- **Terminal tab** in the dashboard provides direct SSH to the jumpbox and GOAD team server — no manual SSH tunnel needed from the operator laptop
- **VPC peering** gives the dashboard server direct network access to all GOAD instances (jumpbox, team server, Windows VMs)
- **GOAD provisioning** can be triggered directly from the dashboard UI; the server communicates with the jumpbox over the peered network to run Ansible
- **No SOCKS proxy needed** for dashboard-initiated operations — the server reaches GOAD VMs directly

Operators only need to SSH tunnel to the Dashboard Server itself (production control plane + jump):
```bash
ssh -L 5000:localhost:5000 ubuntu@<dashboard-eip>
# Then open http://localhost:5000 and use the Terminal tab for GOAD access
```

For RDP access to Windows GOAD VMs from the operator laptop, tunnel through the Dashboard Server:
```bash
ssh -L 13389:192.168.56.10:3389 ubuntu@<dashboard-eip>
# Then RDP to localhost:13389
```

### SSH to Jumpbox (Local Mode)

```bash
# Direct SSH
ssh -i ~/.ssh/goad-key.pem ubuntu@<jumpbox-public-ip>

# Using GOAD's built-in command (from tools/goad directory)
./goad.sh -t ssh_jumpbox
```

### RDP to Windows VMs

From the jumpbox, you can access Windows VMs:

```bash
# Create SOCKS proxy
./goad.sh -t ssh_jumpbox_proxy 1080

# Then use xfreerdp or similar through the proxy
proxychains xfreerdp /v:192.168.56.10 /u:Administrator /p:<password>
```

### Default Credentials

GOAD labs come with pre-configured vulnerable users. After deployment, credentials are available:

```bash
# View credentials (from GOAD directory)
cat ad/GOAD/data/inventory

# Common default accounts:
# Domain: SEVENKINGDOMS
# Users with weak/guessable passwords are configured
```

## Attack Techniques Available

GOAD labs are pre-configured with these vulnerabilities:

### ✅ Works in AWS
- Kerberoasting
- AS-REP Roasting
- DCSync
- DCShadow
- Pass-the-Hash
- Pass-the-Ticket
- Golden/Silver Tickets
- Constrained/Unconstrained Delegation
- NTLM Relay (with proper setup)
- PetitPotam, PrinterBug
- ACL Abuse
- GPO Abuse

### ❌ Does NOT Work in AWS
- LLMNR/NBTNS Poisoning (broadcast-based)
- Other broadcast/multicast attacks

## Cost Management

### Stop Lab (Save ~70%)

```bash
# Via web app: Deployment Manager → Stop Lab

# Via CLI (from GOAD directory)
./goad.sh -t stop
```

### Start Lab

```bash
# Via web app: Deployment Manager → Start Lab

# Via CLI
./goad.sh -t start
```

### Destroy Lab

```bash
# Via web app: Deployment Manager → Destroy

# Via CLI
cd ad/GOAD/providers/aws
terraform destroy
```

## Troubleshooting

### Can't SSH to Jumpbox

1. Check security group allows SSH from your IP
2. Verify key permissions: `chmod 600 ~/.ssh/goad-key.pem`
3. Check jumpbox is running: `terraform output`

### Windows VMs Not Responding

1. Windows VMs take 10-15 minutes to fully boot
2. Check VM status in AWS Console
3. Ansible provisioning may still be running

### Cobalt Strike Can't Reach GOAD

1. Verify SOCKS proxy is running
2. Check VPC peering routes (if using direct access)
3. Verify security groups allow traffic between VPCs
4. Test connectivity: `proxychains ping 192.168.56.10`

### High AWS Costs

1. Stop labs when not in use: `./goad.sh -t stop`
2. Use smaller labs (GOAD-Mini, GOAD-Mini) for basic testing
3. Set up AWS Budget alerts

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         AWS Account                              │
│                                                                  │
│  ┌──────────────────────┐  (Dashboard VPC 10.100.0.0/16)        │
│  │  Dashboard Server    │  sole SSH jump — peered to BOTH VPCs   │
│  │  (own VPC, EIP)      │──────────────┬──────────────┐         │
│  └──────────────────────┘   VPC peering│   VPC peering │         │
│                                        ▼              ▼          │
│  ┌─────────────────────────┐    ┌─────────────────────────────┐ │
│  │   Your C2 VPC           │    │      GOAD VPC               │ │
│  │                         │    │                             │ │
│  │  ┌─────────────────┐   │    │  ┌─────────────────────┐   │ │
│  │  │ C2 Team Server  │   │    │  │ DC01, DC02, DC03    │   │ │
│  │  │ (Cobalt Strike) │   │◄──►│  │ SRV02, SRV03        │   │ │
│  │  └─────────────────┘   │ VPC│  │ (Windows Servers)   │   │ │
│  │                         │Peer│  └─────────────────────┘   │ │
│  │  ┌─────────────────┐   │    │  ┌─────────────────────┐   │ │
│  │  │ Attack Box      │   │    │  │ GOAD Jumpbox        │   │ │
│  │  │ (Windows+WSL2)  │   │    │  │ (Ubuntu, Ansible —  │   │ │
│  │  └─────────────────┘   │    │  │  provisions the lab)│   │ │
│  │                         │    │  └─────────────────────┘   │ │
│  └─────────────────────────┘    └─────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Next Steps

1. **Deploy a lab**: Start with GOAD-Mini
2. **Test connectivity**: SSH to jumpbox, verify SOCKS proxy works
3. **Generate payload**: Create Cobalt Strike beacon for GOAD network
4. **Practice attacks**: Use the pre-configured vulnerabilities
5. **Document findings**: Great for training and skill development

## References

- [GOAD GitHub Repository](https://github.com/Orange-Cyberdefense/GOAD)
- [GOAD Documentation](https://orange-cyberdefense.github.io/GOAD/)
- [GOAD AWS Provider Docs](https://orange-cyberdefense.github.io/GOAD/providers/aws/)
- [GOAD Integration Plan](./GOAD_INTEGRATION_PLAN.md) - Full architecture details
- [Operator Access Methods](./GOAD_INTEGRATION_PLAN.md#operator-access-methods-connecting-to-your-c2-infrastructure) - How to connect from your laptop

