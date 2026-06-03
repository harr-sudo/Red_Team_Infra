# Centralized Server Mode — Implementation Spec

**Date:** 2026-04-03
**Status:** Approved
**Depends on:** Existing local mode (must remain unchanged)

---

## Goal

Add a centralized server deployment mode to the dashboard. Same codebase, configuration-only differences. Every change is a no-op in local mode.

---

## Implementation Order

Compatibility changes first (testable locally) → Dashboard module (new files only) → State config (server-only).

---

## Workstream 1: Dual-Mode Compatibility

Build and test all changes locally before touching any server infrastructure.

### 1a. Terraform — Optional Dashboard Peering Variables

Add to `security/variables.tf`, `c2_team_server/variables.tf`, `goad/variables.tf`:

```hcl
variable "dashboard_vpc_id"   { default = "" }
variable "dashboard_vpc_cidr" { default = "" }
variable "dashboard_sg_id"    { default = "" }
```

Add conditional peering resources using `count = var.dashboard_vpc_id != "" ? 1 : 0`:
- VPC peering connection (dashboard VPC ↔ deployment VPC)
- Route table entries in both directions
- Security group rules: dashboard SG → team server:50050/50443, redirector:22, attack box:22, jumpbox:22

Wire variables through `main.tf` — passed to modules only when set.

**Test:** `terraform plan` locally shows zero changes (empty defaults = count 0).

### 1b. Flask — Operator Identity

New file `webapp/backend/middleware/identity.py`:
- `get_operator()` → returns `os.getlogin()`
- Registered as `/api/whoami` endpoint → `{"operator": "harris"}`

Update `webapp/backend/routes/deploy.py`:
- Tag deployment history entries with `initiated_by: get_operator()`

**Test:** Start webapp, `curl /api/whoami` returns macOS username.

### 1c. Frontend — Operator Badge

On page load, fetch `/api/whoami`. Show username badge in nav bar (right side, before theme toggle). `--text-muted` color, small font. No UI disruption.

**Test:** Open browser, badge shows username.

### 1d. Terminal Tab — Adaptive SSH Routing

When opening an SSH session to a private instance, check if the target IP is directly reachable (TCP connect with 2s timeout on port 22). If yes → direct SSH (server mode, VPC peering). If no → ProxyJump through bastion/jumpbox (local mode).

Detection runs once per session open, not continuously.

**Test:** Terminal tab still SSHs via ProxyJump locally (private IPs not directly reachable from laptop).

### 1e. Public IP Endpoint

No change needed. `/api/config/public-ip` already curls external services. On the server this returns the server's public IP (what AWS sees for Terraform). Locally returns the operator's IP. Both correct for their context.

---

## Workstream 2: Dashboard Server Module

All new files. Zero modification to existing code.

### 2a. Terraform Module: `terraform/modules/dashboard_server/`

**`main.tf`:**
- VPC: `var.vpc_cidr` (default `10.100.0.0/16`)
- One public subnet
- Internet gateway + route table
- EC2 instance: Ubuntu 22.04, `var.instance_type` (default `t3.medium`)
- EBS: `var.ebs_volume_size` (default 50GB), gp3, encrypted
- Security group: SSH/22 from `var.dashboard_allowed_ips` only
- IAM role + instance profile: EC2, VPC, S3, Route53, ACM, IAM, Secrets Manager, CloudWatch, Cost Explorer, SSM
- User data: `user_data.sh`

**`variables.tf`:**
```hcl
variable "dashboard_allowed_ips" {
  description = "Operator IP CIDRs for SSH access"
  type        = list(string)
}
variable "operator_ssh_public_keys" {
  description = "Map of operator name to SSH public key"
  type        = map(string)
}
variable "instance_type"   { default = "t3.medium" }
variable "aws_region"      { default = "eu-central-1" }
variable "vpc_cidr"        { default = "10.100.0.0/16" }
variable "project_name"    { default = "redteam-dashboard" }
variable "ebs_volume_size" { default = 50 }
```

**`outputs.tf`:**
- `dashboard_public_ip`
- `dashboard_vpc_id`
- `dashboard_vpc_cidr`
- `dashboard_sg_id`

