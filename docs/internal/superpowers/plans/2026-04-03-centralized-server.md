# Centralized Server Mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add centralized server deployment mode without breaking existing local mode. Every change is a no-op locally.

**Architecture:** Three workstreams executed in order: (1) dual-mode compatibility changes tested locally, (2) new dashboard server Terraform module + scripts, (3) state configuration. Workstream 1 modifies existing files but with zero-impact defaults. Workstreams 2-3 are entirely new files.

**Tech Stack:** Terraform (HCL), Python/Flask, Bash, AWS (EC2, VPC, S3, DynamoDB, IAM)

**Spec:** `docs/superpowers/specs/2026-04-03-centralized-server-implementation-design.md`

---

## Workstream 1: Dual-Mode Compatibility

### Task 1: Terraform — Dashboard Peering Variables

Add optional variables to existing modules so deployments can accept peering from a dashboard server. Empty defaults = no-op when unset.

**Files:**
- Modify: `terraform/modules/security/variables.tf` (after line 79)
- Modify: `terraform/modules/security/main.tf` (after line 374)
- Modify: `terraform/modules/c2_team_server/variables.tf` (after line 203)
- Modify: `terraform/modules/goad/variables.tf` (after line 249)
- Modify: `terraform/modules/vpc/main.tf` (after existing route tables)
- Modify: `terraform/main.tf` (module blocks, pass optional vars)

- [ ] **Step 1: Add variables to security module**

In `terraform/modules/security/variables.tf`, append:

```hcl
# Dashboard server peering (optional — empty = no peering)
variable "dashboard_vpc_id" {
  description = "Dashboard server VPC ID for peering (empty = disabled)"
  type        = string
  default     = ""
}

variable "dashboard_vpc_cidr" {
  description = "Dashboard server VPC CIDR for security group rules"
  type        = string
  default     = ""
}

variable "dashboard_sg_id" {
  description = "Dashboard server security group ID for ingress rules"
  type        = string
  default     = ""
}
```

- [ ] **Step 2: Add conditional SG rules to security module**

In `terraform/modules/security/main.tf`, after the existing VPC peering rules (line ~374), append conditional rules for dashboard access. Follow the existing `enable_vpc_peering` pattern:

```hcl
# =============================================================================
# DASHBOARD SERVER PEERING (optional — allows dashboard to reach C2 infra)
# =============================================================================

# Dashboard → C2 Team Server: SSH + CS port + REST API
resource "aws_security_group_rule" "c2_from_dashboard_ssh" {
  count                    = var.dashboard_sg_id != "" ? 1 : 0
  type                     = "ingress"
  from_port                = var.ssh_port
  to_port                  = var.ssh_port
  protocol                 = "tcp"
  source_security_group_id = var.dashboard_sg_id
  security_group_id        = aws_security_group.c2_team_server_sg.id
  description              = "SSH from dashboard server"
}

resource "aws_security_group_rule" "c2_from_dashboard_cs" {
  count                    = var.dashboard_sg_id != "" ? 1 : 0
  type                     = "ingress"
  from_port                = var.c2_server_port
  to_port                  = var.c2_server_port
  protocol                 = "tcp"
  source_security_group_id = var.dashboard_sg_id
  security_group_id        = aws_security_group.c2_team_server_sg.id
  description              = "CS client port from dashboard server"
}

resource "aws_security_group_rule" "c2_from_dashboard_rest" {
  count                    = var.dashboard_sg_id != "" && var.enable_cs_rest_api ? 1 : 0
  type                     = "ingress"
  from_port                = 50443
  to_port                  = 50443
  protocol                 = "tcp"
  source_security_group_id = var.dashboard_sg_id
  security_group_id        = aws_security_group.c2_team_server_sg.id
  description              = "CS REST API from dashboard server"
}

# Dashboard → Redirectors: SSH
resource "aws_security_group_rule" "redirector_from_dashboard" {
  count                    = var.dashboard_sg_id != "" ? 1 : 0
  type                     = "ingress"
  from_port                = var.ssh_port
  to_port                  = var.ssh_port
  protocol                 = "tcp"
  source_security_group_id = var.dashboard_sg_id
  security_group_id        = aws_security_group.proxy_redirector_sg.id
  description              = "SSH from dashboard server"
}

# Dashboard → Attack Box: SSH + RDP
resource "aws_security_group_rule" "attackbox_from_dashboard_ssh" {
  count                    = var.dashboard_sg_id != "" ? 1 : 0
  type                     = "ingress"
  from_port                = var.ssh_port
  to_port                  = var.ssh_port
  protocol                 = "tcp"
  source_security_group_id = var.dashboard_sg_id
  security_group_id        = aws_security_group.attack_box_sg.id
  description              = "SSH from dashboard server"
}

# Note: No RDP rule from dashboard — operators RDP via their own SSH tunnels, not through the dashboard server
```

- [ ] **Step 3: Add variables to c2_team_server and goad modules**

In `terraform/modules/c2_team_server/variables.tf`, append the same 3 variables (dashboard_vpc_id, dashboard_vpc_cidr, dashboard_sg_id with empty defaults).

In `terraform/modules/goad/variables.tf`, append the same 3 variables.

