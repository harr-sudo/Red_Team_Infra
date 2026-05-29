# Dashboard Server Jump Host (+ GOAD provisioning jumpbox)

> **There is no per-deployment bastion.** Earlier versions of this framework deployed a dedicated SSH-relay "bastion" host inside each C2 deployment. That host has been **removed from the architecture**. The AWS-hosted **Dashboard Server** is now the sole SSH jump into every instance. This document describes the Dashboard Server as the jump host, and the **GOAD jumpbox** as the Active Directory lab provisioning host (a separate, GOAD-only role — not a bastion).

## Dashboard Server — the single SSH jump

The **Dashboard Server** is a dedicated EC2 instance in its own VPC (`10.100.0.0/16`) with a public EIP. It is the production control plane AND the SSH jump host. Every deployment branches out from it via VPC peering, so it reaches all instances directly — no SSH-hopping through an intermediate relay.

It does everything an SSH bastion traditionally did, and more:

- **SSH access to instances** — The Terminal tab in the dashboard provides in-browser SSH to all C2 servers, redirectors, and the attack box. The Dashboard Server is a single-hop jump into every instance.
- **VPC peering** — The Dashboard Server's VPC (10.100.0.0/16) is peered with all deployment VPCs, giving it direct network access to every instance.
- **Operator tunnels go through the Dashboard Server EIP**, e.g. `ssh -L 50050:<c2-ip>:50050 ubuntu@<dashboard-eip>` for the CS client and `ssh -L 13389:<attackbox-ip>:3389 ubuntu@<dashboard-eip>` for RDP.

The operator's local machine runs only a **dev instance** of the dashboard; production always runs on the AWS Dashboard Server. See the Centralized Dashboard Design doc for the full architecture.

### Architecture (operator access path)

```
Operator Laptop
    |
    └── SSH (key + IP allow-list) ──> Dashboard Server (own VPC 10.100.0.0/16, EIP)
                                          | VPC peering (direct, no relay hop)
                                          ├── SSH ─────> C2 Team Servers (private subnet)
                                          ├── SSH tunnel ─> Attack Box RDP (private subnet)
                                          └── SSH ─────> Redirectors (DMZ subnet)
```

## Access Patterns (through the Dashboard Server)

### 1. Open the Dashboard UI

```bash
ssh -L 5000:localhost:5000 ubuntu@<dashboard-eip>
# Then open http://localhost:5000 in your browser
```

### 2. Tunnel RDP to the Attack Box

From your operator laptop, create an SSH tunnel through the Dashboard Server to the attack box (private subnet, reached via VPC peering):

```bash
# Create tunnel (attack box is in the private subnet at 10.0.10.50)
ssh -i ~/.ssh/key.pem -L 13389:10.0.10.50:3389 ubuntu@<dashboard-eip>

# Then connect your RDP client to localhost
mstsc /v:localhost:13389        # Windows
open rdp://localhost:13389      # macOS
xfreerdp /v:localhost:13389     # Linux
```

### 3. Tunnel CS Client to the Team Server

```bash
# Create tunnel to team server's CS listener (port 50050)
ssh -i ~/.ssh/key.pem -L 50050:10.0.10.10:50050 ubuntu@<dashboard-eip>

# Then connect Cobalt Strike client to localhost:50050
```

### 4. Multiple Tunnels at Once

```bash
# Tunnel both RDP to attack box and CS client to team server
ssh -i ~/.ssh/key.pem \
    -L 13389:10.0.10.50:3389 \
    -L 50050:10.0.10.10:50050 \
    ubuntu@<dashboard-eip>
```

### In-browser alternative (no manual tunnels)

The dashboard's **Terminal tab** provides in-browser SSH to any instance using the server's own keypair, and **Tunnel shortcuts** (RDP, CS Client, REST API). For routine access you never need to set up SSH tunnels by hand.

## C2 Server Access (security groups)

C2 servers allow SSH (22), the CS client port (50050), and the REST API port (50443) inbound from the **Dashboard Server's security group** (or the Dashboard VPC CIDR). Management CIDR blocks remain as a direct-SSH fallback for break-glass scenarios.

---

## GOAD Jumpbox — Active Directory lab provisioning host

The **GOAD jumpbox** is a **separate, GOAD-only host** and is **not** a bastion. It is a `t2.small` Ubuntu instance in the GOAD VPC's public subnet, pre-loaded with Ansible and the GOAD repository. Its job is to **provision the vulnerable Active Directory lab** — it runs the GOAD Ansible playbooks against the Windows AD VMs.

| Property | Value |
|----------|-------|
| **Role** | Runs GOAD Ansible playbooks to provision the AD lab (DC, member servers, workstations) |
| **OS** | Ubuntu 22.04 LTS |
| **Instance Type** | `t2.small` |
| **Subnet** | GOAD VPC public subnet |
| **User** | `ubuntu` |
| **Tooling** | Ansible + GOAD repo pre-installed; SOCKS proxy support for C2 integration |

The jumpbox is reached the same way as everything else — **through the Dashboard Server** (the dashboard is the access jump; the jumpbox only provisions the lab):

```bash
# Reach the GOAD jumpbox via the Dashboard Server
ssh -L 22022:<goad-jumpbox-ip>:22 ubuntu@<dashboard-eip>
# Then: ssh -p 22022 ubuntu@localhost
```

From the jumpbox, the operator (or the dashboard's GOAD provisioning workflow) runs Ansible to stand up the AD lab. The jumpbox also offers a SOCKS proxy so a Cobalt Strike beacon can pivot into the GOAD network.

### Jumpbox vs Dashboard Server

| | Dashboard Server | GOAD Jumpbox |
|---|---|---|
| **Role** | Control plane + sole SSH jump into all instances | Provisions the GOAD AD lab (runs Ansible) |
| **Scope** | All deployments (C2, GOAD, combined) | GOAD / combined deployments only |
| **Reached via** | Operator laptop → Dashboard EIP (SSH tunnel) | Through the Dashboard Server |
| **Provisions AD?** | No | Yes — runs the GOAD playbooks |

## Cost

The GOAD jumpbox runs only with GOAD/combined deployments:

- **t2.small Ubuntu**: ~$15/month
- **20 GB EBS storage**: ~$1.90/month

The Dashboard Server (t3.medium + 20 GB EBS + EIP) is a one-per-team control plane, not a per-deployment cost.

## Troubleshooting

### Can't reach an instance through the Dashboard Server

- Verify your IP is in the dashboard's `management_cidr_blocks` allow-list
- Check the Dashboard Server security group allows SSH (22) from your IP
- Confirm VPC peering is active between the Dashboard VPC and the deployment VPC
- Confirm the target instance's security group allows traffic from the Dashboard SG / VPC CIDR

### GOAD provisioning fails on the jumpbox

- Confirm the jumpbox can reach the AD VMs (same GOAD VPC): `nc -zv <ad-vm-ip> 5985`
- Check the GOAD Ansible run logs on the jumpbox
- Verify the inventory `ip_range` was resolved correctly for the deployment
