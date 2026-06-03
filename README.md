# Red Team Infrastructure

A scalable, replicable red team infrastructure deployment framework for AWS with integrated vulnerable Active Directory lab environments.

## Overview

This project provides Infrastructure as Code (IaC) and automation scripts to deploy and manage red team infrastructure on AWS. Everything is driven from a single **AWS-hosted Dashboard Server** — the production control plane and the sole SSH jump into every deployment. The infrastructure is designed to be:

- **Scalable**: Easily expand to support larger operations
- **Replicable**: Deploy identical infrastructure across environments
- **Automated**: Minimal manual intervention required
- **Secure**: Built with security best practices
- **Maintainable**: Well-documented and version-controlled
- **Training Ready**: Includes GOAD (Game Of Active Directory) labs and a CCRTS exam-mirror lab for realistic attack practice

## Architecture

The infrastructure is built using:

- **Terraform**: Infrastructure provisioning and management
- **Ansible**: Configuration management and software deployment
- **AWS Services**: EC2, VPC, S3, Route 53, ACM, IAM, Secrets Manager, CloudWatch
- **Bash/Python Scripts**: Orchestration and automation
- **Web Application**: Flask + JavaScript management interface, hosted on the AWS Dashboard Server

### Access Model

The **Dashboard Server** is a dedicated EC2 instance in its own VPC (`10.100.0.0/16`) with a public Elastic IP, locked to your IP and SSH key. It is the **production control plane and the single SSH jump host** — every deployment branches out from it via VPC peering, so it reaches all instances directly (C2 servers, redirectors, attack box, GOAD jumpbox).

- **Operator laptop** → (SSH key + IP allow-list) → **Dashboard Server** (public EIP). The UI is reached with `ssh -L 5000:localhost:5000 <operator>@<dashboard-eip>`, then `http://localhost:5000`.
- **Deployments branch out from the Dashboard Server.** Its VPC is peered with every deployment VPC, so the dashboard reaches each instance directly. **There is no per-deployment SSH-relay bastion** — the Dashboard Server is the sole jump. (The GOAD jumpbox is retained, but only as the AD-lab Ansible provisioning host — not an access path.)
- **Running the dashboard on your laptop is a dev/test instance only.** Real engagements always run on the AWS Dashboard Server.

### Infrastructure Components

- **Dashboard Server**: AWS-hosted EC2 control plane + sole SSH jump host (own VPC, public EIP)
- **C2 Team Servers**: Command and control servers (private subnets)
- **Proxy/Redirector Servers**: Traffic forwarding servers (public subnets)
- **VPC**: Isolated network with public/private subnets, peered to the Dashboard Server
- **Security Groups**: Firewall rules for traffic control
- **GOAD Labs** (Optional): Vulnerable Active Directory environments, with a GOAD jumpbox that provisions the AD lab via Ansible
- **CCRTS Lab** (Optional): Self-contained CREST exam-mirror estate (Kali + Windows + AD + ELK)

## Getting Started

> **New to this project?** This section is the single blessed path. For the full walkthrough with prompt-by-prompt detail, see the **[Getting Started Guide](./docs/GETTING_STARTED.md)**.

Production runs on the **AWS Dashboard Server** — a dedicated EC2 instance that is the control plane and SSH jump host for every deployment. You provision it once from your laptop with one script; after that, operators only need an SSH key and a browser.

### Before you begin (on your laptop)

- An **AWS account** with permissions to create VPCs, EC2 instances, and IAM roles
- **AWS CLI** installed and configured (`aws configure`)
- **Terraform** >= 1.0
- **ssh**, **rsync**, **git**, and **jq**
- An **SSH key pair** (e.g. `~/.ssh/id_ed25519` — the setup script auto-detects common locations)

### Step 1 — Clone the repo and provision the Dashboard Server

```bash
git clone https://github.com/harr-sudo/Red_Team_Infra.git
cd Red_Team_Infra
./scripts/server/setup-dashboard.sh
```

`setup-dashboard.sh` is interactive. It prompts for your SSH public key, operator name, public IP, AWS region, and (optionally) a second operator, then it:

1. Writes `configs/dashboard.tfvars` from your answers.
2. Runs `terraform apply` on `module.dashboard_server` — provisioning a **new EC2 "Dashboard Server"** in its own VPC (`10.100.0.0/16`, public EIP, locked to your IP + SSH key).
3. Waits for the instance to come up (~2-3 minutes), then `rsync`s the repo to `/opt/redteam`, creates a Python venv, installs dependencies, and registers a **systemd `dashboard` service** so the web app runs persistently on the EC2.

