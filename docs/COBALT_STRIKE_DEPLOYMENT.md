# Cobalt Strike Deployment & License Activation

## Overview

Cobalt Strike deployment is **fully automated** via Terraform user_data scripts. The team server is installed, configured, and (optionally) license-activated at boot — no manual SSH required.

## How It Works

### Deployment Flow

```
1. Terraform creates EC2 instance with user_data bootstrap script
2. Script waits for cloud-init + NAT Gateway connectivity
3. Installs Java 17, awscli, and dependencies
4. Downloads CS archive from S3 (uploaded via web app before deploy)
5. Extracts to /opt/cobaltstrike/
6. Checks for cobaltstrike.auth.server (license activation indicator)
7. If not found AND license secret configured → auto-activates via Secrets Manager
8. Creates systemd service (teamserver.service)
9. If password + license both set → auto-starts team server on port 50050
```

### Files Involved

| File | Purpose |
|------|---------|
| `terraform/scripts/install_cobalt_strike.sh` | C2-only team server bootstrap |
| `terraform/modules/goad/scripts/teamserver_init.sh` | GOAD team server bootstrap |
| `terraform/modules/c2_team_server/main.tf` | Passes config to templatefile() |
| `terraform/modules/deployment_storage/main.tf` | IAM policies for Secrets Manager access |

## License Activation

### Option A: Automated (Recommended)

Store your license key once in AWS Secrets Manager. Every deployment fetches it automatically.

**One-time setup:**
```bash
aws secretsmanager create-secret \
    --name cs-license-key \
    --secret-string "xxxx-xxxx-xxxx-xxxx" \
    --region eu-central-1
```

**Configure in tfvars:**
```hcl
cobalt_strike_license_secret_name = "cs-license-key"
```

Or select "Auto-activate from Secrets Manager" in the web app deploy page and enter `cs-license-key`.

**What happens at boot:**
1. Script detects `cobaltstrike.auth.server` is missing → `LICENSE_STATUS=needs_activation`
2. Fetches license key from Secrets Manager via IAM role
3. Pipes key to `./update`: `echo "$KEY" | ./update`
4. CS downloads latest licensed binaries + creates auth file
5. Script re-checks → `cobaltstrike.auth.server` exists → `LICENSE_STATUS=ready`
6. If password also configured → team server starts automatically

**OPSEC:**
- License key is never in Terraform state, user_data, or logs
- Only the secret NAME is in scripts — the VALUE is fetched at runtime via IAM
- Key is `unset` from memory immediately after use
- `./update` output is filtered to remove sensitive content before logging

### Option B: Manual

Leave `cobalt_strike_license_secret_name` empty. After deployment:

```bash
# SSH to team server via bastion
ssh -J ubuntu@<bastion_ip> ubuntu@<c2_ip>

# Activate license
cd /opt/cobaltstrike && sudo ./update
# Enter your license key when prompted

# Set password and start
sudo /opt/cobaltstrike/set-password.sh
```

## Team Server Password

### Option A: Pre-set (Auto-start)

Set `cs_teamserver_password` in tfvars or via the web app. The team server starts automatically after license activation.

**Note:** Password is embedded in EC2 user_data (readable via `ec2:DescribeInstanceAttribute`) and visible in systemd service args. Acceptable for training labs, consider manual setup for production engagements.

### Option B: Manual (Recommended for OPSEC)

Leave password empty. After deployment:
```bash
sudo /opt/cobaltstrike/set-password.sh
```

Password is prompted interactively and never touches Terraform state or user_data.

## S3 Archive Requirements

> **Server Mode:** SCP the CS archive once to the dashboard server: `scp cobaltstrike.tar harris@<server-ip>:/opt/redteam/uploads/`. It persists on the server's EBS volume and is reused for all subsequent deployments. No need to re-upload.

Upload your Cobalt Strike distribution archive via the web app before deploying. The archive should contain at minimum:

- `update` — The CS updater script (runs `./update` to download licensed binaries)
- `teamserver` (optional — downloaded by `./update`)
- `cobaltstrike.jar` (optional — downloaded by `./update`)

The `./update` command downloads the latest licensed binaries, so the archive only needs the updater itself. The rest is pulled from Cobalt Strike's servers during license activation.

## Malleable C2 Profile

### Default Profile (jQuery)

