# Deployment Dashboard — Design Spec

**Date:** 2026-04-01 (updated 2026-04-03)
**Status:** Draft — Pending review

---

## Overview

The dashboard runs from a single codebase — no code forks, no feature flags — on two targets, but only **one is the production path**:

- **Dashboard Server (production — the path)** — runs on a dedicated EC2 instance in AWS (own VPC, public EIP). This is the **production control plane and sole SSH/RDP jump host**: every deployment branches out from it via VPC peering, and it is the single entry point into all instances. Supports multi-operator shared access. Operators provision it with `./scripts/server/setup-dashboard.sh`, then `ssh -L 5000:localhost:5000 <op>@<dashboard-eip>` → browser.
- **Local Dev (dev/testing only)** — the same app run on the operator's laptop, for development/testing. **Not a production deployment option.**

> There is no per-deployment SSH-relay bastion — the Dashboard Server is the sole jump into all instances.

---

## Dual-Mode Architecture

| | Local Dev | Dashboard Server (production) |
|---|---|---|
| **Runs on** | Operator's laptop (dev/testing) | EC2 instance (`t3.medium`, own VPC, public EIP) |
| **Accessed via** | `http://localhost:5000` directly | SSH tunnel → `http://localhost:5000` |
| **AWS credentials** | Operator's `~/.aws/credentials` | IAM instance role (no creds on disk) |
| **Terraform state** | Local `.tfstate` per workspace | S3 backend + DynamoDB locking |
| **CS archive** | `uploads/` in project dir | `/opt/redteam/uploads/` on EBS (SCP once) |
| **Terminal SSH** | SSM / direct SSH to public hosts | Jump via Dashboard Server (direct VPC peering) |
| **Operator identity** | Single user (no tracking) | Per-user Linux accounts + audit trail |
| **Multi-operator** | No | Yes (2+ operators via SSH tunnel) |
| **Prerequisites** | Terraform, AWS CLI, Python, SSH | SSH client + browser (nothing else) |

**Architecture:**
- Dashboard runs on a dedicated EC2 instance in its own VPC (10.100.0.0/16)
- Operators access via SSH tunnel to localhost:5000
- VPC peering connects dashboard to deployment VPCs
- S3 backend for Terraform state, DynamoDB for locking
- Per-operator Linux accounts with scoped sudo

**Security model:**
- SSH tunnel is the authentication layer (SSH key + IP allowlist)
- Flask binds to 127.0.0.1 only, with loopback guard rejecting non-localhost requests
- CORS locked to localhost origins
- Scoped IAM role (no `ec2:*` / `secretsmanager:*` wildcards)
- StrictHostKeyChecking=accept-new with persistent known_hosts
- Shared SSH key for instance access (accepted risk — per-operator keys tracked as future improvement)

## Setup

```
1. Clone the repo
2. ./scripts/server/setup-dashboard.sh
3. ssh -L 5000:localhost:5000 ubuntu@<dashboard-eip>
4. Open http://localhost:5000
5. Configure deployment on the Configuration page
6. Deploy
```

Prerequisites: AWS account, SSH key, registered domain.

---

## Server Mode — Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Access method | SSH tunnel + localhost | Zero public web exposure, reuses CS client tunnel pattern |
| Terraform execution | On the server | Single source of truth, operators don't need AWS CLI locally |
| Provisioning | New Terraform module in this repo | Self-bootstrapping, one repo |
| App state persistence | File-based on EBS | No code changes, proven approach for 2 operators |
| Terraform state | S3 + DynamoDB locking | Durable, versioned, safe for concurrent access |
| CS archive | SCP once, reuse forever | 500MB upload once, persists on EBS |
| Tool uploads | Browser upload (small files) | Works through SSH tunnel for small files |
| Operator identity | SSH key mapping (per-user Linux accounts) | Audit trail without auth UI |
| Server resilience | Single EC2, no snapshots | Terraform state in S3, everything else regenerable |
| Instance type | t3.medium | Flask is lightweight, Terraform is bursty |
| Networking | Standalone VPC | Independent of deployments, always available |
| Deployment connectivity | VPC peering per deployment | Low-latency, reuses existing vpc_peering module |
| IP allowlisting | Static IPs in security group | Separate from per-deployment management_cidr_blocks |

---

## 1. Server Infrastructure

- Single `t3.medium` EC2 in dedicated VPC (`10.100.0.0/16`)
- One public subnet (internet access for AWS APIs, Terraform providers, apt)
- Ubuntu 22.04 LTS, 50GB gp3 EBS root volume
- IAM instance role with broad permissions (EC2, VPC, S3, Route53, ACM, IAM, Secrets Manager, CloudWatch, Cost Explorer, SSM)
- Security group: SSH (22) from `dashboard_allowed_ips` only — zero other inbound
- Flask binds `127.0.0.1:5000` — only accessible via SSH tunnel

