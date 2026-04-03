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
- **Web Application**: Local management interface (Flask + JavaScript)

### Infrastructure Components

- **C2 Team Servers**: Command and control servers (private subnets)
- **Proxy/Redirector Servers**: Traffic forwarding servers (public subnets)
- **Bastion/Jump Box**: Windows Server with WSL2 for management access (public subnet)
- **VPC**: Isolated network with public/private subnets
- **Security Groups**: Firewall rules for traffic control
- **GOAD Labs** (Optional): Vulnerable Active Directory environments for testing

## Quick Start

> **New to this project?** Start with the [Getting Started Guide](./docs/GETTING_STARTED.md) for detailed step-by-step instructions.

### Option A: Run Locally (Single Operator)

Run the dashboard on your own machine. You need Terraform, AWS CLI, Python 3, and an SSH key.

```bash
# 1. Clone the repo
git clone https://github.com/harr-sudo/Red_Team_Infra.git
cd Red_Team_Infra

# 2. Start the dashboard
./webapp/start.sh

# 3. Open http://localhost:5000
```

Configure your deployment, upload Cobalt Strike, and deploy — all through the browser.

### Option B: Centralized Server (Multi-Operator)

Deploy the dashboard to an EC2 instance in AWS. Multiple operators access it via SSH tunnel — they only need an SSH client and a browser.

```bash
# 1. Stand up the dashboard server
cd terraform
terraform apply -target=module.dashboard_server

# 2. SCP the Cobalt Strike archive (once)
scp cobaltstrike-dist.tar ubuntu@<dashboard-ip>:/opt/redteam/uploads/

# 3. SSH tunnel in
ssh -L 5000:localhost:5000 youruser@<dashboard-ip>

# 4. Open http://localhost:5000
```

Second operator onboarding: add their SSH public key + IP to the dashboard Terraform config, `terraform apply`, done.

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
# Or use web app: ./webapp/start.sh
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
│   ├── modules/        # Infrastructure modules (VPC, C2 servers, proxies, bastion)
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

### 🪟 Windows Jump Box with WSL2
- **Dedicated Windows Server bastion host** for management access
- **WSL2 (Ubuntu)** for easy SSH access to C2 servers
- **RDP access** from home for Windows management
- **Linux environment** via WSL2 for command-line operations
- **Tools Repository** automatically deployed to `C:\Tools\` (Windows) and `/opt/tools/` (WSL2)

See [Bastion/Jump Box Guide](./docs/BASTION_JUMPBOX.md) for details.

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

## Documentation

### Essential Guides (Start Here)

- **[Getting Started Guide](./docs/GETTING_STARTED.md)** ⭐ - **Complete step-by-step setup guide for new users**
- **[Web Application Guide](./webapp/README.md)** 🌐 - **User-friendly web interface** for infrastructure management
- **[Bastion/Jump Box Guide](./docs/BASTION_JUMPBOX.md)** 🪟 - **Windows Server jump box with WSL2** - Easy access to C2 servers from home
- **[Access Methods](./docs/ACCESS_METHODS.md)** 🔑 - **How to access C2 servers** - Various access methods and options
- **[AWS Authentication Guide](./docs/AWS_AUTHENTICATION.md)** 🔐 - **How deployment connects to AWS** - Credential setup and authentication
- **[Domain Requirements](./docs/DOMAIN_REQUIREMENTS.md)** ⚠️ - **REQUIRED PREREQUISITE** - Domain registration guide
- **[Cobalt Strike Deployment](./docs/COBALT_STRIKE_DEPLOYMENT.md)** 📦 - **REQUIRED PREREQUISITE** - Cobalt Strike file upload and deployment automation
- **[GOAD Quick Start](./docs/GOAD_QUICK_START.md)** 🏰 - **Deploy vulnerable AD labs** - Quick setup for GOAD environments
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

