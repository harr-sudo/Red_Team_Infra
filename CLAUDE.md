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
    ├── deployment_storage/ # S3 bucket + IAM + Secrets (3-layer security)
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

# SSM (preferred for remote instance access — no SSH key hopping needed)
aws ssm send-command --instance-ids <id> --region <region> \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["<command>"]'
aws ssm get-command-invocation --command-id <id> --instance-id <id> --region <region>
# Install session-manager-plugin for interactive sessions:
# brew install --cask session-manager-plugin
# aws ssm start-session --target <instance-id> --region <region>
```

### SSM Access Pattern
- **Prefer SSM over SSH hopping** for running commands on internal instances (C2 servers, redirectors, attack box)
- All EC2 instances have SSM agent installed and IAM roles attached
- Use `aws ssm send-command` for non-interactive commands, `aws ssm start-session` for interactive shells
- SSM eliminates the need for SSH key distribution to bastion for multi-hop access
- SSH is still used for: operator CS client tunnel (`ssh -L 50050:...`), bastion direct access
- **Use SSM for remote management and diagnostics:** checking service status, reading bootstrap logs, verifying setup steps, restarting services, and troubleshooting deployment issues on any instance
- **Use `AWS-RunPowerShellScript`** for Windows instances (attack box, bastion), **`AWS-RunShellScript`** for Linux (C2 servers, redirectors, jumpbox)
- **Always retrieve command output** via `aws ssm get-command-invocation` — SSM commands are async and may take time to complete
- **Bootstrap log locations:** Linux team servers: `/var/log/cs-install.log`, Windows attack box: `C:\Users\Administrator\Desktop\Deployment-Logs-Scripts\attackbox-init.log`, setup status JSON: `/opt/cobaltstrike/bootstrap-status` (Linux) or `C:\ProgramData\setup-status.json` (Windows)

## Coding Conventions

### Cobalt Strike REST API (MANDATORY)
- **ALWAYS read the OpenAPI spec before writing or modifying any CS REST API code.** The spec is at `docs/cobalt-strike-api/spec.js` (14K lines) with a summary at `docs/cobalt-strike-api/REST_API_REFERENCE.md`.
- **Check DTO schemas for exact field names.** Do NOT guess — e.g., the spec says `sleep` not `sleepTime`, `fakeArguments` not `args`, `pid` as int32 not string. Wrong field names cause silent 400 errors.
- **Every beacon POST endpoint returns `AsyncCommandResponse` with a `taskId`.** You MUST poll `GET /api/v1/tasks/{taskId}` for results. The response includes `taskAcknowledgements` (what CS client shows immediately) and `result` (actual output). Never fire-and-forget.
- **Task statuses:** `NOT_FOUND | IN_PROGRESS | COMPLETED | FAILED | OUTPUT_RECEIVED`. Some commands (sleep, checkin) stay `IN_PROGRESS` forever — check acknowledgements and stop polling after ~3 attempts.
- **Use dedicated endpoints, not consoleCommand**, when they exist. The REST API has structured endpoints for spawnto, ppid, blockdlls, argue, sleep, beaconGate, syscallMethod, tokenStore, BOF execution, etc. ConsoleCommand is the fallback only when no dedicated endpoint exists.
- **Non-beacon endpoints are synchronous.** Credential CRUD, listener CRUD, download listing, artifact listing return data immediately — no task polling needed.
- Backend code: `webapp/backend/services/beacon_service.py`, routes: `webapp/backend/routes/beacon.py`

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

### Frontend CSS / Light Mode
- **This app has dark AND light themes.** Every CSS change MUST be tested in both modes.
- Colors are defined in `webapp/frontend/css/palette.css` — never use raw hex values in `style.css` or inline styles. Use CSS variables.
- **Light mode gotcha:** `--gold` (`--accent`) and `--gold-muted` (`--accent-muted`) are olive/cream in dark mode but resolve to low-contrast values on light surfaces. In light mode, use `--text-primary` or `--text-secondary` for text that sits on card/section backgrounds.
- **Global `table thead tr`** has `background: var(--burgundy-dark)` with cream text. Any new table that does NOT use a brand-colored header must override this (e.g., `.my-table thead tr { background: transparent; }`).
- **Terminal-safe variables** (`--terminal-*`, `--bg-terminal`, `--text-terminal`) keep bright colors in both themes because terminal backgrounds are always dark. Use these for terminal/code areas only.
- **Rule of thumb:** if adding a `color:` or `background:` anywhere, check the resolved value in BOTH `[data-theme="light"]` and default (dark) in `palette.css`. Contrast ratio must be >= 4.5:1 for text.
- Inline `style="color: ..."` with CSS variables is fine, but verify the variable resolves correctly in both themes.

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
| `terraform/modules/deployment_storage/main.tf` | S3 storage, IAM, secrets (confused deputy protection) |
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