**Bootstrap (user data):**
- Installs Python 3, pip, Terraform, AWS CLI v2, jq, git
- Clones repo from private GitHub (deploy key in Secrets Manager)
- Initializes git submodules (`tools/goad/`)
- Creates venv, installs requirements
- Registers Flask as `systemd` service with auto-restart
- Creates directory structure: `uploads/`, `uploads_tools/`, `logs/`, `configs/`

---

## 2. Operator Access

**SSH tunnel per operator (to the Dashboard Server EIP):**
```bash
ssh -L 5000:localhost:5000 ubuntu@<dashboard-eip>
# Open http://localhost:5000
```

**Identity via dedicated Linux users:**
- Each operator gets their own Linux user (`harris`, `operator2`)
- Server detects operator from `os.getlogin()` or SSH session
- All API actions tagged with operator name in logs

**Onboarding a new operator:**
1. Generate SSH key pair on their laptop
2. Send public key to admin
3. Admin adds key + IP to dashboard Terraform config
4. `terraform apply` updates instance
5. Operator tunnels in, opens browser — done

**What operators need locally:**
- SSH client
- A browser
- Nothing else

---

## 3. Terraform State Migration

Uncomment existing S3 backend in `terraform/main.tf`:

```hcl
backend "s3" {
  bucket         = "redteam-dashboard-tfstate"
  key            = "infrastructure/terraform.tfstate"
  region         = "eu-central-1"
  encrypt        = true
  dynamodb_table = "redteam-dashboard-tflock"
}
```

- S3 bucket: versioned, encrypted, private
- DynamoDB table: prevents concurrent applies
- Dashboard module provisions these resources (bootstrap with local state, then migrate)
- All deployment workspaces share the bucket, isolated by workspace key path

---

## 4. App State (Non-Terraform)

File-based on EBS — no code changes:

| State | Location | Regenerable? |
|-------|----------|-------------|
| Deployment state | `logs/deployment_state/*.json` | No (but terraform state in S3 is authoritative) |
| Deployment history | `logs/deployment_history.json` | No |
| Cost cache | `logs/cost_cache/*.json` | Yes (re-query AWS) |
| Cost settings | `logs/cost_settings.json` | Trivial to recreate |
| Setup check cache | `logs/setup_check_cache/*.json` | Yes (re-run SSM checks) |
| Config files | `configs/*.tfvars` | Recreatable via UI |
| CS archive | `uploads/*.tar` | Re-SCP from laptop |
| CS client | `uploads_client/*.zip` | Re-SCP from laptop |
| Tools staging | `uploads_tools/*` | Re-upload |
| C2 profiles | `profiles/` | In git repo |

If instance dies: stand up new one from Terraform module, re-SCP CS archive. ~15 min recovery.

---

## 5. VPC Peering to Deployments

Dashboard needs network path to:
- Team servers (beacon REST API, port 50050)
- Attack boxes (SCP tool transfers, SSH)
- GOAD jumpboxes (provisioning status, SSH)
- Redirectors (log checking, SSH)

SSM goes through AWS APIs — no VPC peering needed for SSM commands.

**Automatic peering per deployment:**
1. Dashboard module outputs VPC ID, CIDR, security group ID
2. Deployment modules accept optional `dashboard_vpc_id`, `dashboard_vpc_cidr`, `dashboard_sg_id`
3. When set, deployment creates:
   - VPC peering connection (dashboard ↔ deployment VPC)
   - Route table entries in both VPCs
   - Security group rules: dashboard SG → team server:50050, attack box:22, jumpbox:22, redirector:22
4. Peering destroyed with deployment

---

## 6. IP Allowlisting

Two separate, independent allowlists:

1. **Dashboard security group** — `dashboard_allowed_ips` — who can SSH into the dashboard server
2. **Per-deployment security groups** — `management_cidr_blocks` — break-glass direct SSH/RDP to deployment instances (the Dashboard Server is the normal path)

May overlap but managed independently. Dashboard module prompts for `dashboard_allowed_ips` as required variable.

---

## 7. CS Archive Management

- SCP once to server: `scp cobaltstrike-dist.tar ubuntu@<dashboard-eip>:/opt/redteam/uploads/`
- Persists on EBS, reused for every deployment
- Dashboard detects existing archive — skips "upload CS archive" prerequisite
- Only re-SCP when upgrading CS version

---

## 8. Code Changes Required