- [ ] **Step 4: Wire variables through main.tf**

In `terraform/main.tf`, add the optional variables to each module block that needs them. Only pass them when the dashboard module exists:

In the `locals` block (around line 85), add:
```hcl
dashboard_vpc_id   = var.enable_dashboard_server ? module.dashboard_server[0].dashboard_vpc_id : ""
dashboard_vpc_cidr = var.enable_dashboard_server ? module.dashboard_server[0].dashboard_vpc_cidr : ""
dashboard_sg_id    = var.enable_dashboard_server ? module.dashboard_server[0].dashboard_sg_id : ""
```

Pass to security module:
```hcl
dashboard_vpc_id   = local.dashboard_vpc_id
dashboard_vpc_cidr = local.dashboard_vpc_cidr
dashboard_sg_id    = local.dashboard_sg_id
```

Same for c2_team_server and goad modules.

- [ ] **Step 5: Verify local mode unaffected**

Run:
```bash
cd terraform
terraform plan -var-file=../configs/terraform.tfvars
```

Expected: Zero changes. All dashboard-related resources have count=0 because `enable_dashboard_server` defaults to false and all dashboard variables default to empty.

- [ ] **Step 6: Commit**

```bash
git add terraform/modules/security/variables.tf terraform/modules/security/main.tf \
  terraform/modules/c2_team_server/variables.tf terraform/modules/goad/variables.tf \
  terraform/main.tf
git commit -m "feat: add optional dashboard server peering variables (no-op when unset)"
```

---

### Task 2: Flask — Operator Identity

**Files:**
- Create: `webapp/backend/middleware/identity.py`
- Modify: `webapp/backend/app.py` (line 20 imports, line 44 blueprint registration)
- Modify: `webapp/backend/routes/deploy.py` (line 251, add_history_entry)

- [ ] **Step 1: Create identity module**

Create `webapp/backend/middleware/__init__.py` (empty) and `webapp/backend/middleware/identity.py`:

```python
"""
Operator Identity
Local mode: returns laptop username via os.getlogin()
Server mode: traces the SSH tunnel back to the Linux user who owns it
"""

import os
import re
import subprocess
from flask import Blueprint, jsonify, request

bp = Blueprint('identity', __name__)


def get_operator():
    """Detect the current operator.

    Local mode: os.getlogin() returns the macOS/Linux username.
    Server mode: traces the TCP connection from Flask back through the
    SSH tunnel to determine which Linux user owns the forwarding sshd process.
    """
    # Try os.getlogin() first — works in local mode
    try:
        name = os.getlogin()
        if name and name not in ('root', 'dashboard'):
            return name
    except OSError:
        pass

    # Server mode: trace the request's source port to its SSH tunnel owner
    try:
        remote_port = request.environ.get('REMOTE_PORT')
        if remote_port:
            result = subprocess.run(
                ['ss', '-tnp', f'sport = :{remote_port}'],
                capture_output=True, text=True, timeout=2
            )
            match = re.search(r'pid=(\d+)', result.stdout)
            if match:
                pid = match.group(1)
                user = subprocess.run(
                    ['ps', '-o', 'user=', '-p', pid],
                    capture_output=True, text=True, timeout=2
                ).stdout.strip()
                if user and user not in ('root', 'dashboard', ''):
                    return user
    except Exception:
        pass

    return os.environ.get('USER', 'unknown')


@bp.route('/api/whoami', methods=['GET'])
def whoami():
    """Return the current operator identity."""
    return jsonify({"operator": get_operator()})
```

- [ ] **Step 2: Register in app.py**

In `webapp/backend/app.py`, add import (line 20):
```python
from webapp.backend.middleware import identity
```

Add blueprint registration (after line 44):
```python
app.register_blueprint(identity.bp)
```

- [ ] **Step 3: Tag deployment history with operator**

In `webapp/backend/routes/deploy.py`, in the `add_history_entry()` function (around line 251), add `initiated_by`:

```python
from webapp.backend.middleware.identity import get_operator

# Inside add_history_entry(), add to the entry dict:
entry['initiated_by'] = get_operator()
```

- [ ] **Step 4: Test**

```bash
source venv/bin/activate
python3 -c "from webapp.backend.middleware.identity import get_operator; print(get_operator())"
# Expected: your macOS username

# Start the server and test the endpoint:
curl -s http://localhost:5000/api/whoami | python3 -m json.tool
# Expected: {"operator": "harriskhalid"}
```

- [ ] **Step 5: Commit**

```bash
git add webapp/backend/middleware/ webapp/backend/app.py webapp/backend/routes/deploy.py
git commit -m "feat: add operator identity middleware (/api/whoami)"
```

---

### Task 3: Frontend — Operator Badge

**Files:**
- Modify: `webapp/frontend/index.html` (line 22, before theme toggle)
- Modify: `webapp/frontend/js/app.js` (APP.init, around line 87)

- [ ] **Step 1: Add badge element to nav bar**

In `webapp/frontend/index.html`, before the theme toggle button (line 22), add:

```html
<span id="operator-badge" style="display: none; font-size: 0.8em; color: var(--text-muted); padding: 4px 10px; border: 1px solid var(--border-light); border-radius: 4px; white-space: nowrap;"></span>
```

- [ ] **Step 2: Fetch and display operator on page load**

In `webapp/frontend/js/app.js`, inside `APP.init()` (around line 87), add:

```javascript
// Fetch operator identity for badge
fetch('/api/whoami').then(r => r.json()).then(data => {
    const badge = document.getElementById('operator-badge');
    if (badge && data.operator) {
        badge.textContent = data.operator;
        badge.style.display = '';
    }
}).catch(() => {});
```

- [ ] **Step 3: Test**

Open browser, check nav bar shows your username in a subtle badge.

- [ ] **Step 4: Commit**

```bash
git add webapp/frontend/index.html webapp/frontend/js/app.js
git commit -m "feat: show operator identity badge in nav bar"
```

---

### Task 4: Terminal — Adaptive SSH Routing

**Files:**
- Modify: `webapp/backend/routes/terminal.py` (line 210-223, SSH command building)

- [ ] **Step 1: Add reachability check before SSH**

In `webapp/backend/routes/terminal.py`, before the SSH command is built (around line 210), add a TCP connectivity check:

```python
import socket

def _is_host_reachable(host, port=22, timeout=2):
    """Check if a host is directly reachable (e.g., via VPC peering)."""
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except (ConnectionRefusedError, socket.timeout, OSError):
        return False
```

- [ ] **Step 2: Use reachability to decide ProxyJump**

Update the SSH command building section. Replace the fixed ProxyJump logic:

```python
    # Build SSH command — skip ProxyJump if target is directly reachable (server mode with VPC peering)
    cmd = ['ssh',
           '-o', 'StrictHostKeyChecking=no',
           '-o', 'UserKnownHostsFile=/dev/null',
           '-o', 'ServerAliveInterval=30',
           '-o', 'LogLevel=ERROR']

    if bastion and not _is_host_reachable(host):
        cmd += ['-J', f'ubuntu@{bastion}']
    elif bastion and _is_host_reachable(host):
        ws.send(f'\x1b[90mDirect route available — skipping bastion jump\x1b[0m\r\n')

    if key_path:
        cmd += ['-i', os.path.expanduser(key_path)]

    cmd.append(f'{user}@{host}')
```

- [ ] **Step 3: Test locally**

Open Terminal tab, SSH to a private instance. Should still use ProxyJump (private IPs not reachable from laptop).

- [ ] **Step 4: Commit**

```bash
git add webapp/backend/routes/terminal.py
git commit -m "feat: adaptive SSH routing — direct when reachable, ProxyJump when not"
```

---

### Task 5: Verify Local Mode Intact

- [ ] **Step 1: Run full local verification**

```bash
# Terraform — no changes
cd terraform && terraform plan -var-file=../configs/terraform.tfvars
# Expected: No changes

# Flask — all endpoints work
cd .. && source venv/bin/activate
python3 -c "from webapp.backend.app import app; print('OK')"

# Start server, verify key endpoints
curl -s http://localhost:5000/api/whoami
curl -s http://localhost:5000/api/health/terraform
curl -s http://localhost:5000/api/config/

# Open browser — all tabs work, badge shows, topology works, terminal works
```

- [ ] **Step 2: Commit verification checkpoint**

```bash
git commit --allow-empty -m "checkpoint: workstream 1 complete — local mode verified unchanged"
```

---

## Workstream 2: Dashboard Server Module

### Task 6: Dashboard Server Terraform Module

All new files — zero risk to existing code.

**Files:**
- Create: `terraform/modules/dashboard_server/main.tf`
- Create: `terraform/modules/dashboard_server/variables.tf`
- Create: `terraform/modules/dashboard_server/outputs.tf`
- Create: `terraform/modules/dashboard_server/user_data.sh`

- [ ] **Step 1: Create variables.tf**

```hcl
variable "dashboard_allowed_ips" {
  description = "Operator IP CIDRs allowed to SSH into the dashboard"
  type        = list(string)
}

variable "operator_ssh_public_keys" {
  description = "Map of operator name to SSH public key"
  type        = map(string)

  validation {
    condition     = alltrue([for name, _ in var.operator_ssh_public_keys : can(regex("^[a-z][a-z0-9_-]{0,31}$", name))])
    error_message = "Operator names must be valid Linux usernames: lowercase, start with letter, 1-32 chars, only a-z 0-9 _ -"
  }

  validation {
    condition     = alltrue([for _, key in var.operator_ssh_public_keys : can(regex("^ssh-(ed25519|rsa|ecdsa) ", key))])
    error_message = "SSH keys must start with a valid key type (ssh-ed25519, ssh-rsa, ssh-ecdsa)"
  }
}

variable "instance_type" {
  description = "EC2 instance type for dashboard server"
  type        = string
  default     = "t3.medium"
}

variable "aws_region" {
  description = "AWS region for the dashboard server"
  type        = string
  default     = "eu-central-1"
}

variable "vpc_cidr" {
  description = "VPC CIDR for the dashboard server"
  type        = string
  default     = "10.100.0.0/16"
}

variable "project_name" {
  description = "Project name for resource tagging"
  type        = string
  default     = "redteam-dashboard"
}

variable "ebs_volume_size" {
  description = "Root EBS volume size in GB"
  type        = number
  default     = 50
}

variable "tags" {
  description = "Additional tags for all resources"
  type        = map(string)
  default     = {}
}
```

