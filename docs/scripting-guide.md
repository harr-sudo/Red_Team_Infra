# Scripting Guide

This document outlines the scripting strategy and approach for automating the red team infrastructure deployment and management.

## Scripting Philosophy

### Principles
1. **Idempotency**: Scripts should be safe to run multiple times
2. **Error Handling**: Proper error checking and meaningful error messages
3. **Logging**: Comprehensive logging for troubleshooting
4. **Modularity**: Small, focused scripts that can be composed
5. **Documentation**: Clear comments and usage instructions

## Script Categories

### 1. Deployment Scripts (`scripts/deployment/`)

These scripts handle the full lifecycle of infrastructure deployment.

#### `deploy.sh`
**Purpose**: Main orchestration script for deploying infrastructure

**Workflow**:
1. Validate prerequisites (AWS CLI, Terraform, Ansible)
2. Check AWS credentials
3. Validate configuration files
4. Run Terraform to provision infrastructure
5. Wait for instances to be ready
6. Run Ansible playbooks for configuration
7. Output connection information

**Usage**:
```bash
./scripts/deployment/deploy.sh
```

**Dependencies**:
- AWS CLI configured
- Terraform installed
- Ansible installed
- `terraform.tfvars` configured

#### `destroy.sh`
**Purpose**: Safely tear down infrastructure

**Workflow**:
1. Confirm destruction (requires typing "DESTROY")
2. Run Terraform destroy
3. Clean up temporary files

**Usage**:
```bash
./scripts/deployment/destroy.sh
```

#### `update.sh`
**Purpose**: Update existing infrastructure

**Workflow**:
1. Run Terraform plan to see changes
2. Apply updates
3. Run Ansible playbooks for configuration updates
4. Verify changes

**Usage**:
```bash
./scripts/deployment/update.sh
```

### 2. Configuration Scripts (`scripts/configuration/`)

These scripts handle specific component configurations.

#### `setup-c2.sh`
**Purpose**: Configure C2 infrastructure

**Tasks**:
- Install C2 framework (Cobalt Strike, Sliver, etc.)
- Configure team server
- Set up listeners
- Generate initial payloads
- Configure logging

**Usage**:
```bash
./scripts/configuration/setup-c2.sh <instance-ip>
```

#### `setup-redirector.sh`
**Purpose**: Configure redirector instances

**Tasks**:
- Install web server (Apache/Nginx)
- Configure domain fronting (if applicable)
- Set up SSL termination
- Configure logging
- Set up health checks

**Usage**:
```bash
./scripts/configuration/setup-redirector.sh <instance-ip> <domain>
```

#### `configure-ssl.sh`
**Purpose**: Manage SSL/TLS certificates

**Tasks**:
- Request certificates via AWS Certificate Manager
- Deploy certificates to instances
- Configure certificate rotation
- Validate certificate installation

**Usage**:
```bash
./scripts/configuration/configure-ssl.sh <domain>
```

### 3. Utility Scripts (`scripts/utilities/`)

These scripts provide operational support.

#### `health-check.sh`
**Purpose**: Check infrastructure health

**Checks**:
- AWS connectivity
- Terraform state
- EC2 instance status
- Service availability
- Network connectivity

**Usage**:
```bash
./scripts/utilities/health-check.sh
```

#### `backup.sh`
**Purpose**: Backup critical configurations

**Backups**:
- Terraform state
- Ansible inventories
- Configuration files
- SSL certificates (if applicable)

**Usage**:
```bash
./scripts/utilities/backup.sh
```

#### `cleanup.sh`
**Purpose**: Clean up temporary files and resources

**Tasks**:
- Remove temporary files
- Clean old logs
- Remove unused resources
- Maintain directory hygiene

**Usage**:
```bash
./scripts/utilities/cleanup.sh
```

## Scripting Languages

### Bash
**Primary Language**: Used for orchestration and system-level tasks

**Use Cases**:
- Deployment orchestration
- File operations
- Command execution
- Simple conditionals and loops

**Example**:
```bash
#!/bin/bash
set -euo pipefail

log_info() {
    echo "[INFO] $1"
}

check_prerequisites() {
    command -v terraform >/dev/null 2>&1 || {
        echo "Error: terraform not found"
        exit 1
    }
}
```

