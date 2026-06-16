# Getting Started Guide

This guide walks a brand-new operator from an empty laptop to a deployed engagement. It follows the **single blessed path**: provision the AWS **Dashboard Server**, then drive everything from the browser.

The Dashboard Server is a dedicated EC2 instance in its own VPC (`10.100.0.0/16`) with a public Elastic IP, locked to your IP and SSH key. It is the **production control plane and the sole SSH jump host** — every C2/GOAD/CCRTS deployment branches out from it via VPC peering. You provision it once; after that, operators only need an SSH key and a browser.

> **Running the dashboard on your laptop is dev/test only.** Real engagements run on the AWS Dashboard Server. The local-dev CLI path is covered briefly at the end under [Advanced: Local Dev / CLI](#advanced-local-dev--cli).

## Table of Contents

1. [Local Prerequisites](#1-local-prerequisites)
2. [Provision the Dashboard Server](#2-provision-the-dashboard-server)
3. [Connect to the Dashboard](#3-connect-to-the-dashboard)
4. [Your First Deployment (via the UI)](#4-your-first-deployment-via-the-ui)
5. [Onboard a Second Operator](#5-onboard-a-second-operator)
6. [Verification](#6-verification)
7. [Where to Go Next](#7-where-to-go-next)
8. [Advanced: Local Dev / CLI](#advanced-local-dev--cli)
9. [Troubleshooting](#troubleshooting)

---

## 1. Local Prerequisites

You run the one-time setup script from your laptop. Install these first.

### AWS account + credentials

You need an AWS account with permission to create VPCs, EC2 instances, and IAM roles, plus the AWS CLI configured:

```bash
# Install the AWS CLI
brew install awscli                 # macOS
# Linux: curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip && unzip awscliv2.zip && sudo ./aws/install

aws configure                       # enter Access Key, Secret Key, default region, output=json
aws sts get-caller-identity         # verify — should print your account/ARN
```

### Terraform >= 1.0

```bash
brew install terraform              # macOS (or use HashiCorp tap)
terraform --version
```

### ssh, rsync, git, jq

```bash
# macOS
brew install rsync git jq           # ssh and git are usually preinstalled

# Debian/Ubuntu
sudo apt-get update && sudo apt-get install -y openssh-client rsync git jq

ssh -V && rsync --version | head -1 && git --version && jq --version
```

### An SSH key pair

The setup script auto-detects `~/.ssh/id_ed25519.pub`, `~/.ssh/id_rsa.pub`, or `~/.ssh/id_ecdsa.pub` (and common Windows/WSL locations). If you don't have one:

```bash
ssh-keygen -t ed25519 -C "you@machine"
```

This key is used for two things: creating your Linux user on the Dashboard Server, and letting the setup script `rsync`/SSH into it.

> **No domain or Cobalt Strike archive needed yet.** Those are deployment prerequisites you'll handle in the browser at Step 4 — not for provisioning the Dashboard Server itself.

---

## 2. Provision the Dashboard Server

Clone the repo and run the interactive setup script:

```bash
git clone https://github.com/harr-sudo/Red_Team_Infra.git
cd Red_Team_Infra
./scripts/server/setup-dashboard.sh
```

### What each prompt asks

The script opens with an overview of what it will create — a `t3.medium` EC2 instance, a VPC (`10.100.0.0/16`), an Elastic IP, a security group, and an IAM role — along with the rough running cost (**~$30-45/mo while running**) and how long it takes (**~5-10 minutes**) — then asks a single **"Continue?"** before it does anything.

After you continue, it batches its prerequisite checks (AWS CLI + credentials, Terraform, `ssh`, `ssh-keygen`, `rsync`, `jq`, `curl`) and reports **all** missing tools at once rather than failing on the first one, then prompts for:

| Prompt | What it is | Default |
|---|---|---|
| **Your operator name** | Your Linux username on the server (lowercase, starts with a letter) | Your current `whoami` |
| **SSH public key path** | The key used to create your Linux user and to rsync/SSH into the server (an auto-generated key's comment is tagged with your operator name) | Auto-detected (`~/.ssh/id_ed25519.pub`, etc.) |
| **Your public IP** | Added to the SSH allow-list as `/32` | Auto-detected via `api.ipify.org` |
| **AWS region** | Region the Dashboard Server is created in | `aws configure get region`, else `eu-central-1` |
| **Second operator SSH key** | Optional — paste a colleague's public key to onboard them now | Skipped if blank (asks for their name + IP if provided) |

It asks for your operator name **before** the SSH key so that, if it auto-generates a key for you, the key's comment matches your operator name. Press Enter to accept any auto-detected default.

### What it provisions

After you confirm the Terraform plan (`yes`), the script:

1. Writes your answers to `configs/dashboard.tfvars` (`enable_dashboard_server = true`, `dashboard_allowed_ips`, `operator_ssh_public_keys`).
2. Runs `terraform apply` on `module.dashboard_server`, creating a **new EC2 "Dashboard Server"** in its own VPC (`10.100.0.0/16`), with a public EIP, a security group locked to your IP + SSH key, and an IAM instance role (so no AWS keys are ever stored on the box).
3. Waits for the instance to pass status checks, then waits for the first-boot completion marker (instead of a fixed sleep) so it only proceeds once `user_data` has actually finished.
4. **Probes SSH reachability** before syncing code. If it can't connect, it tells you your egress IP is likely no longer in the allow-list — a VPN or iCloud Private Relay can rotate it — and to re-run with `--update-ip`.
5. `rsync`s the repo to `/opt/redteam` (excluding local-only junk, secrets, and large artifacts), generates a server-side SSH keypair used to reach deployed instances, creates a Python venv, and `pip install`s dependencies.
6. Initializes Terraform on the server (S3 backend) and registers a **systemd `dashboard` service** so the Flask web app runs persistently and restarts on boot.
7. After starting the service, runs a **health check** that confirms the app actually responds on `:5000`, so "Ready!" means it's genuinely up. If the check fails it points you to the logs.

When it's done it prints your connect command and IP:

```
  IP:       <dashboard-eip>
  Connect:  ssh -L 5000:localhost:5000 <operator>@<dashboard-eip>
  Open:     http://localhost:5000
```

The final output also reminds you that if you can't connect later, your egress IP may have changed — re-run the script with `--update-ip` to refresh the allow-list.

> **Re-running is safe.** If a Dashboard Server already exists, the script offers a **resume mode** that re-syncs code, reinstalls deps, and restarts the service without recreating the instance. Use this to push code updates too (or use `dashboard-manage.sh upgrade` from the server). If you decline the resume prompt, the script **exits with guidance** rather than provisioning a second Dashboard Server.

---

## 3. Connect to the Dashboard

From your laptop, open the SSH tunnel printed by the setup script:

```bash
ssh -L 5000:localhost:5000 <operator>@<dashboard-eip>
```

Leave that session open, then browse to:

```
http://localhost:5000
```

The dashboard runs on the EC2 and authenticates to AWS through its IAM instance role — you will not be prompted for AWS credentials. Because the Dashboard Server is the jump host, its in-browser Terminal can SSH straight to any instance you later deploy.

---

## 4. Your First Deployment (via the UI)

Everything below happens in the browser.

### Step 1 — Pick a deployment type

On the Configure page, choose one of the **12** deployment types:

- **C2-Only:** `c2-adhoc`, `c2-purple`, `c2-full`
- **GOAD-Only:** `goad-mini`, `goad-light`, `goad-sccm`, `goad-full`, `goad-nha`
- **CCRTS:** `ccrts` (self-contained CREST exam-mirror lab — no C2 integration)
- **Combined:** `combined-adhoc-mini`, `combined-adhoc-light`, `combined-full-full`

If you're new, `c2-adhoc` is the smallest C2 footprint to start with. For lab practice without C2, `goad-mini` or `ccrts` are good first picks.

### Step 2 — Satisfy the prerequisites

For any C2 deployment the dashboard validates two prerequisites before it lets you deploy:

1. **Domain** — register a primary domain (2-3 backups recommended for OpSec) and set it in the config. Full walkthrough: **[Domain Requirements](./DOMAIN_REQUIREMENTS.md)**.
2. **Cobalt Strike archive** — upload your `.tar.gz` / `.zip` / `.tar` through the Deploy tab. It's stored once on the server and reused for every future C2 deployment. Full walkthrough: **[Cobalt Strike Deployment](./COBALT_STRIKE_DEPLOYMENT.md)**.

Optionally point at a **tools repository** to auto-deploy your tooling to the jumpbox / attack box — see [Tools Repository Quick Start](./TOOLS_REPOSITORY_QUICK_START.md). Pure `goad-*` and `ccrts` deployments don't require the domain or Cobalt Strike prerequisites.

### Step 3 — Deploy and watch the logs

Click **Deploy**. The dashboard runs Terraform on the server and streams the logs live. C2/GOAD/CCRTS deployments are created in their own VPC and **peered back to the Dashboard Server**, so the dashboard immediately becomes the jump into every new instance — no per-deployment bastion is created.

When it finishes, use the **Terminal** tab to SSH into any instance, or the tunnel shortcuts for RDP (attack box / GOAD VMs), the Cobalt Strike client, and the REST API. See [Access Methods](./ACCESS_METHODS.md) for every connection pattern.

---

## 5. Onboard a Second Operator

A second operator needs only an SSH key + a browser. **How you add them depends on whether the dashboard already exists** — operator Linux users are created by the server's `user_data`, which AWS runs **only once, at first boot**.

**Running dashboard (the usual case) — `onboard-operator.sh`.** This creates their `redteam`-group Linux user + authorized key live on the box (give it their name and public-key file):

```bash
./scripts/server/onboard-operator.sh operator2 ./operator2.pub
```

Then permit their source IP — a security-group change, which *does* apply live — by adding it to `dashboard_allowed_ips` in `configs/dashboard.tfvars` and re-applying:

```hcl
dashboard_allowed_ips = [
  "YOUR_PUBLIC_IP/32",
  "SECOND_OPERATOR_IP/32",
]
```

```bash
cd terraform
terraform apply -var-file=../configs/dashboard.tfvars -target=module.dashboard_server
```

> **Note:** adding them to `operator_ssh_public_keys` and re-applying does **not** create their Linux user on a *running* dashboard. `user_data` is boot-only and is intentionally ignored on an existing instance (so it neither re-runs nor replaces the control plane) — use `onboard-operator.sh` for the live user.

**Brand-new dashboard — bake them in.** Set `operator_ssh_public_keys` in `configs/dashboard.tfvars` *before* the first apply and they're created at boot:

```hcl
operator_ssh_public_keys = {
  "your-username" = "ssh-ed25519 AAAA... you@machine"
  "operator2"     = "ssh-ed25519 AAAA... operator2@laptop"
}
```

Either way they then connect with no AWS CLI or Terraform on their laptop — just an SSH key + browser:

```bash
./scripts/server/connect-dashboard.sh operator2@<dashboard-eip>
# forwards the port + opens a single-use signed login URL
```

---

## 6. Verification

**Dashboard Server is up:**

```bash
cd terraform
terraform output dashboard_public_ip      # should print the EIP
```

**Service is running** (SSH to the server, no tunnel needed):

```bash
ssh <operator>@<dashboard-eip>
./scripts/server/dashboard-manage.sh status   # systemd status + disk + active sessions
./scripts/server/dashboard-manage.sh logs     # stream the Flask logs
```

**Dashboard reachable:** the tunnel from Step 3 is open and `http://localhost:5000` loads.

**A deployment is healthy:** after deploying, run the health check from the server or use the dashboard's Host Setup Checker (SSM-based bootstrap validation across all instances):

```bash
./scripts/utilities/health-check.sh
```

---

## 7. Where to Go Next

- **[Access Methods](./ACCESS_METHODS.md)** — every way to reach C2 servers and deployed instances through the Dashboard Server
- **[Dashboard Server Jump Host Guide](./BASTION_JUMPBOX.md)** — the jump-host model in depth (and the GOAD provisioning jumpbox, which is *not* an access bastion)
- **[Centralized Dashboard Design](./CENTRALIZED_DASHBOARD_DESIGN.md)** — full architecture of the control plane
- **[GOAD Quick Start](./GOAD_QUICK_START.md)** — deploy and use the vulnerable AD labs
- **[CCRTS-Lab Operator Guide](./CCRTS_LAB.md)** — the CREST exam-mirror lab (CREST Community AMIs + AD + ELK)
- **[Cobalt Strike Deployment](./COBALT_STRIKE_DEPLOYMENT.md)** and **[Domain Requirements](./DOMAIN_REQUIREMENTS.md)** — the deployment prerequisites in detail
- **[Quick Reference](./QUICK_REFERENCE.md)** — commands and checklists

---

## Advanced: Local Dev / CLI

> This is **not** the production path. Use it only for developing the framework itself or quick local testing. Production runs on the AWS Dashboard Server above.

To run the dashboard on your laptop or deploy straight from the CLI, you need the prerequisites installed locally plus a local config:

```bash
cd Red_Team_Infra

# Python deps for running the dashboard locally
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Local deployment config (separate from dashboard.tfvars)
cp configs/terraform.tfvars.example configs/terraform.tfvars
# Edit configs/terraform.tfvars — set deployment_type, domain, region, allowed IPs, etc.

# Deploy / check / destroy from the CLI
./scripts/deployment/deploy.sh
./scripts/utilities/health-check.sh
./scripts/deployment/destroy.sh
```

When running locally you manage instance access yourself (SSM or direct SSH to public hosts) rather than jumping through the Dashboard Server.

---

## Troubleshooting

#### "AWS credentials not configured"
Run `aws configure` and verify with `aws sts get-caller-identity`. The setup script aborts early if this fails.

#### Setup script can't find an SSH key
Generate one with `ssh-keygen -t ed25519`, or pass the path explicitly at the prompt. The public key (`.pub`) is what's expected.

#### `terraform apply` fails on the dashboard plan
Check your IAM permissions allow VPC/EC2/IAM creation, and that the region you chose supports the instance type. Re-run the script — it resumes safely.

#### Can't open `http://localhost:5000`
- Confirm the tunnel is still open: `ssh -L 5000:localhost:5000 <operator>@<dashboard-eip>`.
- On the server, check the service: `./scripts/server/dashboard-manage.sh status` and `... logs`. The setup script's post-start health check pulls from the same logs if it ever reports the app didn't come up.
- Confirm your current public IP still matches `dashboard_allowed_ips` (it changes if your network changes) — re-run the setup script with `--update-ip`, or update `configs/dashboard.tfvars` and re-apply.

#### SSH to the Dashboard Server is refused
Your source IP must be in the allow-list. A VPN or iCloud Private Relay can rotate your egress IP — this is also what the setup script's SSH-reachability probe warns about. Re-run the setup script with `--update-ip` to refresh the allow-list, or add the new IP to `dashboard_allowed_ips` and `terraform apply -target=module.dashboard_server`.

#### Restart / manage the service
From the server:

```bash
./scripts/server/dashboard-manage.sh restart   # start | stop | restart | status | logs | upgrade
```

## Security Reminders

> This infrastructure is for authorized red team operations only. Ensure you have proper authorization before deploying.

1. **Never commit secrets** — `.gitignore` excludes `configs/*.tfvars`, SSH keys, and credentials.
2. **Keep the allow-list tight** — only your (and your team's) `/32` IPs in `dashboard_allowed_ips`.
3. **Prefer the IAM instance role** — the Dashboard Server authenticates to AWS without static keys; don't add long-lived credentials to it.
4. **Rotate keys** — rotate operator SSH keys and any AWS keys used locally for the CLI path.
5. **Monitor usage** — review CloudTrail and the dashboard's cost tracking regularly.