The **default** Malleable C2 profile is the [jQuery CS 4.9 profile](https://github.com/threatexpress/malleable-c2/blob/master/jquery-c2.4.9.profile) from threatexpress. It's downloaded from GitHub during deployment, validated with `c2lint`, and auto-loaded when the team server starts.

- **Location:** `/opt/cobaltstrike/profiles/jquery.profile`
- **Validate:** `cd /opt/cobaltstrike/server && ./c2lint /opt/cobaltstrike/profiles/jquery.profile`
- **Systemd:** The profile path is included in the `ExecStart` command automatically

The nginx redirectors are pre-configured to match this profile's URIs:

| Block | URI | Purpose |
|-------|-----|---------|
| http-get | `/jquery-3.3.1.min.js` | Beacon check-in (GET) |
| http-post | `/jquery-3.3.2.min.js` | Beacon data exfil (POST) |
| http-stager x86 | `/jquery-3.3.1.slim.min.js` | Staged payload download |
| http-stager x64 | `/jquery-3.3.2.slim.min.js` | Staged payload download |

### Non-Default Profiles

If you select `amazon`, `google`, `microsoft`, or `custom` in the web app:
- **Nginx redirectors** are auto-configured with URI patterns matching the selected profile
- **Team server** starts WITHOUT a profile — you must provide your own `.profile` file
- See `CS-LISTENER-GUIDE.txt` on the team server or the web app Post-Deployment Checklist for step-by-step instructions

## Helper Scripts on Team Server

After deployment, these scripts are available at `/opt/cobaltstrike/`:

| Script | Purpose |
|--------|---------|
| `check-status.sh` | Show license status, service status, listening ports |
| `set-password.sh` | Set/change team server password and restart (auto-detects profile) |
| `activate-license.sh` | Manual license activation (runs `./update`) |
| `restart-teamserver.sh` | Restart the team server service |
| `view-logs.sh` | Tail team server logs |

## Troubleshooting

### Check install log
```bash
cat /var/log/cs-install.log
```

### Check license status
```bash
/opt/cobaltstrike/check-status.sh
```

### License activation failed
```bash
# Check if auth file exists
ls -la /opt/cobaltstrike/server/cobaltstrike.auth.server

# Check IAM role can access Secrets Manager
aws secretsmanager get-secret-value --secret-id cs-license-key --region eu-central-1

# Manual activation
cd /opt/cobaltstrike && sudo ./update
```

### Team server won't start
```bash
# Check service status
journalctl -u teamserver -n 30

# Check if password is set in service
grep ExecStart /etc/systemd/system/teamserver.service

# Re-set password
sudo /opt/cobaltstrike/set-password.sh
```

## Security Architecture

```
┌─────────────────────┐     ┌──────────────────────────┐
│  Secrets Manager    │     │  S3 Bucket               │
│  ┌────────────────┐ │     │  ┌──────────────────┐    │
│  │ cs-license-key │ │     │  │ archives/cs.tar  │    │
│  │ (license key)  │ │     │  │ (CS distribution)│    │
│  └────────────────┘ │     │  └──────────────────┘    │
│  ┌────────────────┐ │     │                          │
│  │ github-token   │ │     │  Created by Terraform    │
│  │ (tools repo)   │ │     │  VPC-restricted access   │
│  └────────────────┘ │     └──────────────────────────┘
│                     │                ▲
│  Pre-existing       │                │
│  (you create once)  │     ┌──────────┴───────────┐
└─────────────────────┘     │  IAM Role            │
          ▲                 │  cs_download_c2      │
          │                 │  ✅ SourceVpc: C2    │
          │                 │  ✅ SourceAccount    │
          │                 │  ✅ SecureTransport  │
          │                 └──────────┬───────────┘
          │                            │
          └────────────────────────────┘
                    │
          ┌────────┴────────┐
          │  Team Server    │
          │  (private subnet)│
          │                 │
          │  Boot sequence: │
          │  1. Download CS │
          │  2. Fetch key   │
          │  3. ./update    │
          │  4. Start       │
          └─────────────────┘
```

### Key Points
- License key is **pre-existing** in Secrets Manager — NOT created by Terraform
- S3 bucket + IAM roles ARE created by Terraform (per-VPC isolation)
- Team server is in a private subnet — no direct internet access
- Outbound traffic goes via NAT Gateway
- Confused deputy protection on all IAM roles (SourceVpc + SourceAccount conditions)
