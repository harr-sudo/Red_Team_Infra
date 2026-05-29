# Red Team Infrastructure

A scalable, replicable red team infrastructure deployment framework for AWS with integrated vulnerable Active Directory lab environments.

## Overview

This project provides Infrastructure as Code (IaC) and automation scripts to deploy and manage red team infrastructure on AWS. The infrastructure is designed to be:

- **Scalable**: Easily expand to support larger operations
- **Replicable**: Deploy identical infrastructure across environments
- **Automated**: Minimal manual intervention required
- **Secure**: Built with security best practices
- **Maintainable**: Well-documented and version-controlled
- **Training Ready**: Includes GOAD (Game Of Active Directory) labs for realistic attack practice

## Architecture

The infrastructure is built using:

- **Terraform**: Infrastructure provisioning and management
- **Ansible**: Configuration management and software deployment
- **AWS Services**: EC2, VPC, S3, CloudWatch, and more
- **Bash/Python Scripts**: Orchestration and automation
- **Web Application**: Flask + JavaScript management interface, hosted on the AWS Dashboard Server

### Access Model

The **Dashboard Server** is a dedicated EC2 instance in its own VPC (`10.100.0.0/16`) hosted in AWS. It is the **production control plane and SSH jump host** — every deployment branches out from it via VPC peering, and it is the single entry point into all instances (C2 servers, redirectors, attack box, GOAD jumpbox).

- **Operator laptop** → SSH key + IP allow-list → **Dashboard Server** (public EIP). The UI is reached with `ssh -L 5000:localhost:5000 ubuntu@<dashboard-eip>`, then `http://localhost:5000`. Running the dashboard on your laptop is a **dev instance only** — production always runs on the AWS Dashboard Server.
- **Deployments branch out from the Dashboard Server.** Its VPC is peered with every deployment VPC, so the dashboard reaches each instance directly. There is no per-deployment SSH-relay bastion — the Dashboard Server is the sole jump. (The GOAD jumpbox is retained, but only as the AD-lab Ansible provisioning host — not an access path.)

### Infrastructure Components

- **Dashboard Server**: AWS-hosted EC2 control plane + sole SSH jump host (own VPC, public EIP)
- **C2 Team Servers**: Command and control servers (private subnets)
- **Proxy/Redirector Servers**: Traffic forwarding servers (public subnets)
- **VPC**: Isolated network with public/private subnets
- **Security Groups**: Firewall rules for traffic control
- **GOAD Labs** (Optional): Vulnerable Active Directory environments for testing, with a GOAD jumpbox that provisions the AD lab via Ansible

## Quick Start

> **New to this project?** Start with the [Getting Started Guide](./docs/GETTING_STARTED.md) for detailed step-by-step instructions.

### Quick Start

Production runs on the **AWS Dashboard Server** — a dedicated EC2 instance that is the control plane and SSH jump host for every deployment. Operators access it via SSH tunnel; they only need an SSH key and a browser. (Running the dashboard on your laptop is a dev instance only.)

```bash
# 1. Clone the repo and provision the dashboard server
git clone https://github.com/harr-sudo/Red_Team_Infra.git
cd Red_Team_Infra
./scripts/server/setup-dashboard.sh

# 2. SSH tunnel in to the Dashboard Server (public EIP)
ssh -L 5000:localhost:5000 ubuntu@<dashboard-eip>

# 3. Open http://localhost:5000
```

Configure your deployment, upload Cobalt Strike, and deploy — all through the browser. Deployments branch out from the Dashboard Server via VPC peering, so it is the jump into every instance. Second operator onboarding: add their SSH public key + IP to the dashboard Terraform config, `terraform apply`, done.

See [Centralized Dashboard Design](./docs/CENTRALIZED_DASHBOARD_DESIGN.md) for full architecture.

### Command Line (Alternative)

Deploy without the web UI:

```bash
./scripts/deployment/deploy.sh      # Deploy infrastructure
./scripts/utilities/health-check.sh # Check status
./scripts/deployment/destroy.sh     # Tear down
```

### Prerequisites

#### Required Tools & Services
- **AWS Account** with appropriate permissions
- **AWS CLI** installed and configured
- **Terraform** >= 1.0
- **Ansible** >= 2.9
- **Python 3.x**
- **jq** (for JSON processing)

#### Deployment Prerequisites ⚠️ **REQUIRED BEFORE DEPLOYMENT**

These must be completed before deploying infrastructure:

1. **Domain Configuration** 🌐
   - **Primary domain** must be registered and configured
   - Configure `primary_domain_name` in `terraform.tfvars`
   - **Recommended**: 2-3 backup domains for redundancy
   - See [Domain Requirements](./docs/DOMAIN_REQUIREMENTS.md) for detailed setup guide

2. **Cobalt Strike File Upload** 📦
   - Cobalt Strike archive file (`.tar.gz`, `.zip`, or `.tar`) must be uploaded
   - **Via Web App**: Upload through the Deploy tab (stored locally in `uploads/` directory)
   - **Via CLI**: Place file in `uploads/` directory before deployment
   - File will be used for automated Cobalt Strike deployment to C2 servers
   - See [Cobalt Strike Deployment Guide](./docs/COBALT_STRIKE_DEPLOYMENT.md) for details

3. **Tools Repository Configuration** 🛠️ (Optional but Recommended)
   - **Repository already created**: `https://github.com/harr-sudo/red-team-tools`
   - Configure authentication in `terraform.tfvars` (Personal Access Token or SSH key)
   - Tools will be automatically deployed to jump box during infrastructure setup
   - See [Tools Repository Quick Start](./docs/TOOLS_REPOSITORY_QUICK_START.md) for setup

> **Note**: The web application will validate domain and Cobalt Strike file prerequisites before allowing deployment. Tools repository is optional but recommended for centralized tool management.

### Quick Setup

```bash
# 1. Clone or download the project
cd Red_Team_Infra

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Configure AWS credentials
aws configure

# 4. Copy and edit configuration
cp configs/terraform.tfvars.example configs/terraform.tfvars
# Edit terraform.tfvars with your values (see GETTING_STARTED.md)

# 5. Configure domain (REQUIRED)
# Set primary_domain_name in terraform.tfvars
# See docs/DOMAIN_REQUIREMENTS.md for details

# 6. Upload Cobalt Strike file (REQUIRED)
# Via web app: Upload through Deploy tab
# Via CLI: Place file in uploads/ directory

# 7. Configure tools repository (OPTIONAL but recommended)
# Set tools_repo_url and authentication in terraform.tfvars
# Repository already created: https://github.com/harr-sudo/red-team-tools
# See docs/TOOLS_REPOSITORY_QUICK_START.md for setup

# 8. Deploy infrastructure
./scripts/deployment/deploy.sh
# Or use the AWS Dashboard Server (production): ssh -L 5000:localhost:5000 ubuntu@<dashboard-eip>
```

### First Time Setup

For first-time users, follow the complete [Getting Started Guide](./docs/GETTING_STARTED.md) which includes:
- Detailed prerequisite installation
- AWS account setup
- Key pair creation
- Configuration walkthrough
- Verification steps

### GitHub Integration (Recommended)

For team collaboration and version control, see the [GitHub Setup Guide](./docs/GITHUB_SETUP.md) to:
- Set up private repository
- Enable team collaboration
- Configure CI/CD (optional)
- Follow best practices

## Project Structure

```
Red_Team_Infra/
├── terraform/          # Terraform configurations
│   ├── modules/        # Infrastructure modules (VPC, C2 servers, proxies, dashboard server)
│   └── main.tf         # Main configuration
├── ansible/            # Ansible playbooks and roles
├── scripts/            # Automation scripts
├── configs/            # Configuration files
├── tools/              # External tools
│   └── goad/           # GOAD (Game Of Active Directory) - vulnerable AD labs
├── webapp/             # Web application for infrastructure management
├── uploads/            # Uploaded files (Cobalt Strike, etc.)
└── docs/               # Documentation
```

See [PLAN.md](./PLAN.md) for detailed architecture and planning information.

## Key Features

### 🔑 Dashboard Server Jump Host (single SSH entry point)
> The AWS-hosted **Dashboard Server** is the sole SSH jump into all instances. There is no per-deployment SSH-relay bastion — it has been removed from the architecture.

- **Single entry point** — one SSH tunnel to the Dashboard Server reaches every instance via VPC peering
- **In-browser Terminal** for SSH to any C2 server, redirector, attack box, or GOAD jumpbox — no manual hopping
- **Tunnel shortcuts** for RDP (attack box / GOAD VMs), the CS client, and the REST API
- **IAM instance role** — no AWS credentials stored on operator laptops
- **Tools Repository** automatically deployed to the GOAD jumpbox / attack box during provisioning

See [Dashboard Server Jump Host Guide](./docs/BASTION_JUMPBOX.md) for details (covers the Dashboard Server jump + the GOAD provisioning jumpbox).

