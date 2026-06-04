# Red Team Infrastructure Dashboard

Centralized web interface for managing and deploying Red Team Infrastructure with integrated GOAD (vulnerable AD) labs. Runs on a dedicated EC2 instance — operators access via SSH tunnel.

## Overview

This web application provides a user-friendly interface for:
- Configuring infrastructure settings
- Deploying C2 infrastructure and GOAD labs
- Monitoring infrastructure status
- Running health checks
- Managing infrastructure lifecycle
- Connecting to deployed resources via in-browser terminal

## Features

- **Configuration Editor** - Web-based form for editing terraform.tfvars
- **Engagement Types** - Pre-configured setups (Ad-Hoc, Purple Team, Full Red Team)
- **GOAD Lab Selection** - Deploy vulnerable AD environments alongside C2 infrastructure
- **Deployment Control** - One-click deployment with real-time status
- **Deployment Manager** - View all deployments, connection info, and manage lifecycle
- **Infrastructure Topology** - Interactive Canvas graph showing VPCs, subnets, and connections
- **In-Browser Terminal** - SSH to deployed instances, local server shell, tunnel shortcuts
- **Beacon Management** - Cobalt Strike REST API integration for beacon interaction
- **Health Checks** - Check prerequisites and infrastructure health
- **AWS Permissions Check** - Validate required AWS permissions before deployment
- **SSH Tunnel Access** - Loopback-only binding with defense-in-depth guard

## Quick Start

```bash
# Provision the dashboard server
./scripts/server/setup-dashboard.sh

# SSH tunnel in
ssh -L 5000:localhost:5000 <operator>@<dashboard-ip>

# Open http://localhost:5000
```

### Manual Start (on server)

Normally `dashboard-manage.sh` runs the app as a systemd service. To start it by hand on the Dashboard Server:

```bash
# Install dependencies
pip install -r requirements.txt

# Start the application (binds to 127.0.0.1:5000 on the server)
cd Red_Team_Infra
python3 webapp/backend/app.py
```

The app listens on `127.0.0.1:5000` on the server — reach it from your laptop via the SSH tunnel above (`ssh -L 5000:localhost:5000 <operator>@<dashboard-ip>`), then open `http://localhost:5000`.

## Usage

### 1. Pre-Reqs Tab
- Check all prerequisites (AWS CLI, Terraform, Ansible, GitHub CLI)
- Verify AWS connectivity and permissions
- Validate GitHub access to tools repository

### 2. Configuration Tab
- Select engagement type (Ad-Hoc, Purple Team, Full Red Team)
- View deployment overview with cost estimates
- Configure AWS region, key pairs, CIDR blocks
- **Select GOAD Lab** (optional) - Choose vulnerable AD environment
- Configure domain settings
- Save configuration

### 3. Deploy Tab
- Run Terraform plan (preview changes)
- Deploy infrastructure
- Monitor deployment progress in real-time
- Upload Cobalt Strike files

### 4. Deployment Manager Tab
- View all active deployments (C2 + GOAD labs)
- **Connection instructions** - SSH tunnel, RDP, direct connection commands
- Start/Stop labs to save costs
- Destroy infrastructure
- View credentials and access info

### 5. Status Tab
- View infrastructure status
- See Terraform outputs
- List deployed resources
- Refresh status

### 6. Health Tab
- Check prerequisites (AWS CLI, Terraform, Ansible, etc.)
- Verify AWS connectivity
- **Check AWS permissions** - Validate required permissions for deployment
- Run infrastructure health checks

## API Endpoints

### Configuration
- `GET /api/config/` - Get current configuration
- `POST /api/config/` - Update configuration
- `POST /api/config/validate` - Validate configuration
- `GET /api/config/templates` - Get configuration templates

### Deployment
- `GET /api/deploy/status` - Get deployment status
- `POST /api/deploy/deploy` - Start deployment
- `POST /api/deploy/destroy` - Destroy infrastructure
- `GET /api/deploy/plan` - Run Terraform plan
- `GET /api/deploy/infrastructure` - Get detailed infrastructure info

### GOAD Labs
- `GET /api/goad/labs` - List available GOAD labs
- `POST /api/goad/deploy` - Deploy GOAD lab
- `GET /api/goad/status` - Get GOAD deployment status
- `POST /api/goad/start` - Start GOAD lab VMs
- `POST /api/goad/stop` - Stop GOAD lab VMs
- `POST /api/goad/destroy` - Destroy GOAD lab
- `GET /api/goad/credentials` - Get lab credentials

### Status
- `GET /api/status/` - Get infrastructure status
- `GET /api/status/outputs` - Get Terraform outputs
- `GET /api/status/resources` - List deployed resources

### Health
- `GET /api/health/prerequisites` - Check prerequisites
- `GET /api/health/aws` - Check AWS connectivity
- `GET /api/health/permissions` - Check AWS permissions for deployment
- `GET /api/aws-check/github-cli` - Check GitHub CLI authentication
- `POST /api/health/check` - Run health check

## Security

- **Loopback Binding**: The Flask app binds to 127.0.0.1 only — on the Dashboard Server it is never exposed publicly; operators reach it through an SSH tunnel (`ssh -L 5000:localhost:5000 ...`). A loopback guard rejects any non-localhost request.
- **SSH Is the Auth Layer**: Access is gated by SSH key + IP allow-list on the Dashboard Server (no separate web login). The operator's laptop only ever SSHes to the Dashboard Server EIP.
- **Input Validation**: All inputs are validated before execution
- **Safe Command Execution**: Commands executed with proper escaping

## Troubleshooting

### Port Already in Use
If port 5000 is already in use, edit `webapp/backend/app.py` and change the port:
```python
app.run(host='127.0.0.1', port=5001)  # Change port number
```

### Dependencies Not Found
```bash
pip install -r requirements.txt
```

### Terraform Not Found
Ensure Terraform is installed and in your PATH:
```bash
terraform --version
```

### AWS Credentials Not Configured
Configure AWS credentials:
```bash
aws configure
```

## Development

### Project Structure
```
webapp/
├── backend/
│   ├── app.py              # Flask application
│   ├── routes/             # API routes
│   ├── services/           # Business logic
│   └── utils/              # Utilities
├── frontend/
│   ├── index.html          # Main page
│   ├── css/                # Styles
│   └── js/                 # JavaScript
└── QUICK_START.md          # Quick start guide
```

### Adding New Features

1. **Add API Route**: Create new file in `backend/routes/`
2. **Register Blueprint**: Add to `app.py`
3. **Update Frontend**: Add UI in `frontend/index.html` and JavaScript in `frontend/js/app.js`

## Notes

- The web application runs on the **AWS-hosted Dashboard Server** — the production control plane and sole SSH/RDP jump host. Operators reach it via an SSH tunnel to the server's EIP, then open `http://localhost:5000`.
- All operations (Terraform, AWS API calls, SSH to instances) execute **on the Dashboard Server**, using its IAM instance role — no AWS credentials or Terraform install needed on operator laptops.
- Running the app on a laptop is a **dev/test instance only**, not the production path.
- Configuration files are stored in the `configs/` directory
- Terraform state is managed via the S3 backend + DynamoDB locking (not local `.tfstate`)