- [ ] **Step 2: Create main.tf**

```hcl
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# =============================================================================
# DATA SOURCES
# =============================================================================

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# =============================================================================
# VPC
# =============================================================================

resource "aws_vpc" "dashboard" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, {
    Name = "${var.project_name}-vpc"
  })
}

resource "aws_subnet" "dashboard" {
  vpc_id                  = aws_vpc.dashboard.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, 1) # x.x.1.0/24
  map_public_ip_on_launch = true

  tags = merge(var.tags, {
    Name = "${var.project_name}-public-subnet"
  })
}

resource "aws_internet_gateway" "dashboard" {
  vpc_id = aws_vpc.dashboard.id

  tags = merge(var.tags, {
    Name = "${var.project_name}-igw"
  })
}

resource "aws_route_table" "dashboard" {
  vpc_id = aws_vpc.dashboard.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.dashboard.id
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-rt"
  })
}

resource "aws_route_table_association" "dashboard" {
  subnet_id      = aws_subnet.dashboard.id
  route_table_id = aws_route_table.dashboard.id
}

# =============================================================================
# SECURITY GROUP
# =============================================================================

resource "aws_security_group" "dashboard" {
  name_prefix = "${var.project_name}-sg-"
  vpc_id      = aws_vpc.dashboard.id
  description = "Dashboard server — SSH from operator IPs only"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.dashboard_allowed_ips
    description = "SSH from operator IPs"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "All outbound"
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-sg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# =============================================================================
# IAM ROLE
# =============================================================================

resource "aws_iam_role" "dashboard" {
  name = "${var.project_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })

  tags = merge(var.tags, {
    Name = "${var.project_name}-role"
  })
}

# Scoped IAM policy — minimum permissions for Terraform operations
resource "aws_iam_policy" "dashboard" {
  name = "${var.project_name}-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "EC2Full"
        Effect   = "Allow"
        Action   = ["ec2:*"]
        Resource = "*"
        Condition = { StringEquals = { "aws:RequestedRegion" = [var.aws_region, "us-east-1"] } }
      },
      {
        Sid      = "NetworkingAndCDN"
        Effect   = "Allow"
        Action   = ["elasticloadbalancing:*", "cloudfront:*"]
        Resource = "*"
      },
      {
        Sid      = "S3Scoped"
        Effect   = "Allow"
        Action   = ["s3:*"]
        Resource = [
          "arn:aws:s3:::${var.project_name}-*",
          "arn:aws:s3:::${var.project_name}-*/*",
          aws_s3_bucket.tfstate.arn,
          "${aws_s3_bucket.tfstate.arn}/*"
        ]
      },
      {
        Sid      = "Route53"
        Effect   = "Allow"
        Action   = ["route53:*", "route53domains:*"]
        Resource = "*"
      },
      {
        Sid      = "ACM"
        Effect   = "Allow"
        Action   = ["acm:*"]
        Resource = "*"
      },
      {
        Sid      = "IAMScoped"
        Effect   = "Allow"
        Action   = [
          "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:PassRole",
          "iam:AttachRolePolicy", "iam:DetachRolePolicy", "iam:PutRolePolicy",
          "iam:DeleteRolePolicy", "iam:GetRolePolicy", "iam:ListRolePolicies",
          "iam:ListAttachedRolePolicies", "iam:TagRole", "iam:UntagRole",
          "iam:CreateInstanceProfile", "iam:DeleteInstanceProfile",
          "iam:AddRoleToInstanceProfile", "iam:RemoveRoleFromInstanceProfile",
          "iam:GetInstanceProfile", "iam:ListInstanceProfiles",
          "iam:ListInstanceProfilesForRole", "iam:CreatePolicy", "iam:DeletePolicy",
          "iam:GetPolicy", "iam:GetPolicyVersion", "iam:ListPolicyVersions"
        ]
        Resource = "*"
      },
      {
        Sid      = "SecretsManager"
        Effect   = "Allow"
        Action   = ["secretsmanager:*"]
        Resource = "*"
      },
      {
        Sid      = "Monitoring"
        Effect   = "Allow"
        Action   = ["logs:*", "cloudwatch:*", "ce:GetCostAndUsage", "ce:GetCostForecast"]
        Resource = "*"
      },
      {
        Sid      = "SSM"
        Effect   = "Allow"
        Action   = ["ssm:*"]
        Resource = "*"
      },
      {
        Sid      = "DynamoDB"
        Effect   = "Allow"
        Action   = ["dynamodb:*"]
        Resource = "arn:aws:dynamodb:${var.aws_region}:*:table/${var.project_name}-*"
      },
      {
        Sid      = "STS"
        Effect   = "Allow"
        Action   = ["sts:GetCallerIdentity"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "dashboard" {
  role       = aws_iam_role.dashboard.name
  policy_arn = aws_iam_policy.dashboard.arn
}

resource "aws_iam_instance_profile" "dashboard" {
  name = "${var.project_name}-profile"
  role = aws_iam_role.dashboard.name
}

# =============================================================================
# S3 STATE BACKEND (created by this module, used by server)
# =============================================================================

resource "aws_s3_bucket" "tfstate" {
  bucket_prefix = "${var.project_name}-tfstate-"
  force_destroy = false

  tags = merge(var.tags, {
    Name = "${var.project_name}-tfstate"
  })
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket                  = aws_s3_bucket.tfstate.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket_policy" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyUnencryptedTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.tfstate.arn, "${aws_s3_bucket.tfstate.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
      {
        Sid       = "DenyOtherAccounts"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.tfstate.arn, "${aws_s3_bucket.tfstate.arn}/*"]
        Condition = { StringNotEquals = { "aws:PrincipalAccount" = data.aws_caller_identity.current.account_id } }
      }
    ]
  })
  depends_on = [aws_s3_bucket_public_access_block.tfstate]
}

resource "aws_dynamodb_table" "tflock" {
  name         = "${var.project_name}-tflock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-tflock"
  })
}

# =============================================================================
# EC2 INSTANCE
# =============================================================================

resource "aws_instance" "dashboard" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.dashboard.id
  vpc_security_group_ids = [aws_security_group.dashboard.id]
  iam_instance_profile   = aws_iam_instance_profile.dashboard.name

  root_block_device {
    volume_size = var.ebs_volume_size
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = templatefile("${path.module}/user_data.sh", {
    operator_keys  = var.operator_ssh_public_keys
    s3_bucket      = aws_s3_bucket.tfstate.id
    dynamodb_table = aws_dynamodb_table.tflock.name
    aws_region     = var.aws_region
  })

  tags = merge(var.tags, {
    Name = "${var.project_name}-server"
  })
}

resource "aws_eip" "dashboard" {
  instance = aws_instance.dashboard.id
  domain   = "vpc"

  tags = merge(var.tags, {
    Name = "${var.project_name}-eip"
  })
}
```

