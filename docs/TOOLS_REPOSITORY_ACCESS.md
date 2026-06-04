# Tools Repository Access Guide

## Overview

The tools repository is automatically deployed during infrastructure deployment. Tools are available at:

- **Windows attack box**: `C:\Tools\`
- **GOAD jumpbox (Ubuntu)**: `/opt/tools/`

> **Access note:** The AWS-hosted Dashboard Server is the sole SSH jump into all instances — there is no per-deployment bastion. Reach the tool hosts through the Dashboard Server: RDP to the Windows attack box (`ssh -L 13389:<attackbox-private-ip>:3389 ubuntu@<dashboard-eip>` then RDP to `localhost:13389`) or SSH to the GOAD jumpbox via the dashboard.

## Access Methods

### Method 1: RDP to the Attack Box (Windows tools at `C:\Tools\`)

1. **Tunnel RDP through the Dashboard Server, then connect:**
   ```bash
   # Tunnel to the attack box (private subnet) via the Dashboard Server
   ssh -L 13389:<attackbox-private-ip>:3389 ubuntu@<dashboard-eip>
   
   # Connect your RDP client to localhost:13389
   # Username: Administrator (renamed per deployment)
   # Password: Retrieved from AWS Secrets Manager
   ```

2. **Access Tools:**
   - Open File Explorer
   - Navigate to `C:\Tools\`
   - All tools are organized in subdirectories

### Method 2: SSH to the GOAD Jumpbox (Linux tools at `/opt/tools/`)

1. **Connect via the Dashboard Server jump:**
   ```bash
   # Reach the GOAD jumpbox (private) through the Dashboard Server
   ssh -J ubuntu@<dashboard-eip> ubuntu@<goad-jumpbox-private-ip>
   ```

2. **Navigate to tools:**
   ```bash
   cd /opt/tools
   
   # List tools
   ls -la
   ```

### Method 3: Direct Git Clone (Recommended for Operators)

Operators can clone the tools repository directly to their laptops:

1. **Setup SSH Key (if using SSH):**
   ```bash
   # Generate SSH key
   ssh-keygen -t ed25519 -C "your-email@example.com" -f ~/.ssh/id_rsa_tools
   
   # Add public key to GitHub/GitLab
   cat ~/.ssh/id_rsa_tools.pub
   # Copy and add to repository settings
   ```

2. **Clone Repository:**
   ```bash
   # Clone tools repository
   git clone git@github.com:org/red-team-tools.git ~/tools
   
   # Or using HTTPS (with personal access token)
   git clone https://github.com/org/red-team-tools.git ~/tools
   ```

3. **Update Tools:**
   ```bash
   cd ~/tools
   git pull origin main
   ```

## Repository Configuration

### Setting Up Tools Repository

**See [Tools Repository Setup Guide](./TOOLS_REPOSITORY_SETUP.md) for complete setup instructions.**

Quick setup:

1. **Create Private Repository:**
   ```bash
   gh repo create red-team-tools --private --description "Red Team Tools Repository"
   ```

2. **Configure in terraform.tfvars:**
   ```hcl
   # Tools Repository Configuration
   tools_repo_url = "git@github.com:org/red-team-tools.git"
   tools_repo_branch = "main"
   tools_repo_ssh_key = "/red-team/tools-repo-ssh-key"  # AWS SSM Parameter Store path
   # OR
   tools_repo_https_token = "ghp_YOUR_TOKEN_HERE"  # Stored in Secrets Manager automatically
   ```

   When using HTTPS tokens, Terraform stores the token in AWS Secrets Manager.
   Instances fetch it at runtime via IAM role -- the token never appears in S3-stored scripts.

## Repository Structure

Recommended structure for the tools repository:

```
red-team-tools/
├── README.md
├── tools/
│   ├── c2/                    # C2 frameworks
│   ├── post-exploitation/     # Post-exploitation tools
│   ├── network/               # Network tools
│   ├── utilities/             # Utility scripts
│   └── custom/               # Custom tools/scripts
└── docs/                      # Tool documentation
```

## Manual Deployment

If you need to manually deploy or update tools on the jump box:

```bash
# Generate inventory first
./scripts/utilities/generate-inventory.sh

# Deploy tools repository
cd ansible
ansible-playbook -i inventory/hosts.yml playbooks/deploy-tools-repo.yml \
    -e "TOOLS_REPO_URL=git@github.com:org/red-team-tools.git" \
    -e "TOOLS_REPO_BRANCH=main" \
    -e "TOOLS_REPO_SSH_KEY=/red-team/tools-repo-ssh-key"
```

## Troubleshooting

### Tools Not Deployed

1. **Check Configuration:**
   ```bash
   # Verify tools_repo_url is set
   grep tools_repo_url configs/terraform.tfvars
   ```

2. **Check Ansible Inventory:**
   ```bash
   # Ensure the tool host (attack box / GOAD jumpbox) is in inventory
   cat ansible/inventory/hosts.yml | grep -A 5 -iE 'jumpbox|attack_box'
   ```

3. **Check Deployment Logs:**
   ```bash
   # Re-run deployment playbook with verbose output
   ansible-playbook -i inventory/hosts.yml playbooks/deploy-tools-repo.yml -vvv
   ```

### Git Authentication Issues

1. **SSH Key Issues:**
   - Verify SSH key is stored in AWS SSM
   - Check key permissions on jump box
   - Test SSH connection manually

2. **HTTPS Token Issues:**
   - Verify token is stored in AWS SSM
   - Check token has repository access
   - Test HTTPS clone manually

### WSL2 Not Available

If WSL2 is not installed on the jump box:
- Tools are still available at `C:\Tools\` (Windows)
- WSL2 sync is optional
- Install WSL2 manually if needed

## Security Considerations

1. **Repository Access:**
   - Keep repository private
   - Use SSH keys or personal access tokens
   - Rotate credentials regularly

2. **Credential Storage:**
   - Store credentials in AWS SSM Parameter Store
   - Use SecureString type for encryption
   - Limit access via IAM policies

3. **Tool Validation:**
   - Verify tool integrity before adding
   - Scan for malware
   - Document tool sources

## Next Steps

1. **Create Tools Repository:**
   - Set up private GitHub/GitLab repository
   - Add initial tools and structure
   - Configure access control

2. **Configure Deployment:**
   - Add repository URL to `terraform.tfvars`
   - Store credentials in AWS SSM
   - Deploy infrastructure

3. **Access Tools:**
   - RDP/SSH to jump box
   - Or clone repository to laptop

See [Tools Repository Plan](./legacy/internal/TOOLS_REPOSITORY_PLAN.md) for detailed architecture.

