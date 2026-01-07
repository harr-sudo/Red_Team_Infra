# GOAD Quick Start Guide

Get a vulnerable Active Directory lab running alongside your C2 infrastructure in minutes.

## What is GOAD?

[GOAD (Game Of Active Directory)](https://github.com/Orange-Cyberdefense/GOAD) is a pentest Active Directory lab project that provides realistic, vulnerable AD environments for practicing attack techniques.

**Included in this repository**: `tools/goad/`

## Available Labs

| Lab | VMs | Description | Est. Monthly Cost | Best For |
|-----|-----|-------------|-------------------|----------|
| **GOAD-Mini** | 1 | Single domain controller | ~$75/mo | Quick testing, learning basics |
| **MINILAB** | 2 | DC + Workstation | ~$150/mo | Basic attack chains |
| **GOAD-Light** | 3 | 2 domains, 1 forest | ~$200/mo | Most common scenarios |
| **SCCM** | 4 | SCCM/ConfigMgr environment | ~$300/mo | SCCM-specific attacks |
| **GOAD** | 5 | Full lab - 3 domains, 2 forests | ~$350/mo | Complete AD training |
| **NHA** | 5 | Challenge lab (no hints!) | ~$350/mo | CTF-style practice |

## Quick Start

### Option 1: Via Web Application (Recommended)

1. **Start the web app**:
   ```bash
   ./webapp/start.sh
   # Open http://127.0.0.1:5000
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

### Method 3: Through Your Bastion

```bash
# SSH tunnel from your bastion to GOAD jumpbox
# Then proxy Cobalt Strike traffic through

# From your laptop:
ssh -L 1080:<goad-jumpbox-private-ip>:22 ubuntu@<your-bastion-ip>

# Then create SOCKS proxy through the tunnel
ssh -D 1080 -p 1080 localhost
```

## Accessing the GOAD Lab

### SSH to Jumpbox

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
2. Use smaller labs (GOAD-Mini, MINILAB) for basic testing
3. Set up AWS Budget alerts

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         AWS Account                              │
│                                                                  │
│  ┌─────────────────────────┐    ┌─────────────────────────────┐ │
│  │   Your C2 VPC           │    │      GOAD VPC               │ │
│  │                         │    │                             │ │
│  │  ┌─────────────────┐   │    │  ┌─────────────────────┐   │ │
│  │  │ C2 Team Server  │   │    │  │ DC01, DC02, DC03    │   │ │
│  │  │ (Cobalt Strike) │   │◄──►│  │ SRV02, SRV03        │   │ │
│  │  └─────────────────┘   │ VPC│  │ (Windows Servers)   │   │ │
│  │                         │Peer│  └─────────────────────┘   │ │
│  │  ┌─────────────────┐   │    │                             │ │
│  │  │ Your Bastion    │   │    │  ┌─────────────────────┐   │ │
│  │  │ (Windows+WSL2)  │   │    │  │ GOAD Jumpbox        │   │ │
│  │  └─────────────────┘   │    │  │ (Ubuntu, Ansible)   │   │ │
│  │                         │    │  └─────────────────────┘   │ │
│  └─────────────────────────┘    └─────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Next Steps

1. **Deploy a lab**: Start with GOAD-Mini or MINILAB
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