- [ ] **Step 3: Create outputs.tf**

```hcl
output "dashboard_public_ip" {
  description = "Dashboard server public IP (EIP)"
  value       = aws_eip.dashboard.public_ip
}

output "dashboard_instance_id" {
  description = "Dashboard EC2 instance ID"
  value       = aws_instance.dashboard.id
}

output "dashboard_vpc_id" {
  description = "Dashboard VPC ID (for peering with deployment VPCs)"
  value       = aws_vpc.dashboard.id
}

output "dashboard_vpc_cidr" {
  description = "Dashboard VPC CIDR"
  value       = aws_vpc.dashboard.cidr_block
}

output "dashboard_sg_id" {
  description = "Dashboard security group ID"
  value       = aws_security_group.dashboard.id
}

output "tfstate_bucket" {
  description = "S3 bucket name for Terraform state"
  value       = aws_s3_bucket.tfstate.id
}

output "tflock_table" {
  description = "DynamoDB table for Terraform state locking"
  value       = aws_dynamodb_table.tflock.name
}
```

- [ ] **Step 4: Create user_data.sh**

```bash
#!/bin/bash
set -euo pipefail

exec > /var/log/dashboard-bootstrap.log 2>&1
echo "=== Dashboard bootstrap started at $(date) ==="

# System packages
apt-get update -y
apt-get install -y python3 python3-pip python3-venv jq unzip curl

# Terraform
TERRAFORM_VERSION="1.9.8"
curl -fsSL "https://releases.hashicorp.com/terraform/$${TERRAFORM_VERSION}/terraform_$${TERRAFORM_VERSION}_linux_amd64.zip" -o /tmp/terraform.zip
unzip -o /tmp/terraform.zip -d /usr/local/bin/
rm /tmp/terraform.zip
terraform --version

# AWS CLI v2
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
unzip -o /tmp/awscliv2.zip -d /tmp/
/tmp/aws/install --update
rm -rf /tmp/aws /tmp/awscliv2.zip
aws --version

# Create dedicated service user (Flask runs as this, not root)
useradd -r -s /usr/sbin/nologin -d /opt/redteam dashboard

# Create operator Linux users
%{ for name, key in operator_keys ~}
if ! id "${name}" &>/dev/null; then
  useradd -m -s /bin/bash "${name}"
  mkdir -p /home/${name}/.ssh
  echo "${key}" > /home/${name}/.ssh/authorized_keys
  chmod 700 /home/${name}/.ssh
  chmod 600 /home/${name}/.ssh/authorized_keys
  chown -R ${name}:${name} /home/${name}/.ssh
  # Scoped sudo — service management + terraform + logs only
  echo "${name} ALL=(ALL) NOPASSWD: /usr/bin/systemctl * dashboard, /usr/local/bin/terraform *, /usr/bin/journalctl *" > /etc/sudoers.d/${name}
fi
%{ endfor ~}

# Create project directories
mkdir -p /opt/redteam/{uploads,uploads_client,uploads_tools,logs,configs}
chown -R dashboard:dashboard /opt/redteam
chmod 755 /opt/redteam

# Write backend config for Terraform S3 state
cat > /opt/redteam/backend.hcl <<'BACKEND'
bucket         = "${s3_bucket}"
key            = "infrastructure/terraform.tfstate"
region         = "${aws_region}"
encrypt        = true
dynamodb_table = "${dynamodb_table}"
BACKEND

echo "=== Dashboard bootstrap completed at $(date) ==="
```

