# CLAUDE.md — Red Team Infrastructure Framework

## Project Overview

Modular, deployable, and manageable AWS infrastructure for red team operations using Cobalt Strike. The framework automates provisioning of C2 servers, redirectors, bastion hosts, and vulnerable Active Directory labs (GOAD) with a security-first architecture.

**Repository:** https://github.com/harr-sudo/Red_Team_Infra

## Tech Stack

| Layer | Technology |
|---|---|
| Infrastructure | Terraform (HCL) >= 1.0 |
| Config Management | Ansible >= 2.9 |
| Web UI | Flask 3.0+ (Python) + vanilla JS |
| Cloud | AWS (EC2, VPC, S3, Route53, ACM, IAM, Secrets Manager, CloudWatch) |
| Scripting | Bash (POSIX-compatible) |
| C2 Framework | Cobalt Strike |
| Training Labs | GOAD (Game of Active Directory) |

## Project Structure

```
terraform/                  # Infrastructure as Code
├── main.tf                 # Main orchestration & deployment mode detection
├── variables.tf            # Input variables (589 lines)
├── outputs.tf              # Output definitions
└── modules/                # Reusable modules
    ├── vpc/                # VPC, subnets, NAT
    ├── security/           # Security groups & IAM
    ├── c2_team_server/     # Cobalt Strike team servers
    ├── proxy_redirector/   # Nginx HTTP/HTTPS redirectors
    ├── bastion/            # Windows jump box (RDP + WSL2)
    ├── goad/               # Vulnerable AD lab environments
    ├── cs_storage/         # S3 bucket + IAM (3-layer security)
    ├── dns/                # Route 53 DNS management
    ├── certificates/       # ACM SSL/TLS certificates
    ├── domain_fronting/    # CloudFront CDN proxy for domain fronting
    └── vpc_peering/        # Cross-VPC connectivity

ansible/                    # Configuration management
├── playbooks/              # SSH keys, tools repo, jumpbox setup
├── roles/
└── inventory/

webapp/                     # Deployment & management UI
├── backend/                # Flask API
│   ├── app.py              # Entry point
│   ├── routes/             # API endpoints (config, deploy, health, goad, aws_check)
│   ├── services/           # Business logic (terraform_service, aws_permissions)
│   └── utils/              # Validators, config parser, S3 upload
├── frontend/               # HTML/CSS/JS SPA
│   ├── index.html          # Main UI
│   ├── js/app.js           # Frontend logic
│   └── css/style.css
└── start.sh                # Startup script

scripts/                    # Orchestration & utilities
├── deployment/             # deploy.sh, destroy.sh
├── setup/                  # create-tools-repo.sh
└── utilities/              # health-check.sh, generate-inventory.sh, setup-ssh-keys.sh

configs/                    # Configuration files
├── terraform.tfvars        # Active config (DO NOT COMMIT secrets)
├── terraform.tfvars.example
└── ansible.cfg

docs/                       # 48+ documentation files
tools/goad/                 # GOAD submodule
generated-diagrams/         # Architecture diagrams (PNG)
```

## Deployment Modes

The `deployment_type` variable drives all architecture decisions. There are 11 options across 3 categories:

- **C2-Only:** `c2-adhoc` (1 server), `c2-purple` (2 servers, redundancy), `c2-full` (3 servers, phase-based)
- **GOAD-Only:** `goad-mini`, `goad-light`, `goad-sccm`, `goad-full`, `goad-nha` (standalone AD labs)
- **Combined:** `combined-adhoc-mini`, `combined-adhoc-light`, `combined-full-full` (C2 + GOAD with VPC peering)

## Key Commands

```bash
# Web app (recommended entry point)
./webapp/start.sh                     # http://127.0.0.1:5000

# Terraform
cd terraform
terraform init -var-file=../configs/terraform.tfvars
terraform plan -var-file=../configs/terraform.tfvars
terraform apply -var-file=../configs/terraform.tfvars
terraform destroy -var-file=../configs/terraform.tfvars

# Scripts
./scripts/deployment/deploy.sh        # Full deployment orchestration
./scripts/deployment/destroy.sh       # Teardown
./scripts/utilities/health-check.sh   # Validate infrastructure

# Python
pip install -r requirements.txt
python3 webapp/backend/app.py
```

## Coding Conventions

### Terraform (HCL)
- One module per infrastructure component in `terraform/modules/`
- Use `count` for conditional module inclusion based on deployment type
- Centralize deployment mode detection in `locals` blocks in `main.tf`
- Naming convention: `{project}-{environment}-{component}`
- All variables must have descriptions and sensible defaults in `variables.tf`
- Sensitive variables marked with `sensitive = true`
- Extensive inline comments explaining logic