**`user_data.sh`** — installs system dependencies only (code is rsynced by setup script after boot):
1. Install: Python 3, pip, Terraform, AWS CLI v2, jq
2. Create Linux users from `operator_ssh_public_keys` map, write authorized_keys
3. Create directories: `/opt/redteam/`, `/opt/redteam/uploads/`, `uploads_client/`, `uploads_tools/`, `logs/`, `configs/`
4. Create `backend.hcl` with S3 backend config

**Code deployment** — handled by `setup-dashboard.sh` after instance boots:
1. `rsync` the repo to server (excluding `uploads/`, `local-only/`, `.git/`, `venv/`, `logs/`)
2. SSH in: create venv, `pip install -r requirements.txt`
3. `terraform init -backend-config=/opt/redteam/backend.hcl`
4. Register Flask as systemd service (`dashboard.service`), enable, start

### 2b. S3 State Backend Resources

Created within the dashboard module:
- S3 bucket: versioned, encrypted (AES-256), private ACL, block public access
- DynamoDB table: hash key `LockID` (string), for Terraform state locking

These are created with local state during the initial `terraform apply` from the operator's laptop. The server then uses them via `backend.hcl`.

### 2c. Management Script: `scripts/server/dashboard-manage.sh`

```
Commands:
  start     systemctl start dashboard
  stop      systemctl stop dashboard
  restart   systemctl restart dashboard
  status    systemctl status + disk usage + active terminal sessions
  logs      journalctl -u dashboard -f
  upgrade   git pull origin main && pip install -r requirements.txt && systemctl restart dashboard
```

### 2d. Main.tf Integration

Add to `terraform/main.tf`:
```hcl
variable "enable_dashboard_server" {
  description = "Deploy centralized dashboard server"
  type        = bool
  default     = false
}

module "dashboard_server" {
  count  = var.enable_dashboard_server ? 1 : 0
  source = "./modules/dashboard_server"
  ...
}
```

`enable_dashboard_server` defaults to `false`. Local users never see it. Only set in `configs/dashboard.tfvars`.

### 2e. Bootstrap Script: `scripts/server/setup-dashboard.sh`

Interactive setup that the lead operator runs once from their laptop:

```
./scripts/server/setup-dashboard.sh

Auto-detects:
  - SSH public key (first found in ~/.ssh/id_ed25519.pub or ~/.ssh/id_rsa.pub)
  - Public IP (curl -s ifconfig.me)
  - AWS region (aws configure get region)
  - AWS identity (aws sts get-caller-identity — verifies credentials work)

Prompts for:
  - Confirm/override SSH public key path
  - Confirm/override public IP
  - Second operator's SSH public key (paste or skip)
  - Second operator's IP (or skip)
  - Confirm AWS region

Actions:
  1. Verifies AWS CLI credentials (`aws sts get-caller-identity`)
  2. Generates configs/dashboard.tfvars
  3. Runs terraform init
  4. Runs terraform apply -var-file=../configs/dashboard.tfvars -target=module.dashboard_server
  5. Waits for EC2 to be running (aws ec2 wait instance-status-ok)
  6. Rsyncs codebase to server (excluding uploads/, local-only/, .git/, venv/, logs/)
  7. SSH into server: create venv, pip install, terraform init with backend config, start systemd service
  8. Prints connection instructions:
     ssh -L 5000:localhost:5000 harris@<dashboard-ip>
     Then open http://localhost:5000
```

### 2f. Dashboard tfvars example

New file `configs/dashboard.tfvars.example`:
```hcl
enable_dashboard_server = true

dashboard_allowed_ips = [
  "YOUR_IP/32",
]

operator_ssh_public_keys = {
  "your-username" = "ssh-ed25519 AAAA... you@machine"
}
```

---

## Workstream 3: Terraform State Configuration

### 3a. Backend Block

The S3 backend block stays **commented out** in the repo's `main.tf`. Local users never see it.

The server's `user_data.sh` creates `/opt/redteam/backend.hcl`:
```hcl
bucket         = "redteam-dashboard-tfstate"
key            = "infrastructure/terraform.tfstate"
region         = "eu-central-1"
encrypt        = true
dynamodb_table = "redteam-dashboard-tflock"
```