- [ ] **Step 5: Commit**

```bash
git add terraform/modules/dashboard_server/
git commit -m "feat: add dashboard server Terraform module (VPC, EC2, IAM, S3 state backend)"
```

---

### Task 7: Main.tf Integration

**Files:**
- Modify: `terraform/main.tf` (add variable + conditional module)

- [ ] **Step 1: Add enable variable and module block**

In `terraform/main.tf`, add the variable in the variables section and the module block after the existing VPC peering module (~line 670):

```hcl
# In variables section
variable "enable_dashboard_server" {
  description = "Deploy centralized dashboard server"
  type        = bool
  default     = false
}

# After VPC peering module
module "dashboard_server" {
  count  = var.enable_dashboard_server ? 1 : 0
  source = "./modules/dashboard_server"

  dashboard_allowed_ips    = var.dashboard_allowed_ips
  operator_ssh_public_keys = var.operator_ssh_public_keys
  instance_type            = var.dashboard_instance_type
  aws_region               = var.aws_region
  project_name             = var.project_name
  tags                     = local.common_tags
}

variable "dashboard_allowed_ips" {
  description = "Operator IP CIDRs for dashboard SSH access"
  type        = list(string)
  default     = []
}

variable "operator_ssh_public_keys" {
  description = "Map of operator name to SSH public key"
  type        = map(string)
  default     = {}
}

variable "dashboard_instance_type" {
  description = "Dashboard server instance type"
  type        = string
  default     = "t3.medium"
}
```

- [ ] **Step 2: Verify no-op when disabled**

```bash
cd terraform
terraform plan -var-file=../configs/terraform.tfvars
# Expected: Zero changes (enable_dashboard_server defaults to false)
```

- [ ] **Step 3: Verify resources when enabled**

```bash
terraform plan -var-file=../configs/terraform.tfvars -var="enable_dashboard_server=true" -var='dashboard_allowed_ips=["0.0.0.0/0"]' -var='operator_ssh_public_keys={"test":"ssh-ed25519 test"}'
# Expected: Shows ~15 resources to create (VPC, subnet, IGW, SG, IAM, EC2, EIP, S3, DynamoDB)
```

- [ ] **Step 4: Commit**

```bash
git add terraform/main.tf
git commit -m "feat: integrate dashboard server module in main.tf (disabled by default)"
```

---

### Task 8: Management Script

**Files:**
- Create: `scripts/server/dashboard-manage.sh`

- [ ] **Step 1: Create the script**

```bash
#!/bin/bash
set -euo pipefail

# Dashboard server management script
# Usage: ./dashboard-manage.sh {start|stop|restart|status|logs|upgrade}

SERVICE="dashboard"
REDTEAM_DIR="/opt/redteam"

case "${1:-help}" in
  start)
    echo "Starting dashboard..."
    sudo systemctl start "$SERVICE"
    echo "Dashboard started. Access via SSH tunnel + http://localhost:5000"
    ;;
  stop)
    echo "Stopping dashboard..."
    sudo systemctl stop "$SERVICE"
    echo "Dashboard stopped."
    ;;
  restart)
    echo "Restarting dashboard..."
    sudo systemctl restart "$SERVICE"
    echo "Dashboard restarted."
    ;;
  status)
    echo "=== Service Status ==="
    sudo systemctl status "$SERVICE" --no-pager || true
    echo ""
    echo "=== Disk Usage ==="
    df -h "$REDTEAM_DIR" 2>/dev/null || true
    echo ""
    echo "=== Active Terminal Sessions ==="
    ss -tnp | grep -c ":5000" || echo "0"
    ;;
  logs)
    echo "Streaming dashboard logs (Ctrl+C to stop)..."
    sudo journalctl -u "$SERVICE" -f
    ;;
  upgrade)
    echo "Upgrading dashboard..."
    echo "Note: Run this from the lead operator's laptop, not the server."
    echo "Rsyncing codebase..."
    # This is run from the operator's laptop:
    # rsync -avz --exclude=uploads/ --exclude=local-only/ --exclude=.git/ --exclude=venv/ --exclude=logs/ . user@server:/opt/redteam/
    # Then SSH in and run:
    cd "$REDTEAM_DIR"
    source venv/bin/activate
    pip install -r requirements.txt
    sudo systemctl restart "$SERVICE"
    echo "Upgrade complete."
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|logs|upgrade}"
    exit 1
    ;;
esac
```

- [ ] **Step 2: Make executable and commit**

```bash
chmod +x scripts/server/dashboard-manage.sh
git add scripts/server/dashboard-manage.sh
git commit -m "feat: add dashboard server management script"
```

---

### Task 9: Bootstrap Setup Script

**Files:**
- Create: `scripts/server/setup-dashboard.sh`

- [ ] **Step 1: Create the interactive setup script**

