# Red Team Infrastructure Web Application

Local-only web interface for managing and deploying Red Team Infrastructure.

## Overview

This web application provides a user-friendly interface for:
- Configuring infrastructure settings
- Deploying infrastructure
- Monitoring infrastructure status
- Running health checks
- Managing infrastructure lifecycle

## Features

- ✅ **Configuration Editor** - Web-based form for editing terraform.tfvars
- ✅ **Deployment Control** - One-click deployment with real-time status
- ✅ **Status Dashboard** - View infrastructure status and outputs
- ✅ **Health Checks** - Check prerequisites and infrastructure health
- ✅ **Local Only** - Runs on localhost only (127.0.0.1:5000)

## Quick Start

### Option 1: Using Start Script (Recommended)

```bash
cd Red_Team_Infra
./webapp/start.sh
```

The script will:
- Create virtual environment if needed
- Install dependencies
- Start the web server
- Open browser to http://127.0.0.1:5000

### Option 2: Manual Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start the application
cd Red_Team_Infra
python3 webapp/backend/app.py
```

Then open your browser to: http://127.0.0.1:5000

## Usage

### 1. Configuration Tab
- Select engagement type (adhoc/purple-team/full-red-team)
- Configure infrastructure settings
- Validate configuration
- Save configuration

### 2. Deploy Tab
- Run Terraform plan (preview changes)
- Deploy infrastructure
- Monitor deployment progress
- Destroy infrastructure (with confirmation)

### 3. Status Tab
- View infrastructure status
- See Terraform outputs
- List deployed resources
- Refresh status

### 4. Health Tab
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

### Status
- `GET /api/status/` - Get infrastructure status
- `GET /api/status/outputs` - Get Terraform outputs
- `GET /api/status/resources` - List deployed resources

### Health
- `GET /api/health/prerequisites` - Check prerequisites
- `GET /api/health/aws` - Check AWS connectivity
- `GET /api/health/permissions` - Check AWS permissions for deployment
- `POST /api/health/check` - Run health check

## Security

- **Localhost Only**: Web server binds to 127.0.0.1 only
- **No Authentication**: Not needed for local-only access
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
└── start.sh                # Startup script
```

### Adding New Features

1. **Add API Route**: Create new file in `backend/routes/`
2. **Register Blueprint**: Add to `app.py`
3. **Update Frontend**: Add UI in `frontend/index.html` and JavaScript in `frontend/js/app.js`

## Notes

- The web application is for **local use only**
- All operations execute on your local machine
- Configuration files are stored in `configs/` directory
- Terraform state is managed in `terraform/` directory

