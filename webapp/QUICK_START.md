# Dashboard Quick Start

## Provisioning the Dashboard Server

```bash
cd Red_Team_Infra
./scripts/server/setup-dashboard.sh
```

The script will:
1. Prompt for operator name, SSH key, and IP allowlist
2. Provision a dedicated EC2 instance with IAM role, VPC, and S3 state backend
3. Sync the codebase and start the dashboard as a systemd service

## Accessing the Dashboard

SSH tunnel to the dashboard server, then open the browser:

```bash
ssh -L 5000:localhost:5000 <operator>@<dashboard-ip>
# Open http://localhost:5000
```

## First Steps

1. **Check Prerequisites** (Health tab)
   - Verify AWS connectivity and IAM permissions

2. **Configure Infrastructure** (Configuration tab)
   - Select deployment type (c2-adhoc, goad-light, etc.)
   - Fill in required fields
   - Save configuration

3. **Deploy** (Deploy tab)
   - Run plan to preview changes
   - Deploy infrastructure
   - Monitor progress

4. **Monitor** (Status tab)
   - View infrastructure status
   - Check outputs and connection info

## Managing the Service

```bash
# On the server (via SSH)
./scripts/server/dashboard-manage.sh status
./scripts/server/dashboard-manage.sh restart
./scripts/server/dashboard-manage.sh logs
./scripts/server/dashboard-manage.sh upgrade   # Pull latest code + restart
```

## Adding Another Operator

Add their SSH public key and IP to `configs/dashboard.tfvars`, then `terraform apply`.
