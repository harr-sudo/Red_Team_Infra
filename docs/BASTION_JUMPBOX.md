# Bastion Host - Linux SSH Relay

> **Server Mode Note:** In Server Mode, the centralized dashboard server replaces most bastion functions. The dashboard provides in-browser SSH via the Terminal tab and has direct access to all instances through VPC peering. The bastion is still created for fallback/legacy access but is no longer the primary access path. See the Centralized Dashboard Design doc for server mode architecture.

## Server Mode vs Local Mode

In **Server Mode**, the dashboard server handles what the bastion traditionally does:

- **SSH access to instances** — The Terminal tab in the dashboard provides in-browser SSH to all C2 servers, redirectors, and the attack box. No manual bastion hopping required.
- **VPC peering** — The dashboard server's VPC (10.100.0.0/16) is peered with all deployment VPCs, giving it direct network access to every instance.
- **Bastion is still useful for:**
  - **RDP tunnel to attack box** — If you prefer a native RDP client over the web terminal, you can still tunnel through the bastion (or through the dashboard server).
  - **Direct SSH from operator laptop** — As a fallback when the dashboard is down or for operators who prefer CLI-only workflows.
  - **Legacy compatibility** — Existing scripts and SSH configs that reference the bastion will continue to work.

In **Local Mode**, the bastion remains the primary access point as described below.

---

## Overview

The bastion is a **lightweight Ubuntu 22.04 LTS instance** in the management subnet. It serves as an SSH relay/tunnel host for accessing private-subnet resources (C2 team servers, attack box). No red team tools are installed on the bastion — all operations happen on the Windows attack box.

## Architecture

```
Operator Laptop
    |
    ├── SSH ──────────────> Bastion (Ubuntu, Management Subnet, 10.0.0.10)
    |                          |
    |                          ├── SSH tunnel ──> C2 Team Servers (Private Subnet)
    |                          └── SSH tunnel ──> Attack Box RDP (Private Subnet)
    |
    └── SSH -L 3389:attack_box_ip:3389 ──> Bastion ──> Attack Box
            then RDP to localhost:3389
```

## Configuration

### Enable/Disable

In `terraform.tfvars`:
```hcl
enable_bastion = true  # Set to false to disable
```

### Instance Specifications

| Property | Default | Configurable |
|----------|---------|--------------|
| **OS** | Ubuntu 22.04 LTS | Yes (`bastion_ami_id`) |
| **Instance Type** | `t3.micro` | Yes (`bastion_instance_type`) |
| **vCPU** | 1 | Based on instance type |
| **RAM** | 1 GB | Based on instance type |
| **Storage** | 20 GB gp3, encrypted | Yes (`bastion_root_volume_size`) |
| **Elastic IP** | Always enabled | Automatic |
| **Auth** | SSH key-based only | Via EC2 key pair |

## Access Patterns

### 1. SSH to Bastion

```bash
ssh -i ~/.ssh/key.pem ubuntu@<bastion-eip>
```

### 2. Tunnel RDP to Attack Box

From your operator laptop, create an SSH tunnel through the bastion to the attack box:

```bash
# Create tunnel (attack box is in private subnet at 10.0.10.50)
ssh -i ~/.ssh/key.pem -L 3389:10.0.10.50:3389 ubuntu@<bastion-eip>

# Then connect your RDP client to localhost
mstsc /v:localhost:3389        # Windows
open rdp://localhost:3389      # macOS
xfreerdp /v:localhost:3389     # Linux
```

### 3. Tunnel CS Client to Team Server

```bash
# Create tunnel to team server's CS listener (port 50050)
ssh -i ~/.ssh/key.pem -L 50050:10.0.10.10:50050 ubuntu@<bastion-eip>

# Then connect Cobalt Strike client to localhost:50050
```

### 4. Multiple Tunnels at Once

```bash
# Tunnel both RDP to attack box and CS client to team server
ssh -i ~/.ssh/key.pem \
    -L 3389:10.0.10.50:3389 \
    -L 50050:10.0.10.10:50050 \
    ubuntu@<bastion-eip>
```

## Security Configuration

### Security Group Rules

**Inbound:**
- **SSH (22)**: From management CIDR blocks only

**Outbound:**
- **All traffic**: Allowed (for SSH to C2 servers, attack box, internet)

### SSH Hardening (Applied Automatically)

- `PermitRootLogin no`
- `PasswordAuthentication no`
- `MaxAuthTries 3`
- `AllowTcpForwarding yes` (required for tunneling)
- `X11Forwarding no`

### C2 Server Access

C2 servers allow SSH from:
- Bastion security group (primary method)
- Management CIDR blocks (fallback)

## Cost

**Monthly Cost (24/7):**
- **t3.micro Ubuntu**: ~$8/month
- **20 GB EBS storage**: ~$1.60/month
- **Elastic IP**: Free (when attached to running instance)
- **Total**: ~$10/month

## Bastion vs Attack Box

| Feature | Bastion | Attack Box |
|---------|---------|------------|
| **Purpose** | SSH relay/tunnel host | Red team operations workstation |
| **OS** | Ubuntu 22.04 | Windows Server 2022 |
| **Subnet** | Management (public) | Private |
| **Public IP** | Elastic IP | None |
| **Access** | SSH from internet | RDP via bastion tunnel only |
| **Tools** | None (minimal) | CS Client, PowerSploit, tools repo |
| **Cost** | ~$10/mo | ~$58/mo |

## Troubleshooting

### Can't SSH to Bastion

- Verify your IP is in `management_cidr_blocks`
- Check security group allows SSH (22) from your IP
- Verify key pair matches: `ssh -i ~/.ssh/key.pem ubuntu@<bastion-eip>`

### Can't Tunnel to C2 Servers / Attack Box

- Verify bastion security group allows outbound traffic
- C2/attack box security groups must allow SSH/RDP from bastion security group
- Test from bastion: `nc -zv 10.0.10.10 22` (C2 server) or `nc -zv 10.0.10.50 3389` (attack box)

### RDP Tunnel Not Working

- Ensure tunnel is active: `ssh -L 3389:10.0.10.50:3389 ubuntu@bastion`
- Check attack box is running: verify in AWS console
- Try alternate local port if 3389 is in use: `ssh -L 3390:10.0.10.50:3389 ...`

## Terraform Outputs

```bash
terraform output bastion_public_ip
terraform output bastion_private_ip
terraform output bastion_ssh_command
```