```bash
#!/bin/bash
set -euo pipefail

# ============================================================================
# Dashboard Server Setup — Interactive Bootstrap
# Run this from your laptop to provision the centralized dashboard in AWS
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"
CONFIGS_DIR="$PROJECT_ROOT/configs"
TFVARS_FILE="$CONFIGS_DIR/dashboard.tfvars"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

echo ""
echo "============================================"
echo "  Red Team Dashboard — Server Setup"
echo "============================================"
echo ""

# --- Prerequisites ---
info "Checking prerequisites..."

command -v aws >/dev/null 2>&1 || error "AWS CLI not found. Install: https://aws.amazon.com/cli/"
command -v terraform >/dev/null 2>&1 || error "Terraform not found. Install: https://terraform.io"
command -v ssh >/dev/null 2>&1 || error "SSH client not found."
command -v rsync >/dev/null 2>&1 || error "rsync not found."

# Verify AWS credentials
info "Verifying AWS credentials..."
AWS_IDENTITY=$(aws sts get-caller-identity 2>/dev/null) || error "AWS credentials not configured. Run: aws configure"
AWS_ACCOUNT=$(echo "$AWS_IDENTITY" | jq -r '.Account')
success "AWS account: $AWS_ACCOUNT"

# --- Auto-detect values ---

# SSH key
SSH_KEY_PATH=""
for candidate in ~/.ssh/id_ed25519.pub ~/.ssh/id_rsa.pub; do
    if [ -f "$candidate" ]; then
        SSH_KEY_PATH="$candidate"
        break
    fi
done

# Public IP
DETECTED_IP=$(curl -4 -s --max-time 5 https://api.ipify.org 2>/dev/null || echo "")

# AWS region
DETECTED_REGION=$(aws configure get region 2>/dev/null || echo "eu-central-1")

# Operator name
DETECTED_USER=$(whoami)

# --- Prompt for values ---
echo ""
info "Configure your dashboard server:"
echo ""

# SSH key
read -rp "Your SSH public key path [$SSH_KEY_PATH]: " INPUT_KEY
SSH_KEY_PATH="${INPUT_KEY:-$SSH_KEY_PATH}"
[ -f "$SSH_KEY_PATH" ] || error "SSH public key not found: $SSH_KEY_PATH"
SSH_KEY_CONTENT=$(cat "$SSH_KEY_PATH")
success "SSH key: $SSH_KEY_PATH"

# Operator name
read -rp "Your operator name [$DETECTED_USER]: " INPUT_USER
OPERATOR_NAME="${INPUT_USER:-$DETECTED_USER}"

# Public IP
read -rp "Your public IP [$DETECTED_IP]: " INPUT_IP
OPERATOR_IP="${INPUT_IP:-$DETECTED_IP}"
[ -n "$OPERATOR_IP" ] || error "Could not detect public IP. Enter manually."
success "Your IP: $OPERATOR_IP"

# Region
read -rp "AWS region [$DETECTED_REGION]: " INPUT_REGION
AWS_REGION="${INPUT_REGION:-$DETECTED_REGION}"

# Second operator (optional)
echo ""
read -rp "Second operator SSH public key (paste full key, or press Enter to skip): " OP2_KEY
OP2_NAME=""
OP2_IP=""
if [ -n "$OP2_KEY" ]; then
    read -rp "Second operator name: " OP2_NAME
    read -rp "Second operator IP: " OP2_IP
    [ -n "$OP2_NAME" ] || error "Operator name required"
    [ -n "$OP2_IP" ] || error "Operator IP required"
fi

# --- Generate tfvars ---
echo ""
info "Generating $TFVARS_FILE..."

mkdir -p "$CONFIGS_DIR"
cat > "$TFVARS_FILE" <<EOF
# Dashboard Server Configuration
# Generated by setup-dashboard.sh on $(date)

enable_dashboard_server = true
aws_region              = "$AWS_REGION"

dashboard_allowed_ips = [
  "$OPERATOR_IP/32",
$([ -n "$OP2_IP" ] && echo "  \"$OP2_IP/32\",")
]

operator_ssh_public_keys = {
  "$OPERATOR_NAME" = "$SSH_KEY_CONTENT"
$([ -n "$OP2_KEY" ] && echo "  \"$OP2_NAME\" = \"$OP2_KEY\"")
}
EOF

success "Generated: $TFVARS_FILE"

# --- Terraform ---
echo ""
info "Initializing Terraform..."
cd "$TERRAFORM_DIR"
terraform init

info "Planning dashboard server..."
terraform plan -var-file="$TFVARS_FILE" -target=module.dashboard_server -out=dashboard.tfplan

echo ""
read -rp "Apply this plan? (yes/no): " CONFIRM
[ "$CONFIRM" = "yes" ] || { warn "Aborted."; exit 0; }

info "Applying..."
terraform apply dashboard.tfplan
rm -f dashboard.tfplan

# Get the dashboard IP
DASHBOARD_IP=$(terraform output -raw -state=terraform.tfstate dashboard_public_ip 2>/dev/null || echo "")
[ -n "$DASHBOARD_IP" ] || error "Could not determine dashboard IP from Terraform output"

success "Dashboard server provisioned: $DASHBOARD_IP"

# --- Wait for instance ---
echo ""
info "Waiting for instance to be ready (this may take 2-3 minutes)..."
INSTANCE_ID=$(terraform output -raw -state=terraform.tfstate dashboard_instance_id 2>/dev/null || echo "")
if [ -n "$INSTANCE_ID" ]; then
    aws ec2 wait instance-status-ok --instance-ids "$INSTANCE_ID" --region "$AWS_REGION" 2>/dev/null || true
fi
# Extra wait for user_data to complete
sleep 30

# --- Rsync codebase ---
echo ""
info "Copying codebase to server..."
SSH_KEY_PRIVATE="${SSH_KEY_PATH%.pub}"
rsync -avz --progress \
    --exclude='uploads/' \
    --exclude='uploads_client/' \
    --exclude='uploads_tools/' \
    --exclude='local-only/' \
    --exclude='.git/' \
    --exclude='venv/' \
    --exclude='logs/' \
    --exclude='terraform.tfstate*' \
    --exclude='*.tfplan' \
    --exclude='.terraform/' \
    -e "ssh -i $SSH_KEY_PRIVATE -o StrictHostKeyChecking=accept-new" \
    "$PROJECT_ROOT/" \
    "$OPERATOR_NAME@$DASHBOARD_IP:/opt/redteam/"

success "Codebase synced"

# --- Remote setup ---
info "Setting up dashboard on server..."
ssh -i "$SSH_KEY_PRIVATE" -o StrictHostKeyChecking=accept-new "$OPERATOR_NAME@$DASHBOARD_IP" bash <<'REMOTE'
set -euo pipefail
cd /opt/redteam

# Create venv and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Initialize Terraform with S3 backend
cd terraform
terraform init -backend-config=/opt/redteam/backend.hcl

# Create systemd service
sudo tee /etc/systemd/system/dashboard.service > /dev/null <<'SERVICE'
[Unit]
Description=Red Team Dashboard
After=network.target

[Service]
Type=simple
User=dashboard
Group=dashboard
WorkingDirectory=/opt/redteam
ExecStart=/opt/redteam/venv/bin/python3 webapp/backend/app.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

# Hardening
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/redteam
PrivateTmp=true

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable dashboard
sudo systemctl start dashboard
REMOTE

success "Dashboard service started"

# --- Done ---
echo ""
echo "============================================"
echo "  Dashboard Server Ready!"
echo "============================================"
echo ""
echo "  IP:       $DASHBOARD_IP"
echo "  Connect:  ssh -L 5000:localhost:5000 $OPERATOR_NAME@$DASHBOARD_IP"
echo "  Open:     http://localhost:5000"
echo ""
echo "  Next steps:"
echo "  1. SCP Cobalt Strike archive:"
echo "     scp cobaltstrike.tar $OPERATOR_NAME@$DASHBOARD_IP:/opt/redteam/uploads/"
echo ""
if [ -n "$OP2_NAME" ]; then
echo "  2. Second operator connects:"
echo "     ssh -L 5000:localhost:5000 $OP2_NAME@$DASHBOARD_IP"
echo ""
fi
echo "============================================"
```

