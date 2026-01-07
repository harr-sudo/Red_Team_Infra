# Red Team Infrastructure

A scalable, replicable red team infrastructure deployment framework for AWS.

## Overview

This project provides Infrastructure as Code (IaC) and automation scripts to deploy and manage red team infrastructure on AWS. The infrastructure is designed to be:

- **Scalable**: Easily expand to support larger operations
- **Replicable**: Deploy identical infrastructure across environments
- **Automated**: Minimal manual intervention required
- **Secure**: Built with security best practices
- **Maintainable**: Well-documented and version-controlled

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

## Quick Start

> **New to this project?** Start with the [Getting Started Guide](./docs/GETTING_STARTED.md) for detailed step-by-step instructions.

### Web Application (Recommended)

For a user-friendly interface, use the web application:

```bash
# Start web application
./webapp/start.sh

# Then open browser to: http://127.0.0.1:5000
```

The web application provides:
- Configuration editor
- **Prerequisite validation** (Domain configuration & Cobalt Strike file)
- One-click deployment
- Status dashboard
- Health checks
- AWS permissions checker

See [Web Application README](./webapp/README.md) for details.

### Command Line

Alternatively, use the command-line scripts:

```bash
# Deploy infrastructure
./scripts/deployment/deploy.sh

# Check infrastructure status
./scripts/utilities/health-check.sh

# Destroy infrastructure
./scripts/deployment/destroy.sh
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
├── webapp/             # Web application for infrastructure management
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

### 🌐 Web Application
- **Local web interface** for infrastructure management
- **Configuration editor** for terraform.tfvars
- **Prerequisite validation** - Checks domain configuration and Cobalt Strike file before deployment
- **One-click deployment** with real-time status
- **AWS permissions checker** to validate required permissions

See [Web Application Guide](./webapp/README.md) for details.

## Documentation

### Essential Guides (Start Here)

- **[Getting Started Guide](./docs/GETTING_STARTED.md)** ⭐ - **Complete step-by-step setup guide for new users**
- **[Web Application Guide](./webapp/README.md)** 🌐 - **User-friendly web interface** for infrastructure management
- **[Bastion/Jump Box Guide](./docs/BASTION_JUMPBOX.md)** 🪟 - **Windows Server jump box with WSL2** - Easy access to C2 servers from home
- **[Access Methods](./docs/ACCESS_METHODS.md)** 🔑 - **How to access C2 servers** - Various access methods and options
- **[AWS Authentication Guide](./docs/AWS_AUTHENTICATION.md)** 🔐 - **How deployment connects to AWS** - Credential setup and authentication
- **[Domain Requirements](./docs/DOMAIN_REQUIREMENTS.md)** ⚠️ - **REQUIRED PREREQUISITE** - Domain registration guide
- **[Cobalt Strike Deployment](./docs/COBALT_STRIKE_DEPLOYMENT.md)** 📦 - **REQUIRED PREREQUISITE** - Cobalt Strike file upload and deployment automation
- **[Quick Reference](./docs/QUICK_REFERENCE.md)** - Quick commands and checklists
- **[GitHub Setup Guide](./docs/GITHUB_SETUP.md)** - Setting up GitHub integration (recommended for team collaboration)

### Detailed Documentation

- [High-Level Plan](./PLAN.md) - Comprehensive project plan and architecture
- [Ansible SSH Key Distribution](./docs/ANSIBLE_SSH_KEYS.md) 🔑 - **Automated SSH key distribution** to all instances
- **[Tools Repository Setup](./docs/TOOLS_REPOSITORY_SETUP.md)** 🛠️ - **Setting up tools repository** - Create repo and configure multi-user access
- [Tools Repository Access](./docs/TOOLS_REPOSITORY_ACCESS.md) 🛠️ - **Accessing tools repository** on jump box
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

