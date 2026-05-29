# Bastion Host - Linux SSH Relay (Legacy / Fallback)

> **Primary access is the Dashboard Server, not the bastion.** The AWS-hosted **Dashboard Server** — a dedicated EC2 instance in its own VPC (`10.100.0.0/16`) with a public EIP — is THE production control plane and SSH jump host. Every deployment branches out from it via VPC peering, and it reaches all instances directly. The per-deployment bastion documented below is **legacy/fallback only**. The operator's local machine runs only a **dev instance** of the dashboard; production always runs on the AWS Dashboard Server. See the Centralized Dashboard Design doc for the full architecture.

## Dashboard Server (primary) vs Bastion (legacy/fallback)

The AWS-hosted **Dashboard Server** is the primary jump and does everything the bastion traditionally did:

- **SSH access to instances** — The Terminal tab in the dashboard provides in-browser SSH to all C2 servers, redirectors, and the attack box. The Dashboard Server is a single-hop jump into every instance — no bastion hopping.
- **VPC peering** — The Dashboard Server's VPC (10.100.0.0/16) is peered with all deployment VPCs, giving it direct network access to every instance.
- **Operator tunnels go through the Dashboard Server EIP**, e.g. `ssh -L 50050:<c2-ip>:50050 ubuntu@<dashboard-eip>` for the CS client and `ssh -L 13389:<attackbox-ip>:3389 ubuntu@<dashboard-eip>` for RDP.

The **bastion is legacy/fallback only**. It is still created, but it is no longer the primary access path. It remains useful for:

- **Fallback access** — when the Dashboard Server is unavailable, or for operators who prefer a CLI-only workflow.
- **Legacy compatibility** — existing scripts and SSH configs that reference the bastion still work.

The remainder of this document describes the legacy bastion access patterns. For day-to-day operations, route through the Dashboard Server instead.

---

## Overview

The bastion is a **lightweight Ubuntu 22.04 LTS instance** in the management subnet. It serves as an SSH relay/tunnel host for accessing private-subnet resources (C2 team servers, attack box). No red team tools are installed on the bastion — all operations happen on the Windows attack box.

## Architecture (legacy path)

> Primary access is operator laptop → Dashboard Server (AWS) → instances. The diagram below shows the legacy bastion path, retained for fallback only.

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
