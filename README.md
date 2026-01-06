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
- One-click deployment
- Status dashboard
- Health checks

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

- **AWS Account** with appropriate permissions
- **Domain Registrations** ⚠️ **REQUIRED** - Primary domain + 2-3 backup domains (see [Domain Requirements](./docs/DOMAIN_REQUIREMENTS.md))
- **AWS CLI** installed and configured
- **Terraform** >= 1.0
- **Ansible** >= 2.9
- **Python 3.x**
- **jq** (for JSON processing)

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

# 5. Deploy infrastructure
./scripts/deployment/deploy.sh
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
├── ansible/            # Ansible playbooks and roles
├── scripts/            # Automation scripts
├── configs/            # Configuration files
└── docs/               # Documentation
```

See [PLAN.md](./PLAN.md) for detailed architecture and planning information.

## Documentation

### Essential Guides (Start Here)

- **[Getting Started Guide](./docs/GETTING_STARTED.md)** ⭐ - **Complete step-by-step setup guide for new users**
- **[Web Application Guide](./webapp/README.md)** 🌐 - **User-friendly web interface** for infrastructure management
- **[AWS Authentication Guide](./docs/AWS_AUTHENTICATION.md)** 🔐 - **How deployment connects to AWS** - Credential setup and authentication
- **[Domain Requirements](./docs/DOMAIN_REQUIREMENTS.md)** ⚠️ - **REQUIRED PREREQUISITE** - Domain registration guide
- **[Quick Reference](./docs/QUICK_REFERENCE.md)** - Quick commands and checklists
- **[GitHub Setup Guide](./docs/GITHUB_SETUP.md)** - Setting up GitHub integration (recommended for team collaboration)

### Detailed Documentation

- [High-Level Plan](./PLAN.md) - Comprehensive project plan and architecture
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