- [ ] **Step 2: Make executable and commit**

```bash
chmod +x scripts/server/setup-dashboard.sh
git add scripts/server/setup-dashboard.sh
git commit -m "feat: add interactive dashboard server setup script"
```

---

### Task 10: Dashboard tfvars Example

**Files:**
- Create: `configs/dashboard.tfvars.example`

- [ ] **Step 1: Create example file**

```hcl
# Dashboard Server Configuration
# Copy to configs/dashboard.tfvars and fill in your values
# Or run: ./scripts/server/setup-dashboard.sh (auto-generates this)

enable_dashboard_server = true

# AWS region for the dashboard server
aws_region = "eu-central-1"

# Operator IPs allowed to SSH into the dashboard (CIDR format)
dashboard_allowed_ips = [
  "YOUR_PUBLIC_IP/32",
  # "SECOND_OPERATOR_IP/32",
]

# SSH public keys for each operator (used for Linux user creation)
operator_ssh_public_keys = {
  "your-username" = "ssh-ed25519 AAAA... you@machine"
  # "operator2"   = "ssh-ed25519 AAAA... operator2@laptop"
}

# Optional overrides
# dashboard_instance_type = "t3.medium"
# ebs_volume_size         = 50
```

- [ ] **Step 2: Commit**

```bash
git add configs/dashboard.tfvars.example
git commit -m "feat: add dashboard.tfvars.example template"
```

---

### Task 11: Final Verification + Push

- [ ] **Step 1: Verify local mode one more time**

```bash
cd terraform
terraform plan -var-file=../configs/terraform.tfvars
# Expected: Zero changes

cd ..
source venv/bin/activate
python3 -c "from webapp.backend.app import app; print('App loads OK')"
node -c webapp/frontend/js/app.js && echo "JS OK"
```

- [ ] **Step 2: Commit and push**

```bash
git add -A
git status  # Review — no sensitive files, no local-only/
git commit -m "feat: centralized dashboard server mode (complete implementation)"
git push origin main
```