### Python / Flask
- Blueprint pattern: separate route files per endpoint group in `routes/`
- Service layer in `services/` for business logic, separate from routes
- Utility modules in `utils/` (validators, config parsers, S3 operations)
- Flask binds to localhost only (security)
- CORS enabled for frontend-backend communication
- Error handling with meaningful messages in JSON responses

### Bash Scripts
- Always use `set -euo pipefail` for strict error handling
- ANSI color output for log levels (info, warn, error, success)
- Modular function structure
- Prerequisite checks before operations
- Resolve paths with `$(cd "$(dirname "$0")" && pwd)`

### Ansible
- Playbooks in `ansible/playbooks/`, roles in `ansible/roles/`
- SSH key-based auth only, no passwords
- Tasks must be idempotent (safe to re-run)
- Inventory-driven host discovery

### General
- No hardcoded secrets — use AWS Secrets Manager or `terraform.tfvars` (marked sensitive)
- Prefer editing existing files over creating new ones
- Keep modules self-contained with their own `main.tf`, `variables.tf`, `outputs.tf`

## Security Architecture

### Network
- **VPC isolation:** Private subnets for C2 servers, public subnets for redirectors
- **Bastion host pattern:** Single entry point for SSH/RDP access
- **Security group granularity:** Separate groups per component type
- **Management CIDR blocks:** Whitelist operator IPs only
- **VPC peering:** Controlled cross-VPC traffic for combined C2+GOAD

### S3 — Confused Deputy Protection (3 Layers)
1. **IAM Role Trust Policy:** `aws:SourceAccount` + `aws:SourceVpc` conditions
2. **IAM Permission Policy:** `aws:SourceVpc` + `aws:SecureTransport` conditions
3. **S3 Bucket Policy:** VPC endpoint restriction + account validation

Separate IAM roles per VPC (C2 vs GOAD). See `docs/S3_CONFUSED_DEPUTY_FIX.md`.

### Secrets & Credentials
- AWS Secrets Manager for passwords (bastion, team server)
- SSH keys generated locally, distributed via Ansible
- `terraform.tfvars` for deployment config (`.gitignore`d)
- Never commit: `.env`, credentials, SSH private keys, `terraform.tfvars`

### SSL/TLS
- Let's Encrypt (auto-renewal) or ACM certificates
- HTTPS enforced on redirectors
- Wildcard certificate support

### Domain Fronting (Optional)
- CloudFront CDN proxy hides redirector IPs behind CloudFront edge IPs
- Enabled via `enable_domain_fronting = true` — only for C2 deployments
- ACM certificate auto-provisioned in us-east-1 (CloudFront requirement, no Let's Encrypt needed)
- Caching fully disabled (required for C2 beacon callbacks)
- All headers, cookies, query strings forwarded to origin
- Redirector security groups locked to CloudFront IPs only when enabled
- Primary + backup domains pre-loaded as CloudFront aliases for instant rotation
- Front domain chosen operationally (not in Terraform) using recon tools like `FindFrontableDomains`

## Important Files

| File | Purpose |
|---|---|
| `terraform/main.tf` | Core orchestration, deployment mode detection |
| `terraform/variables.tf` | All input variable definitions |
| `terraform/modules/cs_storage/main.tf` | S3 security (confused deputy protection) |
| `terraform/modules/c2_team_server/main.tf` | Cobalt Strike server provisioning |
| `webapp/backend/app.py` | Flask API entry point |
| `webapp/backend/routes/deploy.py` | Deployment API endpoints |
| `webapp/backend/services/terraform_service.py` | Terraform integration logic |
| `webapp/frontend/js/app.js` | Frontend deployment UI logic |
| `configs/terraform.tfvars.example` | Configuration template |
| `scripts/deployment/deploy.sh` | CLI deployment orchestrator |

## Testing & Validation

No automated test suite. Validation is done via:
- `terraform validate` and `terraform plan` for infrastructure
- Web app health checks (prerequisites, AWS connectivity, IAM permissions)
- `scripts/utilities/health-check.sh` for post-deployment verification
- Manual verification of deployment outputs

## Prerequisites

- AWS account with appropriate IAM permissions
- AWS CLI configured (`aws configure`)
- Terraform >= 1.0
- Ansible >= 2.9
- Python 3.x with pip
- jq (JSON processing)
- Registered domain with Route 53 (for DNS/SSL)
- Cobalt Strike archive uploaded to S3 (for C2 deployments)

## Context for AI Assistance

- This is an **authorized security tool** for legitimate red team engagements and training
- All infrastructure is deployed into the operator's own AWS account
- GOAD labs provide **isolated, vulnerable AD environments** for practice
- The project prioritizes **operational security** — C2 servers are never directly internet-facing
- Redirectors act as traffic proxies with domain categorization support
- When modifying Terraform modules, always consider the impact across all 11 deployment types
- The web app is a local-only management interface, not a production web service