When it finishes it prints your `ssh -L ...` connect command.

### Step 2 — Tunnel in and open the dashboard

```bash
ssh -L 5000:localhost:5000 <operator>@<dashboard-eip>
```

Then open **http://localhost:5000** in your browser.

### Step 3 — Configure and deploy from the browser

In the dashboard:

1. **Configure a deployment** — pick a deployment type (C2, GOAD, CCRTS, or combined) and set its options.
2. **Satisfy prerequisites** — register a domain (see [Domain Requirements](./docs/DOMAIN_REQUIREMENTS.md)) and upload your Cobalt Strike archive (see [Cobalt Strike Deployment](./docs/COBALT_STRIKE_DEPLOYMENT.md)). The dashboard validates both before letting you deploy.
3. **Deploy** — launch and watch the streaming logs.

C2/GOAD/CCRTS deployments branch out from the Dashboard Server via VPC peering, so it becomes the jump into every instance. There is no per-deployment bastion.

### Adding a second operator

Add their SSH public key and source IP to `configs/dashboard.tfvars` (`operator_ssh_public_keys` + `dashboard_allowed_ips`) and run `terraform apply` — or just answer the setup script's second-operator prompts. They then connect with the same `ssh -L 5000:localhost:5000 <operator>@<dashboard-eip>` tunnel. No AWS CLI, Terraform, or local tooling required on their end.

See [Centralized Dashboard Design](./docs/CENTRALIZED_DASHBOARD_DESIGN.md) for the full architecture and [Dashboard Server Jump Host Guide](./docs/BASTION_JUMPBOX.md) for the access model.

### Deployment Prerequisites (configured in the browser)

The dashboard enforces these before a deployment runs:

1. **Domain Configuration** — a registered primary domain (2-3 backups recommended for OpSec). See [Domain Requirements](./docs/DOMAIN_REQUIREMENTS.md).
2. **Cobalt Strike Archive** — upload your `.tar.gz` / `.zip` / `.tar` through the Deploy tab; it is reused for all future C2 deployments. See [Cobalt Strike Deployment](./docs/COBALT_STRIKE_DEPLOYMENT.md).
3. **Tools Repository** (optional) — point at `https://github.com/harr-sudo/red-team-tools` and configure auth to auto-deploy your tooling to the jumpbox / attack box. See [Tools Repository Quick Start](./docs/TOOLS_REPOSITORY_QUICK_START.md).

### Advanced / dev-only: laptop CLI

For development and testing you can run the dashboard locally or deploy straight from the CLI. **This is not the production path** — real engagements run on the AWS Dashboard Server above.

```bash
./scripts/deployment/deploy.sh        # Deploy infrastructure from the laptop
./scripts/utilities/health-check.sh   # Check status
./scripts/deployment/destroy.sh       # Tear down
```

This flow uses local AWS credentials and a local `configs/terraform.tfvars`. See the [Getting Started Guide](./docs/GETTING_STARTED.md) for the local-dev walkthrough.

## Project Structure

```
Red_Team_Infra/
├── terraform/          # Terraform configurations
│   ├── modules/        # Infrastructure modules (VPC, C2 servers, proxies, dashboard server, GOAD, CCRTS)
│   └── main.tf         # Main orchestration & deployment mode detection
├── ansible/            # Ansible playbooks and roles
├── scripts/            # Automation scripts
│   ├── server/         # setup-dashboard.sh, dashboard-manage.sh (production control plane)
│   └── deployment/     # deploy.sh, destroy.sh (CLI / dev path)
├── configs/            # Configuration files (dashboard.tfvars, terraform.tfvars)
├── tools/              # External tools
│   └── goad/           # GOAD (Game Of Active Directory) — vulnerable AD labs
├── webapp/             # Web application for infrastructure management (runs on the Dashboard Server)
├── uploads/            # Uploaded files (Cobalt Strike, etc.)
└── docs/               # Documentation
```

See [PLAN.md](./PLAN.md) for detailed architecture and planning information.

## Deployment Types

The `deployment_type` variable drives all architecture decisions. There are **12** deployment types across 4 categories:

- **C2-Only (3):** `c2-adhoc` (1 server), `c2-purple` (2 servers, redundancy), `c2-full` (3 servers, phase-based)
- **GOAD-Only (5):** `goad-mini`, `goad-light`, `goad-sccm`, `goad-full`, `goad-nha` (standalone AD labs)
- **CCRTS (1):** `ccrts` (self-contained CREST exam-mirror lab — no C2 integration)
- **Combined (3):** `combined-adhoc-mini`, `combined-adhoc-light`, `combined-full-full` (C2 + GOAD via VPC peering)