### A. New Module: `terraform/modules/dashboard_server/`
- `main.tf` — EC2, VPC, subnet, IGW, SG, IAM role, EBS
- `variables.tf` — `dashboard_allowed_ips`, `operator_ssh_public_keys`, `github_deploy_key_secret_arn`, region, instance type, VPC CIDR
- `outputs.tf` — dashboard IP, VPC ID, CIDR, SG ID
- `user_data.sh` — Bootstrap script

### B. Terraform Backend Migration
- Uncomment S3 backend in `main.tf`
- Add S3 bucket + DynamoDB table to dashboard module
- One-time `terraform init -migrate-state`

### C. Deployment Modules — Peering Wiring
- Optional `dashboard_vpc_id`, `dashboard_vpc_cidr`, `dashboard_sg_id` variables
- Conditional VPC peering + routes + SG rules
- Reuses existing `vpc_peering` module pattern

### D. Flask — Operator Identity
- Middleware: detect operator from Linux username (`os.getlogin()`)
- Tag deployment history with `initiated_by` field
- New `/api/whoami` endpoint

### E. Flask — Public IP Endpoint
- On server, returns server's public IP (which is what AWS sees for Terraform operations)
- Operator's home IP only relevant for `dashboard_allowed_ips`

### F. CS Archive — Persistent Location
- Check `/opt/redteam/uploads/` for existing archive
- Skip upload prerequisite if present

### G. Frontend — Operator Badge
- "Connected as: harris" in header bar
- Deployment history shows operator name

---

## 9. Terraform Variables

```hcl
variable "dashboard_allowed_ips" {
  description = "Operator IP CIDRs for SSH access"
  type        = list(string)
}

variable "operator_ssh_public_keys" {
  description = "Map of operator name to SSH public key"
  type        = map(string)
}

variable "github_deploy_key_secret_arn" {
  description = "Secrets Manager ARN for GitHub deploy key"
  type        = string
}

variable "instance_type" {
  default = "t3.medium"
}

variable "aws_region" {
  default = "eu-central-1"
}

variable "vpc_cidr" {
  default = "10.100.0.0/16"
}

variable "project_name" {
  default = "redteam-dashboard"
}

variable "ebs_volume_size" {
  default = 50
}
```

---

## 10. Bootstrap Sequence (One-Time)

```
Step 1: Create S3 bucket + DynamoDB for Terraform state
        (small bootstrap TF with local state)

Step 2: terraform apply -target=module.dashboard_server
        Provisions VPC, EC2, IAM, SG
        User data installs deps, clones repo, starts Flask

Step 3: SCP CS archive + client to server (once)
        scp cobaltstrike-dist.tar harris@<ip>:/opt/redteam/uploads/
        scp cobaltstrike-client.zip harris@<ip>:/opt/redteam/uploads_client/

Step 4: SSH tunnel in, verify
        ssh -L 5000:localhost:5000 harris@<ip>
        Open http://localhost:5000

Step 5: All subsequent deployments through dashboard UI
```

**Second operator onboarding:**
1. Generate SSH key, send public key
2. Add to `operator_ssh_public_keys` + `dashboard_allowed_ips`
3. `terraform apply`
4. Operator tunnels in — done

---

## 11. Security Model

| Layer | Control |
|-------|---------|
| Network | SSH only, operator IP allowlist |
| Authentication | SSH key per operator |
| Authorization | Both operators full access (2-person team) |
| Identity | Linux user per operator |
| Audit | Deployment history tagged with operator + timestamp |
| AWS access | IAM instance role (no credentials on disk) |
| Terraform state | S3 encrypted, DynamoDB locking |
| Dashboard | localhost-only binding, zero public web exposure |
| VPC peering | SG rules scoped to dashboard SG → specific ports |

---

## 12. Not In Scope (Server Mode)

- No database (file-based state is fine for 2 operators)
- No RBAC/permissions (both operators are equal)
- No HA/auto-scaling (single instance)
- No containerization (Flask on EC2)
- No EBS snapshots (everything regenerable)
- No CI/CD (git pull to update)
- No VPN (SSH tunnel sufficient)
- No HTTPS on dashboard (localhost via tunnel)

---

## 13. Choosing a Mode

**Production is always the Dashboard Server.** Local Dev is for working on the dashboard codebase itself, not for running engagements. Use the Dashboard Server for every real scenario:

| Scenario | Mode |
|----------|------|
| Solo operator, short engagement | Server |
| Solo operator, wants to close laptop and keep infra running | Server |
| Two operators, same engagement | Server |
| Training / GOAD lab | Server |
| Long-running engagement (weeks) | Server |
| Quick test deployment | Server |
| Developing/testing the dashboard app itself | Local (dev only) |

If you have been running a dev instance locally and want to move to the production Server:
1. Stand up the dashboard server (Section 10)
2. `terraform init -migrate-state` to move state to S3
3. SCP the CS archive to the server
4. Done — all existing deployments are visible on the server