### 🛠️ Tools Repository
- **Private GitHub repository** for all red team tools
- **Automated deployment** to jump box during infrastructure setup
- **Centralized tool management** - single source of truth
- **Multi-user access** - each team member can clone to their laptop
- **Repository URL**: `https://github.com/harr-sudo/red-team-tools`

**Quick Setup:**
1. Repository already created at `harr-sudo/red-team-tools`
2. Configure authentication in `terraform.tfvars` (see [Quick Start](./docs/TOOLS_REPOSITORY_QUICK_START.md))
3. Tools automatically deployed to jump box during deployment
4. Access tools via RDP/SSH to jump box or clone directly to laptop

See [Tools Repository Quick Start](./docs/TOOLS_REPOSITORY_QUICK_START.md) for setup instructions.
See [Tools Repository Access](./docs/TOOLS_REPOSITORY_ACCESS.md) for accessing tools.

### 🏰 GOAD Integration (Vulnerable AD Labs)
- **Integrated GOAD labs** for realistic attack practice
- **Multiple lab types**: GOAD, GOAD-Light, GOAD-Mini, SCCM, NHA
- **Pre-configured vulnerabilities**: Kerberoasting, AS-REP Roasting, DCSync, Pass-the-Hash, and more
- **Built-in jumpbox**: SSH access and SOCKS proxy for C2 integration
- **Cost management**: Start/Stop labs to save money when not in use
- **VPC peering**: Seamless connectivity between C2 infrastructure and GOAD labs

**Quick Setup:**
1. Select GOAD lab type in Configuration page
2. Deploy alongside C2 infrastructure
3. Use jumpbox SOCKS proxy for Cobalt Strike access
4. Practice attacks on realistic AD environment

See [GOAD Integration Plan](./docs/GOAD_INTEGRATION_PLAN.md) for detailed architecture.
See [GOAD Quick Start](./docs/GOAD_QUICK_START.md) for deployment instructions.

### 🌐 Web Application
- **Configuration editor** with deployment templates (save/load)
- **Prerequisite validation** — domain, Cobalt Strike, AWS permissions checked before deploy
- **One-click deployment** with real-time progress and streaming logs
- **Deployment Manager** — multi-project management, stop/start instances, destroy
- **Infrastructure Topology** — full-screen interactive graph with subnet clustering, draggable nodes, config-driven port labels, side panel with details
- **Beacon Management** — CS REST API integration with health monitoring, task correlation, network graph, quick payload generator
- **Terminal** — in-browser local shell + SSH to any deployed instance, multi-tab, tunnel shortcuts (RDP, CS Client, REST API)
- **Elastic Detection Rules** — MITRE-mapped SIEM rules for CS commands with one-click update
- **AWS Cost Tracking** — per-project cost monitoring with budget alerts
- **Host Setup Checker** — SSM-based validation of bootstrap scripts across all instances

See [Web Application Guide](./webapp/README.md) for details.

### 🏰 GOAD Labs (Game Of Active Directory)

Integrated vulnerable Active Directory environments for testing your C2 infrastructure:

| Lab | VMs | Forests | Domains | Description | Est. Cost |
|-----|-----|---------|---------|-------------|-----------|
| **GOAD** | 5 | 2 | 3 | Full lab - complete AD environment | ~$350/mo |
| **GOAD-Light** | 3 | 1 | 2 | Smaller lab for limited resources | ~$200/mo |
| **GOAD-Mini** | 1 | 1 | 1 | Minimalist - single domain | ~$75/mo |
| **SCCM** | 4 | 1 | 1 | Microsoft Configuration Manager lab (sccm.lab) | ~$300/mo |
| **NHA** | 5 | 1 | 2 | CTF challenge lab (ninja.hack + academy.ninja.lan) | ~$350/mo |

**Key Features:**
- 🎯 Pre-configured vulnerabilities (Kerberoasting, AS-REP Roasting, DCSync, etc.)
- 🔗 Integrated with C2 infrastructure via VPC peering
- 📡 Built-in jumpbox for SOCKS proxy access
- 💰 Start/Stop functionality to save costs when not in use

See [GOAD Integration Plan](./docs/GOAD_INTEGRATION_PLAN.md) for setup details.
See [GOAD Quick Start](./docs/GOAD_QUICK_START.md) for deployment instructions.

### 🎓 CCRTS-Lab (CREST Exam Mirror)