### Python
**Secondary Language**: Used for complex automation and API interactions

**Use Cases**:
- AWS API interactions
- JSON/YAML processing
- Complex data manipulation
- CLI tools

**Example**:
```python
#!/usr/bin/env python3
import boto3
import json

def get_instance_status(instance_id):
    ec2 = boto3.client('ec2')
    response = ec2.describe_instance_status(InstanceIds=[instance_id])
    return response['InstanceStatuses'][0]['InstanceState']['Name']
```

## AWS Automation

### AWS CLI
**Purpose**: Direct AWS service interaction

**Common Commands**:
```bash
# Check credentials
aws sts get-caller-identity

# Get instance status
aws ec2 describe-instances --instance-ids i-1234567890abcdef0

# Wait for instance
aws ec2 wait instance-status-ok --instance-ids i-1234567890abcdef0
```

### AWS SDK (boto3)
**Purpose**: Programmatic AWS access from Python

**Use Cases**:
- Complex AWS operations
- Custom automation logic
- Integration with other tools

## Terraform Integration

### Running Terraform from Scripts

```bash
# Initialize
terraform init

# Validate
terraform validate

# Plan
terraform plan -out=tfplan -var-file=configs/terraform.tfvars

# Apply
terraform apply tfplan

# Get outputs
terraform output -json > outputs.json
```

### Parsing Terraform Outputs

```bash
# Using jq
instance_id=$(jq -r '.instance_ids.value[0]' terraform-outputs.json)
public_ip=$(jq -r '.instance_public_ips.value[0]' terraform-outputs.json)
```

## Ansible Integration

### Running Ansible from Scripts

```bash
# Run playbook
ansible-playbook -i inventory/hosts.yml playbooks/base-setup.yml

# Run with specific tags
ansible-playbook -i inventory/hosts.yml playbooks/base-setup.yml --tags "security"

# Run with extra variables
ansible-playbook -i inventory/hosts.yml playbooks/base-setup.yml -e "var=value"
```

### Dynamic Inventory

Generate Ansible inventory from Terraform outputs:

```bash
# Generate inventory from Terraform outputs
jq -r '.instance_public_ips.value[]' terraform-outputs.json | \
  awk '{print "server" NR " ansible_host=" $1}' > ansible/inventory/hosts.yml
```

## Error Handling

### Best Practices

1. **Use `set -euo pipefail`** in Bash scripts
   ```bash
   set -e  # Exit on error
   set -u  # Exit on undefined variable
   set -o pipefail  # Exit on pipe failure
   ```

2. **Check command success**
   ```bash
   if ! command; then
       log_error "Command failed"
       exit 1
   fi
   ```

3. **Validate inputs**
   ```bash
   if [ -z "$1" ]; then
       log_error "Missing required argument"
       exit 1
   fi
   ```

4. **Cleanup on exit**
   ```bash
   trap cleanup EXIT
   
   cleanup() {
       rm -f /tmp/tempfile
   }
   ```

## Logging

### Standard Format

```bash
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}
```

### Log Levels

- **INFO**: Normal operation messages
- **WARN**: Warning messages (non-fatal)
- **ERROR**: Error messages (fatal)

## Testing Scripts

### Manual Testing
1. Test in development environment first
2. Use dry-run modes where available
3. Test error conditions
4. Verify cleanup on failure

### Automated Testing
- Use shellcheck for Bash scripts
- Use pytest for Python scripts
- Test with different inputs
- Test error conditions

## Security Considerations

1. **Never commit secrets**
   - Use AWS Secrets Manager
   - Use environment variables
   - Use configuration files excluded from Git

2. **Validate inputs**
   - Sanitize user inputs
   - Validate file paths
   - Check permissions

3. **Least privilege**
   - Use IAM roles with minimal permissions
   - Don't use root accounts
   - Rotate credentials regularly

4. **Audit logging**
   - Log all operations
   - Store logs securely
   - Review logs regularly

## Future Enhancements

1. **CI/CD Integration**
   - GitHub Actions workflows
   - Automated testing
   - Automated deployments

2. **Monitoring Integration**
   - Health check automation
   - Alerting on failures
   - Metrics collection

3. **Advanced Features**
   - Multi-region support
   - Blue/green deployments
   - Rollback capabilities