And runs: `terraform init -backend-config=/opt/redteam/backend.hcl`

### 3b. Local Mode

Unchanged. No backend flags → Terraform uses local `.tfstate` files. Existing workflows unaffected.

---

## Onboarding Flow

### Lead Operator (first time)
```
1. Clone repo
2. ./scripts/server/setup-dashboard.sh
   → auto-detects key, IP, region
   → prompts for second operator details (optional)
   → generates dashboard.tfvars
   → terraform apply → EC2 running
3. SCP Cobalt Strike archive:
   scp cobaltstrike.tar harris@<ip>:/opt/redteam/uploads/
4. SSH tunnel in:
   ssh -L 5000:localhost:5000 harris@<ip>
5. Open http://localhost:5000
6. All deployments from here on go through the dashboard
```

### Second Operator
```
1. Generate SSH key: ssh-keygen -t ed25519
2. Send public key + IP to lead operator
3. Lead updates dashboard.tfvars, runs terraform apply
4. Operator connects:
   ssh -L 5000:localhost:5000 operator2@<ip>
5. Open http://localhost:5000
```

### IP Change
```
1. Update IP in dashboard.tfvars
2. terraform apply (updates security group in seconds)
```

---

## Files Changed (Existing)

| File | Change | Risk |
|------|--------|------|
| `terraform/modules/security/variables.tf` | Add 3 optional variables (empty defaults) | None — count=0 when unset |
| `terraform/modules/c2_team_server/variables.tf` | Same | None |
| `terraform/modules/goad/variables.tf` | Same | None |
| `terraform/modules/security/main.tf` | Add conditional peering SG rules | None — count=0 |
| `terraform/modules/vpc/main.tf` | Add conditional peering route table entries | None — count=0 |
| `terraform/main.tf` | Add dashboard_server module (count=0 by default) + pass optional vars | None |
| `webapp/backend/app.py` | Register identity blueprint | Additive |
| `webapp/backend/routes/deploy.py` | Add `initiated_by` to history entries | Additive |
| `webapp/frontend/index.html` | Add operator badge element | Additive |
| `webapp/frontend/js/app.js` | Fetch `/api/whoami`, show badge; adaptive SSH in terminal | Additive |

## Files Created (New)

| File | Purpose |
|------|---------|
| `terraform/modules/dashboard_server/main.tf` | Dashboard EC2, VPC, SG, IAM |
| `terraform/modules/dashboard_server/variables.tf` | Dashboard config variables |
| `terraform/modules/dashboard_server/outputs.tf` | VPC ID, CIDR, SG ID for peering |
| `terraform/modules/dashboard_server/user_data.sh` | System dependency installation + user creation |
| `webapp/backend/middleware/identity.py` | Operator identity + `/api/whoami` |
| `scripts/server/setup-dashboard.sh` | Interactive first-time setup (provision + rsync + start) |
| `scripts/server/dashboard-manage.sh` | Server lifecycle management |
| `configs/dashboard.tfvars.example` | Template for dashboard config |

---

## Testing Plan

| Step | Test | Pass criteria |
|------|------|---------------|
| After 1a | `terraform plan` locally | Zero changes |
| After 1b | `curl localhost:5000/api/whoami` | Returns username |
| After 1c | Open dashboard in browser | Badge visible |
| After 1d | Terminal SSH to team server | Works via ProxyJump |
| After 2d | `terraform plan` (no dashboard flag) | Zero changes |
| After 2d | `terraform plan -var="enable_dashboard_server=true"` | Shows dashboard resources |
| After 2e | Run setup script in dry-run | Generates valid tfvars |
| Full integration | Deploy server, tunnel in, deploy C2 from server | All tabs work, topology, terminal direct SSH via peering |

---

## Not In Scope

- Terraform state migration (separate task when ready to cut over)
- Database (file-based state is sufficient)
- RBAC / permissions (2-person team)
- HA / auto-scaling (single instance)
- Docker / containerization
- VPN (SSH tunnel is sufficient)
