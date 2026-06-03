# Tools Repository Setup Guide

## Overview

This guide walks you through creating the private tools repository and configuring it for automated deployment to the jump box.

## Step 1: Create Private Repository

### Using GitHub CLI (Recommended)

```bash
# Create private repository
gh repo create red-team-tools \
    --private \
    --description "Red Team Tools Repository - Private" \
    --clone

cd red-team-tools
```

### Using GitHub Web Interface

1. Go to GitHub.com
2. Click "New repository"
3. Name: `red-team-tools` (or your preferred name)
4. Description: "Red Team Tools Repository - Private"
5. Set to **Private**
6. **DO NOT** initialize with README (we'll create structure)
7. Click "Create repository"

## Step 2: Initialize Repository Structure

Create the following structure in your repository:

```bash
# If you cloned via GitHub CLI, you're already in the repo
# Otherwise: git clone git@github.com:YOUR-ORG/red-team-tools.git && cd red-team-tools

# Create directory structure
mkdir -p tools/{c2,post-exploitation,network,utilities,custom}
mkdir -p docs/{installation,usage}

# Create README
cat > README.md << 'EOF'
# Red Team Tools Repository

Private repository for red team tools and utilities.

## Structure

- `tools/c2/` - C2 frameworks and tools
- `tools/post-exploitation/` - Post-exploitation tools
- `tools/network/` - Network analysis tools
- `tools/utilities/` - Utility scripts
- `tools/custom/` - Custom tools and scripts
- `docs/` - Tool documentation

## Access

Tools are automatically deployed to the jump box at:
- **Windows**: `C:\Tools\`
- **WSL2**: `/opt/tools/`

Access via RDP or SSH to the jump box.

## Adding Tools

1. Add tools to appropriate directory
2. Include README.md in tool directory with:
   - Tool description
   - Installation instructions
   - Usage examples
3. Commit and push changes
4. Tools will be updated on jump box on next deployment

## Security

- **Private repository only**
- Access restricted to authorized team members
- Do not commit sensitive data or credentials
- Scan all tools before adding
EOF

# Create .gitignore
cat > .gitignore << 'EOF'
# Binaries and executables
*.exe
*.dll
*.so
*.dylib
*.bin

# Archives (unless they're tool distributions)
*.zip
*.tar.gz
*.tar
*.rar
*.7z

# Sensitive files
*.key
*.pem
*.p12
*.pfx
*.secret
*.env
*.config
credentials.*
secrets.*

# OS files
.DS_Store
Thumbs.db
*.swp
*.swo
*~

# IDE
.vscode/
.idea/
*.iml

# Temporary files
*.tmp
*.log
*.cache
EOF

# Create initial structure files
cat > tools/.gitkeep << 'EOF'
# Tools directory
EOF

cat > tools/c2/README.md << 'EOF'
# C2 Frameworks

Place C2 framework tools here.

## Examples
- Cobalt Strike
- Empire
- Covenant
- Sliver
EOF

cat > tools/post-exploitation/README.md << 'EOF'
# Post-Exploitation Tools

Place post-exploitation tools here.

## Examples
- Mimikatz
- BloodHound
- PowerView
- Rubeus
EOF

cat > tools/network/README.md << 'EOF'
# Network Tools

Place network analysis and tools here.

## Examples
- Nmap
- Wireshark
- tcpdump
- Network scanners
EOF

cat > tools/utilities/README.md << 'EOF'
# Utility Scripts

Place utility scripts here.

## Examples
- Persistence scripts
- Privilege escalation scripts
- Data exfiltration scripts
EOF

cat > tools/custom/README.md << 'EOF'
# Custom Tools

Place custom tools and scripts here.

## Examples
- Custom payloads
- Team-specific tools
- One-off scripts
EOF

# Commit and push
git add .
git commit -m "Initial repository structure"
git push -u origin main
```

## Step 3: Configure Access for Multiple Users

### Option A: Personal Access Tokens (Recommended for Multiple Users)

Each user creates their own Personal Access Token (PAT):

1. **User creates PAT:**
   - GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
   - Generate new token (classic)
   - Name: "Red Team Tools Access"
   - Expiration: Set appropriate expiration (e.g., 90 days)
   - Scopes: Select `repo` (full control of private repositories)
   - Generate token
   - **Copy token immediately** (won't be shown again)

2. **Configure in terraform.tfvars:**
   ```hcl
   tools_repo_url         = "https://github.com/YOUR-ORG/red-team-tools.git"
   tools_repo_https_token = "ghp_YOUR_TOKEN_HERE"
   ```
   Terraform automatically stores the token in AWS Secrets Manager. Instances
   fetch it at runtime via IAM role -- the token never appears in S3-stored scripts.

### Option B: Deploy Key (Single Key for Deployment)

Create a deploy key that the jump box uses:

1. **Generate SSH key for deployment:**
   ```bash
   ssh-keygen -t ed25519 -C "red-team-tools-deploy" -f ~/.ssh/red-team-tools-deploy
   ```

2. **Add public key to repository:**
   - Repository → Settings → Deploy keys → Add deploy key
   - Title: "Jump Box Deploy Key"
   - Key: Contents of `~/.ssh/red-team-tools-deploy.pub`
   - ✅ Allow write access (if you want to push updates from jump box)
   - Add key

3. **Store private key in AWS SSM:**
   ```bash
   aws ssm put-parameter \
       --name "/red-team/tools-repo-ssh-key" \
       --type "SecureString" \
       --value "$(cat ~/.ssh/red-team-tools-deploy)" \
       --region eu-central-1 \
       --overwrite
   ```

4. **Configure in terraform.tfvars:**
   ```hcl
   tools_repo_url = "git@github.com:YOUR-ORG/red-team-tools.git"
   tools_repo_ssh_key = "/red-team/tools-repo-ssh-key"
   ```

### Option C: GitHub App (Advanced - Best for Teams)

For larger teams, consider using a GitHub App:
- More granular permissions
- Better audit trail
- Can be shared across team
- See GitHub documentation for setup

## Step 4: Add Team Members

### Add Collaborators

1. **Via GitHub Web:**
   - Repository → Settings → Collaborators → Add people
   - Search for team members
   - Add with appropriate permissions (usually "Write")

2. **Via GitHub CLI:**
   ```bash
   gh repo add-collaborator YOUR-ORG/red-team-tools USERNAME --permission write
   ```

### Configure User Access

Each team member should:

1. **Clone repository to their laptop:**
   ```bash
   # Using SSH (if they have SSH keys set up)
   git clone git@github.com:YOUR-ORG/red-team-tools.git ~/tools
   
   # Or using HTTPS with their PAT
   git clone https://github.com/YOUR-ORG/red-team-tools.git ~/tools
   ```

2. **Set up their credentials:**
   ```bash
   # For HTTPS with PAT
   git config --global credential.helper store
   # When prompted, use PAT as password
   
   # Or use GitHub CLI
   gh auth login
   ```

## Step 5: Configure Infrastructure Deployment

### Update terraform.tfvars

```hcl
# Tools Repository Configuration
tools_repo_url = "https://github.com/YOUR-ORG/red-team-tools.git"  # Use HTTPS for PAT
# OR
tools_repo_url = "git@github.com:YOUR-ORG/red-team-tools.git"  # Use SSH for deploy key

tools_repo_branch = "main"
tools_repo_https_token = "ghp_YOUR_TOKEN_HERE"  # Stored in AWS Secrets Manager automatically
# OR
tools_repo_ssh_key = "/red-team/tools-repo-ssh-key"  # For deploy key
```

### Token Security

When `tools_repo_https_token` is set in `terraform.tfvars`, Terraform automatically:
1. Creates an AWS Secrets Manager secret named `{project}-{env}-github-token`
2. Adds IAM permissions for instances to read the secret
3. Instances fetch the token at runtime via `Get-SECSecretValue` (Windows) or `aws secretsmanager get-secret-value` (Linux)

The token **never appears** in S3-stored init scripts -- only the secret name is embedded.

## Step 6: Test Deployment

1. **Deploy infrastructure:**
   ```bash
   ./scripts/deployment/deploy.sh
   ```

2. **Verify tools are deployed:**
   ```bash
   # RDP to jump box and check
   # C:\Tools\ should contain the repository
   
   # Or SSH and check WSL2
   ssh Administrator@<jump-box-ip>
   wsl
   ls -la /opt/tools
   ```

## Repository URL Reference

After creating the repository, note the exact URL:

**SSH Format:**
```
git@github.com:YOUR-ORG/red-team-tools.git
```

**HTTPS Format:**
```
https://github.com/YOUR-ORG/red-team-tools.git
```

Replace `YOUR-ORG` with your GitHub organization or username.

## Adding New Users

When adding new team members:

1. **Add as collaborator:**
   ```bash
   gh repo add-collaborator YOUR-ORG/red-team-tools NEW-USERNAME --permission write
   ```

2. **User creates PAT:**
   - Follow Step 3, Option A above

3. **Update terraform.tfvars with their token:**
   ```hcl
   tools_repo_https_token = "ghp_THEIR_TOKEN"
   ```
   Terraform stores the token in AWS Secrets Manager automatically.

## Security Best Practices

1. **Repository Access:**
   - Keep repository private
   - Only add authorized team members
   - Review access regularly

2. **Credentials:**
   - GitHub tokens are stored in AWS Secrets Manager (managed by Terraform)
   - Only instances with the correct IAM role can retrieve tokens at runtime
   - Rotate tokens regularly
   - Tokens never appear in S3-stored scripts

3. **Token Management:**
   - Set appropriate expiration dates
   - Revoke tokens when users leave
   - Use least privilege (only `repo` scope needed)

4. **Tool Validation:**
   - Scan all tools before adding
   - Document tool sources
   - Verify checksums when possible

## Troubleshooting

### Repository Not Cloning

1. **Check credentials:**
   ```bash
   # Verify SSM parameter exists
   aws ssm get-parameter --name "/red-team/tools-repo-ssh-key" --with-decryption
   ```

2. **Test authentication manually:**
   ```bash
   # For SSH
   ssh -T git@github.com
   
   # For HTTPS
   curl -H "Authorization: token YOUR_TOKEN" https://api.github.com/user
   ```

3. **Check Ansible logs:**
   ```bash
   ansible-playbook -i inventory/hosts.yml playbooks/deploy-tools-repo.yml -vvv
   ```

### Access Denied

- Verify user is added as collaborator
- Check PAT has `repo` scope
- Verify SSH key is added to GitHub account or repository deploy keys

## Next Steps

1. ✅ Create repository (this guide)
2. ✅ Set up authentication
3. ✅ Add initial tools
4. ✅ Deploy infrastructure
5. ✅ Verify tools are accessible on jump box

See [Tools Repository Access](./TOOLS_REPOSITORY_ACCESS.md) for accessing tools after deployment.