See [Deployment Modes](./docs/DEPLOYMENT_MODES.md) for the C2 sizing details.

## Key Features

### Dashboard Server Jump Host (single SSH entry point)

> The AWS-hosted **Dashboard Server** is the sole SSH jump into all instances. There is no per-deployment SSH-relay bastion — it has been removed from the architecture.

- **Single entry point** — one SSH tunnel to the Dashboard Server reaches every instance via VPC peering
- **In-browser Terminal** for SSH to any C2 server, redirector, attack box, or GOAD jumpbox — no manual hopping
- **Tunnel shortcuts** for RDP (attack box / GOAD VMs), the CS client, and the REST API
- **IAM instance role** — no AWS credentials stored on operator laptops
- **Tools Repository** automatically deployed to the GOAD jumpbox / attack box during provisioning

See [Dashboard Server Jump Host Guide](./docs/BASTION_JUMPBOX.md) (covers the Dashboard Server jump + the GOAD provisioning jumpbox).

### Web Application

- **Configuration editor** with deployment templates (save/load)
- **Prerequisite validation** — domain, Cobalt Strike, AWS permissions checked before deploy
- **One-click deployment** with real-time progress and streaming logs
- **Deployment Manager** — multi-project management, stop/start instances, destroy
- **Infrastructure Topology** — full-screen interactive graph with subnet clustering, draggable nodes, config-driven port labels, side panel with details
- **Beacon Management** — CS REST API integration with health monitoring, task correlation, network graph, quick payload generator
- **Terminal** — in-browser SSH to any deployed instance, multi-tab, tunnel shortcuts (RDP, CS Client, REST API)
- **Elastic Detection Rules** — MITRE-mapped SIEM rules for CS commands with one-click update
- **AWS Cost Tracking** — per-project cost monitoring with budget alerts
- **Host Setup Checker** — SSM-based validation of bootstrap scripts across all instances

See [Web Application Guide](./webapp/README.md) for details.

### Tools Repository

- **Private GitHub repository** for all red team tools — single source of truth
- **Automated deployment** to the jumpbox / attack box during infrastructure setup
- **Multi-user access** — each team member can clone to their laptop
- **Repository URL**: `https://github.com/harr-sudo/red-team-tools`

See [Tools Repository Quick Start](./docs/TOOLS_REPOSITORY_QUICK_START.md) for setup and [Tools Repository Access](./docs/TOOLS_REPOSITORY_ACCESS.md) for accessing tools.

### GOAD Labs (Game Of Active Directory)

Integrated vulnerable Active Directory environments for testing your C2 infrastructure:

| Lab | VMs | Forests | Domains | Description | Est. Cost |
|-----|-----|---------|---------|-------------|-----------|
| **goad-full** | 5 | 2 | 3 | Full lab — complete AD environment | ~$350/mo |
| **goad-light** | 3 | 1 | 2 | Smaller lab for limited resources | ~$200/mo |
| **goad-mini** | 1 | 1 | 1 | Minimalist — single domain | ~$75/mo |
| **goad-sccm** | 4 | 1 | 1 | Microsoft Configuration Manager lab (sccm.lab) | ~$300/mo |
| **goad-nha** | 5 | 1 | 2 | CTF challenge lab (ninja.hack + academy.ninja.lan) | ~$350/mo |

**Key Features:**
- Pre-configured vulnerabilities (Kerberoasting, AS-REP Roasting, DCSync, Pass-the-Hash, etc.)
- Integrated with C2 infrastructure via VPC peering (combined deployments)
- Built-in jumpbox that provisions the AD lab via Ansible
- Start/Stop functionality to save costs when not in use

See [GOAD Quick Start](./docs/GOAD_QUICK_START.md) for deployment instructions.

### CCRTS-Lab (CREST Exam Mirror)

AWS-hosted rehearsal environment that mirrors the **CCRTS** (CREST Certified Red Team Specialist) exam estate. Uses the publicly available CREST Community AMIs (account `126620636130`) copied cross-region into `eu-central-1`, with an AD estate and an ELK stack for detection-rule iteration. A single, fully self-contained deployment type — no size tiers and no C2 integration.

| Lab | Hosts | Description | Est. Cost |
|-----|-------|-------------|-----------|
| **ccrts** | 5 | Kali + Windows ws + DC (`ccrts.local`) + domain-joined ws + ELK (self-contained, no C2) | ~$310/mo |