AWS-hosted rehearsal environment that mirrors the **CCRTS** (CREST Certified Red Team Specialist) exam estate. Uses the publicly available CREST Community AMIs (account `126620636130`) copied cross-region into `eu-central-1`, with an AD estate and an ELK stack for detection rule iteration. A single, fully self-contained deployment type — no size tiers and no C2 integration, matching upstream [`spark42/ccrts-lab`](https://gitlab.com/spark42/ccrts-lab).

| Lab | Hosts | Description | Est. Cost |
|-----|-------|-------------|-----------|
| **ccrts** | 5 | Kali + Windows ws + DC (ccrts.local) + domain-joined ws + ELK (self-contained, no C2) | ~$310/mo |

**Key Features:**
- 🇬🇧 CREST Community AMIs (Kali + Windows) auto-discovered and copied to `eu-central-1`
- 🏰 `ccrts.local` AD estate (DC + domain-joined Win workstation)
- 📊 Single-node ELK stack for detection rule development
- 🔐 Fully isolated — connects through the dashboard EC2 jump host (no public-facing services, no C2 peering)
- ⚠️ Cobalt Strike not included — exam CS is licensed only inside Pearson VUE; bring your own (runs on the Kali host directly)

See [CCRTS-Lab Operator Guide](./docs/CCRTS_LAB.md) for deployment, connection, and upgrade details.

## Documentation

### Essential Guides (Start Here)

- **[Getting Started Guide](./docs/GETTING_STARTED.md)** ⭐ - **Complete step-by-step setup guide for new users**
- **[Web Application Guide](./webapp/README.md)** 🌐 - **User-friendly web interface** for infrastructure management
- **[Dashboard Server Jump Host Guide](./docs/BASTION_JUMPBOX.md)** 🔑 - **Single SSH jump into all instances** (+ the GOAD provisioning jumpbox)
- **[Access Methods](./docs/ACCESS_METHODS.md)** 🔑 - **How to access C2 servers** - Various access methods and options
- **[AWS Authentication Guide](./docs/AWS_AUTHENTICATION.md)** 🔐 - **How deployment connects to AWS** - Credential setup and authentication
- **[Domain Requirements](./docs/DOMAIN_REQUIREMENTS.md)** ⚠️ - **REQUIRED PREREQUISITE** - Domain registration guide
- **[Cobalt Strike Deployment](./docs/COBALT_STRIKE_DEPLOYMENT.md)** 📦 - **REQUIRED PREREQUISITE** - Cobalt Strike file upload and deployment automation
- **[GOAD Quick Start](./docs/GOAD_QUICK_START.md)** 🏰 - **Deploy vulnerable AD labs** - Quick setup for GOAD environments
- **[CCRTS-Lab Operator Guide](./docs/CCRTS_LAB.md)** 🎓 - **CREST exam mirror** - CREST Community AMI lab with optional AD + ELK
- **[Quick Reference](./docs/QUICK_REFERENCE.md)** - Quick commands and checklists
- **[GitHub Setup Guide](./docs/GITHUB_SETUP.md)** - Setting up GitHub integration (recommended for team collaboration)

### Detailed Documentation

- [High-Level Plan](./PLAN.md) - Comprehensive project plan and architecture
- [Ansible SSH Key Distribution](./docs/ANSIBLE_SSH_KEYS.md) 🔑 - **Automated SSH key distribution** to all instances
- **[Tools Repository Setup](./docs/TOOLS_REPOSITORY_SETUP.md)** 🛠️ - **Setting up tools repository** - Create repo and configure multi-user access
- [Tools Repository Access](./docs/TOOLS_REPOSITORY_ACCESS.md) 🛠️ - **Accessing tools repository** on jump box
- **[GOAD Integration Plan](./docs/GOAD_INTEGRATION_PLAN.md)** 🏰 - **Detailed GOAD architecture** - Full integration plan and connectivity
- [Deployment Guide](./docs/deployment-guide.md) - Detailed deployment instructions and advanced scenarios
- [Scripting Guide](./docs/scripting-guide.md) - Understanding automation scripts
- [Architecture Guide](./docs/architecture.md) - Detailed architecture (coming soon)
- [Operational Procedures](./docs/operational-procedures.md) - Day-to-day operations (coming soon)

## Security

⚠️ **Important**: This infrastructure is designed for authorized red team operations only. Ensure you have proper authorization before deploying.

- All secrets stored in AWS Secrets Manager
- IAM roles with least privilege
- Comprehensive logging and monitoring
- Network isolation via VPC

## Contributing

1. Create a feature branch
2. Make your changes
3. Test thoroughly
4. Submit a pull request

## License

[Specify your license here]

## Support

For issues and questions, please open an issue in the repository.