**Key Features:**
- CREST Community AMIs (Kali + Windows) auto-discovered and copied to `eu-central-1`
- `ccrts.local` AD estate (DC + domain-joined Win workstation)
- Single-node ELK stack for detection-rule development
- Fully isolated — connects through the Dashboard Server jump (no public-facing services, no C2 peering)
- Cobalt Strike not included — exam CS is licensed only inside Pearson VUE; bring your own (runs on the Kali host directly)

See [CCRTS-Lab Operator Guide](./docs/CCRTS_LAB.md) for deployment, connection, and upgrade details.

## Documentation

### Essential Guides (Start Here)

- **[Getting Started Guide](./docs/GETTING_STARTED.md)** — Complete step-by-step setup for new operators (the blessed AWS-dashboard path)
- **[Web Application Guide](./webapp/README.md)** — The web interface for infrastructure management
- **[Centralized Dashboard Design](./docs/CENTRALIZED_DASHBOARD_DESIGN.md)** — Full Dashboard Server architecture
- **[Dashboard Server Jump Host Guide](./docs/BASTION_JUMPBOX.md)** — Single SSH jump into all instances (+ the GOAD provisioning jumpbox)
- **[Access Methods](./docs/ACCESS_METHODS.md)** — How to access C2 servers and deployed instances
- **[AWS Authentication Guide](./docs/AWS_AUTHENTICATION.md)** — How deployment connects to AWS (credentials / IAM instance role)

### Prerequisites

- **[Domain Requirements](./docs/DOMAIN_REQUIREMENTS.md)** — REQUIRED — domain registration and DNS setup
- **[Cobalt Strike Deployment](./docs/COBALT_STRIKE_DEPLOYMENT.md)** — REQUIRED — Cobalt Strike upload and deployment automation
- **[Tools Repository Quick Start](./docs/TOOLS_REPOSITORY_QUICK_START.md)** — Optional — tools repo setup and multi-user access

### Labs

- **[GOAD Quick Start](./docs/GOAD_QUICK_START.md)** — Deploy vulnerable AD labs
- **[CCRTS-Lab Operator Guide](./docs/CCRTS_LAB.md)** — CREST exam-mirror lab (CREST Community AMIs + AD + ELK)
- **[Deployment Modes](./docs/DEPLOYMENT_MODES.md)** — C2 deployment sizing (adhoc / purple / full)

### Reference

- **[Quick Reference](./docs/QUICK_REFERENCE.md)** — Quick commands and checklists
- **[Ansible SSH Key Distribution](./docs/ANSIBLE_SSH_KEYS.md)** — Automated SSH key distribution to all instances
- **[Tools Repository Setup](./docs/TOOLS_REPOSITORY_SETUP.md)** — Create the tools repo and configure multi-user access
- **[Tools Repository Access](./docs/TOOLS_REPOSITORY_ACCESS.md)** — Accessing tools on the jumpbox
- **[SSL Configuration](./docs/SSL_CONFIGURATION.md)** — TLS / certificate setup for redirectors
- [High-Level Plan](./PLAN.md) — Comprehensive project plan and architecture

### Legacy / Internal (historical design notes)

These are archived design and planning documents, kept for history. They are not part of the supported onboarding path.

- [GOAD Integration Plan](./docs/legacy/internal/GOAD_INTEGRATION_PLAN.md) — original GOAD integration architecture
- [Deployment Guide (legacy)](./docs/legacy/internal/deployment-guide.md) — older CLI deployment notes
- [Scripting Guide (legacy)](./docs/legacy/internal/scripting-guide.md) — automation-script internals
- [GitHub Setup (legacy)](./docs/legacy/internal/GITHUB_SETUP.md) — repository / collaboration setup notes

## Security

> **Important**: This infrastructure is designed for authorized red team operations only. Ensure you have proper authorization before deploying.

- Single SSH entry point — the Dashboard Server, gated by SSH key + IP allow-list
- All secrets stored in AWS Secrets Manager
- IAM roles with least privilege; the Dashboard Server uses an IAM instance role (no static keys on disk)
- Network isolation via VPC; C2 servers live in private subnets and are never directly internet-facing
- S3 confused-deputy protection (3-layer: trust policy, permission policy, bucket policy)
- Comprehensive logging and monitoring

## Contributing

1. Create a feature branch
2. Make your changes
3. Test thoroughly
4. Submit a pull request

## License

[Specify your license here]

## Support

For issues and questions, please open an issue in the repository.
